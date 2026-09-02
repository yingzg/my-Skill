#!/usr/bin/env python3
"""Phase 0.5: Discover datasource mappings from Java source and config files.

Scans src/main/java for @DS and @MapperScan annotations, plus
application.yml/properties for datasource URLs. Never exits non-zero.

Usage:
    python3 discover_datasource.py
    python3 discover_datasource.py --project-root /path/to/java/project
"""

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path


DS_RE = re.compile(r'@DS\s*\(\s*"([^"]+)"\s*\)')
MAPPER_SCAN_RE = re.compile(
    r'@MapperScan\s*\([^)]*basePackages\s*=\s*\{?\s*([^)}]+)'
)
QUOTED_STRING_RE = re.compile(r'"([^"]+)"')
CONFIG_PREFIX_RE = re.compile(
    r'@ConfigurationProperties\s*\(\s*prefix\s*=\s*"([^"]+)"\s*\)'
)
PACKAGE_RE = re.compile(r'^\s*package\s+([\w.]+)\s*;')


def scan_java_files(project_root: str) -> list[Path]:
    src = Path(project_root) / "src" / "main" / "java"
    if not src.is_dir():
        return []
    return sorted(src.rglob("*.java"))


def scan_config_files(project_root: str) -> list[Path]:
    resources = Path(project_root) / "src" / "main" / "resources"
    if not resources.is_dir():
        return []
    files: list[Path] = []
    for pattern in ["application*.yml", "application*.yaml", "application*.properties"]:
        files.extend(sorted(resources.rglob(pattern)))
    return sorted(files)


def extract_package(filepath: Path) -> str:
    try:
        text = filepath.read_text(encoding="utf-8")
    except Exception:
        return ""
    m = PACKAGE_RE.search(text)
    return m.group(1) if m else ""


def extract_ds_mappings(java_files: list[Path]) -> dict[str, str]:
    mappings: dict[str, str] = {}
    for f in java_files:
        try:
            text = f.read_text(encoding="utf-8")
        except Exception:
            continue
        m = DS_RE.search(text)
        if m:
            pkg = extract_package(f)
            if pkg:
                mappings[pkg] = m.group(1)
    return mappings


def extract_mapperscan_configs(java_files: list[Path]) -> list[dict]:
    configs = []
    for f in java_files:
        try:
            text = f.read_text(encoding="utf-8")
        except Exception:
            continue
        scan_m = MAPPER_SCAN_RE.search(text)
        prefix_m = CONFIG_PREFIX_RE.search(text)
        if not scan_m or not prefix_m:
            continue
        base_packages_str = scan_m.group(1)
        packages = QUOTED_STRING_RE.findall(base_packages_str)
        if not packages:
            continue
        config_prefix = prefix_m.group(1)
        for pkg in packages:
            configs.append({
                "mapper_package": pkg,
                "config_prefix": config_prefix,
            })
    return configs


def read_yaml_urls(files: list[Path]) -> dict[str, tuple[str, str]]:
    result: dict[str, tuple[str, str]] = {}
    for f in files:
        if f.suffix in (".yml", ".yaml"):
            try:
                text = f.read_text(encoding="utf-8")
            except Exception:
                continue
            for ds_name, url in _parse_yaml_urls(text).items():
                if ds_name not in result:
                    result[ds_name] = (url, _parse_url_type(url))
        elif f.suffix == ".properties":
            try:
                text = f.read_text(encoding="utf-8")
            except Exception:
                continue
            for ds_name, url in _parse_properties_urls(text).items():
                if ds_name not in result:
                    result[ds_name] = (url, _parse_url_type(url))
    return result


