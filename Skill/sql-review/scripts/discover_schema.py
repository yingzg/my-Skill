#!/usr/bin/env python3
"""Phase 3.5c: Discover table schema (columns / primary key / indexes) from DDL.

Reads a list of table names, runs SHOW CREATE TABLE against the database via
the toolbox MCP, and parses each DDL into column types, primary key, and index
definitions. This feeds schema-aware static rules and explain-sql generation.

Usage:
    echo '["crm_customer","crm_supplier"]' | python3 discover_schema.py --db-type mysql
"""

import argparse
import json
import re
import sys

import db_client

COLUMN_TYPE_RE = re.compile(
    r'`(\w+)`\s+(bigint|mediumint|smallint|tinyint|int|longtext|mediumtext|tinytext|text|'
    r'varchar|char|datetime|timestamp|date|time|year|decimal|double|float|'
    r'longblob|mediumblob|tinyblob|blob|bit|json|enum|set)\b'
)
PRIMARY_KEY_RE = re.compile(r'PRIMARY KEY\s*\(([^)]+)\)')
INDEX_RE = re.compile(r'(?:UNIQUE\s+)?KEY\s+`(\w+)`\s*\(([^)]+)\)')


def parse_create_table(ddl: str) -> dict:
    columns = {}
    for match in COLUMN_TYPE_RE.finditer(ddl):
        columns[match.group(1)] = match.group(2)

    primary_key = None
    primary_keys = []
    match = PRIMARY_KEY_RE.search(ddl)
    if match:
        primary_keys = re.findall(r'`(\w+)`', match.group(1))
        if primary_keys:
            primary_key = primary_keys[0]

    indexes = {}
    for match in INDEX_RE.finditer(ddl):
        indexes[match.group(1)] = re.findall(r'`(\w+)`', match.group(2))

    return {"columns": columns, "primary_key": primary_key,
            "primary_keys": primary_keys, "indexes": indexes}


def main() -> None:
    parser = argparse.ArgumentParser(description="Discover table schema from DDL")
    parser.add_argument("--db-type", default="mysql", choices=["mysql", "oceanbase"])
    args = parser.parse_args()

    text = sys.stdin.read().strip()
    if not text:
        return
    try:
        tables = json.loads(text)
    except json.JSONDecodeError:
        tables = [line.strip() for line in text.splitlines() if line.strip()]
    if not isinstance(tables, list):
        tables = [tables]

    db_env = db_client.db_env(args.db_type)
    if not db_env:
        print(json.dumps({"schemas": {}, "error": "db credentials not configured"}, ensure_ascii=False))
        return

    schemas = {}
    mcp = db_client.ToolboxMcp(args.db_type, db_env)
    try:
        mcp.initialize()
        for table in tables:
            if not table or table == "UNKNOWN":
                continue
            try:
                text = mcp.execute_sql(f"SHOW CREATE TABLE `{table}`")
                data = json.loads(text)
                ddl = data.get("Create Table", "")
                if ddl:
                    schemas[table] = parse_create_table(ddl)
            except Exception as exc:
                print(f"WARNING: schema for {table} failed: {exc}", file=sys.stderr)
    finally:
        mcp.close()

    print(json.dumps({"schemas": schemas}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
