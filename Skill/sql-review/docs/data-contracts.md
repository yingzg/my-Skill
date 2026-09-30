# Auto SQL Review — 数据契约

> 定义脚本间的输入输出规范、哪些走内存/管道、哪些落盘、以及落盘文件的生命周期。
>
> **状态说明**：本文保留早期设计思路，不作为当前实现的权威契约。当前可执行契约以 `references/report-schema.md`、`docs/scripts-spec.md`、`scripts/run_review.py` 和 `tests/expected/*` 为准。新增或修改脚本时，先更新测试和 `report-schema.md`，再回填本文。

---

## 一、数据流向总览

```
                    Phase 0                     Phase 0.5
                 extract_changes            discover_datasource
                       │                           │
                       ▼                           ▼
                 ┌───────────┐              ┌──────────────┐
                 │ 变更文件列表│              │  数据源映射表  │
                 └─────┬─────┘              └──────┬───────┘
                       │                           │
                       └──────┬────────────────────┘
                              │       ┌──────────────────────────────┐
                              ▼       ▼                              │
                           Phase 1: parse_mapper                      │
                              │       │                               │
                              │       └── 产出: SqlRecord[]          │
                              │           每一条包含:                  │
                              │             sql_id                   │
                              │             file / line / type       │
                              │             method_name              │
                              │             datasource               │
                              │             template_sql             │
                              │             params[]                 │
                              │                                     │
              ┌───────────────┼───────────────┐                     │
              │               │               │               内存传递 │
              ▼               │               ▼                     │
       Phase 2: trace_        │        Phase 3.5a/b + Phase 4a      │
       callchain              │        extract_tables               │
              │               │        dml_to_select_proxy          │
              ▼               │        match_rules                  │
       ┌────────────┐         │               │                     │
       │ 调用链结果  │         │               ▼                     │
       └─────┬──────┘         │    ┌─────────────────────┐          │
              │               │    │ 规则匹配结果 ──→ 落盘 │          │
              │               │    │  phase4a_rules.json  │          │
              └───────┬───────┘    └──────────┬──────────┘          │
                      │                      │                      │
                      ▼                      │                      │
               Phase 3: resolve              │                      │
               dynamic_sql (LLM)             │                      │
                      │                      │                      │
                      ▼                      │                      │
               ┌──────────┐                  │                      │
               │resolved  │                  │                      │
               │_sql[]    │                  │                      │
               └────┬─────┘                  │                      │
                    │                        │                      │
                    ├─→ Phase 3.5a ──────────┘                      │
                    ├─→ Phase 3.5b ──→ proxy_sql[]（内存）           │
                    └─→ Phase 4a   ──→ rules.json（落盘）            │
                                                                    │
  ═══════════════════════════════════════════════════════════════════│
  ↑ 以上全部走内存/管道，不落盘 ↑                                    │
  ═══════════════════════════════════════════════════════════════════│
  ↓ 以下的关键结果落盘 ↓                                            │
                                                                    │
                          Phase 4b                                  │
              execute_explain + LLM 风险定性                         │
                          │                                         │
              ┌───────────┼───────────┐                             │
              ▼           ▼           │                             │
     phase4b_explain  phase4b_risk    │                             │
       .json（落盘）    .json（落盘）   │                             │
              │           │           │                             │
              └─────┬─────┘           │                             │
                    │                 │                             │
                    ▼                 │                             │
              Phase 5: build_report   │                             │
                    │                 │                             │
                    ▼                 │                             │
            phase5_report.json        │                             │
              （落盘）                 │                             │
                                      │                             │
  run.json ─── 运行元信息（落盘，用于清理判断）                       │
  ──────────────────────────────────────────────────────────────────│
```

### 传递方式总结

