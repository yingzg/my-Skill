# SQL Review Skill — 问题清单（Problems Inventory）

> **生成方式**：逐文件精读 `SKILL.md`、`scripts/` 全部 11 个脚本、`references/` 全部文件、`docs/`（spec v1→v4 / data-contracts / scripts-spec / references-design）、`tests/`（run.sh / expected / fixtures）后，将「代码实际行为」与「设计文档承诺」逐条对照得出。
>
> **结论定性**：当前工具是 **spec v4 的「确定性 MVP 子集」**——三层架构与确定性管道已落地，但「动态执行轨（真实 EXPLAIN）」未实现，多个 spec 设计点（分批、预筛、LLM 深度分析）停留在文档，且存在若干数据链路断裂的 bug。**作为「生产试用/面试演示」当前不可用**，需按本文优先级修复。

---

## 严重度定义

| 级别 | 含义 |
|------|------|
| 🔴 P0 | 阻断性：核心能力缺失或数据错误，工具在目标场景下不可用 |
| 🟠 P1 | 高：主要功能缺陷或 bug，显著影响结果正确性/可用性 |
| 🟡 P2 | 中：次要缺陷、性能优化、文档不一致 |
| 🟢 P3 | 低：代码卫生、可维护性 |

---

## 一、问题总览表

| # | 问题 | 类别 | 严重度 | 一句话根因 |
|---|------|------|:---:|------|
| A1 | 真实数据库 EXPLAIN 未实现 | 功能缺失 | 🔴 P0 | execute_explain 只有 dry-run mock，无连接代码 |
| A2 | discover_datasource 未接入主流程 | 功能缺失 | 🟠 P1 | run_review.py 从不调用它，datasource 恒 UNKNOWN |
| A3 | LLM 深度分析未内联 | 功能缺失 | 🟠 P1 | 真实路径还原 + 风险定性只在 spec/`--mode resolve` 留口子 |
| A4 | 降级矩阵未在编排层落地 | 功能缺失 | 🟠 P1 | run_review `_run` 遇非 0 直接 raise，无查表降级 |
| A5 | 分批策略（AD10）未实现 | 功能缺失 | 🟡 P2 | main_table 提取了但没用，全量一次性 EXPLAIN |
| A6 | 两阶段预筛（AD11）未实现 | 功能缺失 | 🟡 P2 | match_rules 只输出 overall_risk，无分流 |
| A7 | CI 模式 MR 评论回贴未实现 | 功能缺失 | 🟡 P2 | build_report 仅存 mr_url 到 context |
| B1 | 4 条 static 规则永不命中 | 实现缺陷 | 🔴 P0 | match_rules 只实现 regex/regex_absence，static 无 pattern |
| B2 | 规则匹配对象错误 | 实现缺陷 | 🟠 P1 | 匹配 raw_sql（含 `<if>` 标签），而非 resolved_sql |
| B3 | 报告数据链路断裂 | 实现缺陷 | 🟠 P1 | file_path/line/resolved_sql 未从 parse→match→report 传递 |
| B4 | 修复建议模板未传递 | 实现缺陷 | 🟠 P1 | rules.json 模板未带出，short/long_term_fix 恒为空 |
| B5 | 行号恒为 0 | 实现缺陷 | 🟡 P2 | xml.etree 拿不到行号，line 写死 0 |
| B6 | rule dict 被临时污染 | 实现缺陷 | 🟢 P3 | `rule["_stmt_type"]` 就地修改，逻辑隐晦 |
| C1 | data-contracts.md 非权威 | 文档不一致 | 🟡 P2 | 自述「保留早期设计，不作为当前契约」 |
| C2 | report-schema explain 段与实现不符 | 文档不一致 | 🟡 P2 | schema 复杂结构 vs 实际简单字段 |
| C3 | 门禁阈值文档不符 | 文档不一致 | 🟡 P2 | schema 说 MEDIUM=WARN，代码硬编码 BLOCK |
| C4 | scripts-spec 多处与实现不符 | 文档不一致 | 🟡 P2 | foreach 展开/line_start/匹配对象三处偏差 |
| C5 | rules.json 与 spec v4 规则体系不一致 | 文档不一致 | 🟡 P2 | 规则数量/编号/字段名均不同 |

---

## 二、分类详述

### A. 功能缺失（设计有、代码没实现）

#### A1 ✅ 真实数据库 EXPLAIN 已实现（阶段 2）

- **现象**（已修复）：`scripts/execute_explain.py` 只有 `--dry-run` 走 `MOCK_EXPLAIN` 硬编码字典，非 dry-run 时无真实连接代码。
- **实现**：接入 Google Toolbox for Databases（`--prebuilt mysql --stdio`），内置最小 MCP stdio 客户端 `ToolboxMcp`，对每条 SQL 执行 `EXPLAIN FORMAT=JSON` 并解析 `access_type/key/rows/extra`（`_extract_explain_fields`）。凭据走 `MYSQL_HOST/PORT/USER/PASSWORD/DATABASE` 环境变量；未配置凭据或连接失败（30s 超时）自动降级为 `explain_unavailable`（`executed: false`）；保留 `--dry-run` 作测试通道。
- **待验证**：`_extract_explain_fields` 对 MySQL `EXPLAIN FORMAT=JSON` 真实输出的字段提取（含 `{"EXPLAIN": "<json string>"}` 包装形态）需在配置真实库后实测校准。

#### A2 ✅ discover_datasource 已接入主流程（阶段 2）

