#!/usr/bin/env python3
"""Heuristic quality checks for newly added JUnit/Mockito tests."""

import argparse
import json
import re
import subprocess
from pathlib import Path


ASSERT_RE = re.compile(r"\b(assert\w+)\s*\(")
VERIFY_RE = re.compile(r"\bverify\s*\(")
WEAK_ASSERT_TRUE_RE = re.compile(r"\bassertTrue\s*\(\s*true\s*\)")
ASSERT_NOT_NULL_RE = re.compile(r"\bassertNotNull\s*\(")
PRIVATE_REFLECTION_RE = re.compile(
    r"(getDeclaredMethod|setAccessible\s*\(\s*true\s*\)|ReflectionTestUtils)"
)
VERIFY_ANY_RE = re.compile(r"\bverify\s*\([^;]+;\s*", re.DOTALL)


def strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    text = re.sub(r"//.*", "", text)
    return text


def check_file(path: Path) -> list[dict]:
    findings = []
    text = strip_comments(path.read_text(encoding="utf-8", errors="replace"))

    if WEAK_ASSERT_TRUE_RE.search(text):
        findings.append({
            "file": str(path),
            "severity": "ERROR",
            "rule": "no-assert-true",
            "message": "assertTrue(true) is pseudo-coverage and is forbidden.",
        })

    if PRIVATE_REFLECTION_RE.search(text):
        findings.append({
            "file": str(path),
            "severity": "ERROR",
            "rule": "no-private-reflection",
            "message": "Do not directly test private methods via reflection.",
        })

    asserts = ASSERT_RE.findall(text)
    verify_count = len(VERIFY_RE.findall(text))
    assert_not_null_count = len(ASSERT_NOT_NULL_RE.findall(text))

    if not asserts and verify_count == 0:
        findings.append({
            "file": str(path),
            "severity": "ERROR",
            "rule": "needs-observable-assertion",
            "message": "Test file has no assert* or verify call.",
        })

    if asserts and len(asserts) == assert_not_null_count:
        findings.append({
            "file": str(path),
            "severity": "ERROR",
            "rule": "not-null-only",
            "message": "assertNotNull cannot be the only assertion style.",
        })

    # Heuristic: if any() is used in verification, require argThat or ArgumentCaptor somewhere.
    if "verify(" in text and "any()" in text and "argThat(" not in text and "ArgumentCaptor" not in text:
        findings.append({
            "file": str(path),
            "severity": "WARNING",
            "rule": "verify-precise-arguments",
            "message": "verify(... any()) should be paired with argThat or ArgumentCaptor for key parameters.",
        })

    return findings


def git_changed_source_files(project_root: Path, source_root: str) -> list[str]:
    try:
        out = subprocess.check_output(
            ["git", "status", "--porcelain", "--", source_root],
            cwd=str(project_root),
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except Exception:
        return []
    result = []
    for line in out.splitlines():
        if len(line) > 3:
            result.append(line[3:].strip())
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--source-root", default="src/main/java")
    parser.add_argument("--test-files", nargs="*", default=[])
    parser.add_argument("--output", default="")
    parser.add_argument("--warn-source-changes", action="store_true")
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    findings = []
    for item in args.test_files:
        path = Path(item)
        if not path.is_absolute():
            path = root / path
        if path.exists() and path.is_file():
            findings.extend(check_file(path))
        else:
            findings.append({
                "file": str(path),
                "severity": "ERROR",
                "rule": "test-file-not-found",
                "message": "Test file does not exist.",
            })

    if args.warn_source_changes:
        changed = git_changed_source_files(root, args.source_root)
        if changed:
            findings.append({
                "file": args.source_root,
                "severity": "WARNING",
                "rule": "source-root-has-changes",
                "message": "Source root has changes. Verify the Skill did not modify business code.",
                "changed_files": changed,
            })

    error_count = sum(1 for f in findings if f["severity"] == "ERROR")
    warning_count = sum(1 for f in findings if f["severity"] == "WARNING")
    result = {
        "passed": error_count == 0,
        "errors": error_count,
        "warnings": warning_count,
        "findings": findings,
    }
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if error_count == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
