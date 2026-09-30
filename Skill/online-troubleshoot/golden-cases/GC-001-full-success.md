# GC-001: 完整成功排查

## 目的

验证 Agent 在信息相对完整、工具可用、代码与数据证据都能闭环时，能够按 Skill 输出 `success`，且不会跳过代码定位、SQL 整理、数据库查询和最终验证。

这是 Golden Case，不是经验案例库。它不得被第 1 步历史案例预检当作 `CASES_DIR/CASE-xxx.md` 使用。

## 输入场景

用户输入：

```text
系统：交易中心
问题：订单详情页打开报错“商品明细为空”，用户反馈订单 202607130001 无法查看详情。
接口：GET /api/trade/order/detail
时间：2026-07-13 10:20:00 - 10:40:00
日志：
2026-07-13 10:28:31.455 ERROR [trade-web] c.x.trade.web.OrderController - detail failed, orderId=202607130001
java.lang.IllegalStateException: item snapshot missing
    at com.x.trade.service.OrderDetailService.buildItems(OrderDetailService.java:187)
    at com.x.trade.service.OrderDetailService.detail(OrderDetailService.java:92)
    at com.x.trade.web.OrderController.detail(OrderController.java:54)
```

## 测试环境给定事实

此 GC 假设工具可用，并给出工具应返回的事实，便于未来测试时对照 Agent 输出是否尊重证据。

### 历史案例预检

`CASES_DIR` 中没有高置信命中。允许出现中置信相似案例，但不得跳过第 2-4 步。

### 代码搜索事实

结构搜索或增强 grep 可定位：

```text
file: trade-web/src/main/java/com/x/trade/web/OrderController.java
line: 54
snippet: return orderDetailService.detail(orderId);
matchType: route
confidence: high
source: gitnexus 或 grep
query: /api/trade/order/detail
```

```text
file: trade-service/src/main/java/com/x/trade/service/OrderDetailService.java
line: 187
snippet: if (snapshots.isEmpty()) { throw new IllegalStateException("item snapshot missing"); }
matchType: error
confidence: high
source: gitnexus 或 grep
query: item snapshot missing
```

```text
file: trade-service/src/main/resources/mapper/OrderItemSnapshotMapper.xml
line: 23
snippet: select * from order_item_snapshot where order_id = #{orderId}
matchType: sql
confidence: high
source: gitnexus 或 grep
query: order_item_snapshot order_id
```

### SQL 整理事实

最小验证 SQL：

```sql
select order_id, count(*) as snapshot_count
from order_item_snapshot
where order_id = '202607130001'
group by order_id;
```

根因确认 SQL：

```sql
select id, order_id, sku_id, deleted, created_at
from order_item_snapshot
where order_id = '202607130001'
order by id;
```

表名来源：`OrderItemSnapshotMapper.xml`。  
数据源来源：交易中心订单库配置。  
必要条件：订单 ID 和时间范围均由用户输入提供。

### 数据库查询事实

最小验证查询返回：

```text
0 rows
```

根因确认查询返回：

```text
0 rows
```

## 预期行为

Agent 必须：

1. 执行第 1 步历史案例预检，并说明没有高置信跳跃路径。
2. 第 2 步提取接口、订单 ID、时间范围、错误文本、异常类型、触发类和行号。
3. 第 3 步定位 Controller、Service 异常点和 Mapper SQL，并归一化为 `CodeMatch` 证据。
4. 第 4 步说明 SQL 的表名来源、数据源来源、输入条件和用途。
5. 第 5 步使用真实数据库查询事实作为 DB 证据。
6. 第 6 步输出 v0.2 七字段契约，状态为 `success`。
7. `evidence` 至少包含 `code`、`db`、`log`、`user_input` 四类证据。
8. `restricted_info` 应为空数组，或仅包含非阻断说明。
9. `recommendations` 应包含三层建议：P0（数据修复指引）、P1（防御性代码）、P2（监控告警）。

## 预期输出契约