def _parse_yaml_urls(text: str) -> dict[str, str]:
    urls: dict[str, str] = {}
    lines = text.split("\n")
    stack: list[tuple[int, str]] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        key = stripped.split(":", 1)[0].strip()
        url_m = re.match(r'^\s*url\s*:\s*(.+)$', line)
        if url_m:
            while stack and stack[-1][0] >= indent:
                stack.pop()
            parent_key = stack[-1][1] if stack else ""
            raw_url = url_m.group(1).strip().strip('"').strip("'")
            urls[parent_key] = mask_password(raw_url)
        else:
            while stack and stack[-1][0] >= indent:
                stack.pop()
            stack.append((indent, key))
    return urls


def _parse_properties_urls(text: str) -> dict[str, str]:
    urls: dict[str, str] = {}
    for line in text.split("\n"):
        m = re.match(r'^.+?\.url\s*=\s*(.+)', line.strip())
        if m:
            full_key = line.strip().split(".url")[0]
            ds_name = full_key.split(".")[-1]
            raw_url = m.group(1).strip()
            urls[ds_name] = mask_password(raw_url)
    return urls


def mask_password(url: str) -> str:
    return re.sub(r'://([^:]+):([^@]+)@', r'://\1:***@', url)


def _parse_url_type(url: str) -> str:
    m = re.match(r'jdbc:(\w+):', url)
    return m.group(1) if m else ""


def resolve_mappings(ds_mappings: dict[str, str],
                     mapperscan_configs: list[dict],
                     url_map: dict[str, tuple[str, str]],
                     all_packages: set[str]) -> tuple[list[dict], str, list[str]]:
    mappings: list[dict] = []
    mapped: set[str] = set()

    for pkg, ds_name in ds_mappings.items():
        url, db_type = "", ""
        if ds_name in url_map:
            url, db_type = url_map[ds_name]
        elif pkg.split(".")[-2] in url_map:
            url, db_type = url_map[pkg.split(".")[-2]]
        mappings.append({
            "mapper_package": pkg,
            "datasource_name": ds_name,
            "type": db_type,
            "url": url or "",
        })
        mapped.add(pkg)

    for cfg in mapperscan_configs:
        pkg = cfg["mapper_package"]
        if pkg in mapped:
            continue
        prefix = cfg["config_prefix"]
        ds_name = prefix
        url, db_type = "", ""
        for key, (val, tp) in url_map.items():
            if key == prefix.split(".")[-1]:
                url, db_type, ds_name = val, tp, key
                break
        mappings.append({
            "mapper_package": pkg,
            "datasource_name": ds_name,
            "type": db_type,
            "url": url or "",
        })
        mapped.add(pkg)

    unmapped = sorted(pkg for pkg in all_packages if pkg not in mapped)

    if not mappings:
        return [], "UNKNOWN", sorted(all_packages)
    if unmapped:
        return mappings, "PARTIAL", unmapped
    return mappings, "FOUND", []


def main():
    parser = argparse.ArgumentParser(
        description="Discover datasource mappings from Java project"
    )
    parser.add_argument("--project-root", type=str, default=os.getcwd(),
                        help="Java project root (must contain src/main/java)")
    args = parser.parse_args()

    project_root = os.path.abspath(args.project_root)
    java_files = scan_java_files(project_root)
    config_files = scan_config_files(project_root)

    if not java_files:
        output = {
            "mappings": [],
            "status": "UNKNOWN",
            "unmapped_packages": [],
        }
        json.dump(output, sys.stdout, ensure_ascii=False, indent=2)
        print()
        return

    all_packages = set()
    for f in java_files:
        pkg = extract_package(f)
        if pkg:
            all_packages.add(pkg)

    ds_mappings = extract_ds_mappings(java_files)
    mapperscan_configs = extract_mapperscan_configs(java_files)
    url_map = read_yaml_urls(config_files)

    mappings, status, unmapped = resolve_mappings(
        ds_mappings, mapperscan_configs, url_map, all_packages
    )

    output = {
        "mappings": mappings,
        "status": status,
        "unmapped_packages": unmapped,
    }
    json.dump(output, sys.stdout, ensure_ascii=False, indent=2)
    print()


if __name__ == "__main__":
    main()
