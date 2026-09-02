# 降级决策矩阵

> SKILL.md 编排层在每次脚本/LLM 调用返回非零 exit code 时查此文件，决定降级继续还是中断。
> 脚本和 LLM 不消费此文件。

---

## 一、决策速查表

| # | 失败场景 | Phase | 决策 | 后续行为 | 复查清单标记 |
|---|---------|:---:|:---:|---------|:---:|
| D0 | 非 git 仓库 | 0 | ⚠️ 中断 | 提示用户：`当前目录不是 git 仓库，Skill 无法运行` | — |
| D1 | `git diff` 无 Mapper 变更 | 0 | ✅ 优雅退出 | exit 0，输出「本次变更无 SQL 相关修改」 | — |
| D2 | XML 解析失败（单文件） | 1 | ✅ 降级 | 跳过该文件，记录 `parse_error`，其余继续 | `parse_error` |
| D3 | XML 解析失败（全部文件） | 1 | ⚠️ 中断 | 无法提取任何 SQL，继续无意义 | — |
| D4 | 数据源发现失败（无 @DS、无 @MapperScan 配置） | 0.5 | ✅ 降级 | `datasource=UNKNOWN`，跳过 EXPLAIN，仅执行静态规则分析 | `datasource_unknown` |
| D5 | 数据库连接失败（MCP 不可用、网络不通、权限不足） | 4b | ✅ 降级 | 降级为纯静态规则模式，每条 SQL 标注 `explain_executed: false` | `explain_unavailable` |
| D6 | EXPLAIN 执行失败（单条 SQL） | 4b | ✅ 降级 | 该条标注 `EXPLAIN_FAILED` + 失败原因；其余 SQL 继续执行 | `explain_unavailable` |
| D7 | EXPLAIN 执行失败（全部 SQL） | 4b | ✅ 降级 | 等同于 D5，降级为纯静态规则模式 | `explain_unavailable` |
| D8 | 调用链追踪失败（类文件不存在） | 2 | ✅ 降级 | 标注 `call_chain_broken` + 断裂原因；LLM 做保守判断 | `call_chain_broken` |
| D9 | 参数值无法静态确定（动态 SQL 片段） | 3 | ✅ 降级 | 标注 `param_uncertain: true` + 不确定的动态标签列表 | `param_uncertain` |
| D10 | 规则文件加载失败 | 4a | ⚠️ 中断 | 规则文件是静态分析的唯一依据，缺失则无法工作 | — |
| D11 | 规则文件为空（`rules: []`） | 4a | ⚠️ 中断 | 无规则可执行，继续无意义 | — |
| D12 | `match_rules.py` 执行异常（非单条规则失败） | 4a | ⚠️ 中断 | 脚本崩溃，无法继续 | — |
| D13 | LLM API 超时（单批次） | 4b | ✅ 降级 | 该批次 SQL 标注 ANALYSIS_FAILED，其余批次继续 | `llm_timeout` |
| D14 | LLM API 超时（全部批次） | 4b | ⚠️ 中断 | 无法生成风险分析，最终报告无价值 | — |
| D15 | LLM 输出格式不合法（JSON 解析失败） | 4b | ⚠️ 中断 | 无法产出结构化的风险报告 | — |
| D16 | 报告生成失败（数据校验不通过） | 5 | ⚠️ 中断 | dump 原始中间文件到 `/tmp/sql-review-dump/`，提示用户手动查看 | — |
| D17 | 脚本依赖缺失（Python 解释器无必要包） | 任意 | ⚠️ 中断 | 无法执行脚本，提示安装依赖 | — |

---

## 二、降级与中断的判断原则

### ⚠️ 中断条件（任一满足即中断）

- 继续执行毫无意义（如无 SQL 变更、全部脚本崩溃）
- 最终结果完全不可信（如全部 LLM 调用失败、规则文件缺失）
- 无法输出任何可用的报告
- 缺少必要的运行时依赖

**中断时的输出**：明确的错误信息 + 建议的恢复操作。不要静默失败。

### ✅ 降级条件

- 仍有部分 SQL 可以正常分析
- 虽然不完整，但输出的报告仍有参考价值
- 可以事后通过复查清单弥补缺失的信息

**降级时的输出**：
1. 在报告中标注降级类型和影响范围
2. 在复查清单中记录缺失项，供后续人工复核
3. 不改变门禁结论的计算方式（缺失的部分不影响结论）

---

## 三、复查清单项说明

| 标记 | 含义 | 人需做什么 |
|------|------|-----------|
| `parse_error` | XML 解析失败 | 检查对应的 MyBatis XML 文件语法是否正确 |
| `datasource_unknown` | 数据源未识别 | 手动确认该 Mapper 对应的数据源，补充 `--ds-mapping` 参数 |
| `explain_unavailable` | EXPLAIN 不可用 | 在数据库中手动执行 EXPLAIN，对照 `explain-guide.md` 判断风险 |
| `call_chain_broken` | 调用链断裂 | 手动追踪该 SQL 的上游调用链，判断调用频率和场景 |
| `param_uncertain` | 参数不确定 | 根据业务场景确认动态参数的实际取值，评估风险 |
| `llm_timeout` | LLM 超时 | 手动对照 `rules.json` + `explain-guide.md` 评估该 SQL 的风险 |
