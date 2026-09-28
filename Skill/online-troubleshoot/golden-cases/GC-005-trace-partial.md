# GC-005: Trace API 不可用时的降级行为

## 目的

验证 Agent 在用户提供 traceId 但 Trace 工具不可用时，不会因为快速路径失败而中止排查，而是退回原步骤 2 逻辑继续分析，并通过 `restricted_info` 标注工具限制。

这是 Golden Case，不是经验案例库。它不得被第 1 步历史案例预检当作 `CASES_DIR/CASE-xxx.md` 使用。

## 输入场景

用户输入：

```text
traceId: abc123-def456-ghi789
营销活动页保存活动配置报错"活动名称重复"
```

## 测试环境给定事实

### Trace 数据

ITraceFetcher.getTrace 返回：

```yaml
error:
  type: permission_denied
  message: 无权限访问 Hera 项目，请联系管理员开通
  source: hera
```

`getLogs` 同样不可用（同上错误）。

### 历史案例预检

`.troubleshoot/cases/` 中没有高置信命中。中置信命中一个历史上"活动名称重复保存失败"的案例，但机制不同。

### 代码搜索事实

（给定事实：code-intelligence 未配置，步骤 3 走增强 grep 兜底，source=grep）

增强 grep 可按关键词定位：

```text
file: promotion-service/src/main/java/com/x/promotion/service/ActivityService.java
line: 156
snippet: if (activityMapper.countByName(name) > 0) { throw new BizException("ACTIVITY_NAME_DUPLICATE", "活动名称重复"); }
matchType: error
confidence: high
source: grep
query: 活动名称重复
```

### SQL 整理事实

最小验证 SQL：

```sql
select id, name, status
from activity
where name = '春节大促满减活动'
  and deleted = 0;
```

### 数据库查询事实

数据库工具可用。最小验证查询返回：

```text
id: 1024, name: 春节大促满减活动, status: ACTIVE
```

## 预期行为

Agent 必须：

1. 执行第 1 步历史案例预检，识别到中置信案例但不作为跳跃路径。
2. 第 2 步识别到 traceId → 触发日志驱动快速路径：
   - Phase A：调用 ITraceFetcher.getTrace → 返回 `permission_denied`。
   - 尝试 1 次重试（可选，取决于降级策略）。
   - **不卡死**，立即退回原步骤 2 逻辑：从用户文本中提取"营销活动""保存失败""活动名称重复"等信息。
   - 在 `restricted_info` 中标注 Trace 工具不可用的原因。
3. 第 3 步使用文本提取的关键词（"活动名称重复""营销活动"）进行代码搜索，定位到 ActivityService、Mapper 和异常抛出逻辑。
4. 第 4-5 步按正常流程执行 SQL 和数据库查询。
5. 第 6 步输出 v0.2 七字段契约，状态为 `success`（因为代码和 DB 证据已闭环）。
6. `evidence` 至少包含 `code`、`db`、`user_input` 三类证据。
7. `recommendations` 可以仅包含 P0 和 P1 级别建议（因为工具限制未影响代码和数据的证据闭环），P2 可以被省略或仅包含提示性建议。
8. `restricted_info` 必须包含 Trace 查询失败的说明和已采取的降级措施。

## 预期输出契约

```yaml
status: success
summary: 活动保存报错是因为活动名称"春节大促满减活动"已存在于数据库中，代码在保存前做了唯一性校验。
problem: 营销活动页保存活动配置报错"活动名称重复"，用户输入 traceId abc123 但 Trace 工具权限不可用。
root_cause: ActivityService.saveActivity() 方法在保存前调用 countByName() 检查名称唯一性，数据库中已存在同名且未删除的活动记录。
evidence:
  - type: user_input
    source: 用户输入
    observation: 提供 traceId、模块"营销活动"、错误"活动名称重复"。
    supports: 明确排查对象为活动保存接口。
    confidence: high
  - type: code
    source: promotion-service/src/main/java/com/x/promotion/service/ActivityService.java:156
    observation: countByName(name) > 0 时抛出 BizException 活动名称重复。
    supports: 代码逻辑与用户报错一致。
    confidence: high
  - type: db
    source: 营销活动库
    observation: activity 表中已存在 name='春节大促满减活动' 且 status=ACTIVE 的记录。
    supports: 数据库事实确认名称重复。
    confidence: high
restricted_info:
  - "Trace 查询工具返回 permission_denied，无法通过 Trace 验证请求链路。已退回基于文本关键词的排查路径。"
  - "未通过日志验证，错误日志来源未确认。"
recommendations:
  - level: P0
    action: 联系用户确认是否要覆盖已有活动，或改用新名称后重试。
    owner: 值班/运营
    verification: 用户成功保存活动配置。
    estimated_effort: 10 分钟
  - level: P1
    action: 活动名称唯一性校验改为允许编辑同名活动（如区分新增和编辑场景），或在前端提供"活动名称已存在，是否覆盖"提示。
    owner: 业务开发组
    verification: 编辑已有活动时不再因同名报错。
    estimated_effort: 1 天
  - level: P2
    action: 上线活动软删除后同名校验仅针对非删除记录；建立活动名称变更记录。
    owner: 架构组
    verification: 删除活动后同名可复用；活动名称变更可追溯。
    estimated_effort: 1 周
```

## 失败判据

出现任一情况即判定失败：

- 因 Trace API 返回权限错误而直接输出 `failed`。
- 卡在 Phase A 反复重试或询问用户如何处理，而不是退回原步骤 2。
- 退回原步骤 2 后未从用户文本中提取关键信息。
- `restricted_info` 未说明 Trace 工具不可用及其原因。
- 输出 `success` 但没有代码和 DB 证据闭环。
- 编造 Trace 数据或日志内容。
- 输出 schema 为 v0.1 六字段（缺少 `recommendations`）。
- `recommendations` 为空。

## 对 SKILL.md 的反向要求

为通过此 GC，`SKILL.md` 必须明确：

- 日志驱动快速路径在 Trace 工具不可用时，必须退回原步骤 2 逻辑，不得卡死或直接 `failed`。
- 退回时需要标注 `restricted_info` 说明工具不可用原因和降级措施。
- 退回后排查流程与无 traceId 输入时一致，不得因为快速路径尝试失败而降低后续步骤的执行标准。
- 工具不可用不应将状态直接降为 `failed`——只要文本信息足够支撑代码+DB 闭环，仍可输出 `success`。
