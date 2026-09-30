#!/usr/bin/env python3
"""Extract added/modified Java line numbers from git diff."""

import argparse
import fnmatch
import json
import re
import subprocess
from pathlib import Path


DEFAULT_EXCLUDES = [
    "**/dto/**",
    "**/vo/**",
    "**/bo/**",
    "**/entity/**",
    "**/config/**",
    "**/constant/**",
    "**/generated/**",
    "**/*Mapper.java",
]


class DiffError(RuntimeError):
    pass


def normalize(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")


def is_excluded(path: str, excludes: list[str]) -> bool:
    p = normalize(path)
    return any(fnmatch.fnmatch(p, pat) for pat in excludes)


def run_git(project_root: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(project_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def git_ref_exists(project_root: Path, ref: str) -> bool:
    proc = run_git(project_root, ["rev-parse", "--verify", "--quiet", ref])
    return proc.returncode == 0


def detect_base_ref(project_root: Path) -> str:
    candidates = [
        "master",
        "main",
        "origin/master",
        "origin/main",
        "gitlab/master",
        "gitlab/main",
        "develop",
        "HEAD~1",
    ]
    for ref in candidates:
        if git_ref_exists(project_root, ref):
            return ref
    raise DiffError(
        "Cannot auto-detect a base ref. Configure base_ref explicitly, "
        "for example main, origin/main, gitlab/master, or HEAD~1."
    )


def run_diff(base_ref: str, project_root: Path) -> tuple[str, str]:
    if base_ref == "auto":
        base_ref = detect_base_ref(project_root)

    merge_base = run_git(project_root, ["merge-base", base_ref, "HEAD"])
    diff_base = merge_base.stdout.strip() if merge_base.returncode == 0 else base_ref

    # Compare the working tree to the merge-base so committed, staged, and unstaged
    # Java changes are all included in the pre-push coverage calculation.
    first = run_git(project_root, ["diff", "-U0", diff_base, "--", ":(glob)**/*.java"])
    if first.returncode == 0:
        return first.stdout, base_ref

    message = [
        f"Cannot calculate git diff from base_ref={base_ref!r}.",
        f"merge-base stderr: {merge_base.stderr.strip()}",
        f"diff stderr: {first.stderr.strip()}",
        "Check whether the configured base_ref exists locally.",
    ]
    raise DiffError("\n".join(line for line in message if line))


def parse_diff(diff_text: str, source_root: str, excludes: list[str]) -> dict:
    files: dict[str, set[int]] = {}
    current_file = ""
    new_line = None

    hunk_re = re.compile(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")

    for raw in diff_text.splitlines():
        if raw.startswith("+++ "):
            path = raw[4:].strip()
            if path == "/dev/null":
                current_file = ""
                continue
            if path.startswith("b/"):
                path = path[2:]
            path = normalize(path)
            if not path.endswith(".java"):
                current_file = ""
            elif source_root and source_root not in path:
                current_file = ""
            elif is_excluded(path, excludes):
                current_file = ""
            else:
                current_file = path
                files.setdefault(current_file, set())
            continue

        m = hunk_re.match(raw)
        if m:
            new_line = int(m.group(1))
            continue

        if not current_file or new_line is None:
            continue

        if raw.startswith("+") and not raw.startswith("+++"):
            content = raw[1:].strip()
            if content and content not in ("{", "}", ");"):
                files[current_file].add(new_line)
            new_line += 1
        elif raw.startswith("-") and not raw.startswith("---"):
            # Removed line: no new-file line number advancement.
            continue
        else:
            # Context line. With -U0 this is rare but still valid.
            new_line += 1

    return {
        "files": [
            {"path": path, "changed_lines": sorted(lines)}
            for path, lines in sorted(files.items())
            if lines
        ]
    }


def get_untracked_java_files(project_root: Path) -> list[str]:
    proc = run_git(project_root, ["ls-files", "--others", "--exclude-standard"])
    if proc.returncode != 0:
        return []
    return [
        normalize(line.strip())
        for line in proc.stdout.splitlines()
        if line.strip().endswith(".java")
    ]


def collect_untracked_changes(
    project_root: Path, source_root: str, excludes: list[str]
) -> list[dict]:
    # git diff never includes untracked files, so enumerate them separately.
    entries = []
    for path in get_untracked_java_files(project_root):
        if source_root and source_root not in path:
            continue
        if is_excluded(path, excludes):
            continue
        full = project_root / path
        try:
            content = full.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        line_count = len(content.splitlines())
        if line_count == 0:
            continue
        entries.append({"path": path, "changed_lines": list(range(1, line_count + 1))})
    return entries


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-ref", default="auto")
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--source-root", default="src/main/java")
    parser.add_argument("--exclude", action="append", default=[])
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    excludes = DEFAULT_EXCLUDES + args.exclude
    try:
        diff_text, resolved_base_ref = run_diff(args.base_ref, project_root)
    except DiffError as exc:
        raise SystemExit(str(exc)) from exc
    result = parse_diff(diff_text, normalize(args.source_root), excludes)
    result["files"].extend(
        collect_untracked_changes(project_root, normalize(args.source_root), excludes)
    )
    result["files"].sort(key=lambda f: f["path"])
    result["base_ref"] = resolved_base_ref
    result["project_root"] = str(project_root)
    result["changed_files"] = len(result["files"])
    result["changed_lines"] = sum(len(f["changed_lines"]) for f in result["files"])

    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