```yaml
status: success
summary: 订单 202607130001 详情页报错是因为商品快照为空，代码在组装商品明细时主动抛出 item snapshot missing。
problem: 交易中心订单详情接口 /api/trade/order/detail 在查询订单 202607130001 时返回商品明细为空错误。
root_cause: order_item_snapshot 表中该订单没有商品快照记录，OrderDetailService.buildItems 在快照为空时抛出 IllegalStateException，导致详情页无法展示商品明细。
evidence:
  - type: user_input
    source: 用户输入
    observation: 提供系统、接口、订单 ID、时间范围和错误日志。
    supports: 明确排查对象与查询条件。
    confidence: high
  - type: log
    source: 错误日志
    observation: IllegalStateException: item snapshot missing，触发位置 OrderDetailService.java:187。
    supports: 错误发生在商品明细组装阶段。
    confidence: high
  - type: code
    source: trade-service/src/main/java/com/x/trade/service/OrderDetailService.java:187
    observation: snapshots.isEmpty() 时抛出 item snapshot missing。
    supports: 代码逻辑与日志错误一致。
    confidence: high
  - type: code
    source: trade-service/src/main/resources/mapper/OrderItemSnapshotMapper.xml:23
    observation: 商品快照来自 order_item_snapshot where order_id = #{orderId}。
    supports: SQL 表名来源明确。
    confidence: high
  - type: db
    source: 交易中心订单库
    observation: order_item_snapshot 查询订单 202607130001 返回 0 rows。
    supports: 数据库事实确认该订单商品快照缺失。
    confidence: high
restricted_info: []
recommendations:
  - level: P0
    action: 联系下游系统确认下单时是否触发了快照落库逻辑；若该订单应存在快照，协调数据修复补录 order_item_snapshot 数据。
    owner: 值班/运营
    verification: 用户通过订单详情页正常查看商品明细。
    estimated_effort: 30 分钟
  - level: P1
    action: OrderDetailService.buildItems() 在快照为空时改为返回明确可读的错误提示（如"商品快照数据缺失，请联系客服"），而非直接抛出 IllegalStateException 导致 500 错误。
    owner: 业务开发组
    verification: 相同条件下接口返回 4xx 带明确提示而不是 5xx。
    estimated_effort: 半天
  - level: P2
    action: 建立 order_item_snapshot 表数据完整性监控告警：订单创建后 N 分钟内无快照记录时触发告警。
    owner: 架构组
    verification: 快照缺失问题在用户发现前被监控捕获。
    estimated_effort: 1 周
```

## 失败判据

出现任一情况即判定失败：

- 输出 `success`，但 `evidence` 中没有 DB 查询结果。
- 输出 `success`，但没有代码文件路径或方法/行号证据。
- 编造未给定的 SQL 查询结果、表名、文件路径、行号、历史案例或处理人。
- 将中置信历史案例当作高置信并跳过第 2-4 步。
- 未说明 SQL 的表名来源或数据源来源。
- 逐项追问用户补字段，而不是基于已有输入继续排查。
- 输出 schema 超出 v0.2 七字段，且未将额外需求写入 `restricted_info`。
- `summary` 不是业务可读语言，或默认简版结论超过 300 个中文字符。
- `recommendations` 为空或三层建议未绑定到具体证据。

## 对 SKILL.md 的反向要求

为通过此 GC，`SKILL.md` 必须明确：

- `success` 必须具备代码证据和数据证据闭环。
- SQL 语句本身不是证据，只有实际查询结果才是证据。
- 第 2 步必须一次性结构化提取上下文，不逐项追问。
- 第 3 步必须将工具结果归一化为可追溯代码证据。
- 第 4 步必须说明表名来源、数据源来源和查询目的。
- L4 最终输出验证必须阻止无 DB 证据的 `success`。
- `recommendations` 三层建议必须各有证据锚点（P0 数据修复、P1 防御代码、P2 监控建设）。
- `restricted_info` 不覆盖 `recommendations` 该做的事。
