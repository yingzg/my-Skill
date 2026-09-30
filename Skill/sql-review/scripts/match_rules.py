#!/usr/bin/env python3
"""Phase 4a: Static rule matching against extracted SQL.

Usage:
    python3 match_rules.py --input parse-output.json [--rules references/rules/rules.json]
    python3 match_rules.py --input parse-output.json --output phase4a_rules.json
"""

import argparse
import json
import re
import sys
import os
from pathlib import Path
from datetime import datetime, timezone

SCRIPT_DIR = Path(__file__).resolve().parent.parent  # scripts/ → repo root


def load_rules(rules_path: str) -> dict:
    if not os.path.exists(rules_path):
        print(f"ERROR: Rules file not found: {rules_path}", file=sys.stderr)
        sys.exit(1)
    with open(rules_path, "r", encoding="utf-8") as f:
        rules = json.load(f)
    if not rules.get("rules"):
        print("ERROR: Rules file is empty (rules: [])", file=sys.stderr)
        sys.exit(1)
    return rules


def load_sqls(input_path: str) -> list[dict]:
    if input_path == "-":
        text = sys.stdin.read().strip()
        if not text:
            return []
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return [json.loads(line) for line in text.splitlines()]
    with open(input_path, "r", encoding="utf-8") as f:
        text = f.read().strip()
        if not text:
            return []
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return [json.loads(line) for line in text.splitlines()]


STRING_TYPES = ("varchar", "char", "text", "longtext", "enum", "set")


def _find_column_type(column: str, main_table: str, schemas: dict) -> str | None:
    schema = schemas.get(main_table, {})
    if column in schema.get("columns", {}):
        return schema["columns"][column]
    found = None
    for s in schemas.values():
        col_type = s.get("columns", {}).get(column)
        if col_type is not None:
            if found is not None and found != col_type:
                return None
            found = col_type
    return found


def _is_pk_eq_query(sql_text: str, main_table: str, schemas: dict) -> bool:
    schema = schemas.get(main_table, {})
    pk = schema.get("primary_key")
    if not pk:
        return False
    for match in re.finditer(r"`?(\w+)`?\s*=\s*\?", sql_text):
        if match.group(1) == pk:
            return True
    return False


def _check_string_column_eq_number(sql_text: str, main_table: str, schemas: dict) -> bool:
    for match in re.finditer(r"`?(\w+)`?\s*(?:=|>|<|>=|<=|!=|<>)\s*\d+", sql_text):
        column = match.group(1)
        if _find_column_type(column, main_table, schemas) in STRING_TYPES:
            return True
    return False


def _soft_delete_fields(pattern: str) -> list[str]:
    for group in re.findall(r'\(([^()]*)\)', pattern):
        if group.startswith('?'):
            continue
        return [name.strip() for name in group.split('|') if name.strip()]
    return []


def _table_soft_delete_field(schema: dict, fields: list[str]) -> str | None:
    columns = schema.get("columns", {})
    for field in fields:
        if field in columns:
            return field
    return None


def _where_contains(sql_text: str, field: str) -> bool:
    match = re.search(r'\bWHERE\b', sql_text, re.IGNORECASE)
    if not match:
        return False
    where_part = sql_text[match.end():]
    return re.search(rf'\b{re.escape(field)}\b', where_part, re.IGNORECASE) is not None


def match_rule(sql_text: str, rule: dict, stmt_type: str, main_table: str, schemas: dict) -> tuple[bool, str]:
    """Test if a single rule matches the given SQL text.

    Returns (matched, severity).
    """
    exempt = rule.get("exempt", {})
    if exempt.get("method") == "schema_pk_eq_query" and schemas and _is_pk_eq_query(sql_text, main_table, schemas):
        return (False, "NONE")

    method = rule.get("match", {}).get("method", "regex")

    if method == "schema_column_eq_number":
        is_match = bool(schemas) and _check_string_column_eq_number(sql_text, main_table, schemas)
        if not is_match:
            return (False, "NONE")
        severity_by_type = rule.get("severity_by_type", {})
        return (True, severity_by_type.get(stmt_type, rule.get("risk_level", "MEDIUM")))

    pattern = rule.get("match", {}).get("pattern", "")

    if method == "schema_soft_delete_guard":
        fields = _soft_delete_fields(pattern)
        schema = schemas.get(main_table, {})
        sf = _table_soft_delete_field(schema, fields)
        if sf is None or _where_contains(sql_text, sf):
            return (False, "NONE")
        severity_by_type = rule.get("severity_by_type", {})
        return (True, severity_by_type.get(stmt_type, rule.get("risk_level", "MEDIUM")))

    if not pattern:
        return (False, "NONE")

    try:
        if method == "regex":
            is_match = bool(re.search(pattern, sql_text, re.IGNORECASE))
        elif method == "regex_absence":
            is_match = not bool(re.search(pattern, sql_text, re.IGNORECASE))
        else:
            print(f"WARNING: Unsupported match method '{method}' in rule {rule['id']}", file=sys.stderr)
            is_match = False
    except re.error as e:
        print(f"WARNING: Invalid regex in rule {rule['id']}: {e}", file=sys.stderr)
        return (False, "NONE")

    if not is_match:
        return (False, "NONE")

    severity_by_type = rule.get("severity_by_type", {})
    severity = severity_by_type.get(stmt_type, rule.get("risk_level", "MEDIUM"))

    return (True, severity)


