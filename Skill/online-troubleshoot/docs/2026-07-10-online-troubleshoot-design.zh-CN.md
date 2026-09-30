# 线上工单排查 Skill 设计文档

## 背景

构建一个跨工具通用的 AI Skill，用于线上生产工单排查。这个 Skill 的目标不是让 Agent 自由发挥，而是用稳定的排查流程和证据契约约束 Agent，避免在信息不足、工具不可用或证据不完整时编造数据、过度推断或输出确定性根因。

目标实现目录：

```text
/mnt/g/my-Skill/Skill/online-troubleshoot
```

本设计刻意保持主 Skill 平台无关。Codex、Claude Code、OpenCode、RAG、gitnexus、数据库 MCP、飞书等运行时工具，都被视为可选适配器；Skill 只约束它们最终必须产出统一的证据结构。

## 目标

Skill 实现以下工作模式：

```text
选系统 -> 查经验库 -> 代码+数据双路验证 -> 按固定契约输出结论 -> 可选回写
```

这个 Skill 不是通用调试助手，而是一个面向线上工单根因排查的流程约束和证据契约。

## 不可妥协的约束

1. 零中断：不要逐项追问用户。唯一允许阻塞式提问的场景是系统选择和结案回写确认。
2. 禁止编造：不要虚构接口路径、表名、SQL 结果、历史案例、日志、根因或业务事实。
3. Fail-Closed：关键证据缺失时，必须将结果降级为 `partial_success` 或 `failed`。
4. 证据闭环：每个根因判断都必须能回指到代码、SQL、数据库查询结果、日志或历史案例证据。
5. Golden Cases 是质量标准：Skill 修改后，只有当 Golden Cases 仍然通过，或因预期行为变化而被明确更新时，修改才可接受。

## 范围

### 范围内

- 一个主工作流文件 `SKILL.md`，不设硬性行数上限；以完整、清晰、可执行为优先。
- 七步排查流水线，包含高置信经验库复用跳跃路径。
- v0.1 简化输出 schema，包含 6 个核心字段。
- Checkpoint 与恢复协议。
- `restricted_info` 信息缺口报告。
- 四层验证体系。
- 本地文件模式的经验库复用。
- 代码搜索与数据库查询证据的归一化契约。
- 3 个 Golden 回归案例。
- 日志模式参考文件与输出模板。

### 范围外

- `contract_version` 冻结机制。
- SOP 快速路径自动化。
- 经验库 Git 共享同步。
- RAG、gitnexus 或数据库 MCP 的完整 SDK。
- 冻结真实外部工具命令或 API。
- 复杂的自我执行工具预算机制。

## 目录结构

```text
/mnt/g/my-Skill/Skill/online-troubleshoot/
├── SKILL.md
├── references/
│   ├── log-patterns.md
│   └── troubleshoot-examples.md
├── golden-cases/
│   ├── GC-001-full-success.md
│   ├── GC-002-case-reuse.md
│   ├── GC-003-partial-success.md
│   └── README.md
└── templates/
    └── output.md
```

## 文件职责

### `SKILL.md`

作为 Skill 的“宪法”。优先包含核心原则、触发条件、七步流水线、跳跃路径、输出契约、Fail-Closed 规则、No Invention 规则、Checkpoint 协议、四层验证和自检清单。`SKILL.md` 不设硬性行数上限；当内容属于详细示例、日志模式、输出模板或工具适配细节时，应拆到 `references/` 或 `templates/`，避免主文件承担案例库和模板库职责。

### `references/log-patterns.md`

包含日志格式模式库：

- Exception stack trace：提取异常类型、触发类和行号。
- MyBatis SQL log：提取 SQL、参数和耗时。
- Nginx access log：提取接口路径、状态码和耗时。
- 自定义业务日志：提取时间戳、级别和内容。

如果没有模式命中，Agent 必须保留原始文本，并将 `日志格式未识别，可能遗漏信息` 写入 `restricted_info`。

### `references/troubleshoot-examples.md`

包含 2-3 个完整示例，演示：

