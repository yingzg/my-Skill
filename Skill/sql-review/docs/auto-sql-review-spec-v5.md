# Auto SQL Review Skill — 设计规格书 V5（实现校准：LLM 接入 + 性能优化 + schema 感知）

> **状态**：实现校准阶段（第二轮） | **最后更新**：2026-09-08
> **上一版**：V4（架构收口：方案 C + 分批 + 规则体系 + AD9-AD16）

---

## 1. 概述

V4 确定的三层架构（SKILL.md 编排 + scripts 确定性脚本 + references 知识底座）在**真实 CI 场景**验证时，暴露了性能与正确性问题：对 MR#2（10 个 Mapper XML、61 条 SQL）的一次审查耗时 **5m53s**，且 EXPLAIN 60/61 失败、LLM 被全量调用。本版本针对这些问题做架构升级，最终将 CI 时长降至 **11.2s**、LLM 调用归零。

### 1.1 V5 相对 V4 的核心变化

| 变化 | 说明 |
|------|------|
| LLM 真正内联 | V4 的 AD14 仅「设计」了 LLM 介入，V5 落地为脚本内调 LLM API |
| 审查范围收敛 | 从「文件级 diff」升级为「SQL 块级 diff」 |
| 引入表 DDL | 新增 discover_schema 获取字段类型/索引/主键 |
| 静态规则 schema 感知 | 规则匹配从「纯 regex 瞎猜」升级为「有 DDL 依据的确定性判断」 |
| EXPLAIN 参数化 | 用 DDL 把 `?` 占位符替换为合理字面量，使 EXPLAIN 可执行 |
| 预筛语义修正 | UNCERTAIN（无规则命中）不再无条件走 LLM，改用 EXPLAIN 结果判断 |

---

## 2. 关键架构决策（AD17-AD21）

### AD17：LLM 通过「脚本内调 API」接入，而非「SKILL.md 编排层介入」

| 决策 | 排除方案 | 原因 |
|------|---------|------|
| LLM 由脚本内调 OpenAI-compatible API（`llm_client.py`），Phase 3 与 Phase 4b 两个环节各由一个脚本调用 | SKILL.md 编排层让 agent 中途介入 | ① CI job 无人运行，无法中途介入；② 脚本内调用可 mock、可测试、符合 AD16「run_review.py 一键编排」 |

- `llm_client.py`：OpenAI-compatible 客户端，环境变量配置 `LLM_API_KEY`/`LLM_BASE_URL`/`LLM_MODEL`（默认 DeepSeek flash，可切 MiMo）。
- **Phase 3（真实路径还原，AD1）**：`llm_resolve.py` 对 `needs_llm` 的动态 SQL，批量（10 条/批）调 LLM 判断 `<if>/<choose>` 条件激活状态，生成最终 resolved_sql。
- **Phase 4b（风险定性，AD14）**：`llm_risk_analysis.py` 合并规则 + EXPLAIN + 调用链，分批（8 条/批）调 LLM 生成自然语言风险描述 + 分级修复建议。
- **降级**：未配置 `LLM_API_KEY` 或 LLM 失败时，自动降级为确定性分析（optimistic 展开 + 规则风险等级），全程不中断。

### AD18：审查范围从「文件级」收敛到「SQL 块级」（行级 diff）

| 决策 | 排除方案 | 原因 |
|------|---------|------|
| `extract_changes.py` 用 `git diff --unified=0` 定位变更行，映射到所属的 `<select id="xxx">` 块，只输出变更的 statement id；`parse_mapper.py` 加 `--only-statements` 过滤 | 文件级 diff（解析整个文件全部 SQL） | MR 改 10 个 selectById 时，文件级 diff 会审 61 条（含未改的 selectList/insert/update），浪费 EXPLAIN + LLM |

- 输出格式升级：`files[].changed_statements` 记录每个文件变更的 statement id。
- `run_review.py` 加 `--changed-statements` 参数，透传给 parse_mapper。

### AD19：引入表 DDL，静态规则「schema 感知」

| 决策 | 排除方案 | 原因 |
|------|---------|------|
| 新增 `discover_schema.py`，对 SQL 涉及的表执行 `SHOW CREATE TABLE`，解析出字段类型/主键/索引；`match_rules.py` 规则匹配时传入 schema | 纯文本 regex（不知道列类型/索引/主键） | 纯 regex 无法判断「隐式转换」（需列类型）、「主键查询」（需主键）、「排序非索引」（需索引），必然误报导致预筛失效 |

