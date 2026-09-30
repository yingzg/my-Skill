#!/usr/bin/env python3
"""Phase 4b: Execute EXPLAIN on resolved SQL against target database.

Groups SQL by datasource, connects and runs EXPLAIN FORMAT=JSON, parses
the output to extract type/key/rows/extra fields.

Usage:
    python3 execute_explain.py --batch '[...]' --datasource-map '[...]'
    cat batch.json | python3 execute_explain.py --dry-run
"""

import argparse
import json
import os
import re
import select
import subprocess
import sys
from datetime import datetime, timezone

import db_client

RESULT_SCHEMA_KEYS = {"type", "key", "key_len", "rows", "extra"}

MOCK_EXPLAIN = {
    "default": {"type": "ALL", "key": None, "key_len": None, "rows": 10000, "extra": "Using where"},
    "findById":  {"type": "const", "key": "PRIMARY", "key_len": 4, "rows": 1, "extra": None},
    "findByOrderNo": {"type": "ref", "key": "idx_order_no", "key_len": 258, "rows": 1, "extra": "Using where"},
    "findAll": {"type": "ALL", "key": None, "key_len": None, "rows": 15823, "extra": "Using where"},
    "countByStatus": {"type": "ref", "key": "idx_status", "key_len": 4, "rows": 5000, "extra": "Using index condition"},
    "updateStatus": {"type": "range", "key": "PRIMARY", "key_len": 4, "rows": 1, "extra": "Using where"},
    "updateStatusNoWhere": {"type": "ALL", "key": None, "key_len": None, "rows": 15823, "extra": None},
    "deleteById": {"type": "range", "key": "PRIMARY", "key_len": 4, "rows": 1, "extra": "Using where"},
    "deleteAll": {"type": "ALL", "key": None, "key_len": None, "rows": 15823, "extra": None},
    "insertOrder": {"type": "INSERT", "key": None, "key_len": None, "rows": 1, "extra": None},
    "findWithDetail": {"type": "index_merge", "key": "idx_order_no,PRIMARY", "key_len": None, "rows": 500, "extra": "Using intersect(idx_order_no,PRIMARY); Using where"},
    "findByCondition": {"type": "index_merge", "key": "idx_status,idx_order_no", "key_len": None, "rows": 200, "extra": "Using union(idx_status,idx_order_no); Using where"},
    "findBySubQuery": {"type": "ref", "key": "idx_status", "key_len": 4, "rows": 100, "extra": "Using where; FirstMatch(orders)"},
    "findByIds": {"type": "range", "key": "PRIMARY", "key_len": 4, "rows": 10, "extra": "Using where"},
    "batchInsert": {"type": "INSERT", "key": None, "key_len": None, "rows": 3, "extra": None},
    "deleteByIds": {"type": "range", "key": "PRIMARY", "key_len": 4, "rows": 10, "extra": "Using where"},
    "findByWhere": {"type": "index_merge", "key": "idx_status,idx_order_no", "key_len": None, "rows": 300, "extra": "Using union(idx_status,idx_order_no); Using where"},
    "findByTrim": {"type": "index_merge", "key": "idx_status,idx_order_no", "key_len": None, "rows": 200, "extra": "Using union(idx_status,idx_order_no); Using where"},
    "updateByIf": {"type": "range", "key": "PRIMARY", "key_len": 4, "rows": 1, "extra": "Using where"},
    "updateBySet": {"type": "range", "key": "PRIMARY", "key_len": 4, "rows": 1, "extra": "Using where"},
    "updateByTrimSet": {"type": "range", "key": "PRIMARY", "key_len": 4, "rows": 1, "extra": "Using where"},
    "findByBind": {"type": "ALL", "key": None, "key_len": None, "rows": 15823, "extra": "Using where; Using filesort"},
    "findByBindWithIf": {"type": "ALL", "key": None, "key_len": None, "rows": 500, "extra": "Using where; Using filesort"},
    "findWithInclude": {"type": "ref", "key": "idx_order_no", "key_len": 258, "rows": 1, "extra": None},
    "findByMixed": {"type": "range", "key": "idx_status", "key_len": 4, "rows": 500, "extra": "Using where; Using filesort"},
    "findUserById": {"type": "const", "key": "PRIMARY", "key_len": 4, "rows": 1, "extra": None},
    "findUserWithOrders": {"type": "ALL", "key": None, "key_len": None, "rows": 5000, "extra": "Using where; Using join buffer (Block Nested Loop)"},
    "findUsersByKeyword": {"type": "ALL", "key": None, "key_len": None, "rows": 2000, "extra": "Using where; Using filesort"},
    "gh001_emptyForeach": {"type": "ALL", "key": None, "key_len": None, "rows": 15823, "extra": "Using where"},
    "gh004_limitNoOrder": {"type": "ALL", "key": None, "key_len": None, "rows": 15823, "extra": "Using where"},
    "findBySingleIf": {"type": "ALL", "key": None, "key_len": None, "rows": 5000, "extra": "Using where"},
    "findByChoose": {"type": "ref", "key": "idx_status", "key_len": 4, "rows": 5000, "extra": "Using where"},
    "findWithMultipleJoins": {"type": "ALL", "key": None, "key_len": None, "rows": 15823, "extra": "Using where; Using join buffer (Block Nested Loop); Using temporary; Using filesort"},
    "gh002_foreachNestedIf": {"type": "range", "key": "PRIMARY", "key_len": 4, "rows": 1, "extra": "Using where"},
    "gh003_leftLike": {"type": "ALL", "key": None, "key_len": None, "rows": 15823, "extra": "Using where"},
}