- 代码证据与数据证据完整闭环。
- 高置信历史案例复用。
- 关键配置或数据访问缺失时输出 `partial_success`。

### `templates/output.md`

包含三类模板：

- 简版结论：默认输出，业务语言表达，不超过 300 个中文字符。
- 详版报告：仅在用户要求“详细”时输出。
- 回写草稿：第 7 步生成，只有用户确认后才能写入经验库。

每个输出字段都标注其来源章节，例如 `来源：SKILL.md §Output Contract`。

### `golden-cases/`

包含可执行的回归场景。这些文件不是普通样例，也不是线上经验案例库，而是对未来 Agent 行为的压力测试。

Golden Cases 与经验案例库必须严格区分：

- Golden Cases 是测试资产，用于验证 Agent 是否遵守 Skill 的流程、契约和护栏。
- 经验案例库是排查资产，用于真实工单中复用历史根因、SQL、处理方式和业务经验。
- Golden Cases 不参与第 1 步历史案例检索，不能被当作 `CASES_DIR/CASE-xxx.md` 的检索结果。
- 每个 Golden Case 必须包含输入场景、预期行为和失败判据。

## 工作流

### 第 1 步：历史案例预检

从 `CASES_DIR/CASE-xxx.md` 本地经验库执行两轮检索：

1. 精确匹配：系统名、接口路径、错误码、异常类、页面/模块名、业务 ID 类型。
2. 模糊匹配：业务现象、错误描述、模块语义、相似根因。

置信度分级：

- 高置信：系统和现象一致，且至少两个关键证据点一致。跳到第 5 步做最小验证，再进入第 6 步。
- 中置信：只能作为假设，必须继续正常流程。
- 未命中：继续第 2 步。

高置信经验复用仍然必须执行最小验证。历史相似本身不能直接输出 `success`。

### 第 2 步：上下文提取

从用户文本、截图文字、日志和错误描述中一次性提取结构化上下文摘要。不要按字段逐项追问用户。

如存在，则提取：

- 接口路径。
- 页面或模块名。
- 业务 ID。
- 时间范围。
- 错误文字或错误码。
- 日志文本。
- 用户、租户、门店、订单、结算、商品、活动等业务实体。

在第 2 步结束时冻结 v0.1 输出 schema：

```yaml
status
summary
problem
root_cause
evidence
restricted_info
```

冻结后，不要新增顶层字段。如果后续发现缺少必要字段，保持 schema 不变，将缺口写入 `restricted_info`；如果该缺口影响结论可信度，则降级为 `partial_success`。

### 第 3 步：代码定位

使用归一化代码搜索能力契约，而不是绑定具体工具 API。

概念接口：

```ts
interface ICodeSearcher {
  searchByKeyword(query: string): CodeMatch[]
  searchBySemantics(description: string): CodeMatch[]
  searchByRoute(path: string): CodeMatch[]
  searchByError(errorCode: string): CodeMatch[]
}
```

归一化结果：

```ts
type CodeMatch = {
  file: string
  line?: number
  snippet: string
  matchType: "route" | "error" | "keyword" | "semantic" | "sql" | "call_chain"
  confidence: "high" | "medium" | "low"
  source: "gitnexus" | "rag" | "grep" | "manual"
  query: string
  raw_ref?: string
  restricted_info?: string[]
}
```

路由规则：

- 用户提供接口路径、类名、方法名或错误码：优先使用 gitnexus 等结构搜索。
- 用户只有业务现象描述：优先使用 RAG 等语义搜索。
- RAG 和 gitnexus 不可用，或结果低置信：降级到增强 grep。

增强 grep 需要扩展关键词：

- 原始关键词。
- 错误码和错误文案。
- 页面或模块名。
- 接口路径片段。
- 候选表名。
- 对 Controller、Service、Mapper、DAO、SQL、枚举、常量、配置文件加权排序。
- 基于第一轮命中结果做上下文二次搜索。

第 3 步输出必须包含接口候选、代码路径与行号（如可获得）、调用链摘要、候选表名、置信度和 `restricted_info`。

### 第 4 步：SQL 整理

准备两类 SQL：

