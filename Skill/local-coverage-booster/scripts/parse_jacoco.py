#!/usr/bin/env python3
"""Parse JaCoCo XML into source-file line coverage JSON."""

import argparse
import json
import xml.etree.ElementTree as ET
from pathlib import Path


def normalize(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")


def parse_jacoco(xml_path: Path, source_root: str) -> dict:
    tree = ET.parse(str(xml_path))
    root = tree.getroot()
    source_root = normalize(source_root)
    files = {}

    for package in root.findall(".//package"):
        package_name = normalize(package.get("name", ""))
        for sourcefile in package.findall("sourcefile"):
            name = sourcefile.get("name", "")
            if not name:
                continue
            rel_path = normalize(f"{source_root}/{package_name}/{name}")
            line_map = {}
            for line in sourcefile.findall("line"):
                nr = int(line.get("nr", "0"))
                mi = int(line.get("mi", "0"))
                ci = int(line.get("ci", "0"))
                mb = int(line.get("mb", "0"))
                cb = int(line.get("cb", "0"))
                coverable = (mi + ci + mb + cb) > 0
                covered = ci > 0 or cb > 0
                line_map[str(nr)] = {
                    "covered": covered,
                    "coverable": coverable,
                    "mi": mi,
                    "ci": ci,
                    "mb": mb,
                    "cb": cb,
                }
            files[rel_path] = line_map

    return {
        "jacoco_xml": str(xml_path),
        "source_root": source_root,
        "files": files,
    }


def summary(result: dict) -> dict:
    files = result["files"]
    coverable = 0
    covered = 0
    for line_map in files.values():
        for line in line_map.values():
            if line.get("coverable"):
                coverable += 1
                if line.get("covered"):
                    covered += 1
    coverage = 100.0 if coverable == 0 else round(covered * 100.0 / coverable, 2)
    return {
        "jacoco_xml": result["jacoco_xml"],
        "source_root": result["source_root"],
        "files": len(files),
        "coverable_lines": coverable,
        "covered_lines": covered,
        "line_coverage": coverage,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--xml", required=True)
    parser.add_argument("--source-root", default="src/main/java")
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    xml_path = Path(args.xml)
    if not xml_path.exists():
        raise SystemExit(f"JaCoCo XML not found: {xml_path}")

    result = parse_jacoco(xml_path, args.source_root)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
        print(json.dumps(summary(result), ensure_ascii=False, indent=2))
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
