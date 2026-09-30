#!/usr/bin/env python3
"""Detect Java project defaults for local-coverage-booster."""

import argparse
import json
import os
import subprocess
from pathlib import Path


def run_git_root(cwd: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(cwd),
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except Exception:
        return str(cwd.resolve())


def git_ref_exists(cwd: Path, ref: str) -> bool:
    try:
        subprocess.check_call(
            ["git", "rev-parse", "--verify", "--quiet", ref],
            cwd=str(cwd),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except Exception:
        return False


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
    return "origin/master"


def detect(project_root: Path) -> dict:
    root = project_root.resolve()
    result = {
        "project_root": str(root),
        "build_tool": "unknown",
        "source_root": "src/main/java",
        "test_root": "src/test/java",
        "base_ref": detect_base_ref(root),
        "gate_threshold": 60,
        "local_target_threshold": 68,
        "coverage_command_candidates": [],
        "test_command_candidates": [],
        "jacoco_xml_candidates": [],
        "notes": [],
    }

    if (root / "pom.xml").exists():
        result["build_tool"] = "maven"
        result["coverage_command_candidates"].append(
            "mvn org.jacoco:jacoco-maven-plugin:0.8.12:prepare-agent "
            "test org.jacoco:jacoco-maven-plugin:0.8.12:report"
        )
        result["coverage_command_candidates"].append("mvn test jacoco:report")
        result["test_command_candidates"].append("mvn test")
        result["jacoco_xml_candidates"].append("target/site/jacoco/jacoco.xml")

        modules = []
        for pom in root.glob("*/pom.xml"):
            module = pom.parent.name
            src = pom.parent / "src/main/java"
            if src.exists():
                modules.append(module)
                result["jacoco_xml_candidates"].append(
                    f"{module}/target/site/jacoco/jacoco.xml"
                )
        if modules:
            result["notes"].append(
                "Detected Maven modules: " + ", ".join(sorted(modules))
            )

    elif (root / "build.gradle").exists() or (root / "build.gradle.kts").exists():
        result["build_tool"] = "gradle"
        gradlew = "./gradlew" if (root / "gradlew").exists() else "gradle"
        result["coverage_command_candidates"].append(f"{gradlew} test jacocoTestReport")
        result["test_command_candidates"].append(f"{gradlew} test")
        result["jacoco_xml_candidates"].append(
            "build/reports/jacoco/test/jacocoTestReport.xml"
        )
    else:
        result["notes"].append("No pom.xml or build.gradle found at project root.")

    if not (root / result["source_root"]).exists():
        candidates = list(root.glob("*/src/main/java"))
        if candidates:
            result["source_root"] = str(candidates[0].relative_to(root))
            result["notes"].append(
                "Using first module source root: " + result["source_root"]
            )

    if not (root / result["test_root"]).exists():
        candidates = list(root.glob("*/src/test/java"))
        if candidates:
            result["test_root"] = str(candidates[0].relative_to(root))
            result["notes"].append(
                "Using first module test root: " + result["test_root"]
            )

    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", default="")
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    cwd = Path.cwd()
    project_root = Path(args.project_root) if args.project_root else Path(run_git_root(cwd))
    data = detect(project_root)
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