- **现象**（已修复）：`run_review.py` 从未调用 `discover_datasource.py`，datasource 恒为 UNKNOWN。
- **实现**：`discover_datasource.py` 增加 `--project-src` 参数（java/resources 目录随 project-src 推导）；`run_review.py` 在 parse 前调用它，把 `--datasource-map` 传给 `parse_mapper.py`，映射落盘为 `phase0_5_datasource.json`。
- **待验证**：真实项目（含 @DS/@MapperScan）上验证「Mapper 包 → 数据源名」解析；多数据源下 execute_explain 目前仍只支持单库（MYSQL_* 环境变量），多库凭据映射留待 A5 分批时一并解决。

#### A3 ✅ LLM 深度分析已实现（Phase 3 + Phase 4b）

- **Phase 3 真实路径还原**：`llm_resolve.py` 对 `needs_llm` 的动态 SQL，LLM 基于调用链判断 `<if>/<choose>` 条件激活状态，还原真实执行的 SQL（AD1）。
- **Phase 4b 风险定性**：`llm_risk_analysis.py` 合并规则 + EXPLAIN + 调用链，LLM 生成自然语言风险描述 + 分级修复建议（AD14）。
- **降级**：未配置 `LLM_API_KEY` 或 LLM 失败时，自动降级为确定性分析（optimistic 展开 + 规则风险等级）。

#### A4 ✅ 降级矩阵已确认落地方式（阶段 2）

- **现象**（重新定性）：`run_review.py` 的 `_run()` 遇非 0 直接 `raise`。经分析，脚本内部已承担主要降级——discover/trace/explain/resolve 均「恒 exit 0 + 内部标记降级」（parse 跳过失败文件、trace 断链 `complete:false`、explain `executed:false`、discover `status=UNKNOWN`）。`_run` 的非 0 只发生在「应中断」场景（parse 全失败 D3、规则缺失 D10/D11、报告输入缺失 D16），此时 raise 是正确行为。
- **实现**：`_run()` 错误信息增加降级矩阵场景标注（`SCRIPT_DEGRADATION` 映射脚本名 → D 编号），失败时输出如「Command failed (1) D10/D11 (规则文件)」，便于对照 `degradation-matrix.md` 查表。

#### A5 ✅ 分批策略已实现（LLM 批间并发）

- **实现**：`llm_risk_analysis.py` 按 `BATCH_SIZE=8` 分批，每批一次 LLM 调用；单批失败降级，其余批继续。
- **备注**：「按数据源分组」的多库维度仍需多库凭据配置（当前单库 `MYSQL_*`），属未来扩展。

#### A6 ✅ 两阶段预筛已实现

- **实现**：`llm_risk_analysis.py` 中，静态规则判 LOW/PASS 的 SQL 走快速通道（0 次 LLM），HIGH/MEDIUM/UNCERTAIN 走深度分析（调 LLM）。

#### A7 ✅ CI 门禁已闭环（阶段 3）：GATE 输出 + MR 评论生成 + 回贴说明

- **已实现**：`build_report.py` 在 `--mode ci` 时向 stdout 输出 `GATE: PASS/BLOCK`；`_format_mr_comment()` 生成 markdown 评论（门禁结论 + 统计 + 风险明细表），`--mr-comment-output` 落盘；SKILL.md 记录了「读 mr-comment.md → 调 gitlab MCP `create_merge_request_note` 回贴」的运行时步骤。

---

### B. 实现缺陷（代码 bug / 逻辑错误）

#### B1 ✅ 4 条 static 规则已修复（阶段 1）

- **现象**：`references/rules/rules.json` 中 R009（ORDER BY 非索引）、R010（笛卡尔积 JOIN）、R101（缺失软删除状态守卫）、R104（DELETE 替代方案评估）使用 `"match": {"method": "static", "check": "..."}`，**没有 `pattern` 字段**。而 `match_rules.py` 的 `match_rule()`（第 56-71 行）只处理 `regex` / `regex_absence` 两种 method，且先判 `if not pattern: return (False, "NONE")` → 这 4 条规则**永远返回未命中**。
- **影响**：R101「软删除状态守卫」是数据安全规则（UPDATE/DELETE 漏加 `status=0` 会误改已删数据），漏检有真实风险。4/15 条规则形同虚设。
- **修复方向**：为 `static` method 实现对应检测逻辑（正则也能表达大部分：如「WHERE 中无 status_code/is_deleted」用 regex_absence；「DELETE 存在」用 regex；笛卡尔积/ORDER BY 需结合 EXPLAIN 或更复杂解析，可先降级为「不匹配」或改造成 regex）。

#### B2 ✅ 规则匹配对象已修复（阶段 1）

- **现象**：`match_rules.py` 第 119 行 `sql_text = sql_entry.get("raw_sql", "")`——匹配的是**含 `<if>` 标签的原始 SQL 文本**，而非 `resolved_sql`/`proxy_sql`。spec §8.7 明确「对 proxy_sql（DML）或 resolved_sql（SELECT）执行匹配」。
- **影响**：动态 SQL 中 `<if>` 标签文本可能干扰正则可读性/匹配（如 R007 无 WHERE 检测 `\bWHERE\b`，被 `<if>` 包裹的条件文本会误导）；乐观展开后实际执行的 SQL 与匹配文本不一致。
- **修复方向**：让 match_rules 消费 `resolved_sql`（SELECT）和 `proxy_sql`（DML），与 resolve 阶段产物对齐。

#### B3 ✅ 报告数据链路已修复（阶段 1）

- **现象**：`match_rules.py` 输出不含 `file_path`/`line`/`resolved_sql`，`build_report.py` 从 rules 文件读这些字段 → 全部为空。`tests/expected/report-output.json` 证实：每条 finding 的 `file_path=""`、`line=0`、`resolved_sql=""`。
- **根因**：parse_mapper 产出 file/raw_sql，但中间 match_rules 没透传，build_report 拿不到。
- **影响**：最终报告**无法定位到具体文件行号、看不到实际 SQL**，报告可用性大打折扣。
- **修复方向**：让 match_rules 输出透传 `file_path`/`line`/`resolved_sql`（从 batch 输入的 parsed 字段携带），build_report 直接消费。