| 阶段 | 产出物 | 传递方式 | 原因 |
|------|--------|:---:|------|
| Phase 0 → 1 | 变更文件列表 | 管道 | 一次性消费，不需要复盘 |
| Phase 0.5 → 1 | 数据源映射表 | 管道 | 一次性消费，不需要复盘 |
| Phase 1 → 2, 3 | SqlRecord[] | 内存 | 下游多个脚本消费，但都不需要复盘 |
| Phase 2 → 3 | 调用链结果 | 内存 | LLM 输入，不需要复盘 |
| Phase 3 → 3.5/4a | resolved_sql[] | 内存 | 下游多个脚本消费 |
| Phase 3.5a → 4a.5 | 表名映射 | 内存 | 纯映射表 |
| Phase 3.5b → 4b | proxy_sql[] | 内存 | 纯转换结果 |
| Phase 4a → 4a.5/4b/5 | 规则匹配结果 | **落盘** | 复盘核心数据——"为什么判定 HIGH" |
| Phase 4a.5 → 4b | 批次列表 | 内存 | 纯调度信息 |
| Phase 4b → 5 | EXPLAIN 结果 | **落盘** | 复盘核心数据——"当时执行计划是什么" |
| Phase 4b → 5 | LLM 风险定性 | **落盘** | 复盘核心数据——"LLM 给了什么结论" |
| Phase 5 → 用户/CI | 最终报告 | **落盘** | 交付物 |

---

## 二、落盘文件 JSON Schema

### 2.1 phase4a_rules.json — 规则匹配结果

复盘时回答：**这条 SQL 命中了哪些规则、为什么命中、风险等级是什么。**

```jsonc
[
  {
    "sql_id": "OrderMapper.xml:selectByOrderId:0",
    "match_time": "2026-07-29T14:30:20+08:00",
    "rules_file": "references/rules/rules.json",

    // ═══ 每条规则的匹配结果（含命中和未命中） ═══
    // 保留未命中是为了复盘时能确认"不是漏检，而是确实不匹配"
    "matches": [
      {
        "rule_id": "R001",
        "name": "SELECT * 检测",
        "hit": false,
        "detail": "已显式列出字段: id, name, status"
      },
      {
        "rule_id": "R012",
        "name": "WHERE 子句 OR 条件",
        "hit": true,
        "level": "MEDIUM",
        "detail": "WHERE 包含 OR 条件: status = 'A' OR status = 'B'，可能阻止索引使用"
      }
    ],

    // ═══ 分类结论 ═══
    "channel": "deep_analysis",
    "highest_level": "MEDIUM",
    "hit_rules": ["R012"]
  }
]
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|:--:|------|
| `sql_id` | string | ✅ | 对应 SqlRecord 的唯一标识 |
| `match_time` | string | ✅ | 匹配时间，复盘时用于判断是否用了最新的规则文件 |
| `rules_file` | string | ✅ | 使用的规则文件路径，复盘时确认规则版本 |
| `matches[].rule_id` | string | ✅ | 规则编号 |
| `matches[].name` | string | ✅ | 规则中文名 |
| `matches[].hit` | boolean | ✅ | 是否命中 |
| `matches[].level` | string | ⚠️ | 命中时的风险等级（`LOW`/`MEDIUM`/`HIGH`/`CRITICAL`），未命中时为 `null` |
| `matches[].detail` | string | ✅ | 命中/未命中的具体原因，人工可读 |
| `channel` | string | ✅ | `fast_track`（全 LOW，跳过 LLM）/ `deep_analysis`（需 LLM 深度分析） |
| `highest_level` | string | ✅ | 该 SQL 的最高风险等级 |
| `hit_rules` | string[] | ✅ | 命中的规则 ID 列表 |

---

### 2.2 phase4b_explain.json — EXPLAIN 执行结果

复盘时回答：**当时的执行计划是什么、用了什么索引、扫描多少行。**

```jsonc
[
  {
    "sql_id": "OrderMapper.xml:selectByOrderId:0",
    "explain_time": "2026-07-29T14:30:30+08:00",
    "datasource": "scheme",
    "db_version": "MySQL 8.0.35",
    "executed": true,

    // ═══ 实际执行的 SQL（审计关键——EXPLAIN 到底跑了什么） ═══
    "sql_used": "EXPLAIN SELECT * FROM orders WHERE id = 123 AND status = 'ACTIVE'",

    // ═══ EXPLAIN 原始输出（保留原始格式，供人工肉眼确认） ═══
    "raw": "id: 1  select_type: SIMPLE  table: orders  type: ref  possible_keys: idx_id  key: idx_id  key_len: 8  ref: const  rows: 1  Extra: Using filesort",

    // ═══ 结构化解析结果 ═══
    "parsed": {
      "type": "ref",
      "key": "idx_id",
      "possible_keys": ["idx_id"],
      "rows": 1,
      "extra": "Using filesort",
      "full_scan": false,
      "using_temporary": false
    },

    // ═══ 异常标记 ═══
    "warnings": [
      { "type": "using_filesort", "detail": "ORDER BY 列不在索引中" }
    ]
  },
  {
    "sql_id": "OrderMapper.xml:updateOrderStatus:3",
    "explain_time": "2026-07-29T14:30:30+08:00",
    "datasource": "scheme",
    "executed": false,
    "reason": "datasource_unreachable",
    "sql_used": null,
    "raw": null,
    "parsed": null
  }
]
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|:--:|------|
| `sql_id` | string | ✅ | 对应 SqlRecord 的唯一标识 |
| `explain_time` | string | ✅ | EXPLAIN 执行时间 |
| `datasource` | string | ✅ | 数据源名称（区分多数据源场景） |
| `db_version` | string | ⚠️ | 数据库版本，复盘时确认版本差异 |
| `executed` | boolean | ✅ | 是否成功执行。`false` 时 `raw`/`parsed` 为空 |
| `reason` | string | ⚠️ | `executed=false` 时必须填写原因 |
| `sql_used` | string | ⚠️ | **实际执行的 SQL**（审计关键字段） |
| `raw` | string | ⚠️ | EXPLAIN 原始输出 |
| `parsed.type` | string | ⚠️ | 访问类型：`ALL`/`index`/`range`/`ref`/`const` 等 |
| `parsed.key` | string | ⚠️ | 实际使用的索引名 |
| `parsed.rows` | number | ⚠️ | 预估扫描行数 |
| `parsed.extra` | string | ⚠️ | Extra 信息（`Using filesort`/`Using temporary` 等） |
| `parsed.full_scan` | boolean | ⚠️ | 是否全表扫描（`type=ALL`） |
| `warnings` | array | ✅ | EXPLAIN 中发现的风险点 |

