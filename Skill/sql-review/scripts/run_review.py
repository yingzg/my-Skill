#!/usr/bin/env python3
"""Run the SQL review pipeline end to end.

This runner keeps SKILL.md thin by moving deterministic orchestration into a
tested script. It supports a dry-run mode for local and CI validation without a
database connection.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"


def _run(cmd: list[str], *, input_text: str | None = None) -> str:
    result = subprocess.run(
        cmd,
        input=input_text,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed ({result.returncode}): {' '.join(cmd)}\n{result.stderr.strip()}"
        )
    return result.stdout


def _load_json(text: str) -> Any:
    return json.loads(text) if text.strip() else []


def _load_ndjson(text: str) -> list[dict]:
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _dump_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _dump_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")


def _build_risk_context(parsed: list[dict], trace: dict) -> dict:
    chain_by_method = {
        item.get("method"): item
        for item in trace.get("chains", [])
        if item.get("method")
    }
    results = []
    for rec in parsed:
        method_fqn = f"{rec.get('mapper_namespace')}.{rec.get('method_name')}"
        chain = chain_by_method.get(method_fqn, {})
        results.append({
            "sql_id": rec["sql_id"],
            "call_chain": chain.get("call_chain", []),
            "call_chain_broken": not bool(chain.get("complete", False)),
        })
    return {"results": results}


def _merge_records(
    resolved: list[dict],
    tables: list[dict],
    proxies: list[dict],
    parsed_by_id: dict[str, dict],
) -> list[dict]:
    table_by_id = {r["sql_id"]: r for r in tables}
    proxy_by_id = {r["sql_id"]: r for r in proxies}
    merged = []
    for rec in resolved:
        sql_id = rec["sql_id"]
        parsed = parsed_by_id.get(sql_id, {})
        proxy = proxy_by_id.get(sql_id, {})
        table = table_by_id.get(sql_id, {})
        merged.append({
            **parsed,
            **rec,
            "main_table": table.get("main_table", "UNKNOWN"),
            "original_sql": proxy.get("original_sql", parsed.get("raw_sql", "")),
            "proxy_sql": proxy.get("proxy_sql"),
        })
    return merged


def main() -> None:
    parser = argparse.ArgumentParser(description="Run SQL review pipeline")
    parser.add_argument("--files", required=True, help="JSON array of Mapper XML files")
    parser.add_argument("--project-root", default=".", help="Project root")
    parser.add_argument("--project-src", default="src/main/java", help="Java source path")
    parser.add_argument("--base-branch", default="origin/master")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--work-dir", default="")
    parser.add_argument("--dry-run", action="store_true", help="Use mock EXPLAIN")
    parser.add_argument("--mode", default="local", choices=["local", "ci"])
    parser.add_argument("--output", default="", help="Final report output path")
    args = parser.parse_args()

    run_id = args.run_id or "manual"
    work_dir = Path(args.work_dir or f"/tmp/sql_review/{run_id}")
    work_dir.mkdir(parents=True, exist_ok=True)

    files = json.loads(args.files)
    if not isinstance(files, list) or not files:
        raise SystemExit("--files must be a non-empty JSON array")

    parsed_text = _run([
        sys.executable, str(SCRIPTS / "parse_mapper.py"),
        "--files", json.dumps(files, ensure_ascii=False),
        "--format", "json",
    ])
    parsed = _load_json(parsed_text)
    _dump_json(work_dir / "phase1_parse.json", parsed)

    methods = sorted({
        f"{rec['mapper_namespace']}.{rec['method_name']}"
        for rec in parsed
        if rec.get("mapper_namespace") and rec.get("method_name")
    })
    trace_text = _run([
        sys.executable, str(SCRIPTS / "trace_callchain.py"),
        "--methods", json.dumps(methods, ensure_ascii=False),
        "--project-root", args.project_root,
        "--project-src", args.project_src,
    ])
    trace = _load_json(trace_text)
    _dump_json(work_dir / "phase2_trace.json", trace)

    resolved_text = _run([
        sys.executable, str(SCRIPTS / "resolve_dynamic_sql.py"),
    ], input_text=json.dumps(parsed, ensure_ascii=False))
    resolved = _load_ndjson(resolved_text)
    _dump_text(work_dir / "phase3_resolve.jsonl", resolved_text)

    tables_text = _run([
        sys.executable, str(SCRIPTS / "extract_tables.py"),
    ], input_text=resolved_text)
    tables = _load_ndjson(tables_text)
    _dump_text(work_dir / "phase3_5_tables.jsonl", tables_text)

    proxies_text = _run([
        sys.executable, str(SCRIPTS / "dml_to_select_proxy.py"),
    ], input_text=resolved_text)
    proxies = _load_ndjson(proxies_text)
    _dump_text(work_dir / "phase3_5_proxy.jsonl", proxies_text)

    parsed_by_id = {rec["sql_id"]: rec for rec in parsed}
    explain_batch = _merge_records(resolved, tables, proxies, parsed_by_id)
    _dump_json(work_dir / "phase4b_batch.json", explain_batch)

    rules_file = work_dir / "phase4a_rules.json"
    _run([
        sys.executable, str(SCRIPTS / "match_rules.py"),
        "--input", "-",
        "--output", str(rules_file),
        "--run-id", run_id,
    ], input_text=json.dumps(explain_batch, ensure_ascii=False))

    explain_file = work_dir / "phase4b_explain.json"
    explain_cmd = [
        sys.executable, str(SCRIPTS / "execute_explain.py"),
        "--output", str(explain_file),
    ]
    if args.dry_run:
        explain_cmd.append("--dry-run")
    _run(explain_cmd, input_text=json.dumps(explain_batch, ensure_ascii=False))

    risk_file = work_dir / "phase4b_risk.json"
    _dump_json(risk_file, _build_risk_context(parsed, trace))

    report_file = Path(args.output) if args.output else work_dir / "phase5_report.json"
    report_text = _run([
        sys.executable, str(SCRIPTS / "build_report.py"),
        "--run-id", run_id,
        "--rules-file", str(rules_file),
        "--explain-file", str(explain_file),
        "--risk-file", str(risk_file),
        "--base-branch", args.base_branch,
        "--mode", args.mode,
        "--output", str(report_file),
    ])
    report = _load_json(report_text)
    report["artifacts"] = {
        "work_dir": str(work_dir),
        "parse_file": str(work_dir / "phase1_parse.json"),
        "trace_file": str(work_dir / "phase2_trace.json"),
        "rules_file": str(rules_file),
        "explain_file": str(explain_file),
        "risk_file": str(risk_file),
    }
    _dump_json(report_file, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
