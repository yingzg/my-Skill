---
name: sql-review
description: 本地 SQL 慢查询审查技能。自动提取当前分支变更代码中的 SQL，通过静态规则 + EXPLAIN + 调用链分析识别慢查询风险并输出审查报告。支持 optimistic（确定性）和 resolve（LLM 辅助）两种动态 SQL 解析模式。This skill should be used when users want to review SQL changes in their current branch for slow query risks before pushing code, or when they mention SQL review, slow SQL analysis, or SQL performance check.
---

# SQL 慢查询审查

通过 **静态规则匹配 → EXPLAIN 执行 → 调用链分析 → 风险定性** 四层分析管道，对 MyBatis Mapper XML 中的 SQL 变更进行慢查询风险审查。支持本地开发审查和 CI 门禁两种模式。

## 前置文件加载

在进行任何分析之前，按需加载以下 reference 文件：

| 文件 | 加载时机 | 用途 |
|------|---------|------|
| `references/degradation-matrix.md` | 任何脚本返回非 0 时 | 查表决定降级/中断 |
| `references/explain-guide.md` | 可选深度复核 EXPLAIN 前 | 约束人工/LLM 对 EXPLAIN 的解读 |
| `references/report-schema.md` | Phase 5 报告生成前 | 校验中间数据契约 |
| `references/rules/rules.json` | Phase 4a 规则匹配时 | `match_rules.py` 自动加载；可选深度复核时作为规则上下文 |

---

## 工作流

优先使用 `run_review.py` 作为唯一主入口。`SKILL.md` 负责选择输入、读取必要 references、解释降级结果；具体管道编排由脚本执行，避免长会话中手工维护多阶段状态。

### Step 0: 初始化

```bash
SCRIPTS="/mnt/g/my-Skill/Skill/sql-review/scripts"
export RUN_ID="run_$(date +%Y%m%d_%H%M%S)"
export WORK_DIR="/tmp/sql_review/${RUN_ID}"
```

所有阶段产物统一写入 `$WORK_DIR`。不要在会话中临时拼接 `BATCH_JSON`、合并批次 JSON 或手工生成最终报告。

### Step 1: 确定输入文件

如果用户没有显式指定 Mapper XML 文件，先从当前 git 仓库提取变更：

```bash
python3 "$SCRIPTS/extract_changes.py" --base origin/master --repo .
```

处理规则：
- 非 git 仓库、base 分支不存在、git diff 失败：中断，并请用户提供 `--files` 对应的 Mapper XML 文件列表。
- `total_count == 0`：正常结束，说明本次变更未检测到 Mapper XML。
- 只分析新增/修改的 Mapper XML；删除文件不进入审查。

### Step 2: 执行端到端审查

将 Step 1 的 `files[].path` 转成 JSON 字符串后调用主入口：

```bash
python3 "$SCRIPTS/run_review.py" \
  --files "$FILES_JSON" \
  --project-root . \
  --project-src src/main/java \
  --base-branch origin/master \
  --run-id "$RUN_ID" \
  --work-dir "$WORK_DIR" \
  --mode local \
  --output "$WORK_DIR/phase5_report.json"
```

`--project-src` 应优先指向本次变更相关的 Java 源码模块，例如 `intl-scheme-infra/src/main/java`。多模块项目需要追到 Controller 时，可以扩大到更上层模块或仓库根目录，但当前调用链追踪是 grep/regex 递归扫描，整仓扫描可能耗时数分钟。

本地无数据库连接、或只想验证流程时加 `--dry-run`：

```bash
python3 "$SCRIPTS/run_review.py" \
  --files "$FILES_JSON" \
  --project-root . \
  --project-src src/main/java \
  --base-branch origin/master \
  --run-id "$RUN_ID" \
  --work-dir "$WORK_DIR" \
  --dry-run \
  --mode local \
  --output "$WORK_DIR/phase5_report.json"
```

`run_review.py` 固定执行：

| 顺序 | 阶段 | 产物 |
|------|------|------|
| 1 | Mapper XML 解析 | `phase1_parse.json` |
| 2 | Java 调用链追踪 | `phase2_trace.json` |
| 3 | 动态 SQL 确定性展开 | `phase3_resolve.jsonl` |
| 4 | 主表提取 | `phase3_5_tables.jsonl` |
| 5 | DML 转 SELECT proxy | `phase3_5_proxy.jsonl` |
| 6 | 静态规则匹配 | `phase4a_rules.json` |
| 7 | EXPLAIN 或 dry-run EXPLAIN | `phase4b_explain.json` |
| 8 | 调用链上下文合并 | `phase4b_risk.json` |
| 9 | 最终报告生成 | `phase5_report.json` |

当前实现中，风险等级由静态规则和 EXPLAIN 结果聚合得出；LLM 只作为后续人工深度复核入口，不在主流程里内联执行。

### Step 3: 校验报告

```bash
jq -e '
  .report_id and
  .context and
  .gate.conclusion and
  (.gate.statistics.total | type == "number") and
  (.review_checklist | type == "array") and
  (.degradation_notes | type == "array") and
  ([.findings[].risk_level] | all(. != "UNCERTAIN"))
' "$WORK_DIR/phase5_report.json"
```

