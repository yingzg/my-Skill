# hera-slow-api-analyzer — 测验文档

> 对应学习文档: `04-hera-slow-api-analyzer/learning.md`
>
> 测验类型: **理解 + 设计**（两阶段架构 + APM 平台抽象 + 优化方案设计）

---

## Part A: 架构与流程理解（50分）

### A1. 填空题（每题3分，共15分）

**1.** 两阶段分离中，Phase 1 的职责是 ____，Phase 2 的职责是 ____，两者通过 ____ 进行数据交接。

**2.** Phase Boundary Contract 包含的 5 个核心字段是：____、____、____、____、____。

**3.** 根因定位的 5 层递进逻辑是：____ → ____ → ____ → ____ → ____。

**4.** 优化方案的三段式结构（时间维度）是：____、____、____。

**5.** API_REFERENCE.md 的存在体现的设计意图是：____。

---

### A2. 判断题（每题3分，共9分）

**6.** [ ] Phase 1 失败时（如 Hera 无法访问），Phase 2 也不能执行，因为缺少 Trace 数据。

**7.** [ ] 浏览器自动化应该在 Playwright 中使用截屏 + OCR 来提取 DOM 数据，以兼容各种 UI 框架。

**8.** [ ] 优化方案中"短期 = 不改代码的事（加索引、调配置）"是一种合理的划分方式。

---

### A3. 简答题（每题13分，共26分）

**9.** 比较 hera-slow-api-analyzer 和 code-trace-analyzer 在代码分析策略上的异同：

| 维度 | hera-slow-api-analyzer | code-trace-analyzer |
|------|----------------------|---------------------|
| 起点 | | |
| 分析驱动因素 | | |
| 代码分析侧重点 | | |
| 输出产物 | | |
| 是否可以相互替代？ | | |

**10.** 阅读以下场景，判断问题和改进方向：

> 某接口 `/api/order/search` 在 Hera 上报告 P99 耗时 15s。AI 通过浏览器自动化成功获取了 Trace 数据。Trace 显示：
> - Span 1 (OrderController.search): 15000ms
>   - Span 2 (OrderService.search): 14800ms
>     - Span 3 (OrderMapper.selectByCondition): 14500ms (SQL 查询)
>     - Span 4 (Dubbo:UserService.getById): 150ms
>     - Span 5 (Dubbo:ProductService.getById): 130ms
> 
> AI 定位到 OrderMapper.xml 中的 SQL：`SELECT * FROM t_order WHERE status = #{status} AND created_time BETWEEN #{start} AND #{end}`。本地代码显示 `t_order` 表的 status 字段没有索引，created_time 有单列索引。

请回答：
- a) 根因是什么？请用"因果链"格式输出
- b) 给出短/中/长三期优化方案，每个方案都标注"来源"
- c) 如果还需要验证"status 字段的选-择性"（status 值分布），你应该在 Phase 1 的哪个步骤增加什么操作？

---

## Part B: 平台无关化设计（30分）

### B1. APM 平台抽象设计（15分）

**11.** 设计 `IAPMPlatform` 接口和两个适配器，使 Skill 可以从 Hera 迁移到 Datadog。

设计要求：
1. IAPMPlatform 接口的方法签名
2. WebUI 适配器（通用版，通过 YAML 配置选择器）
3. API 适配器（Datadog 实现）
4. 配置文件的 YAML 格式（声明式平台描述）
5. 如何实现 fallback（API 不可用时降级到 WebUI）

---

### B2. 登录抽象设计（15分）

**12.** 当前通过 `dayu-cas-login` Skill 管理登录态。设计通用的 `IAuthenticator` 接口和配置驱动的登录方案。

设计要求：
1. IAuthenticator 接口定义
2. 三种登录模式的适配器实现伪代码：
   - CAS 单点登录（当前 Hera 模式）
   - OIDC（通用企业 SSO）
   - API Key（Datadog / Grafana 风格）
3. 配置如何声明使用哪种登录方式
4. 登录态过期（如 CAS session 超时）的自动检测和恢复策略

---

## Part C: 报告质量提升题（20分）

**13.** 当前的诊断报告是 Markdown 文本格式。假设你要设计一个"诊断报告质量评分卡"，自动评估每次分析产出的报告质量。

请设计评分卡的维度和测量方法：

