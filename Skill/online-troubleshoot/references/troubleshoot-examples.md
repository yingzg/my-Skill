# 排查示例

这些示例用于校准 Skill 执行方式。它们不是生产经验案例库，不参与第 1 步历史案例检索。

## 示例 1：完整成功

用户输入：

```text
交易中心订单详情页报“商品明细为空”，接口 /api/trade/order/detail，订单 202607130001，日志提示 item snapshot missing。
```

关键执行：

1. 第 1 步：经验库无高置信命中。
2. 第 2 步：提取系统、接口、订单 ID、错误文案和异常栈。
3. 第 3 步：定位 `OrderController.detail`、`OrderDetailService.buildItems` 和 `OrderItemSnapshotMapper.xml`。
4. 第 4 步：准备 `order_item_snapshot where order_id = ?` 的最小验证 SQL。
5. 第 5 步：DB 查询返回 0 rows。
6. 第 6 步：代码逻辑、日志和数据闭环，输出 `success`。

简版输出：

```yaml
status: success
summary: 订单 202607130001 详情页报错是因为商品快照为空，代码在组装商品明细时主动抛出 item snapshot missing。
problem: 交易中心订单详情接口 /api/trade/order/detail 查询订单 202607130001 时商品明细为空。
root_cause: order_item_snapshot 表中该订单没有商品快照记录，OrderDetailService.buildItems 在快照为空时抛出异常，导致详情页无法展示。
evidence:
  - type: code
    source: trade-service/.../OrderDetailService.java:187
    observation: snapshots.isEmpty() 时抛出 item snapshot missing。
    supports: 代码逻辑与日志错误一致。
    confidence: high
  - type: db
    source: 交易中心订单库
    observation: order_item_snapshot 查询订单 202607130001 返回 0 rows。
    supports: 数据库确认商品快照缺失。
    confidence: high
restricted_info: []
```

## 示例 2：经验库复用

用户输入：

```text
营销系统活动页保存失败，报 PROMO_RULE_CONFLICT，活动 ID A2026071308。
```

经验库命中：

```text
CASE-021: 营销活动规则冲突导致保存失败
系统：营销系统
错误码：PROMO_RULE_CONFLICT
机制：活动规则表中存在同优先级、同渠道、时间重叠的启用规则。
验证 SQL：select ... from promo_rule where activity_id = ? and enabled = 1
```

正确行为：

1. 第 1 步：系统、错误码、机制至少两个关键点一致，判定高置信。
2. 跳过第 2-4 步详细定位。
3. 第 5 步：必须执行最小验证 SQL，确认活动 A2026071308 是否存在冲突规则。
4. 第 6 步：只有最小验证返回真实冲突记录时，才能输出 `success`。

错误行为：

- 仅凭 CASE-021 直接输出 `success`。
- 没有最小验证结果。
- 把经验库中的历史活动 ID 当成本次活动 ID。

## 示例 3：部分成功

用户输入：

```text
结算系统导出账单失败，页面提示“状态不允许导出”，没有给账单 ID。数据库 MCP 当前无权限。
```

正确行为：

1. 第 1 步：检索经验库，可找到相似“状态不允许导出”案例，但没有账单 ID，不能高置信复用。
2. 第 2 步：提取系统、页面现象和错误文案；记录缺少账单 ID。
3. 第 3 步：搜索错误文案，定位导出状态校验代码。
4. 第 4 步：整理建议 SQL，但因缺少账单 ID 不能执行最小验证。
5. 第 5 步：数据库 MCP 无权限，记录工具错误。
6. 第 6 步：输出 `partial_success`。

简版输出：

```yaml
status: partial_success
summary: 当前更倾向于账单状态未满足导出条件，但缺少账单 ID 且数据库无权限，无法确认具体数据状态。
problem: 结算系统导出账单失败，页面提示“状态不允许导出”。
root_cause: 代码定位到导出前会校验账单状态；现有证据只能说明失败可能来自状态校验，尚不能确认该账单真实状态。
evidence:
  - type: code
    source: settlement-service/.../BillExportService.java
    observation: 导出前校验 bill.status 是否在允许导出集合内。
    supports: 页面错误与状态校验逻辑一致。
    confidence: medium
  - type: tool_error
    source: database MCP
    observation: 当前账号无结算库查询权限。
    supports: 无法完成数据侧验证。
    confidence: high
restricted_info:
  - 缺少账单 ID，无法构造最小验证 SQL。
  - 数据库权限不可用，无法验证真实账单状态。
```

错误行为：

- 输出 `success`。
- 编造账单 ID、账单状态或 SQL 查询结果。
- 忽略数据库权限缺失。