#### B4 ✅ 修复建议模板已传递（阶段 1）

- **现象**：rules.json 每条规则有 `short_term_fix_template` / `long_term_fix_template`，但 match_rules.py 只输出 `rule_id/matched/severity`，不输出模板；build_report 拿不到 → 报告 `short_term_fix`/`long_term_fix` 恒为空（report-output.json 里大量 `""`）。
- **影响**：spec 宣称的核心能力「分级修复建议」未兑现，报告只有「命中 R002」却没有「该怎么改」。
- **修复方向**：match_rules 命中时附带该规则的 fix_template；build_report 合并时填充。这是 A3 的确定性替代方案——不依赖 LLM 就能给出建议。

#### B5 ✅ 行号已修复（阶段 1，文本定位法）

- **现象**：`parse_mapper.py` 第 127-128 行 `"line_start": 0, "line_end": 0`，注释承认 xml.etree 拿不到行号。
- **影响**：报告无法定位到行号（与 B3 叠加）。
- **修复方向**：改用 `lxml`（支持 `sourceline`）或解析后二次定位（在原始文件里找 SQL 片段的首行）。

#### B6 ✅ rule dict 污染已修复（阶段 1，显式传参）

- **现象**：`match_rules.py` main 里 `rule["_stmt_type"] = stmt_type` 就地改规则对象，`match_rule()` 里 `rule.get("_stmt_type", "SELECT")` 读回。隐式状态传递，违反「脚本无隐藏状态」原则。
- **影响**：可维护性差，易埋雷（如未来并发/复用 rules 对象）。
- **修复方向**：把 stmt_type 作为 `match_rule()` 的显式参数传入，不污染 rule dict。

---

### C. 文档不一致（设计文档 vs 实现）

#### C1 ✅ data-contracts.md 顶部已标注权威文档

- **现象**：文件顶部自述「本文保留早期设计思路，不作为当前实现的权威契约」。但它是 docs 里最详尽的「数据流」文档。
- **影响**：读者（含面试官/未来的你）无法分辨哪份文档可信。
- **修复方向**：明确标注权威文档（report-schema.md + scripts-spec.md + run_review.py + tests/expected），或直接更新 data-contracts 至与实现一致。

#### C2 ✅ report-schema.md explain 段已修正（阶段 3）

- **现象**：report-schema.md §三 定义 phase4b_explain.json 为复杂结构（explain_raw_table/explain_raw_json/explain_parsed/proxy_sql/original_sql/statement_type），但 execute_explain.py 实际输出简单结构（sql_id/executed/type/key/key_len/rows/extra/raw_explain/error）。
- **修复方向**：以实现为准更新 schema，或让实现对齐 schema。

#### C3 ✅ 门禁阈值文档已修正（阶段 3，MEDIUM=BLOCK）

- **现象**：report-schema.md §一 说「MEDIUM 默认 WARN（可配置为 BLOCK）」，但 `build_report.py` `_gate_decision()` 硬编码 `lvl >= MEDIUM → BLOCK`。
- **修复方向**：统一为「MEDIUM 即 BLOCK」（与 SKILL.md、spec AD6 一致），修正 schema 表述。

#### C4 ✅ scripts-spec.md 已修正（阶段 3）

- **现象**：① §5.3 说 foreach 展开为 `(?, ?, ...)`，实际 `_process_foreach` 只产出一个 `?`（open+body+close，不迭代）；② §3.5 说 line_start 有值，实际恒 0；③ §8.7 说匹配 resolved_sql/proxy_sql，实际 raw_sql。
- **修复方向**：修正 scripts-spec 三处，或以实现为准更新。

#### C5 ✅ 已记录落地变更（阶段 3，spec v4 §12 加落地说明）

- **现象**：spec v4 §12 称「通用规则 40+ 条 + DML 专属 7 条（R101-R107）」；实际 rules.json 仅 15 条（R001-R011 + R101-R104），且字段名不同（`rule_id`→`id`、`type`→`method`、`short_term_fix`→`short_term_fix_template`）。spec 里的「R002 缺失 WHERE + severity_by_type」示例在最终 rules.json 中拆成了 R007/R102 两条独立规则。
- **性质**：属正常的历史演进（spec 是草案，rules.json 是落地），但需在文档里记录这个变更，避免面试/复盘时混淆。

---

## 三、修复优先级路线图（建议）

### 阶段 1 —— 让「确定性管道」正确可用（P0，先做）

| 顺序 | 问题 | 目标 |
|:---:|------|------|
| 1 | B1 静态规则 | 让 4 条 static 规则真正生效（或改造成 regex） |
| 2 | B2 匹配对象 | 规则匹配改用 resolved_sql/proxy_sql |
| 3 | B3 数据链路 | 报告补上 file_path / line / resolved_sql |
| 4 | B4 修复建议 | 用 rules.json 模板填充 short/long_term_fix |

> 这 4 项是**纯确定性、无外部依赖**的 bug 修复，做完后报告就能「定位到行 + 看到 SQL + 给出建议」，本地自查基本可用。

### 阶段 2 —— 补上「动态执行轨」（P1，核心能力）

| 顺序 | 问题 | 目标 |
|:---:|------|------|
| 5 | A1 真实 EXPLAIN | 接入真实 MySQL 连接，执行 EXPLAIN FORMAT=JSON |
| 6 | A2 数据源发现 | discover_datasource 接入主流程，实现多数据源映射 |
| 7 | A4 降级矩阵 | run_review.py 实现降级继续，而非遇错即中断 |

> 这 3 项让「EXPLAIN 执行」真正落地，工具从「静态规则扫描器」升级为「静态+动态双轨分析」。是「生产试用」的准入门槛。

