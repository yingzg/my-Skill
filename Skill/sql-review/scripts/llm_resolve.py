#!/usr/bin/env python3
"""Phase 3: LLM-assisted dynamic SQL resolution (real-path restoration).

Reads the resolve-mode output of resolve_dynamic_sql.py (which keeps <if>/<choose>
tags and marks needs_llm), asks an LLM to judge which dynamic conditions are
likely active, and produces the final resolved SQL.

needs_llm SQL is resolved in batches (10/batch) to bound LLM round-trips. SQL
that does not need the LLM is finalized deterministically (optimistic). When
the LLM is unavailable, needs_llm SQL falls back to optimistic finalize.

Usage:
    resolve_dynamic_sql.py --mode resolve --skip-finalize ... | \
        python3 llm_resolve.py --trace-file phase2_trace.json
"""

import argparse
import json
import re
import sys

import llm_client
from resolve_dynamic_sql import finalize_sql

BATCH_SIZE = 10

SYSTEM_PROMPT = (
    "你是 MyBatis 动态 SQL 专家。给定多条含 <if>/<choose> 动态标签的 SQL 和各自的调用链上下文，"
    "判断每条 SQL 的动态条件激活状态，输出最终实际执行的 SQL。\n\n"
    "规则：\n"
    "1. 输出纯 SQL（不含 <if>/<choose>/<when>/<otherwise>/<foreach> 标签）\n"
    "2. <if test=\"xxx != null\">：参数通常有值则保留条件体，否则删除整个 if 片段\n"
    "3. <choose>：只保留最可能命中的 <when> 或 <otherwise> 分支\n"
    "4. 不确定时保守处理（保留条件，避免漏检风险）\n"
    "5. 严格输出 JSON 数组，每个元素格式：{\"sql_id\":\"...\",\"resolved_sql\":\"...\"}，"
    "不要输出任何解释或 markdown 代码块"
)


def build_chain_map(trace_file: str) -> dict[str, list[dict]]:
    with open(trace_file, encoding="utf-8") as f:
        trace = json.load(f)
    chain_map = {}
    for chain in trace.get("chains", []):
        method = chain.get("method", "")
        short = method.rsplit(".", 1)[-1] if "." in method else method
        chain_map[short] = chain.get("call_chain", [])
    return chain_map


def format_chain(call_chain: list[dict]) -> str:
    if not call_chain:
        return "（调用链不可用）"
    return " → ".join(f"{c.get('class', '')}.{c.get('method', '')}" for c in call_chain)


def build_user_prompt(items: list[dict], chain_map: dict[str, list[dict]]) -> str:
    parts = ["以下动态 SQL 需要判断条件激活状态：", ""]
    for i, item in enumerate(items, 1):
        sql_id = item.get("sql_id", "?")
        method_short = sql_id.rsplit(":", 2)[-2] if ":" in sql_id else ""
        chain = chain_map.get(method_short, [])
        parts.append(f"【SQL {i}】")
        parts.append(f"sql_id: {sql_id}")
        parts.append(f"动态 SQL: {item.get('resolved_sql', '')}")
        parts.append(f"调用链: {format_chain(chain)}")
        parts.append("")
    return "\n".join(parts)


def parse_llm_response(text: str) -> list[dict]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = "\n".join(stripped.split("\n")[1:-1]).strip()
    try:
        data = json.loads(stripped)
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass
    match = re.search(r"\[.*\]", stripped, re.DOTALL)
    if match:
        data = json.loads(match.group(0))
        if isinstance(data, list):
            return data
    raise RuntimeError(f"unable to parse LLM response as JSON array: {stripped[:200]}")


def main() -> None:
    parser = argparse.ArgumentParser(description="LLM-assisted dynamic SQL resolution")
    parser.add_argument("--trace-file", default="", help="phase2_trace.json path")
    args = parser.parse_args()

    text = sys.stdin.read().strip()
    if not text:
        return
    try:
        records = json.loads(text)
    except json.JSONDecodeError:
        records = [json.loads(line) for line in text.splitlines() if line.strip()]

    chain_map = build_chain_map(args.trace_file) if args.trace_file else {}

    non_needs = [r for r in records if not r.get("needs_llm")]
    needs = [r for r in records if r.get("needs_llm")]

    resolved = {}
    for record in non_needs:
        resolved[record["sql_id"]] = finalize_sql(record.get("resolved_sql", ""))

    if needs and llm_client.available():
        for start in range(0, len(needs), BATCH_SIZE):
            batch = needs[start:start + BATCH_SIZE]
            try:
                text = llm_client.call_llm(SYSTEM_PROMPT, build_user_prompt(batch, chain_map))
                parsed = parse_llm_response(text)
                for item in parsed:
                    if isinstance(item, dict) and item.get("sql_id"):
                        resolved[item["sql_id"]] = finalize_sql(item.get("resolved_sql", ""))
            except Exception as exc:
                print(f"WARNING: LLM batch failed, degrade to optimistic: {exc}", file=sys.stderr)

    for record in records:
        sql_id = record.get("sql_id", "?")
        final = resolved.get(sql_id)
        if final is None:
            final = finalize_sql(record.get("resolved_sql", ""))
        print(json.dumps({
            "sql_id": sql_id,
            "resolved_sql": final,
            "uncertain": record.get("uncertain", False),
            "uncertain_tags": record.get("uncertain_tags", []),
        }, ensure_ascii=False))


if __name__ == "__main__":
    main()
