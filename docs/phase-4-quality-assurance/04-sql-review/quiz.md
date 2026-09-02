# sql-review — 测验文档

> 对应学习文档: `04-sql-review/learning.md`
>
> 测验类型: **理解 + 设计**（三阶段分析原理 + 悲观策略 + Prompt 工程 + 通用化能力）

---

## Part A: 功能介绍与理解（60分）

### A1. 填空题（每题3分，共18分）

**1.** SQL Review 的完整 Pipeline 共 ____ 步，其中三阶段分析（Phase 0 / Phase 1 / Phase 2）发生在 Step ____，自动更新检查发生在 Step ____。

**2.** Phase 1 的"确定性悲观基线"分为三类：`extract_static_worst_case` 处理 ____ SQL，`extract_update_worst_case` 处理 ____ SQL，`extract_select_worst_case_multi_chain` 处理 ____ SQL。

**3.** 悲观清洗中，包含 LIMIT/OFFSET 的 `<if>` 分支会被 ____（保留/去掉），原因是 ____。

**4.** Phase 1 的 LLM 校正中，7 种必传证据包括：显式断言、抛异常中断、____、参数校验注解、____、接口层强制、____。

**5.** 分批策略中，`_split_oversized_batches` 的 prompt 上限是 ____ KB，`_merge_small_batches` 将少于 ____ 条的 batch 合并。

**6.** JSON 解析的降级链共 ____ 层：优先从 ____ 提取 → 失败后从文本中找数组 → 再失败用正则从 ____ 提取 → 全部失败返回 ____。

---

### A2. 判断题（每题3分，共12分）

**7.** [ ] Phase 0（LLM 代码精选）对所有 SQL 都会触发，无论方法体多长。

**8.** [ ] 当 `worst_case_sqls` 为空时，EXPLAIN 步骤会被跳过，直接进入 Phase 2（降级模式）。

**9.** [ ] `merge_deterministic_and_llm` 的合并策略是：当 LLM 校正结果与确定性基线冲突时，始终使用 LLM 校正结果。

**10.** [ ] 贪心聚类以共享表为依据将 SQL 聚到 batch，如果单个 batch 超过 15 条则强制切开，尾部 <5 条的 batch 合并到前一个 batch。

---

### A3. 单选题（每题3分，共9分）

**11.** 以下哪种情况属于 Phase 1 中的"必传证据"（应加回条件）？

A. `query.setCountryCode(request.getCountryCode())` — request 直接透传
B. `if (typeList == null) typeList = getDefaultList(); query.setTypeList(typeList)` — 默认值兜底
C. `BeanUtil.copyBean(request, queryBO)` — 全量拷贝
D. `if (StringUtils.isNotBlank(keyword)) query.setKeyword(keyword)` — 条件赋值

**12.** 关于多链模式（multi-chain），以下说法正确的是：

A. 多链模式下所有 chain 共享同一个 worst_case_sql
B. `dedup_phase1_chains` 通过哈希调用方类名来去重
C. 不同调用链可能产出不同的 worst_case_sql，Phase 2 取最差的 EXPLAIN
D. 多链模式仅在 CI 模式下启用，本地模式只支持单链

**13.** 关于悲观清洗中 `<trim prefixOverrides="OR">` 的处理，以下正确的是：

A. `<trim>` 块内的 `<if>` 分支全部去掉（与其他 `<if>` 一致）
B. `<trim>` 块内的 `<if>` 分支全部保留（最差场景）
C. `<trim>` 块内的 `<if>` 分支保留，但 `<if test="xxx">AND x = #{x}</if>` 仍被去掉
D. `<trim>` 块被整体删除，换为 `WHERE 1=1`

---

### A4. 简答题（每题7分，共21分）

**14.** 请画出 Phase 1 从"原始 MyBatis XML SQL"到"最终 worst_case_sqls"的完整处理流程，标注每个环节的输入/输出、LLM 介入点、以及降级路径。

**15.** 以下 SQL 片段来自某 Mapper XML：
```xml
<select id="getOrders">
  SELECT * FROM t_order WHERE 1=1
  <if test="status != null">AND status = #{status}</if>
  <if test="countryCode != null">AND country_code = #{countryCode}</if>
  <if test="createTime != null">AND create_time >= #{createTime}</if>
  ORDER BY id DESC
  LIMIT #{offset}, #{limit}
</select>
```

调用链分析发现：
- Controller 层：`@Validated @RequestBody OrderRequest`（其中 `countryCode` 有 `@NotBlank` 注解）
- Service 层：`if (request.getStatus() == null) throw new BizException("status required")`
- `createTime` 直接从 request 透传，无校验