### 阶段 3 —— 完善与对齐（P2）

| 顺序 | 问题 | 目标 |
|:---:|------|------|
| 8 | A5/A6 分批 + 预筛 | 大批量 SQL 性能优化 |
| 9 | A7 CI 回贴 | CI 门禁场景闭环 |
| 10 | A3 LLM 深度分析 | 真实路径还原 + 风险叙事（成本最高，最后做） |
| 11 | B5/B6 + C1-C5 | 行号、代码卫生、文档对齐 |

---

## 四、待确认的开放问题（进入讨论阶段前需要你拍板）

> 注：以下三个问题均已在后续讨论中解决——① A1 凭据走 toolbox MCP（环境变量 `MYSQL_*`）；② A3 已引入 LLM（脚本内调 API，见 spec v5 AD17）；③ 阶段 1 已全部完成。

1. ~~**A1 真实 EXPLAIN 的数据源凭据来源**~~ → 已定：toolbox MCP（`--prebuilt mysql --stdio`）+ 环境变量 `MYSQL_HOST/PORT/USER/PASSWORD/DATABASE`。
2. ~~**A3 LLM 深度分析的取舍**~~ → 已定：引入 LLM，脚本内调 OpenAI-compatible API（DeepSeek 默认，可切 MiMo）。
3. ~~**阶段 1 的 4 项 bug 修复**~~ → 已完成。

---

## 五、性能问题（真实环境验证发现，第二轮修复）

> 第一轮修复完成后，用真实 MR#2（10 个 Mapper XML、61 条 SQL）+ 真实 MySQL + DeepSeek 做端到端验证，发现三个性能/正确性问题，导致 CI 时长 5m53s、EXPLAIN 大量失败、LLM 被全量调用。第二轮修复后降至 11.2s。详见 spec v5。

### P1 🔴 EXPLAIN 参数化缺失（`?` 无法 EXPLAIN）—— 已修复

- **现象**：`resolve_dynamic_sql.py` 把 `#{param}` 替换为 `?`（JDBC 占位符），但 MySQL EXPLAIN 不认 `?`，报 `Error 1064`。真实验证 60/61 条 EXPLAIN 失败（唯一成功的是无参数的 `WHERE region != ''`）。
- **根因**：spec AD2「必须 EXPLAIN」设计时未考虑参数化后的 `?` 无法 EXPLAIN。
- **修改方案**：新增 `discover_schema.py` 获取表 DDL（字段类型）；`execute_explain.py` 加 `_explain_sql()`，EXPLAIN 前用 DDL 把 `?` 按列类型替换——数字列（bigint/int/tinyint…）→ `1`，字符串列（varchar/char/text…）→ `'x'`，日期列（datetime/date）→ `'2024-01-01'`，其余兜底 `1`。替换策略：先按「列 = ?」模式查 DDL 精确替换，剩余 `?` 兜底。
- **验证**：真实 EXPLAIN 从 1/61 → 10/10 成功（`type=const, key=PRIMARY`）。

### P2 🔴 规则误报导致预筛失效（0 条 LOW/PASS，全部走 LLM）—— 已修复

- **现象**：真实验证 61 条 SQL 全部是 MEDIUM/HIGH/UNCERTAIN，A6 预筛完全失效，61 条全走 LLM。根因是规则误报：
  - **R006 隐式转换**：pattern `[=<>]\s*\d+` 把 `del_flag = 0`（tinyint 数字列 = 数字，完全正常）误判，命中 36 次。
  - **R101 软删除守卫**：只认 `status_code/is_deleted/statecode`，项目用 `del_flag` 做软删除标记，误报 20 次。
  - **R002 缺失 LIMIT**：把主键等值查询（`WHERE id = ?`）误判（主键查询最多 1 行，不需要 LIMIT）。
- **根因**：静态规则是纯 regex、无 schema 信息，无法判断列类型/主键/软删除字段名，必然误报。
- **修改方案**：
  1. 新增 `discover_schema.py` 获取表 DDL（`SHOW CREATE TABLE` → 字段类型/主键/索引）；
  2. `match_rules.py` 加 schema 感知——`exempt.method = "schema_pk_eq_query"`（R002 主键豁免）+ `match.method = "schema_column_eq_number"`（R006 用 DDL 判断「字符串列 = 数字」才是真隐式转换）；
  3. R101 字段名扩展（`del_flag/deleted/is_del/delete_flag` 等）；
  4. `llm_risk_analysis.py` 预筛语义修正——UNCERTAIN（无规则命中）用 EXPLAIN 判断：`type∈{const,eq_ref,ref,range}`（索引查询）→ fast；`type∈{ALL,index}`（全扫描）或失败 → deep。
- **验证**：10 条 selectById 全部走 fast 通道，0 次 LLM。

### P3 🟠 审查范围过大（文件级 diff）—— 已修复

- **现象**：MR 只改 10 个 selectById，但 `extract_changes.py` 是文件级 diff，`parse_mapper.py` 解析整个文件 61 条 SQL（含未改的 selectList/insert/update）。
- **根因**：spec AD4「分析范围 = MR diff + 项目分支全量代码」是文件级设计，未收敛到 SQL 块级。
- **修改方案**：`extract_changes.py` 用 `git diff --unified=0` 定位变更行，向上映射到所属 `<select id="xxx">` 块，输出 `files[].changed_statements`；`parse_mapper.py` 加 `--only-statements` 只解析变更的 statement；`run_review.py` 加 `--changed-statements` 透传。
- **验证**：审查 SQL 从 61 → 10 条。

### 第二轮性能结果（真实 MR#2）

