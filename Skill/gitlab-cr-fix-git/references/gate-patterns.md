# 门禁文本解析模式

`parse_gate_discussions.ts` 支持中文门禁报告，也支持英文模拟门禁报告。

## Bot 用户名

从 `config.json` 的 `gate.bot_usernames` 读取，默认识别这些 Bot 用户名：

```text
MockGateBot
GateBot
QualityBot
```

## 支持的文本行

中文示例：

```text
有效评论数：2 / 5
变更代码单元测试覆盖率：45.00% / 60%
单元测试覆盖率：45.00% / 60%
单测用例执行通过率：97.67% / 100%
Sonar质量门禁：未通过
Pipeline：failed
Approve：missing
```

英文示例：

```text
Effective comments: 2 / 5
Coverage: 45.00% / 60%
Test pass rate: 97.67% / 100%
Sonar quality gate: failed
Pipeline: failed
Approval: missing
```

## 输出语义

比例类门禁项输出：

```json
{
  "current": 45,
  "required": 60,
  "passed": false
}
```

状态类门禁项输出：

```json
{
  "status": "failed",
  "passed": false
}
```

## 设计约束

1. 门禁解析只提取事实，不负责修复。
2. 同一个 MR 中如果存在多条 Bot 门禁评论，后解析到的字段会覆盖前面的同名字段，用于表示最新状态。
3. 解析失败时不要推断门禁通过或失败，应在最终报告中标记为缺少证据。
4. 如果实际项目的 Bot 文案不同，应扩展解析模式或配置项，而不是把某个公司格式硬编码进 `SKILL.md`。

## 与门禁 Bot 的自洽闭环

`build_gate_report.ts`（门禁 Bot）生成的报告使用本文件定义的字段格式，因此能被 `parse_gate_discussions.ts` 精确回读：

- Bot 是「生产端」，`parse_gate_discussions.ts` 是「消费端」，格式天然自洽。
- Bot 报告的缺失维度（如 `Sonar质量门禁：缺失`）回读后 `passed` 为 `null`，不会误判为通过或失败。
- Bot 报告的 `blockers`（`passed === false` 的字段集合）与回读结果一致。

差异点：Bot 自行统计的「有效评论数」口径是「非 bot、非 system 评论数」，可能与外部门禁 bot 的权威判定不同；Bot 自产报告是「通用降级」，独立于任何特定门禁系统的实现。
