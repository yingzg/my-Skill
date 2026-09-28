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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"

SCRIPT_DEGRADATION = {
    "discover_datasource.py": "D4 (数据源发现)",
    "parse_mapper.py": "D2/D3 (XML 解析)",
    "trace_callchain.py": "D8 (调用链追踪)",
    "resolve_dynamic_sql.py": "D9 (动态 SQL 解析)",
    "extract_tables.py": "—",
    "dml_to_select_proxy.py": "—",
    "match_rules.py": "D10/D11 (规则文件)",
    "execute_explain.py": "D5/D6/D7 (EXPLAIN)",
    "build_report.py": "D16 (报告生成)",
}


def _run(cmd: list[str], *, input_text: str | None = None,
         degradations: list[dict] | None = None) -> str:
    result = subprocess.run(
        cmd,
        input=input_text,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        script = Path(cmd[1]).name if len(cmd) > 1 else str(cmd)
        scene = SCRIPT_DEGRADATION.get(script, "")
        msg = (f"Command failed ({result.returncode}) {scene}: "
               f"{' '.join(cmd)}\n{result.stderr.strip()}")
        if degradations is not None:
            degradations.append({
                "script": script,
                "scene": scene,
                "stderr": result.stderr.strip()[:1000],
            })
            print(f"WARNING: {msg}", file=sys.stderr)
            return ""
        raise RuntimeError(msg)
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
    parser.add_argument("--mr-comment-output", default="",
                        help="Write CI MR comment markdown to this file (mode=ci)")
    parser.add_argument("--changed-statements", default="",
                        help='JSON map of file path -> changed statement ids (optional)')
    parser.add_argument("--db-type", default="mysql", choices=["mysql", "oceanbase"],
                        help="Database type for toolbox prebuilt (default: mysql)")
    args = parser.parse_args()

    run_id = args.run_id or "manual"
    work_dir = Path(args.work_dir or f"/tmp/sql_review/{run_id}")
    work_dir.mkdir(parents=True, exist_ok=True)

    files = json.loads(args.files)
    if not isinstance(files, list) or not files:
        raise SystemExit("--files must be a non-empty JSON array")

    degradations = [] if args.mode == "ci" else None

    changed_statements = {}
    if args.changed_statements:
        changed_statements = json.loads(args.changed_statements)

    ds_text = _run([
        sys.executable, str(SCRIPTS / "discover_datasource.py"),
        "--project-root", args.project_root,
        "--project-src", args.project_src,
    ], degradations=degradations)
    ds_data = _load_json(ds_text)
    _dump_json(work_dir / "phase0_5_datasource.json", ds_data)

    parse_errors_file = work_dir / "phase1_parse_errors.json"
    parse_cmd = [
        sys.executable, str(SCRIPTS / "parse_mapper.py"),
        "--files", json.dumps(files, ensure_ascii=False),
        "--datasource-map", json.dumps(ds_data, ensure_ascii=False),
        "--format", "json",
        "--parse-errors-output", str(parse_errors_file),
    ]
    if changed_statements:
        parse_cmd += ["--only-statements", json.dumps(changed_statements, ensure_ascii=False)]
    parsed_text = _run(parse_cmd, degradations=degradations)
    parsed = _load_json(parsed_text)
    _dump_json(work_dir / "phase1_parse.json", parsed)

    parse_errors = []
    if parse_errors_file.exists():
        parse_errors = _load_json(parse_errors_file.read_text(encoding="utf-8"))

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
    ], degradations=degradations)
    trace = _load_json(trace_text)
    _dump_json(work_dir / "phase2_trace.json", trace)

    resolved_text = _run([
        sys.executable, str(SCRIPTS / "resolve_dynamic_sql.py"),
        "--mode", "resolve",
        "--skip-finalize",
    ], input_text=json.dumps(parsed, ensure_ascii=False), degradations=degradations)

    resolved_text = _run([
        sys.executable, str(SCRIPTS / "llm_resolve.py"),
        "--trace-file", str(work_dir / "phase2_trace.json"),
    ], input_text=resolved_text, degradations=degradations)

    resolved = _load_ndjson(resolved_text)
    _dump_text(work_dir / "phase3_resolve.jsonl", resolved_text)

    tables_text = _run([
        sys.executable, str(SCRIPTS / "extract_tables.py"),
    ], input_text=resolved_text, degradations=degradations)
    tables = _load_ndjson(tables_text)
    _dump_text(work_dir / "phase3_5_tables.jsonl", tables_text)

    proxies_text = _run([
        sys.executable, str(SCRIPTS / "dml_to_select_proxy.py"),
    ], input_text=resolved_text, degradations=degradations)
    proxies = _load_ndjson(proxies_text)
    _dump_text(work_dir / "phase3_5_proxy.jsonl", proxies_text)

    schema_file = None
    table_names = sorted({
        t["main_table"] for t in tables
        if t.get("main_table") and t["main_table"] != "UNKNOWN"
    })
    if table_names:
        schema_file = work_dir / "phase3_5_schema.json"
        schema_text = _run([
            sys.executable, str(SCRIPTS / "discover_schema.py"),
            "--db-type", args.db_type,
        ], input_text=json.dumps(table_names, ensure_ascii=False), degradations=degradations)
        _dump_text(schema_file, schema_text)

    parsed_by_id = {rec["sql_id"]: rec for rec in parsed}
    explain_batch = _merge_records(resolved, tables, proxies, parsed_by_id)
    _dump_json(work_dir / "phase4b_batch.json", explain_batch)

    rules_file = work_dir / "phase4a_rules.json"
    rules_cmd = [
        sys.executable, str(SCRIPTS / "match_rules.py"),
        "--input", "-",
        "--output", str(rules_file),
        "--run-id", run_id,
    ]
    if schema_file:
        rules_cmd += ["--schema-file", str(schema_file)]
    _run(rules_cmd, input_text=json.dumps(explain_batch, ensure_ascii=False), degradations=degradations)

    explain_file = work_dir / "phase4b_explain.json"
    explain_cmd = [
        sys.executable, str(SCRIPTS / "execute_explain.py"),
        "--output", str(explain_file),
        "--db-type", args.db_type,
        "--run-id", run_id,
    ]
    if schema_file:
        explain_cmd += ["--schema-file", str(schema_file)]
    if args.dry_run:
        explain_cmd.append("--dry-run")
    _run(explain_cmd, input_text=json.dumps(explain_batch, ensure_ascii=False), degradations=degradations)

    risk_file = work_dir / "phase4b_risk.json"
    _dump_json(risk_file, _build_risk_context(parsed, trace))

    _run([
        sys.executable, str(SCRIPTS / "llm_risk_analysis.py"),
        "--rules-file", str(rules_file),
        "--explain-file", str(explain_file),
        "--risk-file", str(risk_file),
        "--output", str(risk_file),
    ], degradations=degradations)

    report_file = Path(args.output) if args.output else work_dir / "phase5_report.json"
    report_cmd = [
        sys.executable, str(SCRIPTS / "build_report.py"),
        "--run-id", run_id,
        "--rules-file", str(rules_file),
        "--explain-file", str(explain_file),
        "--risk-file", str(risk_file),
        "--base-branch", args.base_branch,
        "--mode", args.mode,
        "--output", str(report_file),
    ]
    if args.mr_comment_output:
        report_cmd += ["--mr-comment-output", args.mr_comment_output]
    _run(report_cmd, degradations=degradations)

    report = []
    if report_file.exists():
        report = _load_json(report_file.read_text(encoding="utf-8"))
    if not isinstance(report, dict):
        report = {
            "report_id": f"sql-review-{run_id}",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "version": "1.0.0",
            "context": {"mode": args.mode, "total_sql_count": len(parsed)},
            "gate": {"conclusion": "INCONCLUSIVE", "decision": "INCONCLUSIVE",
                     "block_reason": "ANALYSIS_INCOMPLETE", "statistics": {}},
            "findings": [],
            "review_needed": [],
            "review_checklist": [],
            "degradation_notes": [],
        }
    report["artifacts"] = {
        "work_dir": str(work_dir),
        "parse_file": str(work_dir / "phase1_parse.json"),
        "trace_file": str(work_dir / "phase2_trace.json"),
        "rules_file": str(rules_file),
        "explain_file": str(explain_file),
        "risk_file": str(risk_file),
    }

    if parse_errors:
        checklist = list(report.get("review_checklist", []))
        checklist.append({
            "tag": "parse_error",
            "item": "XML parse failed",
            "reason": "以下文件解析失败已跳过，其 MyBatis 写法可能超出解析器能力，需人工确认",
            "sql_ids": [],
            "parse_errors": parse_errors,
        })
        report["review_checklist"] = checklist
        notes = list(report.get("degradation_notes", []))
        notes.append({
            "level": "partial",
            "type": "parse_error",
            "description": f"{len(parse_errors)} 个文件解析失败",
        })
        report["degradation_notes"] = notes

    if degradations:
        notes = list(report.get("degradation_notes", []))
        for d in degradations:
            notes.append({
                "level": "global",
                "type": "script_failed",
                "description": f"{d['script']} 失败: {d['scene']}",
            })
        report["degradation_notes"] = notes

    critical_failed = any(
        d["script"] in ("match_rules.py", "parse_mapper.py")
        for d in (degradations or [])
    )
    if critical_failed and args.mode == "ci":
        report["gate"]["conclusion"] = "INCONCLUSIVE"
        report["gate"]["decision"] = "INCONCLUSIVE"
        report["gate"]["block_reason"] = "ANALYSIS_INCOMPLETE"

    _dump_json(report_file, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
