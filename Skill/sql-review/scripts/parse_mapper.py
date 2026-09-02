#!/usr/bin/env python3
"""Phase 1: Parse MyBatis Mapper XML files, extract SQL statements.

Usage:
    python3 parse_mapper.py --file path/to/mapper.xml
    python3 parse_mapper.py --files '["a.xml","b.xml"]' [--datasource-map '{"mappings":[...]}']
    python3 parse_mapper.py --files '["a.xml"]' --format ndjson
"""

import argparse
import json
import sys
import os
import xml.etree.ElementTree as ET
from typing import Optional


DYNAMIC_TAGS = frozenset({
    "if", "choose", "when", "otherwise", "foreach",
    "where", "set", "trim", "bind", "include",
})

STATEMENT_TAGS = frozenset({"select", "update", "delete", "insert"})

XMLNS = "http://mybatis.org/dtd/mybatis-3-mapper.dtd"


def _strip_ns(tag: str) -> str:
    """Remove XML namespace from tag name."""
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _extract_dynamic_tags(element: ET.Element) -> list[dict]:
    """Recursively extract dynamic MyBatis tags from an element's children."""
    result = []
    for child in element:
        tag = _strip_ns(child.tag)
        if tag in DYNAMIC_TAGS:
            raw = ET.tostring(child, encoding="unicode").strip()
            result.append({"tag": tag, "raw": raw})
        # Recurse into children (e.g., <choose> contains <when>/<otherwise>)
        result.extend(_extract_dynamic_tags(child))
    return result


def _get_text_children(element: ET.Element) -> list[str]:
    """Get text content including text and child element tags as raw strings."""
    parts = []
    if element.text:
        parts.append(element.text)
    for child in element:
        parts.append(ET.tostring(child, encoding="unicode").strip())
    return parts


def _extract_raw_sql(element: ET.Element) -> str:
    """Extract raw SQL text preserving dynamic tag markup."""
    parts = _get_text_children(element)
    return " ".join(p.strip() for p in parts if p.strip())


def parse_mapper_file(
    file_path: str,
    datasource_name: str = "UNKNOWN",
) -> list[dict]:
    """Parse a single MyBatis Mapper XML file, return list of SqlRecord dicts.

    Returns empty list on parse failure (graceful degradation).
    """
    results = []

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        # Strip XML declaration + DOCTYPE; wrap in synthetic root for multi-<mapper> files
        import re
        content = re.sub(r'<\?xml[^?]*\?>', '', content, count=1)
        content = re.sub(r'<!DOCTYPE[^>]*>', '', content, count=1)
        wrapped = f"<root>{content}</root>"
        tree = ET.ElementTree(ET.fromstring(wrapped))
        root = tree.getroot()
    except ET.ParseError as e:
        print(f"ERROR: XML parse failed in {file_path}: {e}", file=sys.stderr)
        return []
    except FileNotFoundError:
        print(f"ERROR: File not found: {file_path}", file=sys.stderr)
        return []

    def find_mappers(element: ET.Element):
        """Yield (mapper_element, namespace) tuples. Handle root being <mapper> or root containing <mapper> children."""
        tag = _strip_ns(element.tag)
        if tag == "mapper":
            yield (element, element.attrib.get("namespace", "UNKNOWN"))
        else:
            for child in element:
                child_tag = _strip_ns(child.tag)
                if child_tag == "mapper":
                    yield (child, child.attrib.get("namespace", "UNKNOWN"))

    for mapper_elem, namespace in find_mappers(root):
        for stmt_elem in mapper_elem:
            tag = _strip_ns(stmt_elem.tag)
            if tag not in STATEMENT_TAGS:
                continue

            stmt_id = stmt_elem.attrib.get("id", "UNKNOWN")
            raw_sql = _extract_raw_sql(stmt_elem)
            dynamic_tags = _extract_dynamic_tags(stmt_elem)

            # Line number: approximate using sourceline if available
            # xml.etree doesn't expose line numbers reliably, so we
            # enumerate within the file as fallback.
            sql_index = len([r for r in results if r["file"] == file_path])
            sql_id = f"{os.path.basename(file_path)}:{stmt_id}:{sql_index}"

            result = {
                "sql_id": sql_id,
                "mapper_namespace": namespace,
                "method_name": stmt_id,
                "statement_type": tag.upper(),
                "raw_sql": raw_sql,
                "dynamic_tags": dynamic_tags,
                "datasource": datasource_name,
                "file": file_path,
                "line_start": 0,   # can't get from xml.etree reliably
                "line_end": 0,
            }
            results.append(result)

    return results