请回答：
- 确定性悲观清洗后（仅清洗，不含 LLM 校正），SQL 会变成什么样？
- Phase 1 LLM 校正后，哪些条件可能被加回？依据是什么（注明证据编号）？
- `LIMIT` 分支会被保留还是去掉？为什么？

**16.** 阅读以下场景，判断 AI 应该采取什么行动：

> 某 batch 包含 8 条 SQL，其中 6 条是纯静态 SQL，2 条是动态 SELECT。这 2 条动态 SELECT 各有 3 条调用链，但其中 2 条调用链的代码片段完全一致（同一个 Service 方法被两个 Controller 调用）。EXPLAIN 执行时，其中 1 条 SQL 的 EXPLAIN 失败（连接超时）。

请回答：
- `is_batch_all_static()` 会返回 true 还是 false？为什么？
- Phase 1 的 `dedup_phase1_chains` 会如何处理这 2 条动态 SELECT？
- EXPLAIN 失败的那条 SQL，Phase 2 应该如何处理？（引用具体的降级逻辑）
- 如果 Phase 2 的 LLM 响应超时，`generate_timeout_pass_report` 会产出什么 risk_level？

---

## Part B: 设计与抽象（40分）

### B1. 接口设计题（20分）

**17.** 当前技能仅支持 MySQL 数据库和 MyBatis 框架。请设计一组通用接口，使 SQL Review 引擎可以适配任意数据库（MySQL、PostgreSQL、MongoDB）和任意 ORM 框架（MyBatis、Hibernate、GORM、Django ORM）。

需要设计：
1. **ISQLExtractor** 接口：不同 ORM 框架的 SQL 提取器
   - 方法签名、参数、返回值
   - 如何处理调用链追踪（不同语言的调用模式不同）
2. **IDatabaseConnection** 接口：不同数据库的连接和执行
   - 方法签名、参数、返回值
   - 如何处理不同数据库的 EXPLAIN 语法差异
3. **IRule** 接口：可配置的审查规则
   - 如何从 Markdown 硬编码规则迁移到结构化规则
   - 规则如何支持"仅适用于 SELECT"、"仅适用于 UPDATE" 等条件
4. 配置文件（YAML）如何声明使用哪些适配器和规则集

---

### B2. 架构设计题（20分）

**18.** 假设你要将 `sql-review` 从 Skill 升级为"跨语言 + 跨数据库"的通用 SQL 审查服务。需要：
1. 保持三阶段分析架构（Phase 0 → Phase 1 → EXPLAIN → Phase 2）不变
2. 将 MyBatis 特有逻辑（XML 清洗、`<if>` 分支处理）抽象为可插拔的"方言"层
3. 支持多数据库方言的 EXPLAIN 输出解析
4. 保持 CI 模式和本地模式共享 review_core.py 的架构

请回答：
- 需要定义哪些抽象接口？画出接口之间的依赖关系图
- MyBatis 的悲观清洗逻辑如何抽象为通用接口？GORM（Go）的动态查询构建器（`Where()` 链式调用）如何适配？
- 17 条硬编码规则如何从 Markdown 迁移到结构化配置？如何支持"跨方言"的规则（如"禁止 SELECT *"同时适用于 MySQL 和 PostgreSQL）和"方言特有"规则（如 MySQL 的 `USE INDEX` 提示）？
- 多数据库的 EXPLAIN 输出差异如何处理？（MySQL: `EXPLAIN SELECT ...` 表格输出，PostgreSQL: `EXPLAIN (ANALYZE, BUFFERS)` 文本输出，MongoDB: `explain("executionStats")` JSON 输出）

---

## Part C: 代码实现题（选做，+10分）

**19.** 请用 Python 实现一个简化版的 `ChainDeduper`，要求：

1. 输入：`batch_sqls`（list of dict，每个 dict 含 `sql_id`、`call_chains`）
2. 输出：`(filtered_batch_sqls, chain_expand_map)`
   - `filtered_batch_sqls`：去重后的 batch_sqls（相同代码的链只保留一条代表）
   - `chain_expand_map`：`{representative_chain_id: [all_original_chain_ids]}`
3. 去重逻辑：
   - 只对同一条 SQL（相同 sql_id）下的调用链去重
   - 两条链"相同"的判定：所有层的 snippet 拼接后的 MD5 相同
   - 选择 chain_id 最小的链作为代表链
