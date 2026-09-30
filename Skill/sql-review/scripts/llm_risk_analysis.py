#!/usr/bin/env python3
"""Phase 4b: LLM risk analysis.

Merges static rule results + EXPLAIN results + call chain context, then asks an
LLM to produce a natural-language risk narrative for HIGH/MEDIUM/UNCERTAIN SQL.
LOW/PASS SQL skip the LLM (fast track). Deep-analysis SQL is batched (8/batch)
to bound LLM concurrency. LLM failures degrade to the deterministic rule level.

Usage:
    python3 llm_risk_analysis.py --rules-file phase4a_rules.json \
        --explain-file phase4b_explain.json --risk-file phase4b_risk.json \
        --output phase4b_risk.json
"""

import argparse
import json
import re
import sys

import llm_client

BATCH_SIZE = 8

SYSTEM_PROMPT = (
    "你是资深的 MySQL 慢查询审查专家。根据每条 SQL 的「SQL 语句、静态规则命中、"
    "EXPLAIN 执行计划、调用链上下文」，判断慢查询风险，输出风险等级、一句话风险描述、"
    "短期修复建议、长期治理建议。\n\n"
    "风险等级枚举（由高到低）：CRITICAL / HIGH / MEDIUM / LOW / PASS\n"
    "- CRITICAL：生产事故级（如无 WHERE 的 UPDATE/DELETE 全表写操作）\n"
    "- HIGH：高风险（如大表全表扫描、索引失效导致的全表扫描）\n"
    "- MEDIUM：中等风险（如缺失 LIMIT、SELECT *）\n"
    "- LOW：低风险（如单行查询、正常索引查找）\n"
    "- PASS：无风险\n\n"
    "必须严格输出 JSON 数组，不要输出任何其他内容。每个元素格式：\n"
    '{"sql_id":"...","level":"...","summary":"一句话风险描述",'
    '"short_term_fix":"短期修复建议","long_term_fix":"长期治理建议"}'
)


def load_json(path: str):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def merge_inputs(rules_file: str, explain_file: str, risk_file: str) -> tuple[list[dict], list[dict]]:
    rules = load_json(rules_file).get("results", [])
    explains = load_json(explain_file).get("results", [])
    risks = load_json(risk_file).get("results", [])

    rules_by_id = {r["sql_id"]: r for r in rules}
    explains_by_id = {e["sql_id"]: e for e in explains}
    risks_by_id = {r["sql_id"]: r for r in risks}

    all_ids = set(rules_by_id) | set(explains_by_id)
    fast, deep = [], []
    for sql_id in sorted(all_ids):
        rule = rules_by_id.get(sql_id, {})
        explain = explains_by_id.get(sql_id)
        risk = risks_by_id.get(sql_id, {})
        base = {
            "sql_id": sql_id,
            "call_chain": risk.get("call_chain", []),
            "call_chain_broken": bool(risk.get("call_chain_broken", False)),
        }
        overall = rule.get("overall_risk", "UNCERTAIN")
        explain_type = explain.get("type") if explain and explain.get("executed") else None
        if overall in ("LOW", "PASS"):
            fast.append({**base, "level": overall})
        elif overall == "UNCERTAIN" and explain_type in ("const", "eq_ref", "ref", "range"):
            fast.append({**base, "level": "LOW"})
        else:
            deep.append({
                **base,
                "statement_type": rule.get("statement_type", ""),
                "resolved_sql": rule.get("resolved_sql", ""),
                "hit_rules": rule.get("risk_reason", ""),
                "overall_risk": overall,
                "explain": (
                    {"type": explain.get("type"), "key": explain.get("key"), "rows": explain.get("rows")}
                    if explain and explain.get("executed") else None
                ),
            })
    return fast, deep


def build_user_prompt(items: list[dict]) -> str:
    parts = ["以下 SQL 需要风险审查：", ""]
    for i, item in enumerate(items, 1):
        chain = " → ".join(f"{c.get('class', '')}.{c.get('method', '')}" for c in item.get("call_chain", []))
        if not chain:
            chain = "（调用链不可用）"
        explain = item.get("explain")
        explain_text = (
            f"type={explain['type']}, key={explain['key']}, rows={explain['rows']}"
            if explain else "EXPLAIN 不可用"
        )
        parts.append(f"【SQL {i}】")
        parts.append(f"sql_id: {item['sql_id']}")
        parts.append(f"语句类型: {item['statement_type']}")
        parts.append(f"SQL: {item['resolved_sql']}")
        parts.append(f"命中规则: {item['hit_rules'] or '无'}")
        parts.append(f"EXPLAIN: {explain_text}")
        parts.append(f"调用链: {chain}")
        parts.append(f"调用链完整: {item['call_chain_broken'] == False}")
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


def degrade_batch(items: list[dict], reason: str) -> list[dict]:
    return [
        {
            "sql_id": item["sql_id"],
            "call_chain": item.get("call_chain", []),
            "call_chain_broken": item.get("call_chain_broken", False),
            "level": item.get("overall_risk", "UNCERTAIN"),
            "summary": f"[LLM 不可用] {item.get('hit_rules', '')}",
            "short_term_fix": "",
            "long_term_fix": "",
            "uncertain": True,
            "degradation": reason,
        }
        for item in items
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="LLM risk analysis for SQL review")
    parser.add_argument("--rules-file", required=True)
    parser.add_argument("--explain-file", required=True)
    parser.add_argument("--risk-file", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--timeout", type=int, default=60, help="Per-batch LLM timeout in seconds")
    args = parser.parse_args()

    fast, deep = merge_inputs(args.rules_file, args.explain_file, args.risk_file)

    results = list(fast)
    llm_failed = 0

    if deep and llm_client.available():
        for start in range(0, len(deep), BATCH_SIZE):
            batch = deep[start:start + BATCH_SIZE]
            try:
                text = llm_client.call_llm(SYSTEM_PROMPT, build_user_prompt(batch), timeout=args.timeout)
                parsed = parse_llm_response(text)
                by_id = {item["sql_id"]: item for item in parsed if isinstance(item, dict)}
                for item in batch:
                    llm_result = by_id.get(item["sql_id"], {})
                    results.append({
                        "sql_id": item["sql_id"],
                        "call_chain": item.get("call_chain", []),
                        "call_chain_broken": item.get("call_chain_broken", False),
                        "level": llm_result.get("level", item.get("overall_risk", "UNCERTAIN")),
                        "summary": llm_result.get("summary", ""),
                        "short_term_fix": llm_result.get("short_term_fix", ""),
                        "long_term_fix": llm_result.get("long_term_fix", ""),
                        "uncertain": False,
                    })
            except Exception as exc:
                print(f"WARNING: LLM batch failed, degrade to rule level: {exc}", file=sys.stderr)
                results.extend(degrade_batch(batch, "llm_failed"))
                llm_failed += 1
    elif deep:
        print("WARNING: LLM_API_KEY not set, deep-analysis SQL degrade to rule level", file=sys.stderr)
        results.extend(degrade_batch(deep, "llm_unavailable"))

    payload = {"results": results}
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