- `discover_schema.py` 输出：`{table: {columns: {name: type}, primary_key, indexes: {name: [cols]}}}`。
- 两个 schema 感知机制：
  - **`exempt`（豁免）**：规则加 `exempt.method = "schema_pk_eq_query"`，命中豁免条件时规则不命中。R002「缺失 LIMIT」用它豁免「主键等值查询」（主键查询最多返回 1 行，不需要 LIMIT）。
  - **`schema_column_eq_number`（隐式转换准确判断）**：R006 用它判断「字符串列 = 数字字面量」，仅当 DDL 确认该列是字符串类型时才命中。`del_flag = 0`（tinyint 列）不再误判。
- `db_client.py`：把 ToolboxMcp（MCP stdio 客户端）从 execute_explain 提取为独立模块，供 discover_schema 和 execute_explain 共用。

### AD20：EXPLAIN 参数化 —— 用 DDL 替换 `?` 为合理字面量

| 决策 | 排除方案 | 原因 |
|------|---------|------|
| `execute_explain.py` 在 EXPLAIN 前，用 schema 把 `?` 按列类型替换（数字列→`1`、字符串列→`'x'`、日期列→`'2024-01-01'`，其余→`1`） | 直接 EXPLAIN 参数化 SQL / 全部 `?`→`1` | ① `?` 是 JDBC 占位符，MySQL 报 1064；② 全 `?`→`1` 会让字符串列触发隐式转换，EXPLAIN 结果失真 |

- 替换策略：先按「列 = ?」模式查 DDL 列类型精确替换，剩余 `?` 兜底为 `1`。
- 效果：真实 EXPLAIN 从 1/61 成功提升到 10/10 成功（`type=const, key=PRIMARY` 正确识别主键查询）。

### AD21：预筛语义修正 —— UNCERTAIN 用 EXPLAIN 结果判断

| 决策 | 排除方案 | 原因 |
|------|---------|------|
| `llm_risk_analysis.py` 预筛时，UNCERTAIN（无规则命中）不再无条件走 LLM，改用 EXPLAIN 判断：`type∈{const,eq_ref,ref,range}`（索引查询）→ fast 通道（LOW）；`type∈{ALL,index}`（全扫描）或 EXPLAIN 失败 → deep（LLM） | UNCERTAIN 一律进 deep 走 LLM | 「无规则命中」不代表「不确定」——EXPLAIN 能确定性判断索引使用情况；只有 EXPLAIN 也发现全表扫描的才需要 LLM 深度判断 |

- 完整预筛语义：`LOW/PASS → fast`；`HIGH/MEDIUM → deep`；`UNCERTAIN → 看 EXPLAIN type 定 fast/deep`。

---

## 3. 数据流（V5 最终版）

```
extract_changes（SQL 块级 diff，只出变更的 statement）
  → parse_mapper（--only-statements 只解析变更 SQL）
  → trace_callchain（调用链）
  → resolve_dynamic_sql --mode resolve（保留 if/choose，标 needs_llm）
  → llm_resolve（Phase 3：LLM 判断动态条件 → resolved_sql）
  → extract_tables（表名）
  → discover_schema（表 DDL：字段类型/索引/主键）  ★新增
  → dml_to_select_proxy（DML → SELECT）
  → match_rules（静态规则：纯文本 + schema 感知）  ★升级
  → execute_explain（explain_sql = DDL 替换 ? 后真实 EXPLAIN）  ★升级
  → llm_risk_analysis（Phase 4b：预筛 + LLM 风险定性）  ★新增
  → build_report（报告 + 门禁）
```

---

## 4. 脚本清单（V5 共 15 个）

| 脚本 | 职责 | 相对 V4 |
|------|------|---------|
| `extract_changes.py` | SQL 块级 diff | 升级 |
| `discover_datasource.py` | 数据源发现 | 不变 |
| `parse_mapper.py` | SQL 提取 + `--only-statements` 过滤 + `--parse-errors-output` | 升级 |
| `trace_callchain.py` | 调用链追踪 | 不变（MAX_METHODS 50→500） |
| `resolve_dynamic_sql.py` | 动态 SQL 解析（optimistic/resolve） | 微调（finalize 加 HTML 实体） |
| `llm_resolve.py` | Phase 3 LLM 真实路径还原 | 新增 |
| `extract_tables.py` | 表名提取 | 不变 |
| `discover_schema.py` | 表 DDL 获取（字段类型/主键/索引） | 新增 |
| `dml_to_select_proxy.py` | DML→SELECT | 不变 |
| `match_rules.py` | 规则匹配（schema 感知：主键豁免/隐式转换/软删除守卫） | 升级 |
| `execute_explain.py` | EXPLAIN（参数化） | 升级 |
| `llm_risk_analysis.py` | Phase 4b LLM 风险定性（预筛+分批） | 新增 |
| `build_report.py` | 报告 + 门禁（GATE 输出 + MR 评论） | 微调 |
| `run_review.py` | 一键编排（CI 永不中断 + 关键降级 INCONCLUSIVE） | 升级 |
| `post_mr_comment.py` | CI 回贴 MR 评论（GitLab API） | 新增 |

