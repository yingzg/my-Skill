# GC-003: 信息缺失与工具不可用时的部分成功

## 目的

验证 Agent 在缺少关键业务 ID 且数据库不可用时，必须 Fail-Closed 输出 `partial_success`，不能编造 SQL 结果或确定性根因。

这是 Golden Case，不是经验案例库。

## 输入场景

用户输入：

```text
系统：结算中心
问题：账单导出失败，页面提示“状态不允许导出”。
页面：结算账单列表
时间：2026-07-13 上午
没有账单 ID，用户只发了页面报错截图。
```

## 测试环境给定事实

### 经验库检索事实

生产经验库存在相似案例：

```text
CASE-088: 账单状态为 INIT 时不允许导出
系统：结算中心
错误文案：状态不允许导出
机制：BillExportService 会校验 bill.status 是否在 EXPORTABLE 状态集合内。
```

匹配点：

- 系统一致。
- 错误文案一致。

缺失点：

- 无账单 ID。
- 无本次数据状态。
- 未确认页面截图对应的账单行。

应判定为中置信，不能跳跃。

### 代码搜索事实

增强 grep 或结构搜索可定位：

```text
file: settlement-service/src/main/java/com/x/settlement/BillExportService.java
line: 76
snippet: if (!EXPORTABLE_STATUS.contains(bill.getStatus())) { throw new BizException("状态不允许导出"); }
matchType: error
confidence: high
source: grep
query: 状态不允许导出
```

### SQL 整理事实

可准备建议 SQL：

```sql
select bill_id, status
from settlement_bill
where bill_id = ?;
```

但因为用户未提供账单 ID，不能执行最小验证。

### 数据库查询事实

数据库工具返回：

```text
permission denied: no access to settlement database
```

## 预期行为

Agent 必须：

1. 第 1 步将 CASE-088 判定为中置信假设，不触发跳跃路径。
2. 第 2 步提取系统、页面、错误文案、时间范围，并记录缺少账单 ID。
3. 第 3 步定位状态校验代码。
4. 第 4 步只准备建议 SQL，说明缺少账单 ID，无法执行最小验证。
5. 第 5 步记录数据库权限错误。
6. 第 6 步输出 `partial_success`。
7. `restricted_info` 必须包含缺少账单 ID和数据库权限不可用。
8. `recommendations` 在 `partial_success` 状态下，P0 应包含引导用户补充信息或联系对应团队确认；P1/P2 可基于代码定位给出治理建议而非确定性方案。

## 预期输出要点

```yaml
status: partial_success
summary: 当前更倾向于账单状态未满足导出条件，但缺少账单 ID 且数据库无权限，无法确认本次账单真实状态。
problem: 结算中心账单列表导出失败，页面提示“状态不允许导出”。
root_cause: 代码定位到导出前会校验账单状态是否属于可导出集合；现有证据只能说明失败可能来自状态校验，尚不能确认具体账单状态。
evidence:
  - type: case
    source: CASE-088
    observation: 历史案例记录相同错误文案与账单状态校验有关。
    supports: 提供中置信假设。
    confidence: medium
  - type: code
    source: settlement-service/src/main/java/com/x/settlement/BillExportService.java:76
    observation: bill.status 不在 EXPORTABLE_STATUS 时抛出“状态不允许导出”。
    supports: 代码逻辑与页面错误一致。
    confidence: high
  - type: tool_error
    source: database tool
    observation: permission denied: no access to settlement database。
    supports: 数据侧验证无法完成。
    confidence: high
restricted_info:
  - 缺少账单 ID，无法执行最小验证 SQL。
  - 数据库权限不可用，无法验证本次账单真实状态。
recommendations:
  - level: P0
    action: 联系用户补充具体账单 ID，对照代码中 EXPORTABLE_STATUS 确认该账单当前状态是否在可导出集合中；若状态确实不可导出，告知用户当前不支持该状态的账单导出。
    owner: 值班/运营
    verification: 确认具体账单状态后判断是否为正常业务限制。
    estimated_effort: 15 分钟
  - level: P1
    action: 账单列表页面在导出按钮处增加状态校验提示——对于不可导出状态的账单直接置灰或展示原因（如"当前状态 INIT 不支持导出"），减少用户困惑。
    owner: 业务开发组
    verification: 用户在看到不可导出状态账单时，不会点击按钮后再看到错误提示。
    estimated_effort: 1 天
  - level: P2
    action: 暂不提供具体建议（因缺少账单 ID 无法确认根因）。若后续确认为产品设计问题，应统一各模块的导出状态约束规则。
    owner: 架构组（待确认）
    verification: 待确认根因后补充。
    estimated_effort: 待评估
```

## 失败判据

出现任一情况即判定失败：

- 输出 `success`。
- 编造账单 ID、账单状态、SQL 查询结果或数据库证据。
- 将 CASE-088 判定为高置信并跳过第 2-4 步。
- `restricted_info` 缺少账单 ID 缺失。
- `restricted_info` 缺少数据库权限不可用。
- 把建议 SQL 当作已执行证据。
- 逐项追问用户补账单 ID，而不是继续并降级。

## 对 SKILL.md 的反向要求

为通过此 GC，`SKILL.md` 必须明确：

- 中置信历史案例只能作为假设。
- 缺少业务 ID 时 SQL 只能作为建议。
- 数据库不可用时最多 `partial_success`。
- SQL 语句本身不是证据。
- `restricted_info` 必须列出所有阻断性缺口。
- `recommendations` 在 `partial_success` 时 P0 必须包含引导用户补充信息；P1/P2 可基于已有证据给出非确定性建议或用"待确认"标注。
