# 输出格式规范

> `build_report.py`（Phase 5）加载此文件校验输入数据的字段完整性。
> LLM（Phase 4b）将此文件的输出 Schema 注入 Prompt，约束输出格式。
>
> 对应数据契约文件 `docs/data-contracts.md`，本文件仅定义 **字段 Schema**（类型、必填、可选值）。

---

## 一、风险等级枚举

最终报告中所有出现 `risk_level` 的字段均使用此枚举：

| 值 | 含义 | 门禁行为（默认） |
|----|------|:---:|
| `CRITICAL` | 生产事故级风险 | BLOCK + 必须修复 |
| `HIGH` | 高风险，强烈建议修复 | BLOCK |
| `MEDIUM` | 中等风险，建议修复 | WARN（可配置为 BLOCK） |
| `LOW` | 低风险，可在后续迭代优化 | PASS |
| `PASS` | 无风险 | PASS |

`UNCERTAIN` 只允许出现在中间产物，例如 `phase4a_rules.json` 的 `overall_risk`。最终报告不得输出 `risk_level: "UNCERTAIN"`；缺少明确风险时按 `PASS` 输出，并用 `uncertain: true` 或复查清单保留上下文。

---

## 二、phase4a_rules.json — 规则匹配结果

> 由 `match_rules.py` 生成，每条 SQL 的所有规则匹配明细。

```jsonc
{
  "run_id": "string",              // ✅ 本次运行 ID
  "generated_at": "string",        // ✅ ISO 8601 时间戳
  "rules_version": "string",       // ✅ 规则文件版本
  "results": [
    {
      "sql_id": "string",          // ✅ SQL 唯一标识
      "statement_type": "string",  // ✅ SELECT / UPDATE / DELETE / INSERT
      "rule_matches": [
        {
          "rule_id": "string",     // ✅ 规则编号，如 "R001"
          "matched": "boolean",    // ✅ 是否命中
          "severity": "string"     // ✅ CRITICAL / HIGH / MEDIUM / LOW / NONE
        }
      ],
      "overall_risk": "string",    // ✅ CRITICAL / HIGH / MEDIUM / LOW / UNCERTAIN
      "risk_reason": "string"      // ✅ 简明可读的规则命中说明
    }
  ],
  "summary": {
    "total": "number",
    "by_risk_level": {
      "CRITICAL": "number",
      "HIGH": "number",
      "MEDIUM": "number",
      "LOW": "number",
      "UNCERTAIN": "number"
    }
  }
}
```

---

## 三、phase4b_explain.json — EXPLAIN 结果

> 由 `execute_explain.py` 生成，每条 SQL 的 EXPLAIN 输出。

```jsonc
{
  "sql_id": "string",              // ✅ SQL 唯一标识
  "datasource": "string",          // ✅ 数据源标识（如 "db_order"）
  "explain_executed": "boolean",   // ✅ 是否成功执行 EXPLAIN
  "explain_error": "string | null",// ⚠️ explain_executed=false 时的失败原因

  // ── 原始输出 ──
  "explain_raw_table": "string | null",   // ⚠️ EXPLAIN 的表格输出（执行成功时必填）
  "explain_raw_json": "object | null",    // ⚠️ EXPLAIN FORMAT=JSON 输出（执行成功时必填）

  // ── 结构化解析 ──
  "explain_parsed": {              // ⚠️ 执行成功时必填
    "query_cost": "number | null",        // 优化器估算成本（来自 FORMAT=JSON）
    "estimated_rows": "number | null",    // 预估扫描行数（rows 字段的总和）
    "access_type": "string | null",       // 主表的 type（ALL/range/ref…）
    "key_used": "string | null",          // 实际使用的索引名
    "key_len": "number | null",           // 使用的索引长度
    "extra": ["string"],                  // Extra 字段（数组，可能多个值）
    "using_filesort": "boolean",          // 是否 Using filesort
    "using_temporary": "boolean",         // 是否 Using temporary
    "possible_keys": ["string"]           // 可能使用的索引列表
  },

  // ── 实际执行的 SQL ──
  "proxy_sql": "string | null",    // ⚠️ DML 的 SELECT proxy 或 SELECT 原始 SQL（执行成功时必填）
  "original_sql": "string",        // ✅ 原始 SQL（可能含 MyBatis 动态标签）
  "statement_type": "string"       // ✅ SELECT / UPDATE / DELETE / INSERT
}
```

---

## 四、phase4b_risk.json — 风险上下文与可选风险覆盖