4. 边界条件：
   - 静态 SQL 或非 SELECT 类型 → 不处理，直接原样放入 filtered
   - 单条链 → 不处理
   - 空 batc_sqls → 返回空

---

## 评分标准

| 等级 | 分数 | 要求 |
|------|------|------|
| S | 90+ | 全部理解 + 设计完整 + 代码可运行 |
| A | 75-89 | 全部理解 + 设计合理 |
| B | 60-74 | 基本理解 + 设计有思路 |
| C | <60 | 需要回顾学习文档 |

---

## 参考答案要点

<details>
<summary>点击展开</summary>

### Part A

**1.** **5**，Step **3**，Step **0**

**2.** 纯静态 / **UPDATE** / 动态 **SELECT**（多链模式）

**3.** **保留**。分页参数通常有兜底值（如默认 pageSize=10），去掉 LIMIT 会让最差场景变得不真实（返回全量数据 vs 实际只返回 10 条），反而不利于定位真实瓶颈。

**4.** 提前返回（证据#3）、硬编码赋值（证据#5）、默认值注入（证据#7）

**5.** **40** KB，**5** 条

**6.** **4** 层，```json ``` 代码块，Markdown 文本，**None**

**7.** ❌ 错误。Phase 0 仅当方法体 ≥ 30 行时才触发，短方法直接跳过。

**8.** ✅ 正确。worst_case_sqls 为空意味着没有可 EXPLAIN 的 SQL，降级为纯代码分析模式。

**9.** ❌ 错误。合并策略是取 WHERE AND 条件数更多的版本。如果确定性基线有 5 个 AND 而 LLM 校正只有 3 个，保留确定性基线。

**10.** ✅ 正确。贪心聚类 → 超限拆分 → 小 batch 合并，三步完整流程。

**11.** **B**。默认值兜底属于证据#7。A 是无校验透传（证据#8，不加回），C 是全量拷贝（证据#10，不加回），D 是条件赋值（证据#9，不加回）。

**12.** **C**。多链模式的核心优势就是不同入口独立分析，取最差场景。A 错误（每条链独立基线），B 错误（通过代码 snippet 的 MD5 去重），D 错误（本地和 CI 都支持多链）。

**13.** **B**。`<trim prefixOverrides="OR">` 内的 `<if>` 是 OR 分支，可能部分命中也可能全命中，全命中是最差场景 → 全部保留。

**14.** 略（应包含：原始 XML → clean_mybatis_sql_worst_case → 确定性基线 → LLM 校正 [可选] → merge_deterministic_and_llm → 最终 worst_case_sqls。每条路径标注触发条件和失败降级）。

**15.**
- 确定性悲观清洗后：`SELECT * FROM t_order WHERE 1=1 ORDER BY id DESC LIMIT 10`（所有 AND `<if>` 去掉，LIMIT 保留）
- LLM 校正可能加回：
  - `countryCode`（证据#4: `@NotBlank` + `@Validated` 在 Controller 层生效）
  - `status`（证据#2: Service 层 `throw new BizException`）
  - `createTime` 不加回（透传无校验，证据#8）
- LIMIT 分支保留：分页参数通常有兜底，去掉会导致最差场景不真实

**16.**
- `is_batch_all_static()` 返回 **false**，因为 batch 中有 2 条动态 SELECT（非静态且非 UPDATE）
- `dedup_phase1_chains` 对每条 SQL 独立去重。2 条动态 SELECT 各有 3 条链，其中 2 条代码相同 → 去重后每 SQL 只有 2 条链（1 代表 + 1 不同的），total 从 6 条减到 4 条
- EXPLAIN 失败的处理：`deduped_explains` 中对应 key 为空或含"失败"字符串。Phase 2 prompt 中显示"EXPLAIN 失败（请基于 DDL 和索引定义分析）"，LLM 只能基于 DDL + 硬编码规则判断
- 超时降级：`generate_timeout_pass_report` 产出 **SKIP** 级别的报告，summary 为"LLM 分析超时，未完成审查"

### Part B

**17.** 略（参考 learning.md §5.2，核心接口：ISQLExtractor / IDatabaseConnection / IRule）

**18.** 略（核心抽象：ISQLDialect（SQL 清洗+转换）、IDatabaseExplainer（EXPLAIN 执行+解析）、IRuleEngine（规则评估）、ICallChainTracer（调用链追踪）。跨方言规则写在通用层，方言特有规则写在方言层）

### Part C

**19.** 略（关键：snippet 拼接 → MD5 → 分组 → 选代表 → 构建 expand_map。边界：静态 SQL 原样通过，单链不处理）

</details>
