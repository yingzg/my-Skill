#!/usr/bin/env python3
"""Phase 3.5a: Extract main table name from resolved SQL for batching.

Parses FROM clause of each resolved_sql. "Main table" = first table name
after FROM (before JOIN / comma), used to group SQLs for EXPLAIN batches.

Usage:
    python3 extract_tables.py --input '[...]'
    cat resolve-output.jsonl | python3 extract_tables.py
"""

import argparse
import json
import re
import sys

FROM_RE = re.compile(
    r'(?i)(?<!\w)FROM\s+`?(\w+)`?'
)

UPDATE_RE = re.compile(
    r'(?i)(?<!\w)UPDATE\s+`?(\w+)`?'
)

INSERT_RE = re.compile(
    r'(?i)(?<!\w)INSERT\s+(?:INTO\s+)?`?(\w+)`?'
)

SUBQUERY_MARKER = re.compile(r'(?i)(?<!\w)FROM\s*\(')


def _extract_main(sql: str) -> str:
    if SUBQUERY_MARKER.search(sql):
        return "UNKNOWN"

    for pat in (UPDATE_RE, INSERT_RE, FROM_RE):
        m = pat.search(sql)
        if m:
            return m.group(1)
    return "UNKNOWN"


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract main table from resolved SQL")
    parser.add_argument("--input", default=None,
                        help="JSON array string of [{sql_id, resolved_sql}, ...]")
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
        raw = rec.get("resolved_sql", "")
        table = _extract_main(raw)
        print(json.dumps({"sql_id": sql_id, "main_table": table}))


if __name__ == "__main__":
    main()
