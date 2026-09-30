#!/usr/bin/env python3
"""Phase 2: Trace call chains from Mapper methods back to Controller entry points.

Grep-based (no AST) caller discovery with recursive chain building.
Filters callers by checking class references to avoid false-positive method-name matches.
Always exits 0.

Usage:
    python3 trace_callchain.py --methods '["com.example.mapper.OrderMapper.findById"]'
    python3 trace_callchain.py --methods '["..."]' --project-root . --project-src src/main/java
"""

import argparse
import json
import os
import re
import sys
from functools import lru_cache
from pathlib import Path

ANNOTATION_RE = re.compile(r'@(?:Rest)?Controller\b|@RequestMapping\b')
CLASS_RE = re.compile(r'\b(?:class|interface)\s+(\w+)')
IMPORT_RE = re.compile(r'^\s*import\s+([\w.]+)\s*;', re.MULTILINE)
PACKAGE_RE = re.compile(r'^\s*package\s+([\w.]+)\s*;')
METHOD_DEF_RE = re.compile(
    r'(?:public|private|protected)\s+(?:static\s+)?(?:\w+(?:<[^>]+>)?\s+)?'
    r'(\w+)\s*\('
)

MAX_METHODS = 500
SKIPPABLE = frozenset({
    "if", "for", "while", "switch", "catch", "synchronized",
    "return", "throw", "new", "class", "interface",
})


@lru_cache(maxsize=None)
def _read_text(filepath: str) -> str:
    return Path(filepath).read_text(encoding="utf-8")


def build_index(src_dir: Path) -> dict[str, Path]:
    index: dict[str, Path] = {}
    for java_file in src_dir.rglob("*.java"):
        try:
            text = _read_text(str(java_file))
        except Exception:
            continue
        pkg_m = PACKAGE_RE.search(text)
        if not pkg_m:
            continue
        pkg = pkg_m.group(1)
        for cls_m in CLASS_RE.finditer(text):
            cls_name = cls_m.group(1)
            index[f"{pkg}.{cls_name}"] = java_file
    return index


def is_controller(filepath: Path) -> bool:
    try:
        text = _read_text(str(filepath))
    except Exception:
        return False
    return bool(ANNOTATION_RE.search(text))


def _find_enclosing(lines: list[str], line_no: int) -> str:
    for i in range(line_no - 1, -1, -1):
        m = METHOD_DEF_RE.search(lines[i])
        if m:
            name = m.group(1)
            if not name[0].isupper() and name not in SKIPPABLE:
                return name
    return ""


def _file_references_any(text: str, refs: set[str]) -> bool:
    for ref in refs:
        if ref in text:
            return True
    return False


def _imports_by_short(text: str) -> dict[str, str]:
    imports = {}
    for match in IMPORT_RE.finditer(text):
        fqn = match.group(1)
        imports[fqn.rsplit(".", 1)[-1]] = fqn
    return imports


def _strip_type_name(raw: str) -> str:
    return re.sub(r'<.*?>', '', raw).strip().split()[-1].strip()


def _implemented_type_refs(target_cls_fqn: str, index: dict[str, Path]) -> set[str]:
    filepath = index.get(target_cls_fqn)
    if not filepath:
        return set()

    try:
        text = _read_text(str(filepath))
    except Exception:
        return set()

    short_name = target_cls_fqn.rsplit(".", 1)[-1]
    match = re.search(rf'\bclass\s+{re.escape(short_name)}\b[^\{{]*\bimplements\s+([^\{{]+)', text)
    if not match:
        return set()

    pkg_match = PACKAGE_RE.search(text)
    package = pkg_match.group(1) if pkg_match else ""
    imports = _imports_by_short(text)
    refs = set()

    for raw_name in match.group(1).split(","):
        name = _strip_type_name(raw_name)
        if not name:
            continue
        refs.add(name)
        if "." in name:
            refs.add(name)
        elif name in imports:
            refs.add(imports[name])
        elif package:
            refs.add(f"{package}.{name}")

    return refs


