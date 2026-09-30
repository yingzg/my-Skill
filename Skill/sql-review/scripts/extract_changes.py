#!/usr/bin/env python3
"""Phase 0: Extract changed MyBatis Mapper XML files from git diff.

Usage:
    python3 extract_changes.py --base origin/master
    python3 extract_changes.py --base origin/master --pattern '**/*Mapper.xml' --repo /path/to/repo
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path


def run_git(args: list[str], repo: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git"] + args,
        capture_output=True, text=True, cwd=repo
    )


def is_git_repo(repo: str) -> bool:
    result = run_git(["rev-parse", "--git-dir"], repo)
    return result.returncode == 0


def branch_exists(base: str, repo: str) -> bool:
    result = run_git(["rev-parse", "--verify", base], repo)
    return result.returncode == 0


def glob_match(path: str, pattern: str) -> bool:
    p = Path(path)
    # PurePath.match() uses fnmatch rules — compatible with shell globs
    return p.match(pattern)


def _changed_statements(repo: str, filepath: str, base: str) -> list[str]:
    diff = run_git(["diff", "--unified=0", f"{base}...HEAD", "--", filepath], repo)
    if diff.returncode != 0:
        return []
    changed_lines = set()
    for line in diff.stdout.split("\n"):
        if not line.startswith("@@"):
            continue
        match = re.search(r"\+(\d+)(?:,(\d+))?", line)
        if match:
            start = int(match.group(1))
            count = int(match.group(2)) if match.group(2) else 1
            changed_lines.update(range(start, start + count))
    if not changed_lines:
        return []

    show = run_git(["show", f"HEAD:{filepath}"], repo)
    if show.returncode != 0:
        return []
    lines = show.stdout.split("\n")

    statements = set()
    for line_no in changed_lines:
        if line_no < 1 or line_no > len(lines):
            continue
        for i in range(line_no, 0, -1):
            match = re.search(
                r'<(?:select|update|delete|insert)\b[^>]*\bid\s*=\s*"([^"]+)"',
                lines[i - 1],
            )
            if match:
                statements.add(match.group(1))
                break
    return sorted(statements)


def main():
    parser = argparse.ArgumentParser(
        description="Extract changed MyBatis Mapper XML files from git diff"
    )
    parser.add_argument("--base", type=str, required=True,
                        help="Base branch for git diff (e.g. origin/master)")
    parser.add_argument("--pattern", type=str, default="**/*Mapper.xml",
                        help="Glob pattern to filter file paths")
    parser.add_argument("--repo", type=str, default=os.getcwd(),
                        help="Path to git repository")
    args = parser.parse_args()

    repo = os.path.abspath(args.repo)

    if not is_git_repo(repo):
        print(f"fatal: not a git repository: {repo}", file=sys.stderr)
        sys.exit(1)

    if not branch_exists(args.base, repo):
        print(f"fatal: branch '{args.base}' not found", file=sys.stderr)
        sys.exit(1)

    diff_result = run_git(
        ["diff", "--name-status", "--diff-filter=AM", f"{args.base}...HEAD"],
        repo
    )

    if diff_result.returncode != 0:
        print(diff_result.stderr, file=sys.stderr)
        sys.exit(2)

    head_result = run_git(["rev-parse", "HEAD"], repo)
    if head_result.returncode != 0:
        print(head_result.stderr, file=sys.stderr)
        sys.exit(2)
    head_sha = head_result.stdout.strip()

    files = []
    for line in diff_result.stdout.strip().split("\n"):
        if not line:
            continue
        parts = line.split("\t", 1)
        if len(parts) != 2:
            continue
        status, filepath = parts
        if glob_match(filepath, args.pattern):
            files.append({
                "path": filepath,
                "status": status,
                "changed_statements": _changed_statements(repo, filepath, args.base),
            })

    output = {
        "files": files,
        "total_count": len(files),
        "base_ref": args.base,
        "head_sha": head_sha,
    }

    json.dump(output, sys.stdout, ensure_ascii=False, indent=2)
    print()


if __name__ == "__main__":
    main()