| 指标 | 优化前 | 优化后 |
|------|--------|--------|
| 审查 SQL 数 | 61 | 10 |
| EXPLAIN 成功率 | 1/61 | 10/10 |
| LLM 调用次数 | 11 批 | 0 |
| 门禁结论 | BLOCK（误拦） | PASS（正确） |
| 总耗时 | 5m53s | 11.2s |

### 第二轮新增/修改文件

**新增（5 个）**：`db_client.py`（ToolboxMcp 提取）、`discover_schema.py`（DDL 获取）、`llm_client.py`（LLM API 客户端）、`llm_resolve.py`（Phase 3）、`llm_risk_analysis.py`（Phase 4b）

**修改（7 个）**：`extract_changes.py`（块级 diff）、`parse_mapper.py`（--only-statements）、`match_rules.py`（schema 感知）、`execute_explain.py`（参数化 + db_client 重构）、`run_review.py`（集成）、`rules.json`（exempt/schema 方法/字段扩展）、`resolve_dynamic_sql.py`（finalize 加 HTML 实体）

---

## 六、第三轮问题（Code Review 复查发现，2026-09-08）

> 第二轮修复完成后，对「代码 vs 设计文档 vs 问题清单」做了一轮逐项 Code Review，确认前两轮问题**绝大部分已真实落地**，同时发现以下新问题。按严重度分级，本轮目标是把「确定性管道」打磨到可生产试用。

### 第三轮问题总览表

| # | 问题 | 类别 | 严重度 | 一句话根因 |
|---|------|------|:---:|------|
| D1 | schema 感知跨表混淆 | 实现缺陷 | 🔴 P0 | `_is_pk_eq_query`/`_check_string_column_eq_number`/`_find_column_type` 遍历所有表 schema，不关联 SQL 实际涉及的表 |
| D2 | db_client 硬编码 toolbox 路径 | 实现缺陷 | 🔴 P0 | `TOOLBOX_BIN` 默认值写死 `/root/.claude/bin/toolbox`，跨机器/跨用户失效 |
| D3 | execute_explain run_id 硬编码 | 实现缺陷 | 🟠 P1 | payload 写死 `"run_id": "golden"`，脚本无 `--run-id` 参数 |
| D4 | resolve_dynamic_sql needs_llm 误判 | 实现缺陷 | 🟠 P1 | `needs_llm` 把可确定性处理的 where/foreach/bind 也算进 LLM 条件 |
| D5 | 新增 5 脚本零测试覆盖 | 工程缺口 | 🟠 P1 | discover_schema/db_client/llm_* 无 golden，schema 感知逻辑不可回归 |
| D6 | discover_schema DDL 解析覆盖不全 | 实现缺陷 | 🟡 P2 | 类型白名单缺 bit/json/blob/enum/set 等；复合主键只取第一列 |
| D7 | R101 软删除守卫本质缺陷 | 实现缺陷 | 🟡 P2 | regex_absence 无法判断「字段在 SET 还是 WHERE」「表是否真有软删除字段」，字段扩展只缓解 |
| D8 | D16 dump 未实现 | 文档不一致 | 🟡 P2 | 文档声称转存 `/tmp/sql-review-dump/`，代码无此逻辑且 build_report 无 schema 校验 |
| D9 | SKILL.md 硬编码绝对路径 | 代码卫生 | 🟡 P2 | `SCRIPTS="/mnt/g/my-Skill/..."` 写死本机挂载路径 |
| D10 | 复盘记录数据契约缺失 | 功能缺失 | 🟡 P2 | parse 失败只打 stderr，`run_review._run` 在 exit 0 时丢弃 stderr，失败 SQL 完全不可见 |
| D11 | run.sh 缺负向测试用例 | 工程缺口 | 🟡 P2 | 14 个测试全是正向 golden 对比，无「解析失败优雅降级」用例 |
| D12 | .gitignore 未忽略 __pycache__ | 代码卫生 | 🟢 P3 | `.pyc` 二进制进入版本库 |

### D1 🔴 schema 感知跨表混淆

- **现象**：`match_rules.py` 的 `_is_pk_eq_query`/`_check_string_column_eq_number` 与 `execute_explain.py` 的 `_find_column_type` 都遍历「所有表的 schema 并集」，不关联 SQL 实际涉及的表。
- **反例**：`SELECT * FROM orders WHERE user_id = ?`（`user_id` 是 `users` 表主键、`orders` 表外键）会被误判为「主键等值查询」，从而被 R002（缺失 LIMIT）错误豁免。
- **修复方向**：给辅助函数传入该 SQL 的 `main_table`（`run_review._merge_records` 已产出此字段），采用「主表优先 + 全局唯一兜底（多表同名不同型则返回 None）」两段式。

### D2 🔴 db_client 硬编码 toolbox 路径

- **现象**：`db_client.py` `TOOLBOX_BIN = os.environ.get("TOOLBOX_BIN", "/root/.claude/bin/toolbox")`，默认值写死 root 用户路径。
- **修复方向**：`shutil.which("toolbox")`（PATH 探测）+ `os.path.expanduser("~/.claude/bin/toolbox")`（用户级兜底）多级 fallback，找不到时抛清晰错误（对齐降级矩阵 D17）。

### D3 🟠 execute_explain run_id 硬编码

- **现象**：`execute_explain.py` 输出 payload 写死 `"run_id": "golden"`，且无 `--run-id` 参数，与 `match_rules.py`/`build_report.py` 不一致。
- **修复方向**：加 `--run-id`（默认 `golden` 保持测试兼容），`run_review.py` 调用时透传。

### D4 🟠 resolve_dynamic_sql needs_llm 误判

- **现象**：`needs_llm = (len(unresolved) > 0 or (dynamic_tags and len(dynamic_tags) > 0))`，而 `dynamic_tags` 含 where/foreach/bind/include 等**可确定性处理**的标签，导致只有 `<where>` 的 SQL 也误触发 LLM。
- **修复方向**：`needs_llm = len(unresolved) > 0`（`unresolved` 只含 `<if>/<choose>` 残留）。