def _method_from_sql_id(sql_id: str) -> str:
    parts = sql_id.rsplit(":", 2)
    return parts[-2] if len(parts) >= 2 else "unknown"


def _mock_explain(sql_id: str) -> dict:
    method = _method_from_sql_id(sql_id)
    return MOCK_EXPLAIN.get(method, MOCK_EXPLAIN["default"])


def _extract_explain_fields(explain_json) -> dict:
    fields = {"type": None, "key": None, "key_len": None, "rows": None, "extra": None}

    def walk(node):
        if isinstance(node, dict):
            if "access_type" in node and fields["type"] is None:
                fields["type"] = node["access_type"]
                fields["key"] = node.get("key")
                fields["key_len"] = node.get("key_length")
                rows = node.get("rows_examined_per_scan")
                if rows is None:
                    rows = node.get("rows")
                fields["rows"] = rows
                extra_parts = []
                if node.get("using_filesort"):
                    extra_parts.append("Using filesort")
                if node.get("using_temporary_table") or node.get("using_temporary"):
                    extra_parts.append("Using temporary")
                if node.get("using_join_buffer"):
                    extra_parts.append("Using join buffer")
                fields["extra"] = "; ".join(extra_parts) if extra_parts else None
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(explain_json)
    return fields


def _run_explain(mcp: db_client.ToolboxMcp, sql: str) -> dict:
    text = mcp.execute_sql(f"EXPLAIN FORMAT=JSON {sql}")
    if not text:
        raise RuntimeError("EXPLAIN returned empty result")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"unable to parse EXPLAIN output: {text[:200]}") from exc
    if isinstance(data, dict) and "EXPLAIN" in data and isinstance(data["EXPLAIN"], str):
        data = json.loads(data["EXPLAIN"])
    fields = _extract_explain_fields(data)
    if fields["type"] is None:
        raise RuntimeError(f"no access_type found in EXPLAIN output: {text[:200]}")
    fields["raw_explain"] = text
    return fields


STRING_TYPES = ("varchar", "char", "text", "longtext", "enum", "set")
DATETIME_TYPES = ("datetime", "date", "timestamp")


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


def _explain_sql(sql: str, main_table: str, schemas: dict) -> str:
    if not schemas:
        return re.sub(r"\?", "1", sql)

    def repl(match):
        column = match.group(1)
        col_type = _find_column_type(column, main_table, schemas)
        if col_type in STRING_TYPES:
            return f"{column} = 'x'"
        if col_type in DATETIME_TYPES:
            return f"{column} = '2024-01-01'"
        return f"{column} = 1"

    sql = re.sub(r"\b(\w+)\s*(?:=|>|<|>=|<=|!=|<>)\s*\?", repl, sql)
    return re.sub(r"\?", "1", sql)