| 维度 | 权重 | 测量方法 | 满分标准 | 扣分条件 |
|------|------|---------|---------|---------|
| 证据完整性 | 30% | | | |
| 根因准确度 | 30% | | | |
| 方案可执行性 | 20% | | | |
| 量化程度 | 10% | | | |
| 报告可读性 | 10% | | | |

---

## 评分标准

| 等级 | 分数 | 要求 |
|------|------|------|
| S | 90+ | 架构理解全对 + 平台抽象完整 + 评分卡设计合理 |
| A | 75-89 | 架构理解正确 + 平台抽象可行 |
| B | 60-74 | 基本理解两阶段设计 + 有抽象思路 |
| C | <60 | 需要回顾学习文档 |

---

## 参考答案要点

<details>
<summary>点击展开</summary>

### Part A

1. 浏览器自动化获取 Trace/Log 数据，本地源码分析定位根因，Phase Boundary Contract
2. api_name, p99_latency, trace_id, trace_data, logs
3. Trace 层, Code 层, SQL 层, Data 层, Root Cause
4. 短期（不加代码的修复）, 中期（小规模代码改造）, 长期（架构变更）
5. 准备用 API 替换浏览器自动化，为未来迁移降低切换成本

6. ❌ 错误。Phase 1 失败后，如果已有历史 Trace 数据（如来自其他渠道的 trace_id），Phase 2 可以独立执行。
7. ❌ 错误。应该用 `page.evaluate()` 在浏览器 JS Context 中结构化提取 DOM 数据，比截屏+OCR 高效且准确。
8. ✅ 正确。这是一种务实的划分：短期是不需要改代码的操作性优化，降低了风险和项目阻力。

9. | 维度 | hera-slow-api-analyzer | code-trace-analyzer |
    |------|----------------------|---------------------|
    | 起点 | 慢接口指标（Hera） | 用户提供的包路径/方法名 |
    | 分析驱动 | 性能数据驱动（哪个 Span 最慢） | 代码结构驱动（逐层追踪调用） |
    | 代码侧重点 | 关注"哪里慢"（性能瓶颈） | 关注"谁调用谁"（结构关系） |
    | 输出产物 | 诊断报告（根因+优化方案） | 文档（流程图+SQL+校验点） |
    | 可否替代？ | 不能 — 一个关注性能，一个关注结构，互补 | |

10. a) 因果链: `t_order.status` 无索引 → 查询时全表扫描（created_time 单列索引无法过滤 status）→ SQL 耗时 14500ms → 接口 P99 15s

    b) 优化方案:
    - 短期: 为 `t_order` 添加 `(status, created_time)` 联合索引（来源: OrderMapper.xml 的 WHERE 条件使用 status + created_time）
    - 中期: 对订单搜索加入结果数上限 LIMIT，避免返回海量数据（来源: 无 LIMIT 子句）
    - 长期: 历史订单归档（status=COMPLETED 且 created_time > 90 天），减少主表体积

    c) Phase 1 Step 5（数据导出）后，增加一步：进入数据库查询页面，执行 `SELECT status, COUNT(*) FROM t_order GROUP BY status`，确认 status 值分布和选择性。如果 status 只有 2-3 个值且分布均匀，联合索引效果有限 → 需要考虑其他方案。

### Part B

11. 略（参考 learning.md §5.2）

12. 略（参考 learning.md §5.2.3）

### Part C

13. 示例设计：

| 维度 | 权重 | 测量方法 | 满分标准 | 扣分条件 |
|------|------|---------|---------|---------|
| 证据完整性 | 30% | 统计报告中有 `来源: 文件:行号` 标注的结论占比 | ≥70% | 每个无来源的结论扣 5 分 |
| 根因准确度 | 30% | 因果链是否包含"代码→SQL→数据"的所有层次 | 因果链完整 | 缺失一层扣 10 分 |
| 方案可执行性 | 20% | 优化方案是否包含短期/中期方案 | ≥2 类时间窗 | 缺失一类扣 10 分 |
| 量化程度 | 10% | 是否包含数值（耗时 ms、行数、表大小） | ≥3 个量化指标 | 每个缺失扣 3 分 |
| 报告可读性 | 10% | 是否有分层标题、表格、代码块 | 结构化且无大段文字 | 大段文字扣 5 分 |
</details>
