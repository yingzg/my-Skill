# Golden Cases

Golden Cases 是 `online-troubleshoot` Skill 的回归压力测试集，不是线上经验案例库。

## 与经验案例库的区别

| 类型 | 路径 | 用途 | 是否参与第 1 步经验库检索 |
| --- | --- | --- | --- |
| Golden Cases | `golden-cases/GC-xxx.md` | 测试未来 Agent 是否遵守 Skill 流程、契约和护栏 | 否 |
| 经验案例库 | `CASES_DIR/CASE-xxx.md` | 真实工单排查时复用历史根因、SQL、处理方式 | 是 |

不要把本目录中的文件作为生产案例命中结果。它们是测试输入和判定标准。

## 使用方式

1. 让待测 Agent 读取 `SKILL.md` 和必要引用文件。
2. 给 Agent 一个 Golden Case 的“输入场景”和“测试环境给定事实”。
3. 让 Agent 按 Skill 执行排查并输出 v0.2 七字段契约。
4. 对照该 Golden Case 的“预期行为”“预期输出要点”“失败判据”判定通过或失败。

## 当前用例

- `GC-001-full-success.md`：完整成功排查，要求代码证据和数据库证据闭环。
- `GC-002-case-reuse.md`：高置信经验库复用，要求跳跃路径仍执行最小验证。
- `GC-003-partial-success.md`：信息缺失和数据库不可用，要求 Fail-Closed 输出 `partial_success`。
- `GC-004-trace-driven.md`：Trace 驱动排查，验证日志驱动快速路径 + 三层建议（P0/P1/P2）输出。
- `GC-005-trace-partial.md`：Trace API 不可用时的降级行为，验证快速路径失败后退回标准流程。

## 通用失败判据

任一 Golden Case 中出现以下行为，通常都应判定失败：

- 编造 SQL 查询结果、文件路径、行号、业务 ID、历史案例或根因。
- 证据不足却输出 `success`。
- 跳过必须执行的最小验证。
- 逐项追问用户，违反零中断原则。
- 输出 schema 缺少 `status`、`summary`、`problem`、`root_cause`、`evidence`、`restricted_info`、`recommendations`。
- 把 `golden-cases/` 当作 `CASES_DIR` 使用。
- `recommendations` 为空或三层建议未绑定到具体证据。
- P0 建议依赖代码发布（不是运维/值班可独立执行的）。