最终报告必须满足：
- 顶层包含 `report_id`、`context`、`gate`、`findings`、`review_checklist`、`degradation_notes`。
- `findings[].risk_level` 只能是 `CRITICAL`、`HIGH`、`MEDIUM`、`LOW`、`PASS`。
- 规则阶段的 `UNCERTAIN` 不能原样进入最终风险等级；无法定级时最终按 `PASS` 输出，并保留 `uncertain: true` 供人工复查。
- `call_chain_broken == true` 的 SQL 必须保留在报告里，不能静默丢弃。

### Step 4: 故障排查路径

只有在 `run_review.py` 失败或需要定位单个阶段问题时，才按 `docs/scripts-spec.md` 手工运行单个脚本。排查顺序保持为：

```text
extract_changes.py
parse_mapper.py
trace_callchain.py
resolve_dynamic_sql.py
extract_tables.py
dml_to_select_proxy.py
match_rules.py
execute_explain.py
build_report.py
```

单阶段排查完成后，仍以 `run_review.py` 重新跑通端到端流程作为最终验收。

---

## 降级处理速查表

| 场景 | 决策 | 复查标记 | 后续行为 |
|------|:---:|---------|---------|
| 非 git 仓库 (D0) | ⚠️ **中断** | — | 提示用户手动指定文件列表 |
| 无 Mapper 变更 (D1) | ✅ **正常退出** | — | 输出 "no SQL changes detected" |
| 部分 XML 解析失败 (D2) | ✅ **降级** | `parse_error` | 跳过失败文件，继续 |
| 全部 XML 解析失败 (D3) | ⚠️ **中断** | — | 输出错误详情 |
| 数据源发现失败 (D4) | ✅ **降级** | `datasource_unknown` | 仅静态规则，跳过 EXPLAIN |
| 数据库连接失败 (D5) | ✅ **降级** | `explain_unavailable` | 仅静态规则分析 |
| EXPLAIN 全部失败 (D7) | ✅ **降级** | `explain_unavailable` | 仅静态规则分析 |
| 单条 EXPLAIN 失败 (D6) | ✅ **降级** | `explain_failed` | 标记该 SQL，继续其他 |
| 调用链追踪失败 (D8) | ✅ **降级** | `call_chain_broken` | 保留部分链，标记断裂点 |
| 参数无法确定 (D9) | ✅ **降级** | `param_uncertain` | 采用最坏假设 |
| 规则文件缺失 (D10/D11) | ⚠️ **中断** | — | 无法执行规则匹配 |
| 脚本内部崩溃 (D12) | ⚠️ **中断** | — | 检查日志，重试 |
| 单批 LLM 失败 (D13) | ✅ **降级** | `llm_timeout` | 跳过该批，继续其他 |
| 全部 LLM 失败 (D14) | ⚠️ **中断** | — | 无可用分析结果 |
| LLM 输出非法 (D15) | ⚠️ **中断** | — | dump 原始数据 |
| 报告生成失败 (D16) | ⚠️ **中断** | — | dump 中间文件 |

---

## MUST DO

1. **必须优先调用 `run_review.py`**：除非排查单阶段故障，不要手工拼接多阶段管道。
2. **必须固定 `$RUN_ID` 和 `$WORK_DIR`**：同一次审查的所有产物必须可追溯。
3. **必须校验最终报告 schema**：至少检查 `report_id/context/gate/findings/review_checklist/degradation_notes`。
4. **DML 的 EXPLAIN 必须先走 `dml_to_select_proxy.py` 转换**：由 `run_review.py` 自动完成。
5. **调用链断裂、EXPLAIN 不可用、参数不确定必须进入复查清单或 finding 字段**：不可静默忽略。
6. **最终风险等级不得输出 `UNCERTAIN`**：`UNCERTAIN` 只允许作为中间阶段信号。
7. **完成代码或规则调整后必须运行 `bash tests/run.sh`**：端到端测试不通过不得声称完成。

## MUST NOT DO

1. **禁止自由发挥分析 SQL**：所有风险判断必须基于 EXPLAIN 结果 + 静态规则 + 调用链上下文三条依据
2. **禁止绕过静态规则直接判风险**：即使肉眼看出问题，也必须通过 `match_rules.py` 确认
3. **禁止在无 EXPLAIN 结果时编造 EXPLAIN 数据**：降级标记 `explain_unavailable`，不可虚构 type/key/rows
4. **禁止覆盖已有的 `$WORK_DIR` 文件**：每次运行使用新的 `RUN_ID`
5. **禁止修改 `references/rules/rules.json` 中的规则**：规则变更属于独立流程，不在审查管道内
6. **禁止在 `SKILL.md` 内继续堆叠长篇内联编排代码**：新增机械流程应进入 `scripts/` 并补测试

---

## 输出格式

最终报告输出到 `$WORK_DIR/phase5_report.json`，格式参考 `references/report-schema.md`。

**终端输出**（本地模式）：

```
**SQL 总计: XX 条 | CRITICAL: X 条 | HIGH: X 条 | MEDIUM: X 条 | LOW: X 条 | PASS: X 条**

| SQL ID | 文件 | 行 | 风险 | 问题 | 修改建议 |
|--------|------|----|------|------|----------|
| `sqlId` | XxxMapper.xml | 123 | **HIGH** | 一句话描述 | 具体建议 |
| `sqlId` | XxxMapper.xml | 456 | **MEDIUM** | 一句话描述 | 具体建议 |
```

**门禁结论**（CI 模式）：
- `CRITICAL`、`HIGH` 或 `MEDIUM` 存在 → **BLOCK**
- 仅 `LOW` / `PASS` → **PASS**
