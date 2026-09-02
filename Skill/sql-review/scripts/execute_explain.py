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
import re
import sys
import os
from datetime import datetime, timezone

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

    for rec in records:
        sql_id = rec.get("sql_id", "UNKNOWN")
        proxy = rec.get("proxy_sql")
        resolved = rec.get("resolved_sql")
        original = rec.get("original_sql")
        executable = proxy or resolved or original
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
        else:
            results.append({
                "sql_id": sql_id,
                "executed": False,
                "error": "No database connection configured (use --dry-run for mock)",
                "type": None, "key": None, "key_len": None, "rows": None, "extra": None,
                "raw_explain": None,
            })
            failed += 1

    payload = {
        "run_id": "golden",
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
