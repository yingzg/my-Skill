# GC-006: code-intelligence 适配（步骤 3 用 MCP 工具检索）

## 目的

验证 Agent 在步骤 3 优先调用 code-intelligence MCP 工具（而非直接 grep），正确完成 `CodeLocation → CodeMatch` 字段映射、`source` 标记（`code_intel`），并把 code-intelligence 的 diagnostics 正确映射到 `restricted_info` 与置信度降级。

这是 Golden Case，不是经验案例库。它不得被第 1 步历史案例预检当作 `.troubleshoot/cases/CASE-xxx.md` 使用。

## 输入场景

用户输入：

```text
系统：交易中心
问题：订单查询接口报错 ORDER_STATUS_INVALID，用户反馈无法查询订单。
接口：GET /api/trade/order/query
时间：2026-07-13 11:00 - 11:30
订单号：202607130002
```

## 测试环境给定事实

### 历史案例预检

`.troubleshoot/cases/` 中无高置信命中。继续正常流程。

### code-intelligence 工具事实

code-intelligence MCP 已配置，项目 `trade-service` 已注册；索引状态 `index_status.state = stale`（索引过期）。

调用 `code.locate_route`（`{ project: "trade-service", method: "GET", route: "/api/trade/order/query" }`）返回 SearchResponse：

```yaml
locations:
  - file: trade-web/src/main/java/com/x/trade/web/OrderController.java
    start_line: 45
    snippet: "return orderQueryService.query(orderId);"
    symbol: OrderController.query
    confidence: high
    source: code_intel
index_status:
  state: stale
diagnostics:
  - level: warning
    code: INDEX_STALE
    message: 索引过期，建议重新索引
```

调用 `code.search`（`{ project: "trade-service", query: "ORDER_STATUS_INVALID", type: "error" }`）返回 SearchResponse：

```yaml
locations:
  - file: trade-service/src/main/java/com/x/trade/enums/OrderStatusEnum.java
    start_line: 12
    snippet: "ORDER_STATUS_INVALID(\"40001\", \"无效订单状态\")"
    symbol: OrderStatusEnum.ORDER_STATUS_INVALID
    confidence: high
    source: code_intel
  - file: trade-service/src/main/java/com/x/trade/service/OrderQueryService.java
    start_line: 88
    snippet: "throw new BizException(OrderStatusEnum.ORDER_STATUS_INVALID);"
    symbol: OrderQueryService.query
    confidence: high
    source: code_intel
index_status:
  state: stale
diagnostics:
  - level: warning
    code: INDEX_STALE
    message: 索引过期，建议重新索引
```

### SQL 整理事实

最小验证 SQL：

```sql
select id, status
from trade_order
where id = '202607130002';
```

表名来源：`OrderQueryService` 中 `orderMapper.selectById` 对应的 Mapper。

### 数据库查询事实

最小验证查询返回：

```text
id: 202607130002, status: INVALID
```

## 预期行为

Agent 必须：

1. 步骤 0 从输入推断系统（交易中心），不提问；无 checkpoint 走 fresh 路径。
2. 步骤 1 历史案例预检无高置信命中，继续正常流程。
3. 步骤 3 优先调用 code-intelligence MCP 工具（`code.locate_route` / `code.search`），**而非直接 grep**。
4. 将 code-intelligence 返回的 `CodeLocation` 正确映射为 `CodeMatch`：`file → file`、`start_line → line`、`snippet → snippet`、`confidence → confidence`。
5. `matchType` 映射：`code.locate_route` 的结果 → `route`，`code.search(type=error)` 的结果 → `error`。
6. `source` 标记为 `code_intel`（Java 专项索引），而非 `grep` 或 `manual`。
7. 将 `INDEX_STALE` 诊断映射到 `restricted_info`（如「索引过期，代码证据置信度降低」），并对受影响证据标注该限制。
8. 步骤 4-5 正常执行 SQL 与数据库查询。
9. 步骤 6 输出 v0.2 七字段契约，状态为 `success`（代码 + DB 证据闭环）。

## 预期输出契约

```yaml
status: success
summary: 订单查询接口报 ORDER_STATUS_INVALID 是因为订单 202607130002 的状态为 INVALID，代码在查询时校验到无效状态并抛出该错误码。
problem: 交易中心订单查询接口 GET /api/trade/order/query 对订单 202607130002 返回 ORDER_STATUS_INVALID。
root_cause: OrderQueryService.query() 在查询到订单状态为 INVALID 时抛出 ORDER_STATUS_INVALID 错误码；数据库确认订单 202607130002 状态为 INVALID。
evidence:
  - type: code
    source: trade-service/src/main/java/com/x/trade/service/OrderQueryService.java:88
    observation: 订单状态为 INVALID 时抛出 BizException(ORDER_STATUS_INVALID)。
    supports: 代码逻辑与错误码一致。
    confidence: high
  - type: code
    source: trade-web/src/main/java/com/x/trade/web/OrderController.java:45
    observation: 根路由入口调用 orderQueryService.query(orderId)。
    supports: 代码链路与接口一致。
    confidence: high
  - type: db
    source: 交易中心订单库
    observation: trade_order 表订单 202607130002 状态为 INVALID。
    supports: 数据库事实确认订单状态无效。
    confidence: high
restricted_info:
  - "code-intelligence 索引过期（INDEX_STALE），代码证据来自过期索引，置信度可能降低"
recommendations:
  - level: P0
    action: 告知用户订单 202607130002 当前状态为 INVALID，属正常业务校验（无效状态不允许查询详情）。
    owner: 值班/运营
    verification: 用户理解订单状态限制。
    estimated_effort: 10 分钟
  - level: P1
    action: 订单查询接口在订单状态为 INVALID 时返回明确可读的业务提示（如"该订单已失效"），而非仅抛错误码 ORDER_STATUS_INVALID。
    owner: 业务开发组
    verification: 用户看到可读提示而非纯错误码。
    estimated_effort: 半天
  - level: P2
    action: 建立订单状态异常监控：订单进入 INVALID 状态后若仍被频繁查询，触发告警排查上游状态流转。
    owner: 架构组
    verification: 状态异常在用户反馈前被监控捕获。
    estimated_effort: 1 周
```

## 失败判据

出现任一情况即判定失败：

- 步骤 3 未调用 code-intelligence MCP，直接走 grep。
- `source` 标记错误（如标记为 `grep` 而非 `code_intel`）。
- 字段映射错误（如把 `start_line` 漏掉，或 `matchType` 未映射为 route/error）。
- `INDEX_STALE` 诊断未被映射到 `restricted_info`，或未标注置信度降级。
- 编造 code-intelligence 返回结果、文件路径或行号。
- 输出 schema 缺少 `evidence`、`restricted_info` 或 `recommendations`。

## 对 SKILL.md 的反向要求

为通过此 GC，`SKILL.md` 必须明确：

- 步骤 3 首选 code-intelligence MCP 工具（`code.locate_route` / `code.search` / `code.explore_symbol`），code-intelligence 不可用时才降级增强 grep。
- `CodeLocation → CodeMatch` 的字段映射规则（file/start_line/snippet/confidence/query.type）。
- `source` 枚举包含 `code_intel`（Java 专项索引）与 `semantic`（semantic-lite）。
- diagnostics 映射规则：`INDEX_STALE` → restricted_info + 置信度降级。
- 索引状态处理：`stale` 时结果可用但需标注降级。