### D5 🟠 新增 5 脚本零测试覆盖

- **现象**：`tests/run.sh` 未覆盖 `db_client.py`/`discover_schema.py`/`llm_client.py`/`llm_resolve.py`/`llm_risk_analysis.py`，也未覆盖 `match_rules.py --schema-file` 分支。
- **修复方向**：补 4 个纯离线测试（parse_create_table、主键豁免、隐式转换、跨表回归）。

### D6 🟡 discover_schema DDL 解析覆盖不全

- **现象**：`COLUMN_TYPE_RE` 类型白名单缺 `bit/json/blob/enum/set/year/time`；`PRIMARY_KEY_RE` 对复合主键只取第一列。
- **修复方向**：扩展白名单，`enum` 归入「字符串类」；复合主键解析全部列。

### D7 ✅ R101 软删除守卫本质缺陷（已修复）

- **现象**：R101 用 `regex_absence` 判断「SQL 里是否出现软删除字段名」，无法判断「字段出现在 SET 还是 WHERE」，也无视「表是否真有软删除字段」——日志表/配置表/流水表本无软删除字段，做 UPDATE/DELETE 是正常的，却被一律误报为「缺失软删除守卫」。
- **修复**：R101 改为 schema 感知方法 `schema_soft_delete_guard`。命中条件收紧为「表确实含软删除字段（DDL columns 命中）**且** WHERE 子句未引用该字段」；表无软删除字段、或 WHERE 已含守卫、或无 schema（dry-run）时均不命中，从根上消除误报。

### D8 🟡 D16 dump 未实现

- **现象**：`scripts-spec.md` §10.8 与 `degradation-matrix.md` D16 声称「校验失败转存 `/tmp/sql-review-dump/`」，但 `build_report.py` 无 schema 校验、无 dump 逻辑，且中间文件本就在 `$WORK_DIR` 里，再 dump 一份是冗余。
- **修复方向**：把 D16 语义从「转存 dump 目录」改为「中断时保留 `$WORK_DIR` 并打印路径」，删除文档中从未实现的 dump 目录引用。

### D9 🟡 SKILL.md 硬编码绝对路径

- **现象**：`SKILL.md` Step 0 的 `SCRIPTS="/mnt/g/my-Skill/Skill/sql-review/scripts"` 写死本机挂载路径。
- **修复方向**：改为 `SCRIPTS="$(cd "$(dirname "$0")" && pwd)/scripts"` 相对推导。

### D10 🟡 复盘记录数据契约缺失

- **现象**：`parse_mapper.py` 解析失败时只 `print(... file=sys.stderr)`，`run_review._run` 在 exit 0 时**丢弃 stderr**，导致「被跳过的失败 SQL」在最终报告里完全不可见，人工无法复盘、也无法转录到 fixture 测试库。
- **修复方向**：`parse_mapper.py` 加 `--parse-errors-output`，失败时结构化落盘（含 `raw_fragment` 原始片段 + error）；`run_review.py` 读入并写入 `phase5_report.json` 的 `review_checklist`（tag=parse_error）。

### D11 🟡 run.sh 缺负向测试用例

- **现象**：14 个测试全是「合法写法 → 正向 golden 对比」，无「解析失败优雅降级」用例。
- **修复方向**：加 `run_test_negative`（断言 exit 0 + 输出含降级标记）+ 一个 broken fixture 文件。

### D12 🟢 .gitignore 未忽略 __pycache__

- **现象**：仓库跟踪了 `scripts/__pycache__/*.pyc`，新生成 `.pyc` 也是 untracked 噪音。
- **修复方向**：`.gitignore` 加 `**/__pycache__/`、`*.pyc`。

### 第三轮修复路线图

| 顺序 | 问题 | 目标 |
|:---:|------|------|
| 1 | D2/D3/D4 | 硬编码 + needs_llm 误判（纯 bug，先做） |
| 2 | D1 | schema 感知跨表混淆（主表优先 + 兜底） |
| 3 | D6 | DDL 类型白名单 + 复合主键 |
| 4 | D10 | 复盘记录数据契约（parse-errors 落盘 + 进报告） |
| 5 | D8/D9 | D16 语义修正 + SKILL.md 路径相对化 |
| 6 | D5/D11 | 补测试 + 负向用例 |
| 7 | D7 | R101 语义根治（遗留，依赖 D6 完成后） |
| 8 | D12 | .gitignore 卫生 |

### 第三轮修复状态（2026-09-08 完成）

| # | 状态 | 说明 |
|---|:---:|------|
| D1 | ✅ 已修复 | `match_rules.py`/`execute_explain.py` 改「主表优先 + 全局唯一兜底」，`match_rule()`/`_explain_sql()` 显式传 `main_table` |
| D2 | ✅ 已修复 | `db_client.py` 改 `shutil.which` + `~/.claude/bin/toolbox` 多级 fallback，找不到时抛清晰错误 |
| D3 | ✅ 已修复 | `execute_explain.py` 加 `--run-id`，`run_review.py` 透传 |
| D4 | ✅ 已修复 | `needs_llm = len(unresolved) > 0`；顺带修复了「静态 SQL needs_llm 输出 `[]` 而非 `false`」的类型 bug（golden 已更新） |
| D5 | ✅ 已修复 | `tests/run.sh` 新增 Test 13（parse_create_table）、Test 14（schema 感知 + 跨表回归）、Test 15（负向用例） |
| D6 | ✅ 已修复 | 类型白名单补 bit/json/blob/enum/set/year/time 等；`enum`/`set` 归字符串类；复合主键解析出 `primary_keys` |
| D7 | ✅ 已修复 | R101 改 `schema_soft_delete_guard`：仅「表含软删除字段 且 WHERE 未引用」才命中，消除无软删除字段表的误报 |
| D8 | ✅ 已修复 | D16 语义改为「保留 `$WORK_DIR` 并打印路径」，删除 `/tmp/sql-review-dump/` 引用 |
| D9 | ✅ 已修复 | SKILL.md `SCRIPTS` 改为 `/path/to/...` 占位符 + 注释 |
| D10 | ✅ 已修复 | `parse_mapper.py` 加 `--parse-errors-output`（带 `raw_fragment`），`run_review.py` 读入并写入报告 `review_checklist`（tag=parse_error） |
| D11 | ✅ 已修复 | Test 15 验证「broken XML 跳过 + 失败记录落盘」 |
| D12 | ✅ 已修复 | `.gitignore` 加 `**/__pycache__/`、`*.pyc` |

