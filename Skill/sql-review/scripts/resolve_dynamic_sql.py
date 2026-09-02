#!/usr/bin/env python3
"""Phase 3: Resolve MyBatis dynamic SQL to executable form for EXPLAIN.

Two modes:
  --mode optimistic (default): Assume all <if> conditions are true,
      expand <foreach>, resolve <choose>/<when>/<otherwise>, strip all tags.
      Produces a best-effort SQL for EXPLAIN.

  --mode resolve: Keep <if> and <choose> tags, marking `needs_llm: true`
      for downstream LLM to decide which branches are live.
      foreach/bind/include are still processed deterministically.
      where/set/trim are deferred — use finalize_sql() after LLM resolution.

Usage:
    python3 resolve_dynamic_sql.py --input '[...]' --mode optimistic
    python3 resolve_dynamic_sql.py --input '[...]' --mode resolve
    cat parse-output.json | python3 resolve_dynamic_sql.py
"""

import argparse
import json
import re
import sys

IF_TAG = re.compile(r'<if\b[^>]*>', re.IGNORECASE)
IF_CLOSE = re.compile(r'</if\s*>', re.IGNORECASE)

CHOOSE_BLOCK = re.compile(r'<choose\b[^>]*>(.*?)</choose\s*>', re.IGNORECASE | re.DOTALL)
WHEN_BLOCK = re.compile(r'<when\s[^>]*>(.*?)</when\s*>', re.IGNORECASE | re.DOTALL)
OTHER_BLOCK = re.compile(r'<otherwise\b[^>]*>(.*?)</otherwise\s*>', re.IGNORECASE | re.DOTALL)

FOREACH_TAG = re.compile(r'<foreach\b([^>]*)>', re.IGNORECASE)
FOREACH_CLOSE = re.compile(r'</foreach\s*>', re.IGNORECASE)

BIND_TAG = re.compile(r'<bind\b[^>]*/>', re.IGNORECASE)
INCLUDE_TAG = re.compile(r'<include\b[^>]*/>', re.IGNORECASE)

PARAM_RE = re.compile(r'#\{([^}]+)\}')
DOLLAR_RE = re.compile(r'\$\{([^}]+)\}')

ATTR_RE = re.compile(r'(\w+)\s*=\s*"([^"]*)"', re.IGNORECASE)


def _ws(s: str) -> str:
    return re.sub(r'\s+', ' ', s).strip()


def _process_choose(sql: str) -> str:
    def _resolve(m):
        inner = m.group(1)
        wm = WHEN_BLOCK.search(inner)
        if wm:
            return wm.group(1)
        om = OTHER_BLOCK.search(inner)
        if om:
            return om.group(1)
        return ""
    return CHOOSE_BLOCK.sub(_resolve, sql)


def _process_foreach(sql: str) -> str:
    def _resolve(m):
        attrs_str = m.group(1)
        body = m.group(2)
        body = body.strip()
        attrs = {}
        for am in ATTR_RE.finditer(attrs_str):
            attrs[am.group(1)] = am.group(2)
        open_str = attrs.get("open", "")
        close_str = attrs.get("close", "")
        separator = attrs.get("separator", ",")
        return open_str + body + close_str
    return re.sub(
        r'<foreach\s([^>]*)>(.*?)</foreach\s*>',
        _resolve, sql, flags=re.DOTALL | re.IGNORECASE
    )


WHERE_OPEN = re.compile(r'<where\b[^>]*>', re.IGNORECASE)
WHERE_CLOSE = re.compile(r'</where\s*>', re.IGNORECASE)


def _process_where_tag(sql: str) -> str:
    def _resolve(m):
        body = m.group(1)
        body = _ws(body)
        body = re.sub(r'(?i)^(?:AND|OR)\s+', '', body)
        if not body:
            return ""
        return "WHERE " + body
    return re.sub(r'<where\b[^>]*>(.*?)</where\s*>', _resolve,
                  sql, flags=re.DOTALL | re.IGNORECASE)


def _process_set_tag(sql: str) -> str:
    def _resolve(m):
        body = m.group(1)
        body = _ws(body)
        body = re.sub(r',\s*,', ',', body)
        body = re.sub(r',\s*$', '', body)
        if not body:
            return ""
        return "SET " + body
    return re.sub(r'<set\b[^>]*>(.*?)</set\s*>', _resolve,
                  sql, flags=re.DOTALL | re.IGNORECASE)


def _process_trim_tag(sql: str) -> str:
    def _resolve(m):
        attrs_raw = m.group(1)
        body = m.group(2)
        body = _ws(body)
        prefix = suffix = prefix_ov = suffix_ov = ""
        for am in ATTR_RE.finditer(attrs_raw):
            k, v = am.group(1), am.group(2)
            if k == "prefix": prefix = v
            elif k == "suffix": suffix = v
            elif k == "prefixOverrides": prefix_ov = v
            elif k == "suffixOverrides": suffix_ov = v
        if prefix_ov:
            for token in prefix_ov.replace(' ', '').split('|'):
                body = re.sub(r'(?i)^\s*' + re.escape(token) + r'\s+', '', body)
        if suffix_ov:
            for token in suffix_ov.replace(' ', '').split('|'):
                body = re.sub(r'(?i)\s*' + re.escape(token) + r'\s*$', '', body)
        body = _ws(body)
        if not body:
            return ""
        return _ws(prefix + " " + body + " " + suffix)
    return re.sub(r'<trim\b([^>]*)>(.*?)</trim\s*>', _resolve,
                  sql, flags=re.DOTALL | re.IGNORECASE)


