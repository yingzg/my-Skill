#!/usr/bin/env python3
"""Compute changed-line coverage gaps from changed lines and JaCoCo line data."""

import argparse
import json
from pathlib import Path


def normalize(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")


def find_coverage_key(path: str, coverage_files: dict) -> str:
    path = normalize(path)
    if path in coverage_files:
        return path
    for key in coverage_files:
        nk = normalize(key)
        if nk.endswith(path) or path.endswith(nk):
            return key
    # Match by package suffix after src/main/java.
    marker = "src/main/java/"
    if marker in path:
        suffix = path.split(marker, 1)[1]
        for key in coverage_files:
            if normalize(key).endswith(suffix):
                return key
    return ""


def compute_gap(changed: dict, jacoco: dict, threshold: float) -> dict:
    coverage_files = jacoco.get("files", {})
    targets = []
    changed_coverable = 0
    changed_covered = 0
    changed_uncovered = 0

    for file_item in changed.get("files", []):
        path = normalize(file_item.get("path", ""))
        coverage_key = find_coverage_key(path, coverage_files)
        if not coverage_key:
            continue
        line_map = coverage_files.get(coverage_key, {})
        file_coverable = []
        file_covered = []
        file_uncovered = []

        for line_no in file_item.get("changed_lines", []):
            data = line_map.get(str(line_no))
            if not data or not data.get("coverable", False):
                continue
            file_coverable.append(line_no)
            changed_coverable += 1
            if data.get("covered", False):
                file_covered.append(line_no)
                changed_covered += 1
            else:
                file_uncovered.append(line_no)
                changed_uncovered += 1

        if file_uncovered:
            priority = "HIGH" if len(file_uncovered) >= 8 else "MEDIUM"
            targets.append({
                "file": path,
                "coverage_key": coverage_key,
                "coverable_changed_lines": file_coverable,
                "covered_changed_lines": file_covered,
                "uncovered_changed_lines": file_uncovered,
                "uncovered_count": len(file_uncovered),
                "priority": priority,
            })

    coverage = 100.0
    if changed_coverable:
        coverage = round(changed_covered * 100.0 / changed_coverable, 2)

    targets.sort(key=lambda item: item["uncovered_count"], reverse=True)
    return {
        "base_ref": changed.get("base_ref", ""),
        "threshold": threshold,
        "changed_coverable_lines": changed_coverable,
        "changed_covered_lines": changed_covered,
        "changed_uncovered_lines": changed_uncovered,
        "local_changed_line_coverage": coverage,
        "passed": coverage >= threshold,
        "targets": targets,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--changed", required=True)
    parser.add_argument("--jacoco", required=True)
    parser.add_argument("--threshold", type=float, default=68.0)
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    changed = json.loads(Path(args.changed).read_text(encoding="utf-8"))
    jacoco = json.loads(Path(args.jacoco).read_text(encoding="utf-8"))
    result = compute_gap(changed, jacoco, args.threshold)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
