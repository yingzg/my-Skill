# GC-002: 高置信经验库复用

## 目的

验证 Agent 在历史案例高置信命中时，可以使用跳跃路径跳过第 2-4 步，但仍必须执行第 5 步最小验证。此 GC 专门防止“看到相似案例就直接输出 success”的过度自信行为。

这是 Golden Case，不是经验案例库。

## 输入场景

用户输入：

```text
系统：营销中心
问题：活动 A2026071308 保存失败，页面提示 PROMO_RULE_CONFLICT。
接口：POST /api/promo/activity/save
时间：2026-07-13 14:00 - 14:20
```

## 测试环境给定事实

### 经验库检索事实

生产经验库中存在：

```text
CASE-021: 营销活动规则冲突导致保存失败
系统：营销中心
接口：/api/promo/activity/save
错误码：PROMO_RULE_CONFLICT
根因：同渠道、同优先级、时间重叠的启用规则导致冲突。
最小验证 SQL：
select id, channel, priority, start_time, end_time
from promo_rule
where activity_id = ?
  and enabled = 1
  and conflict_flag = 1;
```

匹配点：

- 系统一致：营销中心。
- 接口一致：`/api/promo/activity/save`。
- 错误码一致：`PROMO_RULE_CONFLICT`。
- 业务现象一致：活动保存失败。

应判定为高置信。

### 数据库查询事实

第 5 步最小验证 SQL 对活动 `A2026071308` 返回：

```text
id=9821, channel=APP, priority=10, start_time=2026-07-12 00:00:00, end_time=2026-07-20 23:59:59
id=9822, channel=APP, priority=10, start_time=2026-07-13 00:00:00, end_time=2026-07-18 23:59:59
```

## 预期行为

Agent 必须：

1. 第 1 步执行两轮经验库检索。
2. 将 CASE-021 判定为高置信。
3. 明确说明触发跳跃路径：跳过第 2-4 步详细定位。
4. 第 5 步仍执行最小验证 SQL。
5. 使用本次活动 `A2026071308` 的真实查询结果作为 DB evidence。
6. 第 6 步输出 `success`，说明保存失败来自同渠道、同优先级、时间重叠规则冲突。
7. `recommendations` 应包含 P0（告知用户哪两条规则冲突让其修改）、P1（保存时前端展示冲突规则提示）、P2（规则冲突自动检测）。

## 预期输出要点

```yaml
status: success
summary: 活动 A2026071308 保存失败是因为存在同渠道、同优先级且时间重叠的启用规则，触发 PROMO_RULE_CONFLICT。
problem: 营销中心活动保存接口 /api/promo/activity/save 对活动 A2026071308 返回 PROMO_RULE_CONFLICT。
root_cause: 高置信历史案例 CASE-021 与本次系统、接口、错误码和现象一致；最小验证 SQL 确认本次活动存在 APP 渠道 priority=10 的时间重叠启用规则。
evidence:
  - type: case
    source: CASE-021
    observation: 历史案例记录 PROMO_RULE_CONFLICT 由同渠道、同优先级、时间重叠规则导致。
    supports: 提供高置信复用假设和验证 SQL。
    confidence: high
  - type: db
    source: 营销中心活动库
    observation: 活动 A2026071308 查询到两条 APP 渠道 priority=10 且时间重叠的启用规则。
    supports: 最小验证确认本次问题与历史案例机制一致。
    confidence: high
restricted_info: []
recommendations:
  - level: P0
    action: 告知用户活动 A2026071308 与已有规则（id=9821, 9822）存在渠道 APP、优先级 10 的时间重叠冲突；指导用户修改冲突规则的时间范围或优先级后重试。
    owner: 值班/运营
    verification: 用户调整规则后活动保存成功。
    estimated_effort: 10 分钟
  - level: P1
    action: 活动保存页面在提交前执行规则冲突预检，如发现冲突在前端展示具体冲突规则（ID + 时间 + 渠道），让运营在提交前发现并自行调整。
    owner: 业务开发组
    verification: 运营在提交前看到冲突提示并自行修改，而非提交后才报错。
    estimated_effort: 1 天
  - level: P2
    action: 规则管理系统增加冲突自动检测能力：新规则保存时自动标注与之冲突的已有规则，并输出冲突报告；降低人工排查成本。
    owner: 架构组
    verification: 新规则冲突在后台自动识别，运营无需手动对照。
    estimated_effort: 2 周
```

## 失败判据

出现任一情况即判定失败：

- 仅凭 CASE-021 直接输出 `success`，没有第 5 步最小验证。
- 最小验证 SQL 使用历史案例中的旧活动 ID，而不是 `A2026071308`。
- 没有说明为什么 CASE-021 是高置信。
- 把高置信跳跃路径误解为可以跳过数据库验证。
- 将 Golden Case 当作生产经验案例库命中。
- 输出 schema 缺少 `evidence`、`restricted_info` 或 `recommendations`。

## 对 SKILL.md 的反向要求

为通过此 GC，`SKILL.md` 必须明确：

- 经验库高置信条件。
- 高置信可以跳过第 2-4 步，但不能跳过第 5 步。
- 历史案例只能提供假设和验证路径，不能直接替代本次数据证据。
- Golden Cases 不参与第 1 步经验库检索。
- v0.2 必须输出 `recommendations` 字段，且建议必须锚定到具体证据（此 GC 中 P0 应指向冲突规则 ID）。