**验证**：`bash tests/run.sh` 17/17 通过；真实项目 `demo-scheme` 的 `DemoCommonMapper.xml`（13 条 SQL，含 CTE/with(nolock)/标量函数/子查询/多 JOIN）端到端 dry-run 通过，broken 文件降级 + 复盘记录落盘链路验证通过。

**遗留项**：`demo-scheme` 的调用链追踪需把 `--project-src` 指向跨模块源码才能追到 Controller（当前只扫 `demo-scheme-infra` 模块，属已知 trace 范围限制，非本轮问题）。

---

## 七、第四轮问题（CI 落地 + 端到端验证，2026-09-09）

> 这一轮把 skill 从「本地工具」落地成「CI 自动化」，并用真实 MR（demo-service !2）端到端验证。暴露的核心问题分两类：**设计缺陷导致 AI 偏离预设流程**（E1-E3）、**CI 落地与调试踩坑**（E4-E8）、**代码 bug**（E9-E11）。

### 第四轮问题总览表

| # | 问题 | 类别 | 严重度 | 一句话根因 |
|---|------|------|:---:|------|
| E1 | AI 偏离预设流程（手动 MR 场景） | 设计缺陷 | 🔴 P0 | SKILL.md 只定义 CI 自动化场景，缺「用户手动给 MR URL」工作流，AI 自由发挥 |
| E2 | dry-run 是干扰项 | 设计缺陷 | 🔴 P0 | dry-run 的 mock EXPLAIN 是假数据，却被列为生产审查选项 |
| E3 | 降级哲学太宽容 | 设计缺陷 | 🟠 P1 | 「缺凭据」被设计成「自动降级」，AI 没停下来问用户 |
| E4 | 回贴 MR 依赖 MCP | 架构缺陷 | 🟠 P1 | 回贴依赖 AI 运行时（MCP），与「CI 无人运行」前提矛盾 |
| E5 | post_mr_comment 认证优先级反转 | 代码 bug | 🔴 P0 | CI_JOB_TOKEN 优先于 GITLAB_TOKEN，但前者恒存在且只读，后者永远用不上 |
| E6 | GITLAB_TOKEN 配置成 Protected | 配置坑 | 🟠 P1 | MR pipeline 运行在非 protected ref，读不到 protected 变量 |
| E7 | GitLab include ref 冻结 | 平台机制 | 🟠 P1 | pipeline 创建时固定 include 的 commit sha，retry 不重新解析 |
| E8 | CI 模板没串 changed_statements | 架构缺陷 | 🔴 P0 | 块级 diff 链路在脚本里通，但 CI 模板只提取 files[].path |
| E9 | R101 软删除守卫误报（D7） | 代码 bug | 🟡 P2 | regex_absence 无法判断表是否真有软删除字段 |
| E10 | 401 提示代码丢失 | 工程卫生 | 🟡 P2 | 两个目录（my-Skill / my-skill-gitlab）不同步，cp 覆盖丢失改动 |
| E11 | run_review 从 stdout 读 report 崩溃 | 代码 bug | 🟠 P1 | ci 模式 build_report stdout 输出 GATE 非 JSON，_load_json 崩溃 |

### E1 🔴 AI 偏离预设流程（手动 MR 场景）

- **现象**：用户手动给 MR URL（`gitlab.com/.../merge_requests/2`）让 AI 检查慢 SQL，AI 的执行链是「clone 仓库 → dry-run → 手工读 DDL 修正 10 条 MEDIUM 误报 → 自定义 markdown 口头汇报」，**没回贴 MR、没输出模板化结果、还违反了 MUST NOT DO（禁止自由发挥/禁止绕过规则）**。
- **根因**：SKILL.md 只定义了「本地交互式」和「CI 自动化」两种模式，「回贴 MR」被绑定在「CI 模式」里，而 CI 模式又被描述为「CI job 无人运行」。用户手动给 MR URL 的场景，SKILL.md **没有任何指引**告诉 AI「应该走 CI 模式回贴」，AI 只能自由发挥。
- **解决方案**：① SKILL.md 明确「数据库凭据是必需前置，缺失即中断问用户」（E3）；② 移除 dry-run 生产模式（E2）；③ 回贴脚本化（E4）；④ 新增 MUST NOT DO「禁止手工修正管道结论」。

### E2 🔴 dry-run 是干扰项

- **现象**：dry-run 用写死的 `MOCK_EXPLAIN` 字典（`type=ALL, key=None, rows=10000`）返回假执行计划。AI 用它跑审查，产出「看似完整实则不可信」的结论，还逼得 AI 手工读 DDL 去「修正」误报。
- **根因**：dry-run 被设计成「本地无数据库时的审查选项」，但它产出的是假数据，不是降级。
- **解决方案**：dry-run 明确「仅用于 `tests/run.sh` 回归测试」（golden file 对比），**从生产审查流程移除**。生产审查必须真实 EXPLAIN，无凭据即中断问用户。