- 最小验证 SQL：能够确认用户报告现象是否存在的最小查询。
- 根因确认 SQL：用于验证因果字段、状态流转、配置值或关联一致性的深入查询。

每条 SQL 必须说明：

- 表名来源。
- 数据源来源。
- 必要输入条件。
- 预期观察结果。
- 执行风险。

如果表名或数据源不确定，必须先从代码或配置中自验。仍不确定时，SQL 只能作为建议，不能作为证据。

### 第 5 步：数据库查询

使用概念数据库查询契约：

```ts
interface IDatabaseQuery {
  query(sql: string, purpose: "minimal_verify" | "root_cause_confirm"): QueryResult
}
```

当重试有意义时，数据库查询失败最多重试 3 次。如果所有数据库访问均失败，将失败原因写入 `restricted_info`，最终最多输出 `partial_success`。

禁止编造查询结果。SQL 语句本身不是证据，只有实际查询结果才是证据。

### 第 6 步：根因分析与输出

默认使用简版结论模板。结论必须使用业务语言，不超过 300 个中文字符。

只有当代码证据、数据证据和业务逻辑形成闭环时，才能输出 `success`。否则使用 `partial_success` 或 `failed`。

响应前必须执行 L4 最终输出验证。

### 第 7 步：案例回写

只生成回写草稿。未经用户确认，不要写入经验库。

回写时优先更新已有案例，而不是创建重复案例。需要采集验证人、证据摘要、最终结论、受限信息和后续负责人（如已知）。

## 输出契约

v0.1 输出 schema 固定为 6 个核心字段：

```yaml
status: success | partial_success | failed
summary: string
problem: string
root_cause: string
evidence: Evidence[]
restricted_info: string[]
```

### `success`

仅在满足以下条件时使用：

- 受影响系统或模块已知。
- 问题被清晰复述。
- 代码证据指向具体文件或方法。
- 数据证据来自实际查询结果。
- 业务逻辑能够解释为什么出现该现象。
- 不存在阻断性的 `restricted_info`。

### `partial_success`

在以下情况使用：

- 已识别高可信方向，但一个或多个关键验证路径缺失。
- 已定位代码，但数据库访问失败。
- 历史案例相关，但无法做最小验证。
- SQL 已准备，但未执行。
- 业务 ID、时间范围、权限、数据源或配置缺失。

### `failed`

在以下情况使用：

- 无法选择或推断系统。
- 无法收集任何可用证据。
- 必要工具不可用，且无可行降级路径。
- 输入过于稀疏，若继续输出有意义假设就必须编造信息。

## 证据模型

证据条目应简洁但可追溯：

```yaml
- type: code | db | log | case | user_input | tool_error
  source: string
  observation: string
  supports: string
  confidence: high | medium | low
```

证据不能包含编造的观察结果。工具错误和权限缺失也可以作为 `partial_success` 或 `failed` 的有效证据。

## Checkpoint 协议

每完成一步，在运行环境允许时写入 checkpoint 状态。Checkpoint 应位于当前排查工作上下文中，而不是 Skill 源码目录内。例如：

```text
.troubleshoot-checkpoints/<ticket-id-or-hash>.json
```

如果该路径不可写，使用本地临时路径，并在输出中说明位置。

Checkpoint 结构：

```json
{
  "skill_name": "online-troubleshoot",
  "skill_version": "0.1",
  "ticket_id": "...",
  "current_step": 3,
  "completed_steps": [1, 2],
  "output_schema": ["status", "summary", "problem", "root_cause", "evidence", "restricted_info"],
  "schema_frozen_at_step": 2,
  "tool_call_count": {
    "case_search": 2,
    "code_search": 4,
    "database_query": 1
  },
  "step_outputs": {},
  "restricted_info": [],
  "resume_notes": []
}
```

恢复时，从 `current_step` 继续。如果 Skill 版本变化导致旧步骤输出与当前 schema 不兼容，不默认从头开始。对已完成步骤标注 `schema 已变更，结论可能需要重新校验`，然后继续排查。

## 四层验证体系

### L1：工具返回验证

