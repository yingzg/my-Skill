#!/usr/bin/env python3
"""Phase 5: Aggregate all results into final SQL review report.

Reads phase4a_rules.json, phase4b_explain.json, phase4b_risk.json,
merges by sql_id, computes gate decision, outputs terminal table and JSON.

Usage:
    python3 build_report.py \
        --rules-file phase4a_rules.json \
        --explain-file phase4b_explain.json \
        --risk-file phase4b_risk.json \
        --base-branch origin/master \
        --mode local
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone

RISK_LEVELS = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1, "PASS": 0, "UNCERTAIN": 0}
FINAL_LEVELS = {"CRITICAL", "HIGH", "MEDIUM", "LOW", "PASS"}

TERMINAL_COLORS = {
    "CRITICAL": "\033[1;35m",
    "HIGH": "\033[0;31m",
    "MEDIUM": "\033[0;33m",
    "LOW": "\033[0;32m",
    "PASS": "\033[0;37m",
    "UNCERTAIN": "\033[0;37m",
    "RESET": "\033[0m",
}


def _load_json(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def _current_branch() -> str:
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        )
        return result.stdout.strip()
    except Exception:
        return ""


def _final_level(level: str | None) -> str:
    if level in FINAL_LEVELS:
        return level
    if level == "UNCERTAIN":
        return "PASS"
    return "PASS"


def _extract_explain_key(result: dict) -> str:
    if result.get("key") is not None:
        return result["key"]
    return ""


def _extract_explain_type(result: dict) -> str:
    return result.get("type") or ""


def _extract_explain_rows(result: dict | None) -> str:
    if result is None or result.get("rows") is None:
        return ""
    return str(result["rows"])


def _gate_decision(findings: list[dict]) -> str:
    for f in findings:
        lvl = RISK_LEVELS.get(f.get("risk_level", "PASS"), 0)
        if lvl >= RISK_LEVELS["MEDIUM"]:
            return "BLOCK"
    return "PASS"


def _gate_statistics(findings: list[dict]) -> dict:
    stats = {
        "total": len(findings),
        "CRITICAL": 0,
        "HIGH": 0,
        "MEDIUM": 0,
        "LOW": 0,
        "PASS": 0,
        "ANALYSIS_FAILED": 0,
    }
    for finding in findings:
        level = finding.get("risk_level", "PASS")
        if level in stats:
            stats[level] += 1
    return stats


def _format_table(findings: list[dict]) -> str:
    if not findings:
        return "No SQL findings.\n"

    lines = [
        "┌──────┬────────────────────────────────────────┬──────────┬──────────┬──────────────────────────────────────┐",
        "│  #   │ SQL ID                                 │ 等级     │ 执行计划 │ 说明                                 │",
        "├──────┼────────────────────────────────────────┼──────────┼──────────┼──────────────────────────────────────┤",
    ]

    for i, f in enumerate(findings, 1):
        sid = f["sql_id"][:38]
        lvl = f["risk_level"]
        color = TERMINAL_COLORS.get(lvl, "")
        reset = TERMINAL_COLORS["RESET"]
        exp = f"{f.get('explain_type', '')}/{f.get('explain_key', '')}"[:8]
        summary = (f.get("summary", "") or "")[:36]
        lines.append(
            f"│ {i:<4} │ {sid:<38} │ {color}{lvl:<8}{reset} │ {exp:<8} │ {summary:<36} │"
        )

    lines.append(
        "└──────┴────────────────────────────────────────┴──────────┴──────────┴──────────────────────────────────────┘"
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="SQL Review final report builder")
    parser.add_argument("--rules-file", required=True)
    parser.add_argument("--explain-file", required=True)
    parser.add_argument("--risk-file", required=True)
    parser.add_argument("--base-branch", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--mode", default="local", choices=["local", "ci"])
    parser.add_argument("--mr-url", default="")
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    rules_data = _load_json(args.rules_file).get("results", [])
    explain_data = _load_json(args.explain_file).get("results", [])

    try:
        risk_data = _load_json(args.risk_file).get("results", [])
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        risk_data = []

    rules_by_id = {r["sql_id"]: r for r in rules_data}
    explain_by_id = {e["sql_id"]: e for e in explain_data}
    risk_by_id = {r["sql_id"]: r for r in risk_data}

    findings = []
    review_items_by_tag: dict[str, dict] = {}
    review_needed = []
    all_ids = set(rules_by_id.keys()) | set(explain_by_id.keys())

    for sql_id in sorted(all_ids):
        rule = rules_by_id.get(sql_id, {})
        explain = explain_by_id.get(sql_id)
        risk = risk_by_id.get(sql_id, {})

        overall_risk = rule.get("overall_risk", "UNCERTAIN")
        if risk:
            level = _final_level(risk.get("level", overall_risk))
        else:
            level = _final_level(overall_risk)

        explain_executed = bool(explain and explain.get("executed"))

        findings.append({
            "sql_id": sql_id,
            "file_path": rule.get("file_path", ""),
            "line": rule.get("line", 0),
            "statement_type": rule.get("statement_type", ""),
            "mapper_method": sql_id.rsplit(":", 2)[-2] if ":" in sql_id else "",
            "risk_level": level,
            "risk_summary": risk.get("summary", rule.get("risk_reason", "")),
            "rationale": {
                "static_rules": rule.get("risk_reason", ""),
                "explain_analysis": (
                    f"type={explain.get('type')}, key={explain.get('key')}, rows={explain.get('rows')}"
                    if explain_executed else None
                ),
                "degradation_note": None if explain_executed else "EXPLAIN not available",
            },
            "short_term_fix": risk.get("short_term_fix", ""),
            "long_term_fix": risk.get("long_term_fix", ""),
            "call_chain": risk.get("call_chain", []),
            "call_chain_broken": bool(risk.get("call_chain_broken", False)),
            "resolved_sql": rule.get("resolved_sql", ""),
            "explain_executed": explain_executed,
            # Legacy compact fields used by the terminal table and older tests.
            "level": level,
            "summary": risk.get("summary", rule.get("risk_reason", "")),
            "explain_type": explain.get("type", "") if explain else "",
            "explain_key": explain.get("key", "") if explain else "",
            "explain_rows": explain.get("rows") if explain else None,
            "rule_matches": rule.get("rule_matches", []),
            "uncertain": risk.get("uncertain", True) if risk else True,
        })

        if not explain_executed:
            review_item = {
                "sql_id": sql_id,
                "reason": "EXPLAIN not available — manual review required",
            }
            review_needed.append(review_item)
            item = review_items_by_tag.setdefault("explain_unavailable", {
                "tag": "explain_unavailable",
                "item": "EXPLAIN not available",
                "reason": "One or more SQL statements could not be explained automatically.",
                "sql_ids": [],
            })
            item["sql_ids"].append(sql_id)

    findings.sort(key=lambda f: RISK_LEVELS.get(f.get("risk_level", "PASS"), 0), reverse=True)

    gate_conclusion = _gate_decision(findings)
    stats = _gate_statistics(findings)
    now = datetime.now(timezone.utc).isoformat()
    review_checklist = list(review_items_by_tag.values())

    report = {
        "report_id": f"sql-review-{args.run_id}",
        "generated_at": now,
        "version": "1.0.0",
        "context": {
            "branch": _current_branch(),
            "base_ref": args.base_branch,
            "mr_url": args.mr_url or None,
            "mode": args.mode,
            "total_sql_count": len(findings),
        },
        "gate": {
            "conclusion": gate_conclusion,
            "decision": gate_conclusion,
            "block_reason": "MEDIUM_OR_ABOVE_SQL_FOUND" if gate_conclusion == "BLOCK" else None,
            "thresholds": {
                "HIGH_block": stats["HIGH"] > 0,
                "MEDIUM_block": stats["MEDIUM"] > 0,
                "CRITICAL_block": stats["CRITICAL"] > 0,
            },
            "statistics": stats,
        },
        "base_branch": args.base_branch,
        "total_sql": len(findings),
        "findings": findings,
        "review_needed": review_needed,
        "review_checklist": review_checklist,
        "degradation_notes": [
            {
                "level": "partial",
                "type": item["tag"],
                "description": item["reason"],
            }
            for item in review_checklist
        ],
    }

    print(_format_table(findings), file=sys.stderr)

    out = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, "w") as f:
            f.write(out + "\n")
    print(out)


if __name__ == "__main__":
    main()