def find_callers_for(target_fqn: str, index: dict[str, Path]) -> list[dict]:
    parts = target_fqn.rsplit(".", 1)
    if len(parts) != 2:
        return []
    target_cls_fqn, method_name = parts
    target_short = target_cls_fqn.rsplit(".", 1)[-1]
    reference_names = {target_cls_fqn, target_short} | _implemented_type_refs(target_cls_fqn, index)

    results = []
    for candidate_fqn, filepath in index.items():
        if candidate_fqn == target_cls_fqn:
            continue
        try:
            text = _read_text(str(filepath))
        except Exception:
            continue

        if not _file_references_any(text, reference_names):
            continue

        if method_name not in text:
            continue

        lines = text.split("\n")
        for line_no, line in enumerate(lines, 1):
            method_def = METHOD_DEF_RE.search(line)
            if method_def and method_def.group(1) == method_name:
                continue
            has_call = (f".{method_name}(" in line or
                        f" {method_name}(" in line or
                        f"\t{method_name}(" in line)
            if not has_call:
                continue

            enclosing = _find_enclosing(lines, line_no)
            if enclosing:
                results.append({
                    "class": candidate_fqn,
                    "method": enclosing,
                    "line": line_no,
                })

    return results


def trace_method(target_fqn: str, index: dict[str, Path],
                 visited: set[str], depth: int = 0) -> tuple[list[dict], bool]:
    if depth > 10:
        return [], False

    parts = target_fqn.rsplit(".", 1)
    if len(parts) != 2:
        return [], False

    visited.add(target_fqn)

    callers = find_callers_for(target_fqn, index)

    best_chain: list[dict] = []
    best_complete = False

    for caller in callers:
        caller_fqn = f"{caller['class']}.{caller['method']}"
        if caller_fqn in visited:
            continue

        cls_file = index.get(caller["class"])
        if cls_file and is_controller(cls_file):
            if not best_complete:
                best_chain = [caller]
                best_complete = True
            continue

        sub_chain, found_ctrl = trace_method(caller_fqn, index, visited, depth + 1)
        candidate = sub_chain + [caller]
        if found_ctrl:
            if not best_complete or len(candidate) > len(best_chain):
                best_chain = candidate
                best_complete = True
        elif not best_complete and len(candidate) > len(best_chain):
            best_chain = candidate

    return best_chain, best_complete


def main():
    parser = argparse.ArgumentParser(
        description="Trace call chains from Mapper methods to Controllers"
    )
    parser.add_argument("--methods", type=str, required=True,
                        help='JSON array: \'["com.example.mapper.OrderMapper.findById"]\'')
    parser.add_argument("--project-root", type=str, default=os.getcwd(),
                        help="Project root directory")
    parser.add_argument("--project-src", type=str, default="src/main/java",
                        help="Java source relative to project-root")
    args = parser.parse_args()

    try:
        methods = json.loads(args.methods)
    except json.JSONDecodeError:
        print("fatal: --methods is not valid JSON", file=sys.stderr)
        sys.exit(1)

    if not isinstance(methods, list):
        print("fatal: --methods must be a JSON array", file=sys.stderr)
        sys.exit(1)

    if len(methods) > MAX_METHODS:
        print(f"fatal: too many methods ({len(methods)}), max {MAX_METHODS}",
              file=sys.stderr)
        sys.exit(1)

    src_dir = Path(args.project_root) / args.project_src
    if not src_dir.is_dir():
        json.dump({"chains": []}, sys.stdout, ensure_ascii=False, indent=2)
        print()
        return

    index = build_index(src_dir)

    chains = []
    for method_fqn in methods:
        visited = set()
        call_chain, complete = trace_method(method_fqn, index, visited)
        chains.append({
            "method": method_fqn,
            "call_chain": call_chain,
            "complete": complete,
        })

    json.dump({"chains": chains}, sys.stdout, ensure_ascii=False, indent=2)
    print()


if __name__ == "__main__":
    main()
