#!/usr/bin/env python3
"""Phase 3.5b: Convert DML (UPDATE/DELETE/INSERT) to SELECT proxy for EXPLAIN.

Many databases cannot EXPLAIN non-SELECT statements. This script constructs
an equivalent SELECT that uses the same WHERE clause, so EXPLAIN can still
reveal index usage and scan characteristics.

Usage:
    python3 dml_to_select_proxy.py --input '[...]'
    cat resolve-output.jsonl | python3 dml_to_select_proxy.py
"""

import argparse
import json
import re
import sys

WHERE_RE = re.compile(r'(?i)\bWHERE\b\s+(.+)', re.DOTALL)
FROM_RE = re.compile(r'(?i)(?<!\w)FROM\s+`?(\w+)`?')
UPDATE_RE = re.compile(r'(?i)(?<!\w)UPDATE\s+`?(\w+)`?')
INSERT_INTO_RE = re.compile(r'(?i)(?<!\w)INSERT\s+INTO\s+`?(\w+)`?')
DELETE_FROM_RE = re.compile(r'(?i)(?<!\w)DELETE\s+FROM\s+`?(\w+)`?')
SET_RE = re.compile(r'(?i)\bSET\b\s+(.+?)(?=\bWHERE\b|$)', re.DOTALL)


def _is_dml(sql: str) -> str:
    """Return 'UPDATE', 'DELETE', 'INSERT', 'SELECT', or 'UNKNOWN'."""
    upper = sql.strip().upper()
    if upper.startswith("UPDATE"):
        return "UPDATE"
    if upper.startswith("DELETE"):
        return "DELETE"
    if upper.startswith("INSERT"):
        return "INSERT"
    if upper.startswith("SELECT"):
        return "SELECT"
    return "UNKNOWN"


def _extract_where(sql: str) -> str | None:
    m = WHERE_RE.search(sql)
    if m:
        return m.group(1).strip()
    return None


def _extract_table(sql: str, stype: str) -> str | None:
    if stype == "UPDATE":
        m = UPDATE_RE.search(sql)
    elif stype == "DELETE":
        m = DELETE_FROM_RE.search(sql)
    elif stype == "INSERT":
        m = INSERT_INTO_RE.search(sql)
    else:
        return None
    return m.group(1) if m else None


def _extract_set_columns(sql: str) -> str:
    """Extract column names from SET clause. Returns '*' if empty."""
    m = SET_RE.search(sql)
    if not m:
        return "*"
    body = m.group(1)
    cols = re.findall(r'`?(\w+)`?\s*=', body)
    if not cols:
        return "*"
    return ", ".join(cols)


def _build_proxy(sql: str) -> str | None:
    stype = _is_dml(sql)
    if stype == "SELECT":
        return None

    table = _extract_table(sql, stype)
    if not table:
        return None

    where = _extract_where(sql)

    if stype == "DELETE":
        if where:
            return f"SELECT * FROM {table} WHERE {where}"
        return f"SELECT * FROM {table}"

    if stype == "UPDATE":
        cols = _extract_set_columns(sql)
        if where:
            return f"SELECT {cols} FROM {table} WHERE {where}"
        return f"SELECT {cols} FROM {table}"

    if stype == "INSERT":
        if re.search(r'\bSELECT\b', sql, re.IGNORECASE):
            m = re.search(r'(?i)INSERT\s+INTO\s+`?\w+`?\s*(\([^)]*\))?\s*(SELECT\s+.+)', sql, re.DOTALL)
            if m:
                return m.group(3).strip()
        return None

    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="DML → SELECT proxy for EXPLAIN")
    parser.add_argument("--input", default=None,
                        help="JSON array string of [{sql_id, original_sql, statement_type}, ...]")
    args = parser.parse_args()

    if args.input:
        text = args.input.strip()
        if not text:
            return
        try:
            records = json.loads(text)
        except json.JSONDecodeError:
            records = [json.loads(line) for line in text.splitlines()]
    else:
        text = sys.stdin.read().strip()
        if not text:
            return
        try:
            records = json.loads(text)
        except json.JSONDecodeError:
            records = [json.loads(line) for line in text.splitlines()]

    for rec in records:
        sql_id = rec.get("sql_id", "UNKNOWN")
        original = rec.get("original_sql", rec.get("resolved_sql", ""))
        proxy = _build_proxy(original)
        print(json.dumps({
            "sql_id": sql_id,
            "original_sql": original,
            "proxy_sql": proxy,
        }))


if __name__ == "__main__":
    main()
