# 门禁文本解析模式

`parse_gate_discussions.ts` 支持类似 MiCR 的中文门禁报告，也支持英文模拟门禁报告。

## Bot 用户名

默认识别这些 Bot 用户名：

```text
MiCR
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