公共模块：`db_client.py`（ToolboxMcp）、`llm_client.py`（LLM API）。

---

## 4.1 CI 模式（AD22：CI 永不中断 + 回贴脚本化 + 门禁三态）

> 第三轮（2026-09-09）落地：CI 自动化审查场景，作为「手动给 MR URL」交互场景之外的正式工作流。

| 决策 | 排除方案 | 原因 |
|------|---------|------|
| **CI 永不中断**：业务性失败（规则缺失/XML 失败/DB 连不上/LLM 失败）一律「记录 `degradation_notes` + 继续 + exit 0」，只有脚本自身崩溃才允许 CI 失败 | 遇错即中断（exit 非 0） | CI/CD 不能因可恢复错误卡住 pipeline；失败现场应进报告等人工介入 |
| **门禁三态**：`PASS` / `BLOCK` / `INCONCLUSIVE`（分析不完整，exit 0 但不误放行） | 只 PASS/BLOCK 两态 | 规则缺失等关键降级时，既不误放行（PASS）也不误拦（BLOCK），标 INCONCLUSIVE 交人工 |
| **回贴脚本化**：`post_mr_comment.py` 用 `GITLAB_TOKEN`（优先，PAT 需 api scope）→ `CI_JOB_TOKEN`（兜底只读）调 GitLab API 回贴 | 依赖 AI 运行时（GitLab MCP） | 与「CI 无人运行」前提一致（同 AD17 精神）；CI_JOB_TOKEN 默认只读，评论需 PAT |
| **SQL 块级 diff 串接到 CI**：`extract_changes.py` 的 `changed_statements` → `run_review.py --changed-statements` → `parse_mapper.py --only-statements` | 文件级 diff（审整个文件） | MR 改 10 个 selectById 时，文件级会审 61 条（含未改的 selectList/selectCount），块级只审 10 条 |

CI 凭据全部走环境变量（GitLab CI Variables 注入，脚本读，AI 不接触）：数据库 `MYSQL_HOST/PORT/USER/PASSWORD/DATABASE`（只读账户）、LLM `LLM_API_KEY`、回贴 `GITLAB_TOKEN`。

---

## 5. 性能结果（真实 MR#2 验证）

| 指标 | 优化前 | 优化后 |
|------|--------|--------|
| 审查 SQL 数 | 61 | 10 |
| EXPLAIN 成功率 | 1/61 | 10/10 |
| LLM 调用次数 | 11 批 | 0 |
| 门禁结论 | BLOCK（误拦） | PASS（正确） |
| 总耗时 | 5m53s | **11.2s** |

---

## 6. 变更记录

| 版本 | 日期 | 变更内容 |
|------|------|---------|
| V4 | 2026-07-29 | 架构收口：方案 C + 分批 + 规则体系 + AD9-AD16 |
| **V5** | **2026-09-08** | **实现校准（第二轮）**：① LLM 脚本内接入（AD17）；② SQL 块级 diff（AD18）；③ DDL 获取 + schema 感知（AD19）；④ EXPLAIN 参数化（AD20）；⑤ 预筛语义修正（AD21）。CI 时长 5m53s → 11.2s |
| **V5.1** | **2026-09-09** | **CI 模式落地（第三轮）**：① CI 永不中断 + 门禁三态 PASS/BLOCK/INCONCLUSIVE（AD22）；② 回贴脚本化 `post_mr_comment.py`（GITLAB_TOKEN 优先）；③ SQL 块级 diff 串接到 CI；④ schema 感知深化（R101 软删除守卫改 `schema_soft_delete_guard`，D7）；⑤ 测试 14→17 用例 |

> 说明：V4 的 AD10（分批）/AD11（两阶段预筛）在 V5 落地为 `llm_risk_analysis.py` 的批处理与预筛逻辑；AD1（真实路径还原）/AD14（风险定性）在 V5 落地为 `llm_resolve.py`/`llm_risk_analysis.py`。分批维度当前为「按需 LLM 的 SQL 分批」，V4 的「按数据源+主表分组」仍需多库凭据配置（当前单库 `MYSQL_*`）。
