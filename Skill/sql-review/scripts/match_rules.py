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


def match_rule(sql_text: str, rule: dict) -> tuple[bool, str]:
    """Test if a single rule matches the given SQL text.

    Returns (matched, severity).
    """
    method = rule.get("match", {}).get("method", "regex")
    pattern = rule.get("match", {}).get("pattern", "")

    if not pattern:
        return (False, "NONE")

    try:
        if method == "regex":
            is_match = bool(re.search(pattern, sql_text, re.IGNORECASE))
        elif method == "regex_absence":
            is_match = not bool(re.search(pattern, sql_text, re.IGNORECASE))
        else:
            is_match = False
    except re.error as e:
        print(f"WARNING: Invalid regex in rule {rule['id']}: {e}", file=sys.stderr)
        return (False, "NONE")

    if not is_match:
        return (False, "NONE")

    stmt_type = rule.get("_stmt_type", "SELECT")
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
    args = parser.parse_args()

    rules = load_rules(args.rules)
    sqls = load_sqls(args.input)

    results = []
    for sql_entry in sqls:
        sql_id = sql_entry["sql_id"]
        stmt_type = sql_entry["statement_type"]
        sql_text = sql_entry.get("raw_sql", "")

        rule_matches = []
        for rule in rules["rules"]:
            applicable_to = rule.get("applicable_to", [])
            if stmt_type not in applicable_to:
                rule_matches.append({
                    "rule_id": rule["id"],
                    "matched": False,
                    "severity": "NONE",
                })
                continue

            rule["_stmt_type"] = stmt_type
            matched, severity = match_rule(sql_text, rule)

            rule_matches.append({
                "rule_id": rule["id"],
                "matched": matched,
                "severity": severity,
            })

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
            "rule_matches": rule_matches,
            "overall_risk": overall_risk,
            "risk_reason": risk_reason,
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
