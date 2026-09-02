#!/usr/bin/env python3
"""Generate a Markdown before/after coverage report."""

import argparse
import json
from pathlib import Path


def load_json(path: str) -> dict:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def pct(value) -> str:
    if value is None or value == "":
        return "-"
    return f"{float(value):.2f}%"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--before", required=True)
    parser.add_argument("--after", required=True)
    parser.add_argument("--quality", default="")
    parser.add_argument("--test-files", nargs="*", default=[])
    parser.add_argument("--output", default=".coverage-booster/report.md")
    args = parser.parse_args()

    before = load_json(args.before)
    after = load_json(args.after)
    quality = load_json(args.quality)

    lines = []
    lines.append("# Local Coverage Booster Report")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| Metric | Before | After |")
    lines.append("|---|---:|---:|")
    metrics = [
        ("Changed coverable lines", "changed_coverable_lines"),
        ("Changed covered lines", "changed_covered_lines"),
        ("Changed uncovered lines", "changed_uncovered_lines"),
    ]
    for label, key in metrics:
        lines.append(f"| {label} | {before.get(key, '-')} | {after.get(key, '-')} |")
    lines.append(
        "| Local changed-line coverage | {0} | {1} |".format(
            pct(before.get("local_changed_line_coverage")),
            pct(after.get("local_changed_line_coverage")),
        )
    )
    lines.append("")
    target = after.get("threshold", before.get("threshold", ""))
    passed = after.get("passed", False)
    result = "PASS" if passed else "NOT PASSED"
    lines.append(f"Result: {result} local target {target}%")
    lines.append("")

    lines.append("## Changed Test Files")
    lines.append("")
    if args.test_files:
        for path in args.test_files:
            lines.append(f"- `{path}`")
    else:
        lines.append("- None recorded")
    lines.append("")

    lines.append("## Test Quality Check")
    lines.append("")
    if quality:
        lines.append(f"- Passed: `{quality.get('passed')}`")
        lines.append(f"- Errors: `{quality.get('errors', 0)}`")
        lines.append(f"- Warnings: `{quality.get('warnings', 0)}`")
        findings = quality.get("findings", [])
        if findings:
            lines.append("")
            lines.append("| Severity | Rule | File | Message |")
            lines.append("|---|---|---|---|")
            for f in findings:
                lines.append(
                    "| {0} | `{1}` | `{2}` | {3} |".format(
                        f.get("severity", ""),
                        f.get("rule", ""),
                        f.get("file", ""),
                        f.get("message", ""),
                    )
                )
    else:
        lines.append("- No quality check data provided")
    lines.append("")

    lines.append("## Remaining Uncovered Changed Lines")
    lines.append("")
    targets = after.get("targets", [])
    if targets:
        lines.append("| File | Lines | Reason |")
        lines.append("|---|---|---|")
        for target_item in targets:
            file_path = target_item.get("file", "")
            nums = ", ".join(str(n) for n in target_item.get("uncovered_changed_lines", []))
            lines.append(f"| `{file_path}` | {nums} | Not covered after local run |")
    else:
        lines.append("- None")
    lines.append("")

    lines.append("## Recommendation")
    lines.append("")
    if passed:
        lines.append("Local target passed. Safe to push for pipeline validation.")
    else:
        lines.append("Local target did not pass. Review remaining uncovered changed lines before pushing.")
    lines.append("")

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    print(str(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