### E3 🟠 降级哲学太宽容

- **现象**：SKILL.md 把「缺数据库凭据」设计成「自动降级为静态规则分析」，导致 AI 没停下来问用户要凭据，直接走了 dry-run/降级。
- **根因**：「凭据缺失」是「可恢复的输入缺失」，应该中断索取，而不是「可接受的降级状态」。
- **解决方案**：SKILL.md 明确「数据库凭据是必需前置，缺失即中断问用户（本地）/ 检查 CI secret（CI）」，禁止静默降级。

### E4 🟠 回贴 MR 依赖 MCP

- **现象**：SKILL.md 写「调用 GitLab MCP 的 create_merge_request_note 回贴」，但 MCP 需要 AI 运行时，与 spec v5 AD17「CI job 无人运行」矛盾。
- **解决方案**：新增 `post_mr_comment.py`，脚本内用 `urllib` 调 GitLab REST API（`POST /projects/:id/merge_requests/:iid/notes`），与 AD17 精神一致。

### E5 🔴 post_mr_comment 认证优先级反转

- **现象**：`_resolve_auth()` 原本 `CI_JOB_TOKEN` 优先于 `GITLAB_TOKEN`。但 GitLab CI 环境里 `CI_JOB_TOKEN` **恒存在且只读**，导致 `GITLAB_TOKEN`（PAT，有写权限）**永远被跳过**，回贴恒 401。
- **根因**：误以为「内置变量优先」是合理默认，忽略了 CI_JOB_TOKEN 的只读特性。
- **解决方案**：优先级反转——`GITLAB_TOKEN`（PRIVATE-TOKEN，PAT 需 api scope）优先，`CI_JOB_TOKEN`（JOB-TOKEN，只读）兜底。

### E6 🟠 GITLAB_TOKEN 配置成 Protected

- **现象**：配了 GITLAB_TOKEN 仍 401，trace 显示 `INFO: 回贴认证方式 JOB-TOKEN`（说明 GITLAB_TOKEN 没被注入）。
- **根因**：GitLab 的 Protected variable 只在「受保护分支/标签」上注入，而 MR pipeline 运行在 `refs/merge-requests/2/head`（非 protected 的 source branch）。
- **解决方案**：去掉 GITLAB_TOKEN 的 Protect 标志（保留 Masked），让 MR pipeline 能读到。

### E7 🟠 GitLab include ref 冻结

- **现象**：改了 my-skill 的 ci 模板（加 changed-statements）并 push，但 retry job 还是用旧模板（审 61 条而非 10 条、单独 build_report + grep gate.log）。
- **根因**：GitLab 的 `include: ref: master` 在 **pipeline 创建时**被冻结为当时的 commit SHA，retry job 不会重新解析。而 before_script 的 `git clone --depth 1` 是动态的（每次拉最新），所以出现「脚本最新、模板旧」的混合状态。
- **解决方案**：模板改动后需**创建新 pipeline**（push 新 commit 或手动 Run pipeline），retry job 无效。

### E8 🔴 CI 模板没串 changed_statements

- **现象**：SQL 块级 diff（P3 修复）在 extract_changes/run_review/parse_mapper 里链路是通的，但 CI 模板只提取 `files[].path`，丢弃了 `changed_statements`，也没传 `--changed-statements`，导致审查整个文件的 61 条 SQL 而非变更的 10 条。
- **解决方案**：CI 模板同时提取 `FILES_JSON` 和 `CHANGED_STATEMENTS`，run_review 加 `--changed-statements` 透传。

### E9 🟡 R101 软删除守卫误报（D7 遗留的根治）

- **现象**：5 个 update 被 R101「缺失软删除守卫」误报 HIGH，而这些表根本没有软删除字段。
- **解决方案**：R101 改 `schema_soft_delete_guard` 方法——仅「表 DDL 确认含软删除字段 且 WHERE 未引用」才命中；表无软删除字段/无 schema 时均不命中。

### E10 🟡 401 提示代码丢失（同步混乱）

- **现象**：在 `/mnt/g/my-skill-gitlab` 加的 401 提示，后来从 `/mnt/g/my-Skill` cp 覆盖时被丢失。
- **根因**：两个目录（本地开发 `my-Skill` / 远程 push `my-skill-gitlab`）不同步，跨目录 cp 覆盖了未同步的改动。
- **教训**：两个目录的同步要严格单向（开发目录 → push 目录），反向 cp 会丢改动。

### E11 🟠 run_review 从 stdout 读 report 崩溃

- **现象**：正常 ci 模式 run_review exit 1。根因是 build_report `--mode ci` 时 stdout 输出 `GATE: BLOCK`（非 JSON），run_review 的 `_load_json("GATE: BLOCK")` 崩溃。
- **解决方案**：run_review 改为从 `--output` 文件读 report，而非从 stdout 读。

### 第四轮修复状态

全部 ✅ 已修复（E1-E11），代码已 push 到 `my-skill` 仓库 master。验证：真实 MR !2 端到端跑通——LLM 生效（自然语言风险描述）、回贴成功（PRIVATE-TOKEN + note posted）、SQL 块级 diff 收敛（待新 pipeline 验证）、GATE 门禁正常。

**经验总结**：这一轮最大的教训是「**AI 工具的偏差，根子在设计，不在 AI**」——AI 偏离流程（E1）不是 AI 笨，而是 SKILL.md 没定义「手动 MR 场景」；AI 产出假结论（E2/E3）不是 AI 编造，而是 dry-run 和「静默降级」给了它假数据和不问凭据的借口。**约束 AI 的正确方式是把每个分叉点写成显式规则，而不是指望 AI 临场判断。**