使用工具结果前先验证：

- 工具返回的是数据、空结果、权限错误、超时还是解析错误？
- 返回结果是否对应本次查询？
- 返回结果是原始输出、转换输出，还是模型解释？

### L2：步骤契约验证

验证当前步骤的必需字段。缺少必需字段的步骤只有在缺口被写入 `restricted_info` 后，才能继续推进。

### L3：业务逻辑验证

验证代码、SQL、数据、日志和业务含义是否一致。例如：

- 表状态值必须能映射到正在讨论的业务状态。
- 被归因的配置开关必须影响对应代码路径。
- 历史案例必须匹配相同现象和机制，而不仅是文字相似。

### L4：最终输出验证

最终输出前检查：

- `status` 必须与证据强度一致。
- `restricted_info` 必须列出所有阻塞项和限制。
- 不允许出现 v0.1 之外的顶层 schema 字段。
- 不允许编造查询结果、文件路径、行号、案例 ID 或根因。
- 简版输出必须是业务可读语言。

## Golden Cases

Golden Cases 的作用是回归测试 Skill 本身，而不是沉淀生产经验。测试方式是：让未来 Agent 只读取当前 Skill 和某个 Golden Case 的输入场景，执行排查后，将输出与该 Golden Case 的预期行为和失败判据对照。

每个 Golden Case 至少包含：

- 输入场景：模拟用户工单、日志、缺失信息、工具不可用、历史案例相似但不完全一致等压力。
- 预期行为：Agent 应走的关键步骤、最终 `status`、必需 `evidence` 和 `restricted_info`。
- 失败判据：明确哪些行为算失败，例如编造数据、跳过最小验证、缺少 DB 证据却输出 `success`、逐项追问用户。

### GC-001：完整成功排查

验证完整路径。输入包含接口路径、订单 ID、时间范围和错误日志。预期状态为 `success`。必需证据包括代码证据和数据库证据。

失败示例：

- 没有 DB 证据却输出 `success`。
- 编造 SQL 结果。
- 缺少代码路径或方法证据。
- Agent 逐项追问用户。

### GC-002：经验库复用

验证高置信历史案例复用。预期行为是第 1 步高置信命中，跳过第 2-4 步，执行第 5 步最小验证，然后进入第 6 步输出结论。

失败示例：

- 仅凭历史案例直接输出 `success`。
- 跳过最小验证。
- 将中置信案例当作高置信处理。

### GC-003：部分成功

验证配置、权限、业务 ID 或数据库访问缺失时的 Fail-Closed 行为。预期状态为 `partial_success`。

失败示例：

- DB 访问缺失仍输出 `success`。
- `restricted_info` 漏掉缺失字段或失败工具。
- Agent 编造缺失 ID、表名、SQL 结果或配置值。

## 实施顺序

按以下顺序实施：

1. 编写 `golden-cases/GC-001-full-success.md`。
2. 基于 GC-001 的压力要求编写 `SKILL.md`。
3. 编写 `templates/output.md`。
4. 编写 `references/log-patterns.md`。
5. 编写 `references/troubleshoot-examples.md`。
6. 编写 `golden-cases/GC-002-case-reuse.md`、`GC-003-partial-success.md` 和 `golden-cases/README.md`。
7. 验证 Skill 结构，并用 Golden Cases 对照 Skill 指令。

## 自检标准

实施完成前必须确认：

- `SKILL.md` 表达完整、清晰、可执行；详细案例、日志模式、输出模板和工具适配细节已合理拆分到支持文件。
- 每条规则都对应一个可观察失败模式。
- 输出 schema 恰好包含 6 个 v0.1 字段。
- 唯一允许的阻塞式提问是系统选择和回写确认。
- RAG 和 gitnexus 是可选适配器，不是硬依赖。
- 工具输出必须先归一化，才能作为证据使用。
- 关键数据缺失时输出 `partial_success` 或 `failed`。
- 历史案例复用不能绕过最小验证。
- Checkpoint 状态包含 `tool_call_count`。
- 所有 Golden Cases 都包含输入、预期输出和失败判据。
