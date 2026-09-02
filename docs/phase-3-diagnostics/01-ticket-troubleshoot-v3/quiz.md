# ticket-troubleshoot-v3 — 测验文档

> 对应学习文档: `01-ticket-troubleshoot-v3/learning.md`
>
> 测验类型: **理解 + 设计**（知识点理解 + 通用化能力 + 依赖剥离方案）

---

## Part A: 功能介绍与理解（60分）

### A1. 填空题（每题3分，共15分）

**1.** 排查流水线共 ____ 步，其中被允许中断的步骤是 Step ____ 和 Step ____。

**2.** 经验库检索分为两轮：第一轮 ____ 匹配，第二轮 ____ 匹配。

**3.** Output Contract 的三个终态（status）是：____、____、____。

**4.** Checkpoint 文件的 TTL 是 ____ 小时，存储在 ____ 目录下。

**5.** Step 5（数据库查询）的 retry 上限是 ____ 次，连续失败后触发 ____ 熔断条件。

---

### A2. 判断题（每题3分，共9分）

**6.** [ ] 经验库高置信匹配后，可以直接跳到 Step 7，跳过 Step 6。

**7.** [ ] 当 `restricted_info` 数组非空时，status 应强制设为 `partial_success` 或 `failed`。

**8.** [ ] Checkpoint 恢复时，已完成步骤需要重新执行以确保数据最新。

---

### A3. 单选题（每题3分，共6分）

**9.** 以下哪种情况应该输出 `partial_success` 而不是 `success`？

A. 找到了根因但缺少一个非关键 SQL 验证
B. 所有步骤都执行完成，但 `confidence` 为 low
C. 经验库匹配到案例但用户拒绝复用
D. 关键证据字段缺失（如 `root_cause` 为空）

**10.** "No Invention" 原则禁止以下哪项？

A. 在 Step 3 中使用 `grep` 搜索代码
B. 在 Step 4 中自行编写 SQL 绕过配置文件
C. 在 Step 6 中引用 Checkpoint 中的既有证据
D. 在 Step 7 中提醒用户确认回写

---

### A4. 简答题（每题10分，共30分）

**11.** 请画出 Pipeline 的完整状态迁移图，标注每个 Step 的输入/输出、允许跳跃的路径、以及跳跃的条件。

**12.** 技能中说"Output Contract 在 Step 2 冻结，contract_version 不得漂移"。请问：
- 为什么选择 Step 2 作为冻结点，而不是 Step 1 或 Step 3？
- "contract_version 漂移"具体指什么场景？会造成什么后果？

**13.** 阅读以下场景，判断 AI 应该采取什么行动：
> AI 在 Step 5 查询数据库时发现，配置文件中写的表名 `t_order` 在线上库中不存在，但有一个结构相似的表 `t_orders`（多了个 s）。同时 AI 搜索代码发现，MyBatis XML 中映射的表名确实是 `t_orders`。

请回答：
- AI 应该使用哪个表？为什么？
- 这个过程涉及哪些验证层次（L1-L4）？
- 这个发现是否应该触发中断（等待用户确认）？为什么？

---

## Part B: 设计与抽象（40分）

### B1. 接口设计题（20分）

**14.** 当前技能通过 `zeus-devx-database` MCP 访问数据库。请设计一个通用的 `IDatabaseQuery` 接口，使排查引擎可以适配任意数据库后端（MySQL、PostgreSQL、MongoDB 等）。

需要设计：
1. 接口定义（方法名、参数、返回值类型）
2. 至少两个适配器实现（MySQL + 一种其他数据库）
3. 配置文件如何声明使用哪个适配器
4. 适配器选择策略（fallback 机制）

---

### B2. 架构设计题（20分）

**15.** 假设你要将 `ticket-troubleshoot` 从 Skill 升级为跨团队复用的通用排障引擎。你需要：
1. 将所有公司特有依赖（Zeus、Feishu、Intl-Retail 项目名）替换为抽象接口
2. 保持原有的 Pipeline/Checkpoint/Output Contract/经验库机制不变
3. 支持多语言/多框架（不只是 Java/MyBatis-Plus）

请回答：
- 需要定义哪些抽象接口？
- 这些接口之间如何组合（画出依赖关系图）？
- 如何支持多语言？判表规则如何做成可插拔的？
- 经验库如何跨团队共享？索引策略如何调整？

---

## Part C: 代码实现题（选做，+10分）

**16.** 请用 Python/TypeScript 实现一个简化版的 Checkpoint 管理器，要求：

1. 支持 `save(step, result)` 和 `load()` 方法
2. 自动处理 TTL 过期（24h）
3. 支持 `restore()` — 返回 `current_step` 和已完成步骤的只读数据
4. 损坏检测（JSON 解析失败时标记为 invalid 并提示重建）

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

1. **7**，Step **1** 和 Step **7**
2. 精确 match（ticket_type + trigger_route + system），模糊 match（related_tables / key_business_ids）
3. success, partial_success, failed
4. 24, RUNS_DIR
5. 3, "数据查询连续 3 次 500 错误"

6. ❌ 错误。快速路径可以跳过 Step 2-5，但必须经过 Step 6 的 Output Contract 校验，不能跳过。
7. ✅ 正确。
8. ❌ 错误。已完成步骤只读复用，校验通过即可，不应重新执行。

9. **D**。关键字段缺失必须降级。A/B 不涉及关键字段缺失，C 是用户选择不是能力不足。
10. **B**。自行编写 SQL 绕过配置属于脑补数据。A/C/D 都是正当操作。

11. 略（应包含：Step 1→高置信→Step 6；Step 3→满足跳过→Step 6；其余顺序流转）

12. - Step 2 选择：Step 1 是元数据选择（系统），还未进入排查逻辑；Step 3 开始产出证据，冻结应该在证据产生前完成
    - 漂移：LLM 在长对话中逐渐改变输出格式（如字段增减、嵌套层级变化），导致 Contract 校验失败
    - 后果：下游步骤依赖的字段类型/结构不一致，Checkpoint 恢复时无法匹配

13. - 使用 `t_orders`：代码中的 MyBatis 映射是权威来源，配置文件可能有误
    - 涉及 L1（MCP 返回"表不存在"）+ L3（代码行号验证：MyBatis XML 映射到 t_orders）
    - 不应中断：§4 明确"代码找不到表时，标注 restricted_info 继续"，这里已找到正确表名

### Part B

14. 略（参考 learning.md §5.2）
15. 略（核心抽象：IDataSourceResolver / IDatabaseQuery / ICaseStore / ICheckpointStore / INotifier）

### Part C

16. 略（关键：TTL 判断、corruption detection、read-only replay 模式）
</details>
