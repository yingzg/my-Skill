# SQL Review Skill — 测试设计

> 用最少文件做回归保护：改脚本 → 跑测试 → 输出和预期不一致 → 看是不是改坏了。

---

## 一、目录结构

```
tests/
├── fixtures/
│   ├── mappers.xml               ← 所有 MyBatis SQL 测试样例放这一个文件
│   ├── mock-risk.json            ← Phase 4b LLM 输出的 mock（build_report 测试用）
│   └── java/                     ← 调用链追踪用的 Java 源码
│       ├── OrderController.java
│       ├── OrderService.java
│       └── OrderMapper.java
│
├── expected/
│   ├── parse-output.json         ← parse_mapper.py 期望输出（JSON 数组）
│   ├── rules-output.json         ← match_rules.py 期望输出
│   ├── discover-output.json      ← discover_datasource.py 期望输出
│   ├── extract-output.json       ← extract_changes.py 期望输出
│   ├── trace-output.json         ← trace_callchain.py 期望输出
│   ├── resolve-output.jsonl      ← resolve_dynamic_sql.py optimistic 模式期望输出
│   ├── resolve-mode-output.jsonl ← resolve_dynamic_sql.py resolve 模式期望输出
│   ├── resolve-skip-finalize-output.jsonl ← resolve 模式 + --skip-finalize
│   ├── tables-output.jsonl       ← extract_tables.py 期望输出
│   ├── proxy-output.jsonl        ← dml_to_select_proxy.py 期望输出
│   ├── explain-output.json       ← execute_explain.py --dry-run 期望输出
│   └── report-output.json        ← build_report.py 期望输出
│
└── run.sh                        ← 跑脚本 → diff golden file → PASS/FAIL
```

---

## 二、核心概念：Golden File

`expected/` 下每个 JSON/JSONL 文件是「正确答案」。一个脚本对应一个 golden file（resolve_dynamic_sql.py 因双模式+新标志有 3 个）。

```
你第一次写好脚本 → 手动确认输出正确 → 复制到 expected/ → 这就是 golden file

三个月后改了脚本 → 再跑一次 → 输出和 expected/ 不一致 → 测试 FAIL
                                    │
                          ┌─────────┴─────────┐
                          ▼                   ▼
                    差异是预期的          差异是意外的
                    （如新增字段）        （如 SQL 解析错了）
                    更新 golden file      → 修 bug
```

---

## 三、fixture 文件设计

### 3.1 mappers.xml — MyBatis SQL 测试样例

一个文件，用注释分隔不同能力区，覆盖所有 MyBatis 动态标签和 SQL 类型。回归 case 用 `gh-XXX` id 命名。

### 3.2 mock-risk.json — 模拟 LLM 风险分析输出

供 `build_report.py` 集成测试使用，包含预定义的 risk 条目。

### 3.3 Java 源码 — 调用链追踪

三个最小文件（Controller → Service → Mapper），供 `trace_callchain.py` 测试。

---

## 四、测试列表（12 个）

| # | 测试对象 | 命令 | Golden File |
|:-:|---------|------|------------|
| 1 | `parse_mapper.py` | `--file tests/fixtures/mappers.xml` | `parse-output.json` |
| 2 | `match_rules.py` | `--input expected/parse-output.json` | `rules-output.json` |
| 3 | `discover_datasource.py` | `--project-root tests/fixtures` | `discover-output.json` |
| 4 | `extract_changes.py` | `--base base-branch --repo <tmp>` | `extract-output.json` |
| 5 | `trace_callchain.py` | `--methods [...] --project-root tests/fixtures` | `trace-output.json` |
| 6 | `resolve_dynamic_sql.py` | optimistic 模式（默认）| `resolve-output.jsonl` |
| 7 | `extract_tables.py` | stdin NDJSON → stdout | `tables-output.jsonl` |
| 8 | `dml_to_select_proxy.py` | stdin NDJSON → stdout | `proxy-output.jsonl` |
| 9 | `execute_explain.py` | `--dry-run` + stdin | `explain-output.json` |
| 10 | `build_report.py` | `--run-id golden --mode local` | `report-output.json` |
| 11 | `resolve_dynamic_sql.py` | `--mode resolve`（含 finalize_sql） | `resolve-mode-output.jsonl` |
| 12 | `resolve_dynamic_sql.py` | `--mode resolve --skip-finalize` | `resolve-skip-finalize-output.jsonl` |

---

## 五、run.sh 验证逻辑

### 5.1 工具函数

- `compare_json`: 对两个 JSON 文件排序 key 后 diff，自动删除 `generated_at` 和 `run_id` 等不稳定字段
- `compare_json_fields`: 同上，但额外用 jq 过滤器裁剪只比较指定字段
- `run_test`: 执行命令 → 输出到临时文件 → compare_json → 报告 PASS/FAIL
- `run_test_subset`: 同上，但用 jq filter 只比较部分字段

### 5.2 不稳定字段处理

`compare_json` 自动忽略：`generated_at`、`run_id`。测试确保它们不影响 diff。

### 5.3 特殊测试

- **Test 4 (extract_changes.py)**: 需要 git repo，在 `/tmp` 下动态创建含 3 个 commit 的最小 git 仓库
- **Test 6-8 (管道模式)**: stdin → stdout 的 NDJSON 流程，用 `jq -s 'sort_by(.sql_id)'` 排序后 diff
- **Test 9 (--dry-run)**: 不连真实数据库，验证 EXPLAIN 输出 schema
- **Test 10 (集成测试)**: 组合 rules + explain + mock risk 验证最终报告

---

## 六、验收流程

### 每次改完脚本后

```
1. bash tests/run.sh

2. 看到结果:
   ✅ All 12 tests PASSED → 提交
   ❌ 有 FAIL           → 跳到步骤 3

3. 看 diff 输出，判断差异:
   差异是预期的（如新增字段）→ 手动复制输出到 expected/ → 回到步骤 1
   差异是意外的（如 SQL 解析结果变了）→ 修 bug → 回到步骤 1
```

### 新增测试样例后

```
1. 在 mappers.xml 追加一条 SQL
2. bash tests/run.sh → 如果 FAIL，确认差异正确后手动更新 golden file
3. git diff tests/expected/ → 确认新增的条目正确
4. 提交
```

---

## 七、覆盖率要求

| 覆盖维度 | 最低要求 |
|---------|:---:|
| MyBatis 动态标签类型 | 全部 9 种标签至少各 1 条 |
| 静态 SQL 类型 | SELECT / UPDATE / DELETE / INSERT 至少各 1 条 |
| 高风险规则命中 | 15 条规则中至少 10 条有命中 case |
| 全 PASS SQL | 至少 1 条干净 SQL（无规则命中） |
