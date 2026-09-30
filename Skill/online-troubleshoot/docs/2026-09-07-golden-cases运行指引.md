# Golden Cases 运行指引

> 目的：说明如何用 Golden Cases 手动验证 online-troubleshoot SKILL 的行为是否符合预期。
> 适用：改完 SKILL.md / references 后回归验证；或日常抽查。
> 说明：Golden Cases 目前是「人工对照测试」（无自动化 runner），判定靠人读对照，而非脚本自动执行。

---

## 一、Golden Cases 是什么

`golden-cases/` 目录下的 6 个 GC 文件是「行为回归测试」，**不是生产案例库**。它们不参与运行时（Step 1 历史案例预检绝不会检索它们，绝不能当 `CASES_DIR` 用）。

每个 GC 文件的结构：

| 字段 | 作用 |
|------|------|
| 输入场景 | 喂给 Agent 的用户输入 |
| 测试环境给定事实 | 模拟工具返回的数据（**不需要真实 GitLab/DB/Sonar/Trace**） |
| 预期行为 | Agent 必须做什么 |
| 预期输出契约 | 预期 Agent 输出的完整七字段 YAML |
| 失败判据 | 什么算失败 |
| 对 SKILL.md 的反向要求 | 这个 GC 要求 SKILL.md 必须写哪些规则 |

---

## 二、怎么跑（人工对照流程）

1. 让待测 Agent 读取 `SKILL.md` 和必要 references（`log-patterns.md`、`trace-diagnosis.md`、`troubleshoot-examples.md`、`templates/output.md`）。
2. 把 GC 的「输入场景」作为用户输入喂给 Agent。
3. 把「测试环境给定事实」作为「模拟的工具返回」提供——告诉 Agent「假设工具返回了这些数据」，让它基于这些事实执行，而不是真的去调工具。
4. 让 Agent 按 SKILL 执行排查，产出 v0.2 七字段契约。
5. 人工对照「预期行为」「预期输出契约」「失败判据」逐条判定通过/失败。

**关键**：Golden Cases 测的是「Agent 是否遵守行为契约」，**不是**「Agent 能否真的查到数据」。给定事实里已经写死了「工具会返回什么」，所以不需要真实环境。

---

## 三、6 个 GC 清单

| GC | 场景 | 核心验证点 |
|---|---|---|
| GC-001 | 完整成功排查 | 代码+DB 证据闭环 → `success`，不跳过验证 |
| GC-002 | 高置信经验库复用 | 跳跃路径（跳 2-4 步）+ Step 5 最小验证强制 |
| GC-003 | 信息缺失 + DB 不可用 | Fail-Closed → `partial_success`，不编造 |
| GC-004 | Trace 驱动 | 黑洞检测 + Pattern 匹配 + P0/P1/P2 |
| GC-005 | Trace API 不可用 | 快速路径失败 → 退回标准流程，不卡死不 `failed` |
| GC-006 | code-intelligence 适配 | Step 3 用 MCP 工具 + `source=code_intel` + diagnostics 映射 |

---

## 四、通用失败判据（任一出现即判失败）

- 编造 SQL 结果、文件路径、行号、业务 ID、历史案例或根因。
- 证据不足却输出 `success`。
- 跳过必须执行的最小验证。
- 逐项追问用户，违反零中断原则。
- 输出 schema 缺少 `status` / `summary` / `problem` / `root_cause` / `evidence` / `restricted_info` / `recommendations` 七字段。
- 把 `golden-cases/` 当作案例库使用。
- `recommendations` 为空或未绑定具体证据。
- P0 建议依赖代码发布（不是运维/值班可独立执行的）。

---

## 五、v0.3 后重点回归项

v0.3 引入的新能力，跑 GC 时重点关注：

1. **Step 0 流程初始化**：选系统是否从输入推断（不追问）；是否检查 `.troubleshoot/checkpoints/` 判断 fresh/resume。
2. **Step 3 首选 code-intelligence**：GC-006 验证「调 code.locate_route / code.search 而非 grep」；GC-003/005 验证「code-intelligence 未配置时降级 grep」。
3. **diagnostics 映射**：`INDEX_STALE` / `GREP_FALLBACK_USED` 等是否映射到 `restricted_info` + 置信度降级。
4. **诊断优先级**：明确异常（异常消息含业务语义）直接 Phase C；症状型异常（Broken pipe/超时）仍需 Pattern 匹配（GC-004 验证）。
5. **路径统一**：checkpoint 是否写 `.troubleshoot/checkpoints/`，案例库是否用 `.troubleshoot/cases/`。

---

## 六、注意事项

- GC 文件里的「预期输出契约」是**参考基准**，不必逐字匹配——重点看「status 是否正确、evidence 是否闭环、restricted_info 是否列出缺口、recommendations 是否锚定证据」。
- 语义项（summary 是否业务可读、是否编造）需要人肉判断，机械项（schema 字段数、evidence 类型）可以脚本化（问题 6 暂缓，未实现）。
- 跑完记录「哪个 GC 通过/失败 + 失败原因」，失败原因指向 SKILL.md 的规则缺口，回填到 SKILL.md。