def resolve_datasource(
    namespace: str,
    datasource_map: list[dict],
) -> str:
    """Match a mapper namespace to a datasource name via prefix matching.

    Example: 'com.example.mapper.order' matches package 'com.example.mapper.order'
    """
    if not datasource_map or not namespace:
        return "UNKNOWN"
    for entry in datasource_map:
        pkg = entry.get("mapper_package", "")
        if pkg and namespace.startswith(pkg):
            return entry.get("datasource_name", "UNKNOWN")
    return "UNKNOWN"


def main():
    parser = argparse.ArgumentParser(
        description="Parse MyBatis Mapper XML files and extract SQL statements"
    )
    parser.add_argument(
        "--file", type=str,
        help="Single Mapper XML file path (convenience mode)"
    )
    parser.add_argument(
        "--files", type=str,
        help='JSON array of Mapper XML file paths, e.g. \'["a.xml","b.xml"]\''
    )
    parser.add_argument(
        "--datasource-map", type=str,
        help='JSON string from discover_datasource.py: {"mappings":[...],"status":"..."}'
    )
    parser.add_argument(
        "--format", choices=["json", "ndjson"], default="json",
        help="Output format: json (JSON array) or ndjson (newline-delimited JSON)"
    )
    parser.add_argument(
        "--strict", action="store_true",
        help="Exit 1 if any file fails to parse (default: skip on failure)"
    )
    args = parser.parse_args()

    if args.file:
        files = [args.file]
    elif args.files:
        try:
            files = json.loads(args.files)
        except json.JSONDecodeError as e:
            print(f"ERROR: Invalid --files JSON: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        print("ERROR: Must specify --file or --files", file=sys.stderr)
        sys.exit(1)

    datasource_map = []
    if args.datasource_map:
        try:
            ds_data = json.loads(args.datasource_map)
            datasource_map = ds_data.get("mappings", [])
        except json.JSONDecodeError as e:
            print(f"ERROR: Invalid --datasource-map JSON: {e}", file=sys.stderr)
            sys.exit(1)

    all_results = []
    parse_errors = 0

    for file_path in files:
        results = parse_mapper_file(file_path)
        if not results:
            parse_errors += 1
            continue

        if datasource_map:
            namespaces_seen = set()
            for r in results:
                ns = r["mapper_namespace"]
                if ns not in namespaces_seen:
                    namespaces_seen.add(ns)
                    ds = resolve_datasource(ns, datasource_map)
                    if ds != "UNKNOWN":
                        for r2 in results:
                            if r2["mapper_namespace"] == ns:
                                r2["datasource"] = ds

        all_results.extend(results)

    if not all_results:
        print(f"ERROR: All {len(files)} file(s) failed to parse", file=sys.stderr)
        sys.exit(2 if args.strict else 1)

    if parse_errors > 0:
        print(f"WARNING: {parse_errors}/{len(files)} file(s) failed to parse", file=sys.stderr)

    if args.format == "ndjson":
        for r in all_results:
            print(json.dumps(r, ensure_ascii=False))
    else:
        print(json.dumps(all_results, ensure_ascii=False, indent=2))

    if args.strict and parse_errors > 0:
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