def _detect_unresolved_tags(sql: str) -> list[str]:
    """Return list of conditional tag names still present in SQL."""
    tags: list[str] = []
    if IF_TAG.search(sql):
        tags.append("if")
    if re.search(r'<choose\b', sql, re.IGNORECASE):
        tags.append("choose")
    return tags


def resolve(raw_sql: str, dynamic_tags: list[dict],
            mode: str = "optimistic") -> dict:
    """Resolve dynamic SQL.

    Returns dict with fields:
      resolved_sql, uncertain, uncertain_tags
      In resolve mode also: needs_llm, unresolved_tags
    """
    uncertain: list[str] = []
    sql = raw_sql

    # Always strip bind/include (non-SQL declarations)
    sql = BIND_TAG.sub('', sql)
    sql = INCLUDE_TAG.sub('', sql)

    if mode == "resolve":
        # Structural tags processed deterministically
        sql = _process_foreach(sql)

        # Conditional tags LEFT in place for LLM
        unresolved = _detect_unresolved_tags(sql)

        if DOLLAR_RE.search(sql):
            uncertain.append("$parameter_detected")
            sql = DOLLAR_RE.sub(r"'\1'", sql)

        sql = PARAM_RE.sub('?', sql)
        sql = _ws(sql)

        needs_llm = (len(unresolved) > 0 or
                     (dynamic_tags and len(dynamic_tags) > 0))

        if dynamic_tags:
            uncertain.append("dynamic_tags_present")

        return {
            "resolved_sql": sql,
            "uncertain": len(uncertain) > 0,
            "uncertain_tags": uncertain,
            "needs_llm": needs_llm,
            "unresolved_tags": unresolved,
        }

    # --- optimistic mode (original behavior) ---
    sql = _process_choose(sql)
    sql = _process_foreach(sql)

    sql = IF_TAG.sub('', sql)
    sql = IF_CLOSE.sub('', sql)

    sql = _process_where_tag(sql)
    sql = _process_set_tag(sql)
    sql = _process_trim_tag(sql)

    sql = sql.replace('&gt;', '>').replace('&lt;', '<').replace('&amp;', '&')

    if DOLLAR_RE.search(sql):
        uncertain.append("$parameter_detected")
        sql = DOLLAR_RE.sub(r"'\1'", sql)

    sql = PARAM_RE.sub('?', sql)
    sql = _ws(sql)

    if dynamic_tags:
        uncertain.append("dynamic_tags_present")

    return {
        "resolved_sql": sql,
        "uncertain": len(uncertain) > 0,
        "uncertain_tags": uncertain,
    }


def finalize_sql(resolved_with_tags: str) -> str:
    """Post-process LLM-resolved SQL: strip remaining if/choose tags,
    apply where/set/trim processing.

    Call this after an LLM has resolved conditionals by removing/keeping
    body text within <if>/<choose> tags. This function cleans up the
    remaining tag artifacts.
    """
    sql = resolved_with_tags

    sql = _process_choose(sql)
    sql = IF_TAG.sub('', sql)
    sql = IF_CLOSE.sub('', sql)

    sql = _process_where_tag(sql)
    sql = _process_set_tag(sql)
    sql = _process_trim_tag(sql)

    sql = _ws(sql)
    return sql


def main():
    parser = argparse.ArgumentParser(
        description="Resolve MyBatis dynamic SQL for EXPLAIN"
    )
    parser.add_argument("--input", type=str, default="",
                        help="JSON array (reads stdin if omitted)")
    parser.add_argument("--mode", type=str, default="optimistic",
                        choices=["optimistic", "resolve"],
                        help="Mode: optimistic (default) or resolve (keep conditionals)")
    parser.add_argument("--skip-finalize", action="store_true",
                        help="Skip finalize_sql() cleanup — keeps raw resolved SQL "
                             "with dynamic tags for LLM inspection (resolve mode only)")
    args = parser.parse_args()

    if args.input:
        records = json.loads(args.input)
    else:
        text = sys.stdin.read().strip()
        if not text:
            return
        try:
            records = json.loads(text)
        except json.JSONDecodeError:
            records = [json.loads(line) for line in text.splitlines()]

    for rec in records:
        sql_id = rec.get("sql_id", "?")
        raw = rec.get("raw_sql", "")
        tags = rec.get("dynamic_tags", [])

        result = resolve(raw, tags, mode=args.mode)
        resolved_sql = result["resolved_sql"]

        if args.mode == "resolve":
            if not args.skip_finalize:
                resolved_sql = finalize_sql(resolved_sql)
            out = {
                "sql_id": sql_id,
                "resolved_sql": resolved_sql,
                "uncertain": result["uncertain"],
                "uncertain_tags": result["uncertain_tags"],
                "needs_llm": result["needs_llm"],
                "unresolved_tags": result["unresolved_tags"],
            }
        else:
            out = {
                "sql_id": sql_id,
                "resolved_sql": resolved_sql,
                "uncertain": result["uncertain"],
                "uncertain_tags": result["uncertain_tags"],
            }

        print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
