#!/usr/bin/env python3
"""Run a coverage/test command and verify a JaCoCo XML report exists."""

import argparse
import hashlib
import subprocess
from pathlib import Path


def tail(text: str, max_lines: int = 80) -> str:
    lines = text.splitlines()
    return "\n".join(lines[-max_lines:])


def resolve_log_path(root: Path, log_arg: str) -> Path:
    preferred = Path(log_arg)
    if not preferred.is_absolute():
        preferred = root / preferred
    try:
        preferred.parent.mkdir(parents=True, exist_ok=True)
        return preferred
    except OSError:
        digest = hashlib.sha1(str(root).encode("utf-8")).hexdigest()[:10]
        fallback_dir = Path("/tmp/local-coverage-booster") / f"{root.name}-{digest}"
        fallback_dir.mkdir(parents=True, exist_ok=True)
        return fallback_dir / preferred.name


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--command", required=True)
    parser.add_argument("--jacoco-xml", default="")
    parser.add_argument("--log", default=".coverage-booster/coverage-command.log")
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    log_path = resolve_log_path(root, args.log)

    proc = subprocess.run(
        args.command,
        cwd=str(root),
        shell=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    log_path.write_text(proc.stdout or "", encoding="utf-8")

    if proc.returncode != 0:
        print(f"Command failed with exit code {proc.returncode}: {args.command}")
        print(f"Log: {log_path}")
        print("--- log tail ---")
        print(tail(proc.stdout or ""))
        return proc.returncode

    if args.jacoco_xml:
        xml_path = root / args.jacoco_xml
        if not xml_path.exists():
            print(f"Command succeeded but JaCoCo XML was not found: {xml_path}")
            print(f"Log: {log_path}")
            return 2
        print(f"JaCoCo XML found: {xml_path}")
    else:
        print("Command succeeded.")

    print(f"Log: {log_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