---

### 2.3 phase4b_risk.json — LLM 风险定性

复盘时回答：**LLM 综合规则和 EXPLAIN 后给出的结论是什么，为什么。**

```jsonc
[
  {
    "sql_id": "OrderMapper.xml:selectByOrderId:0",
    "risk_time": "2026-07-29T14:30:35+08:00",

    // ═══ 风险结论 ═══
    "level": "MEDIUM",
    "summary": "单条 SQL 性能正常，但 N+1 调用模式存在风险",

    // ═══ LLM 的判断依据（可审计） ═══
    "rationale": {
      "static_rules": "R012 命中：OR 条件。EXPLAIN 显示用了 idx_id 索引，rows=1，单次查询性能正常",
      "explain_findings": "type=ref, rows=1, EXPLAIN 未发现全表扫描或临时表",
      "callchain_context": "调用方 OrderService.listOrders() 在循环中调用此方法，批量场景下有 N+1 风险",
      "degradation_note": null
    },

    // ═══ 分级修复建议 ═══
    "short_term_fix": "在调用方改为批量查询：SELECT * FROM orders WHERE id IN (...)",
    "long_term_fix": "抽取 OrderBatchService，统一处理批量订单查询，避免 Service 层循环调 Mapper",

    // ═══ 不确定标记 ═══
    "uncertain": false,
    "uncertain_reason": null
  }
]
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|:--:|------|
| `sql_id` | string | ✅ | 对应 SqlRecord 的唯一标识 |
| `risk_time` | string | ✅ | 结论生成时间 |
| `level` | string | ✅ | 最终风险等级：`LOW` / `MEDIUM` / `HIGH` / `CRITICAL` |
| `summary` | string | ✅ | 一句话摘要（用于报告表格） |
| `rationale.static_rules` | string | ✅ | 基于规则匹配的判定依据 |
| `rationale.explain_findings` | string | ✅ | 基于 EXPLAIN 的判定依据 |
| `rationale.callchain_context` | string | ⚠️ | 基于调用链上下文的判定依据（调用链不完整时可能为空） |
| `rationale.degradation_note` | string | ⚠️ | 降级说明（如"调用链断裂，无法确认 N+1 调用"） |
| `short_term_fix` | string | ✅ | 可立即上线的修复方案 |
| `long_term_fix` | string | ✅ | 需排期重构的治理方案 |
| `uncertain` | boolean | ✅ | 结论是否不确定（如调用链断裂导致的部分推断） |
| `uncertain_reason` | string | ⚠️ | 不确定的原因 |

---

### 2.4 phase5_report.json — 最终报告

复盘时回答：**这次分析的整体结论是什么。**

```jsonc
{
  // ═══ 运行元信息 ═══
  "run_id": "run_20260729_143000_abc123",
  "generated_at": "2026-07-29T14:30:45+08:00",
  "duration_sec": 92.5,
  "base_branch": "origin/master",
  "head_sha": "abc123",

  // ═══ 门禁结论（CI 模式） ═══
  "gate": {
    "decision": "BLOCK",
    "reason": "检测到 2 条 HIGH、4 条 MEDIUM 风险 SQL",
    "blocked_by": [
      { "sql_id": "OrderMapper.xml:updateOrder:3", "level": "HIGH", "rule": "R103" },
      { "sql_id": "BaseInfoMapper.xml:deleteBaseInfo:0", "level": "HIGH", "rule": "R102" }
    ]
  },

  // ═══ 统计 ═══
  "summary": {
    "total": 12,
    "high": 2,
    "medium": 4,
    "low": 5,
    "info": 1,
    "explain_ok": 10,
    "explain_failed": 2,
    "degraded": 3
  },

  // ═══ SQL 级别的详细结果 ═══
  "findings": [
    {
      "sql_id": "OrderMapper.xml:selectByOrderId:0",
      "file": "src/main/java/.../OrderMapper.xml",
      "line": 42,
      "type": "SELECT",
      "method": "com.example.mapper.OrderMapper.selectByOrderId",
      "resolved_sql": "SELECT id, name, status FROM orders WHERE id = 123",
      "level": "MEDIUM",
      "summary": "N+1 调用模式风险",
      "explain": {
        "type": "ref",
        "key": "idx_id",
        "rows": 1
      },
      "short_term": "改为 IN 批量查询",
      "long_term": "抽取批量查询 Service"
    }
  ],

  // ═══ 复查清单（降级项汇总） ═══
  "review_needed": [
    {
      "type": "call_chain_broken",
      "sql_id": "OrderMapper.xml:selectByOrderId:0",
      "detail": "Service 层通过反射调用，无法追踪完整调用链",
      "impact": "N+1 风险判断基于代码命名约定推测，建议人工确认"
    }
  ]
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|:--:|------|
| `run_id` | string | ✅ | 运行唯一标识 |
| `generated_at` | string | ✅ | 报告生成时间 |
| `duration_sec` | number | ✅ | 分析总耗时（秒） |
| `base_branch` | string | ✅ | git diff 的 base 分支 |
| `head_sha` | string | ✅ | HEAD commit SHA |
| `gate.decision` | string | ✅ | `PASS` 或 `BLOCK` |
| `gate.reason` | string | ✅ | 门禁判定原因 |
| `gate.blocked_by` | array | ✅ | 阻塞原因清单 |
| `summary` | object | ✅ | 统计摘要 |
| `findings[].sql_id` | string | ✅ | SQL 标识 |
| `findings[].level` | string | ✅ | 风险等级 |
| `findings[].resolved_sql` | string | ✅ | 还原后的实际 SQL（核心审计信息） |
| `findings[].explain` | object | ⚠️ | EXPLAIN 摘要（`executed=false` 时为空） |
| `findings[].short_term` | string | ✅ | 短期修复方案 |
| `findings[].long_term` | string | ✅ | 长期治理方案 |
| `review_needed` | array | ✅ | 需人工复查的降级项 |

---

## 三、run.json — 运行元信息

每次运行时在 run 目录下自动生成，用于清理逻辑判断。

```jsonc
{
  "run_id": "run_20260729_143000_abc123",
  "created_at": "2026-07-29T14:30:00+08:00",
  "trigger": "CI_MR",
  "base_sha": "abc123",
  "head_sha": "def456",
  "status": "FAILED",
  "has_high_risk": true,
  "file_count": 4,
  "total_size_kb": 48
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `run_id` | string | 运行标识，同时也是目录名 |
| `created_at` | string | 创建时间（ISO 8601） |
| `trigger` | string | `CI_MR`（MR 门禁）/ `LOCAL`（本地自查）/ `MANUAL`（手动触发） |
| `base_sha` | string | git diff base，同 MR 的多轮触发靠它分组 |
| `head_sha` | string | HEAD commit SHA |
| `status` | string | `PASSED` / `FAILED` / `TIMEOUT` |
| `has_high_risk` | boolean | 是否含 HIGH/MEDIUM 风险（决定保留时长） |
| `file_count` | number | 落盘文件数 |
| `total_size_kb` | number | 总大小（KB） |

---

## 四、清理策略

### 规则

```
每次运行结束时自动扫描 /tmp/sql_review/ 下所有 run 目录：

A. PASSED + has_high_risk=false:
   → 只保留 report.json（7 天）
   → 中间文件（rules/explain/risk）不保存

B. FAILED / TIMEOUT / has_high_risk=true:
   → 保留全部 4 个文件（report + rules + explain + risk）
   → 保留时长: 30 天

C. 同 MR（同一 base_sha）:
   → 只保留最近 3 次的中间文件
   → 第 4 次及更旧的: 删除中间文件，只保留 report.json

D. 全局：
   → 不管 PASS/FAIL，保留最近 3 天内所有运行的 report.json
```

### 运行示例

```
/tmp/sql_review/
│
├── run_20260727_090000_aaa111/     ← 3天前，PASS → 删除
├── run_20260728_100000_bbb222/     ← 2天前，PASS → 保留 report.json（D）
├── run_20260729_143000_abc123/     ← 今天，FAIL，has_high=true
│   ├── run.json                    ← 保留 30 天（B）
│   ├── phase4a_rules.json
│   ├── phase4b_explain.json
│   ├── phase4b_risk.json
│   └── report.json
│
├── run_20260729_150000_def456/     ← 今天，同 MR（同一 base_sha）
│   ├── run.json                    ← 同 MR 第 2 次
│   ├── ...(4 文件)
│
├── run_20260729_153000_ghi789/     ← 今天，同 MR
│   ├── run.json                    ← 同 MR 第 3 次
│   ├── ...(4 文件)
│
├── run_20260729_160000_jkl012/     ← 今天，同 MR
│   ├── run.json                    ← 同 MR 第 4 次 → 删除中间文件，只留 report（C）
│   └── report.json
```

---

## 五、目录结构约定

```
/tmp/sql_review/{run_id}/
├── run.json                  ← 元信息（必选，用于清理判断）
├── phase4a_rules.json        ← 规则匹配结果
├── phase4b_explain.json      ← EXPLAIN 结果
├── phase4b_risk.json         ← LLM 风险定性
└── phase5_report.json        ← 最终报告
```

**不在磁盘上的数据**（通过内存/管道传递，不落盘）：
- 变更文件列表（Phase 0）
- 数据源映射表（Phase 0.5）
- SqlRecord 基准数组（Phase 1）
- 调用链结果（Phase 2）
- DynamicTagResolution（Phase 3）
- 表名映射、proxy_sql（Phase 3.5）
- 批次列表（Phase 4a.5）