> 由 `run_review.py` 生成，至少包含调用链上下文。后续如果接入人工或 LLM 深度复核，可以在同一文件中补充风险覆盖字段。

```jsonc
{
  "results": [
    {
      "sql_id": "string",          // ✅ SQL 唯一标识
      "call_chain": [              // ✅ 调用链；找不到时为空数组
        { "class": "string", "method": "string", "line": "number" }
      ],
      "call_chain_broken": "boolean", // ✅ 是否未能追踪到 Controller/API

      // 以下为可选风险覆盖字段。缺省时 build_report.py 回退到规则和 EXPLAIN。
      "level": "string",           // ⚠️ CRITICAL / HIGH / MEDIUM / LOW / PASS
      "summary": "string",         // ⚠️ 一句话风险描述
      "short_term_fix": "string",  // ⚠️ 短期修复建议
      "long_term_fix": "string",   // ⚠️ 长期治理建议
      "uncertain": "boolean"       // ⚠️ 是否存在人工复查不确定性
    }
  ]
}
```

---

## 五、phase5_report.json — 最终报告

> 由 `build_report.py` 合并 `rules.json` + `explain.json` + `risk.json` 生成。

```jsonc
{
  // ═══ 报告元信息 ═══
  "report_id": "string",           // ✅ 唯一报告 ID，格式 "sql-review-{timestamp}"
  "generated_at": "string",        // ✅ ISO 8601 时间戳
  "version": "1.0.0",             // ✅ 报告格式版本

  // ═══ MR 上下文 ═══
  "context": {
    "branch": "string",            // ✅ 当前分支名
    "base_ref": "string",          // ✅ diff 基准（如 "origin/master"）
    "mr_url": "string | null",     // ⚠️ MR 链接（CI 模式下有值）
    "mode": "string",              // ✅ "local" | "ci"
    "total_sql_count": "number"    // ✅ 本次变更涉及的总 SQL 数
  },

  // ═══ 门禁结论 ═══
  "gate": {
    "conclusion": "string",        // ✅ "PASS" | "BLOCK" | "WARN"
    "decision": "string",          // ✅ 兼容字段，当前与 conclusion 相同
    "block_reason": "string | null",// ⚠️ BLOCK 时的原因摘要
    "thresholds": {
      "HIGH_block": "boolean",     // 是否因 HIGH 达到阈值而 BLOCK
      "MEDIUM_block": "boolean",   // 是否因 MEDIUM 达到阈值而 BLOCK
      "CRITICAL_block": "boolean"  // 是否因 CRITICAL 而 BLOCK
    },
    "statistics": {
      "total": "number",
      "CRITICAL": "number",
      "HIGH": "number",
      "MEDIUM": "number",
      "LOW": "number",
      "PASS": "number",
      "ANALYSIS_FAILED": "number"  // 分析失败的数量
    }
  },

  // ═══ 详细发现 = 合并后的 risk.json 条目 ═══
  "findings": [
    {
      "sql_id": "string",
      "file_path": "string",
      "line": "number",
      "statement_type": "string",
      "mapper_method": "string",
      "risk_level": "string",
      "risk_summary": "string",
      "rationale": {
        "static_rules": "string",
        "explain_analysis": "string | null",
        "degradation_note": "string | null"
      },
      "short_term_fix": "string",
      "long_term_fix": "string",
      "call_chain": [{ "class": "string", "method": "string", "line": "number" }],
      "call_chain_broken": "boolean",
      "resolved_sql": "string",
      "explain_executed": "boolean",

      // 兼容旧报告消费者的字段，后续可逐步下线
      "level": "string",
      "summary": "string",
      "explain_type": "string | null",
      "explain_key": "string | null",
      "explain_rows": "number | null",
      "rule_matches": "array",
      "uncertain": "boolean"
    }
  ],

  // ═══ 复查清单 ═══
  "review_checklist": [
    {
      "tag": "string",             // ✅ 降级标记，如 "parse_error"
      "item": "string",            // ✅ 复查项描述
      "reason": "string",          // ✅ 为什么需要复查
      "sql_ids": ["string"]        // ✅ 受影响的 SQL ID 列表
    }
  ],

  // ═══ 全局降级说明 ═══
  "degradation_notes": [           // ⚠️ 如有全局降级，在此汇总
    {
      "level": "string",           // "global" | "partial"
      "type": "string",            // 降级类型
      "description": "string"      // 描述
    }
  ]
}
```