SEVERITY_ORDER = {"CRITICAL": 5, "HIGH": 4, "MEDIUM": 3, "LOW": 2, "INFO": 1, "NONE": 0}


def determine_overall_risk(matches: list[dict]) -> str:
    """Determine overall risk level from rule match results."""
    if not matches:
        return "UNCERTAIN"
    severities = [m["severity"] for m in matches if m["matched"]]
    if not severities:
        return "UNCERTAIN"
    max_sev = max(severities, key=lambda s: SEVERITY_ORDER.get(s, 0))
    return max_sev


def main():
    parser = argparse.ArgumentParser(
        description="Match static rules against extracted SQL statements"
    )
    parser.add_argument("--input", type=str, required=True,
                        help="Path to parse output JSON (use '-' for stdin)")
    parser.add_argument("--rules", type=str,
                        default=str(SCRIPT_DIR / "references/rules/rules.json"),
                        help="Path to rules JSON file")
    parser.add_argument("--output", type=str,
                        help="Write result JSON to file (stdout if omitted)")
    parser.add_argument("--run-id", type=str, default="golden",
                        help="Run identifier (default: golden)")
    parser.add_argument("--schema-file", type=str, default="",
                        help="discover_schema.py output JSON for schema-aware rules")
    args = parser.parse_args()

    rules = load_rules(args.rules)
    sqls = load_sqls(args.input)

    schemas = {}
    if args.schema_file:
        try:
            with open(args.schema_file, encoding="utf-8") as f:
                schemas = json.load(f).get("schemas", {})
        except (FileNotFoundError, json.JSONDecodeError):
            schemas = {}

    results = []
    for sql_entry in sqls:
        sql_id = sql_entry["sql_id"]
        stmt_type = sql_entry["statement_type"]
        sql_text = sql_entry.get("resolved_sql") or sql_entry.get("raw_sql", "")
        main_table = sql_entry.get("main_table", "UNKNOWN")

        rule_matches = []
        best_fix = {"short": "", "long": "", "severity": -1}
        for rule in rules["rules"]:
            applicable_to = rule.get("applicable_to", [])
            if stmt_type not in applicable_to:
                rule_matches.append({
                    "rule_id": rule["id"],
                    "matched": False,
                    "severity": "NONE",
                })
                continue

            matched, severity = match_rule(sql_text, rule, stmt_type, main_table, schemas)

            rule_matches.append({
                "rule_id": rule["id"],
                "matched": matched,
                "severity": severity,
            })

            if matched:
                sev = SEVERITY_ORDER.get(severity, 0)
                if sev > best_fix["severity"]:
                    best_fix = {
                        "short": rule.get("short_term_fix_template", ""),
                        "long": rule.get("long_term_fix_template", ""),
                        "severity": sev,
                    }

        overall_risk = determine_overall_risk(rule_matches)

        matched_rules = [m["rule_id"] for m in rule_matches if m["matched"]]
        risk_reason = ""
        if matched_rules:
            risk_reason = f"Matched: {', '.join(matched_rules)}"
        else:
            risk_reason = "No rules matched (UNCERTAIN)"

        results.append({
            "sql_id": sql_id,
            "statement_type": stmt_type,
            "file_path": sql_entry.get("file", ""),
            "line": sql_entry.get("line_start", 0),
            "resolved_sql": sql_text,
            "rule_matches": rule_matches,
            "overall_risk": overall_risk,
            "risk_reason": risk_reason,
            "short_term_fix": best_fix["short"],
            "long_term_fix": best_fix["long"],
        })

    output = {
        "run_id": args.run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "rules_version": rules["meta"]["version"],
        "results": results,
    }

    json_text = json.dumps(output, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(json_text + "\n")
    else:
        print(json_text)


if __name__ == "__main__":
    main()