def main() -> None:
    parser = argparse.ArgumentParser(description="Execute EXPLAIN on SQL batch")
    parser.add_argument("--batch", default=None,
                        help="JSON array of [{sql_id, datasource, main_table, proxy_sql}]")
    parser.add_argument("--dry-run", action="store_true",
                        help="Use mock EXPLAIN results instead of connecting to DB")
    parser.add_argument("--output", default=None,
                        help="Output file path (default: stdout)")
    parser.add_argument("--timeout", type=int, default=10,
                        help="Per-sql EXPLAIN timeout in seconds")
    parser.add_argument("--db-type", default="mysql", choices=["mysql", "oceanbase"],
                        help="Database type for toolbox prebuilt (default: mysql)")
    parser.add_argument("--schema-file", default="",
                        help="discover_schema.py output JSON for parameter value substitution")
    parser.add_argument("--run-id", default="golden",
                        help="Run identifier embedded in output (default: golden)")
    args = parser.parse_args()

    if args.batch:
        text = args.batch.strip()
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

    results = []
    executed = 0
    failed = 0

    schemas = {}
    if args.schema_file:
        try:
            with open(args.schema_file, encoding="utf-8") as f:
                schemas = json.load(f).get("schemas", {})
        except (FileNotFoundError, json.JSONDecodeError):
            schemas = {}

    mcp = None
    if not args.dry_run:
        db_env = db_client.db_env(args.db_type)
        if db_env:
            try:
                mcp = db_client.ToolboxMcp(args.db_type, db_env)
                mcp.initialize()
            except Exception as exc:
                print(f"WARNING: toolbox unavailable, degrade to static-only: {exc}", file=sys.stderr)
                mcp = None

    for rec in records:
        sql_id = rec.get("sql_id", "UNKNOWN")
        proxy = rec.get("proxy_sql")
        resolved = rec.get("resolved_sql")
        original = rec.get("original_sql")
        executable = proxy or resolved or original
        if not args.dry_run:
            executable = _explain_sql(executable, rec.get("main_table", "UNKNOWN"), schemas)
        if not executable:
            results.append({
                "sql_id": sql_id,
                "executed": False,
                "error": "No SQL available for EXPLAIN",
                "type": None, "key": None, "key_len": None, "rows": None, "extra": None,
                "raw_explain": None,
            })
            failed += 1
            continue

        if args.dry_run:
            mock = _mock_explain(sql_id)
            results.append({
                "sql_id": sql_id,
                "executed": True,
                "type": mock["type"],
                "key": mock["key"],
                "key_len": mock["key_len"],
                "rows": mock["rows"],
                "extra": mock["extra"],
                "raw_explain": json.dumps({"query_block": {"table": {"access_type": mock["type"]}}}),
                "error": None,
            })
            executed += 1
        elif mcp:
            try:
                fields = _run_explain(mcp, executable)
                results.append({
                    "sql_id": sql_id,
                    "executed": True,
                    "type": fields["type"],
                    "key": fields["key"],
                    "key_len": fields["key_len"],
                    "rows": fields["rows"],
                    "extra": fields["extra"],
                    "raw_explain": fields.get("raw_explain"),
                    "error": None,
                })
                executed += 1
            except Exception as exc:
                results.append({
                    "sql_id": sql_id,
                    "executed": False,
                    "error": str(exc),
                    "type": None, "key": None, "key_len": None, "rows": None, "extra": None,
                    "raw_explain": None,
                })
                failed += 1
        else:
            results.append({
                "sql_id": sql_id,
                "executed": False,
                "error": "No database connection configured (set MYSQL_HOST/USER/PASSWORD/DATABASE or use --dry-run)",
                "type": None, "key": None, "key_len": None, "rows": None, "extra": None,
                "raw_explain": None,
            })
            failed += 1

    if mcp:
        mcp.close()

    payload = {
        "run_id": args.run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total": len(results),
        "executed": executed,
        "failed": failed,
        "results": results,
    }

    out = json.dumps(payload, ensure_ascii=False)
    if args.output:
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        with open(args.output, "w") as f:
            f.write(out + "\n")
        print(out)
    else:
        print(out)


if __name__ == "__main__":
    main()
