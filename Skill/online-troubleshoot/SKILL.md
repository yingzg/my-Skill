---
name: online-troubleshoot
description: 当调查线上生产事故、客户工单、数据异常、API 错误、页面故障、缓慢或中断的业务流程，或需要使用代码、日志、SQL、数据库证据、链路数据、历史案例、restricted_info、失败即降级输出、三级（P0/P1/P2）建议以及可选案例回写来分析根因时使用。支持以 traceId 驱动的快速路径进行基于日志的快速诊断。
---

# 线上故障排查（Online Troubleshoot）

## 核心定位

使用本 Skill 按以下运作模式调查线上生产工单：

```text
选系统 -> 查经验库 -> 代码+数据双路验证 -> 按固定契约输出结论 -> 可选回写
```

本 Skill 是一份排查契约，而非通用调试对话。它的职责是防止编造证据、过度自信的根因、跳过验证，以及不稳定的输出。

## 不可妥协原则

1. **零打断优先**：不要逐字段追问。仅允许的阻塞性问题是系统选择与回写确认。
2. **严禁编造**：绝不编造接口路径、表名、SQL 结果、文件路径、行号、历史案例、日志、业务事实、负责人或根因。
3. **失败即降级（Fail-Closed）**：关键证据缺失必须将结果降级为 `partial_success` 或 `failed`。
4. **证据闭环**：根因论断必须能追溯到代码、日志、SQL、数据库结果、用户输入或历史案例证据。
5. **黄金用例（Golden Cases）是测试**：`golden-cases/` 用于验证本 Skill 的行为。它不是生产案例库，绝不能作为 `CASES_DIR` 被检索。

## 资源加载

- 当用户输入包含日志或堆栈信息时，读取 `references/log-patterns.md`。
- 当用户输入包含 traceId 或在步骤 2 中触发链路驱动快速路径时，读取 `references/trace-diagnosis.md`。
- 当行为不明确或需要示例来校准输出时，读取 `references/troubleshoot-examples.md`。
- 当产出简要、详细或回写输出时，读取 `templates/output.md`。
- 仅在验证或修改本 Skill 时读取 `golden-cases/README.md`。

## 允许的阻塞性问题

仅在以下情况下最多提出一个阻塞性问题：

- **系统选择**：多个系统均可能，且选错系统会使代码或数据访问不安全。
- **回写确认**：步骤 7 需要写入或更新一条案例记录。

对于所有其他缺失信息，继续尽力排查，将缺口记录在 `restricted_info` 中，并让缺口影响最终 `status`。

## 文件与目录约定

本 Skill 的所有输出文件统一放在一个根目录下，按类型分子目录：

```text
.troubleshoot/                     # 根目录（默认在项目工作区下，可用 TROUBLESHOOT_HOME 环境变量覆盖）
├── checkpoints/                   # 检查点（断点续跑用，临时）
│   └── <ticket-id-or-hash>.json
└── cases/                         # 生产案例库（永久，供步骤 1 检索、步骤 7 回写）
    └── CASE-xxx.md
```

- 根目录默认值：项目工作区下的 `.troubleshoot/`；通过 `TROUBLESHOOT_HOME` 环境变量可覆盖为绝对路径。
- `golden-cases/` 不在根目录下，它是本 Skill 的测试资产（位于 Skill 目录内），不参与运行时，绝不能作为案例库被检索。

## 七步流水线

除非命中步骤 1 的高置信度跳转路径，否则按顺序执行各步骤。

### 步骤 0：流程初始化

在步骤 1 之前，完成两件事：

1. **选系统**：
   - 默认从用户输入推断 `system/module`，不提问。
   - 仅在「多个系统均可能，且选错会使代码/数据访问不安全」时，才作为阻塞性问题提问。
   - 系统不确定但可安全推断/尝试时，记入 `restricted_info` 并继续。

2. **判断流程类型（fresh vs resume）**：
   - 检查 `.troubleshoot/checkpoints/` 中是否有匹配当前 ticket-id 的检查点。
   - 找到且用户意图是「继续」→ resume 路径（加载检查点，从 `current_step` 继续）。
   - 未找到 → fresh 路径（从步骤 1 开始）。
   - ticket-id 归属不确定 → 作为阻塞性问题询问用户。

步骤 0 之后写入检查点。

### 步骤 1：历史案例预检

检索本地生产案例库，而非 `golden-cases/`。

默认案例路径模式：

```text
.troubleshoot/cases/CASE-xxx.md
```

案例库路径受 `TROUBLESHOOT_HOME` 环境变量覆盖（默认根目录为工作区下的 `.troubleshoot/`）。若案例库不存在，在 `restricted_info` 中记录 `经验库路径未知或未找到` 并继续步骤 2，不要无边界搜索。

执行两轮检索：

1. **精确检索**：系统名、接口路径、错误码、异常类、页面/模块名、业务 ID 类型。
2. **模糊检索**：业务症状、错误文本、模块语义、相似根因。

置信度分级：

| 置信度 | 判定标准 | 行为 |
| --- | --- | --- |
| 高 | 系统与症状匹配，且至少两个关键证据点匹配 | 跳过步骤 2-4，执行步骤 5 最小验证，然后进入步骤 6 |
| 中 | 症状或机制部分匹配，但关键证据点少于两个 | 仅作为假设处理；继续正常流程 |
| 未命中 | 无有用案例 | 继续正常流程 |

仅凭高置信度的历史案例复用不能产出 `success`。步骤 5 的最小验证是强制性的。

步骤 1 的输出：

- 匹配到的案例与置信度；
- 使用的检索查询；
- 跳转路径决策；
- 针对缺失案例库或低置信度的 `restricted_info`。

步骤 1 之后写入检查点。

### 步骤 2：上下文提取

**链路驱动快速路径（Trace-Driven Fast Path）** — 当用户输入包含 traceId 或等效的 Trace 标识时触发。

检测信号：
- 显式的 traceId 字符串（UUID/雪花格式）。
- 关键词：`trace` / `span` / `traceId` / `requestId` 且伴随一个 ID 值。
- 来自 Hera / Jaeger / Zipkin / SkyWalking 的链接。

触发后，加载 `references/trace-diagnosis.md`，并在回落至标准提取逻辑之前执行阶段 A 至 C。

**阶段 A — 获取原始 Trace 与日志数据**

使用 ITraceFetcher 获取 Trace 与日志数据：

```ts
interface ITraceFetcher {
  getTrace(traceId: string, options?: { appName?: string; area?: string; env?: string }): Promise<TraceDetail | TraceError>
  getLogs(traceId: string, options?: { level?: "ERROR"|"WARN"|"INFO"; keyword?: string; timeRange?: string; pageSize?: number; page?: number }): Promise<LogEntry[] | LogError>
}
```

ITraceFetcher 是一个抽象契约。实际的适配器（Hera CLI、Jaeger API、ElasticSearch 等）在外部配置。本 Skill 只依赖该接口。

阶段 A 操作：
1. 调用 `getTrace(traceId)` → TraceDetail。
2. 提取信号：根操作名称、总耗时、根 span 错误标志、子 span 耗时分布、服务/环境/区域、异常类型/消息、线程信息、HTTP 状态码、DB span 标签。
3. 调用 `getLogs(traceId, {level: "ERROR", pageSize: 5})` → 错误日志。
4. 如果阶段 A 产生了异常类型，调用 `getLogs(traceId, {keyword: exceptionType, pageSize: 5})`。

**阶段 A 失败回退**：

| 失败 | 行为 |
|---------|----------|
| permission_denied / not_found | 在 `restricted_info` 中标注 → 放弃快速路径 → 继续下方标准提取 |
| timeout / 504 | 用更小的时间窗口重试（-360,0 → -180,0 → -60,0）；若仍失败 → 标注 `restricted_info` → 以部分数据继续 |
| parse_error | 保留原始响应 → 标注 `restricted_info` → 继续 |
| 日志 is_overflow | 缩小 pageSize（5→1）与 timeRange；此前 ERROR/WARN 级别的日志是完整的；对不完整的 INFO 时间线标注 `restricted_info` |

**阶段 B — Trace 诊断**

1. **时间线重建**：从根 span 开始 → 子 span → 错误/异常日志时间戳构建时间线。
2. **黑洞检测（Blackhole Detection）**：计算 `blackhole_ms = totalDuration - Σ(childSpan.duration)`。若 `blackhole_percent > 50%`，标记为未插桩的处理片段。若 `blackhole_percent > 90%`，则为强信号。
3. **模式匹配**：对照 `references/trace-diagnosis.md` 中的六种诊断模式进行匹配：
   - 模式 1：Broken Pipe / ClientAbortException
   - 模式 2：耗时长但子调用不慢（blackhole > 50%）
   - 模式 3：无明显下游错误却发生回滚
   - 模式 4：高频重复调用（N+1）
   - 模式 5：日志溢出
   - 模式 6：线程阻塞（blackhole > 70% + 线程等待信号 + Broken pipe）
4. 应用模式匹配优先级：模式 5 → 模式 1 → 模式 2 → 模式 6 → 模式 4 → 模式 3。
5. 产出诊断摘要：匹配到的模式、blackhole 百分比、置信度。

**阶段 C — 提取代码检索线索**

从 Trace 数据中提取精确的检索词，供步骤 3 使用：

| Trace 信号 | 步骤 3 检索方法 |
|---|---|
| 根操作名称（如 `/api/trade/order/detail`） | `searchByRoute()` — 高精度 |
| 异常类名（如 `IllegalStateException`） | `searchByKeyword()` — 中精度 |
| 异常消息（如 `item snapshot missing`） | `searchByKeyword()` 或 `searchByError()` |
| 子 span 中的慢方法名 | `searchByKeyword()` |
| DB span 标签中的 SQL 片段 | `searchByKeyword()` |
| 线程阻塞信号 | 对 `synchronized`/`lock`/`CompletableFuture` 使用 `searchByKeyword()` |

将代码检索线索的来源标记为 `"trace"`（区别于 `"user_input"`），以便追踪溯源。

**标准提取** — 在快速路径之后始终执行（或在无 traceId 时直接执行）。

从用户文本、截图、日志与错误描述中提取结构化摘要。不要为每个缺失字段逐一询问。

在存在时提取：

- 系统/模块；
- 接口路径；
- 页面名或模块名；
- 业务 ID 及其类型；
- 时间范围；
- 错误文本或错误码；
- 日志文本；
- 业务实体，如用户、租户、门店、订单、结算、商品、活动；
- 截图衍生的页面线索（如有）。

如果存在日志，加载 `references/log-patterns.md` 并应用模式库。如果没有模式匹配，保留原始文本，并将 `日志格式未识别，可能遗漏信息` 加入 `restricted_info`。

在步骤 2 结束时冻结输出模式（schema）：

```yaml
status
summary
problem
root_cause
evidence
restricted_info
recommendations
```

冻结后，不得新增顶层输出字段。若某个字段会有帮助，将该需求放入 `restricted_info`；若它阻碍置信度，降级为 `partial_success`。

步骤 2 的输出：

- 结构化上下文摘要；
- 提取到的日志字段；
- 排查计划预览；
- 冻结的输出模式；
- `restricted_info`。

步骤 2 之后写入检查点。

### 步骤 3：代码定位

优先使用 code-intelligence MCP 工具进行代码检索（首选实现）；code-intelligence 不可用时降级为增强 grep。

概念接口（5 个方法）：

```ts
interface ICodeSearcher {
  searchByKeyword(query: string): CodeMatch[]
  searchBySemantics(description: string): CodeMatch[]
  searchByRoute(path: string, method?: string): CodeMatch[]
  searchByError(errorCode: string): CodeMatch[]
  searchByExplore(query: string, type?: string, direction?: "upstream" | "downstream" | "both", depth?: number): CodeMatch[]
}
```

#### ICodeSearcher 的 code-intelligence 实现映射

| ICodeSearcher 方法 | code-intelligence MCP 工具 | 调用参数 |
|---|---|---|
| `searchByRoute(path, method?)` | `code.locate_route` | `{ project, route: path, method }` |
| `searchByError(errorCode)` | `code.search` | `{ project, query: errorCode, type: "error" }` |
| `searchByKeyword(query)` | `code.search` | `{ project, query, type: "keyword" 或 "symbol" }` |
| `searchBySemantics(description)` | `code.search` | `{ project, query: description, type: "semantic" }` |
| `searchByExplore(...)` | `code.explore_symbol` | `{ project, query, type, direction, depth, limit }` |

`searchByExplore` 边界：`explore_symbol` 返回的 `main_paths` / `candidate_paths` 是候选路径，不是完整调用链证明。映射成 CodeMatch 时 confidence 降级，并在 `restricted_info` 标注「候选路径，未经 trace 验证」。

对每个结果做标准化：

```ts
type CodeMatch = {
  file: string
  line?: number
  snippet: string
  matchType: "route" | "error" | "keyword" | "semantic" | "sql" | "call_chain"
  confidence: "high" | "medium" | "low"
  source: "gitnexus" | "code_intel" | "semantic" | "grep" | "manual"
  query: string
  raw_ref?: string
  restricted_info?: string[]
}
```

字段映射（code-intelligence 的 `CodeLocation` → `CodeMatch`）：

| CodeLocation | CodeMatch |
|---|---|
| `file` | `file` |
| `start_line` | `line` |
| `snippet` | `snippet` |
| `query.type` | `matchType` |
| `confidence` | `confidence` |
| `source` | `source`（见下表） |

`source` 对齐：

| code-intelligence 的 source | CodeMatch.source |
|---|---|
| GitNexus 归一（`gitnexus`） | `gitnexus` |
| Java 专项索引（route/sql/error） | `code_intel` |
| semantic-lite 语义召回 | `semantic` |
| grep 兜底 | `grep` |
| 人工提供 | `manual` |

#### diagnostics 映射（code-intelligence 诊断码 → restricted_info）

| 诊断码 | 处理 |
|---|---|
| `PROJECT_NOT_REGISTERED` | `restricted_info`（项目未注册）+ 走 grep 兜底 |
| `PROJECT_PATH_NOT_FOUND` | `restricted_info`（项目路径不存在） |
| `INDEX_MISSING` | `restricted_info`（索引缺失）+ 提示先注册/索引 |
| `INDEX_STALE` | `restricted_info`（索引过期）+ confidence 降级 |
| `GREP_FALLBACK_USED` | `restricted_info`（grep 兜底）+ `source=grep` + confidence 降级 |
| `LOW_CONFIDENCE` | confidence=low |
| `GITNEXUS_UNAVAILABLE` | `restricted_info`（调用链降级） |
| `ANCHOR_AMBIGUOUS` | `restricted_info` + 提示缩小查询范围 |

#### 索引状态处理

| `index_status.state` | 处理 |
|---|---|
| `ready` | 正常消费 |
| `missing` | `restricted_info`（项目未索引）+ 降级 grep |
| `stale` | 可用但 confidence 降级 + `restricted_info` |
| `partial` | warning（部分能力降级） |
| `failed` | `restricted_info` + 降级 grep |

本 Skill 不自动触发索引（索引是前置准备，缺失时提示用户 + 降级 grep）。

#### 两层降级链

```text
首选：code-intelligence MCP（工具内部自动降级：结构化索引 → semantic-lite → grep，通过 diagnostics 上报）
工具级降级：code-intelligence 未配置 / 项目未注册 / 索引缺失 → 增强 grep（source=grep + restricted_info）
```

路由规则：

- 接口路径、类名、方法名、注解、SQL 片段或错误码 -> 结构化检索（code-intelligence 的 route/error/symbol/sql 类型）。
- 仅业务症状或页面行为 -> 语义检索（code-intelligence 的 semantic 类型）。
- code-intelligence 不可用、项目未注册/未索引 -> 使用增强 grep。
- 来自 Trace 快速路径（阶段 C）的代码线索带有 `source: "trace"` 且具有最高路由优先级 — 对接口路径使用 `searchByRoute()`，对异常/类/方法名使用 `searchByKeyword()`。

增强 grep 策略：

1. 检索原始关键词。
2. 检索错误码与错误文本。
3. 检索页面/模块名与路由片段。
4. 检索异常类型、枚举名、常量与 i18n 键。
5. 检索候选表与 SQL 片段。
6. 对 Controller、Service、Mapper、DAO、SQL XML、枚举、常量与配置文件给予更高权重。
7. 利用首轮命中结果进行第二轮上下文检索。

（L1 工具返回校验）使用工具结果前，检查：空结果、权限错误、超时、解析错误、数据源不匹配；结果是否为原始输出，而非模型解释。

步骤 3 的输出必须包含：

- 接口候选；
- 代码文件路径与行号（如有）；
- 代码片段；
- 调用链摘要；
- 候选表名；
- `CodeMatch[]`；
- 置信度与 `restricted_info`。

如果仅存在语义命中且无法验证任何代码位置，最终状态不能是 `success`。

步骤 3 之后写入检查点。

### 步骤 4：SQL 准备

仅在理解表与数据源来源之后才准备 SQL。

创建两类 SQL：

- **minimal_verify**：确认所报告现象是否存在的最小查询。
- **root_cause_confirm**：验证因果字段、状态流转、配置值或关系一致性的更深查询。

每条 SQL 必须包含：

- 目的；
- SQL 文本；
- 表名来源；
- 数据源来源；
- 所需的输入条件；
- 预期观察结果；
- 执行风险；
- 是否可在只读模式下安全执行。

如果表名或数据源不确定，先从代码/配置中自行核实。若仍不确定，可以提出 SQL，但绝不能将其视为证据。

步骤 4 之后写入检查点。

### 步骤 5：数据库查询

在统一契约之后使用可用的数据库工具：

```ts
interface IDatabaseQuery {
  query(sql: string, purpose: "minimal_verify" | "root_cause_confirm"): QueryResult
}
```

查询规则：

- 优先只读 SQL。
- 先使用最小验证 SQL。
- 在重试合理的情况下，对瞬时故障最多重试 3 次。
- 将权限、超时、空结果、解析错误与数据源不匹配记录为证据。
- 绝不编造查询结果。

仅凭 SQL 文本不构成证据。数据库证据条目需要真实的查询结果或真实的工具错误。

如果所有数据库访问都失败，最终状态至多为 `partial_success`。

步骤 5 之后写入检查点。

### 步骤 6：根因分析与输出

默认使用 `templates/output.md` 中的简要输出模板。

（L3 业务逻辑校验）在给出根因前，校验代码、SQL、数据、日志与业务含义相互一致（例如状态值能映射到讨论中的业务状态、配置开关作用于被归因的代码路径）。

仅当以下所有条件为真时才输出 `success`：

- 系统/模块已知；
- 问题被清晰复述；
- 代码证据指向具体的文件/方法/行，或等效的稳定代码引用；
- 数据库证据来自真实的查询结果；
- 业务逻辑将数据状态与观察到的症状关联起来；
- 不存在阻塞性的 `restricted_info`。

当存在可能的方向但缺少关键验证时，使用 `partial_success`。

当无法选择系统、无法收集到可用证据、所需工具不可用且无回退，或产出有意义结论需要编造时，使用 `failed`。

**建议生成**

`recommendations` 字段在 v0.2 中是强制性的。在证据支持的情况下，为每个层级至少生成一条建议。建议必须锚定到具体证据 — 绝不要写“建议优化性能”之类的泛泛建议。

三级定义：

| 层级 | 目标 | 负责人 | 时间范围 |
|------|------|-------|-----------|
| P0 | 立即缓解 — 让用户不再看到错误 | 运维/值班，无需代码部署 | 1-2 天 |
| P1 | 性能/逻辑治理 — 让问题可见并防止复发 | 业务开发团队，可改代码 | 1 周 |
| P2 | 架构演进 — 防止此类问题复发 | 架构团队，跨团队协调 | 1 个月以上 |

P0 约束：
- 必须可由运维/值班人员在无代码部署的情况下执行。
- 典型动作：调整超时/配置阈值、切换功能开关、扩容资源、引流。
- 不得要求修改应用代码。

P1 约束：
- 必须锚定到证据中定位到的具体代码文件、方法或数据模式。
- 典型动作：新增 span、加缓存、优化 SQL、并行化串行调用。

P2 约束：
- 可跨团队或需要架构级改动。
- 典型动作：同步转异步、分库分表、框架升级、监控/告警基础设施。

层级省略规则：
- 若证据不足以支撑某个层级，该层级可为空 `[]`。
- 不要写“建议调查 XX” — 调查是本 Skill 的职责，而非建议。
- 在 `partial_success` 或 `failed` 状态下，若 P1/P2 不可靠可省略；仍应提供 P0 以用于分诊。

建议与 `restricted_info` 不得重叠：
- `restricted_info` 描述排查过程中缺失的内容。
- `recommendations` 描述为解决该问题应采取的行动。

在响应之前运行 L4 最终校验。

步骤 6 之后写入检查点。

### 步骤 7：案例回写

仅准备草稿。写入前请求确认。

优先更新已有案例而非创建重复案例。草稿应包含：

- 症状；
- 系统/模块；
- 根因；
- 证据摘要；
- 验证 SQL 或工具引用；
- 处理建议；
- 验证人；
- `restricted_info`；
- 跟进负责人（如已知）。

不得写入 `golden-cases/`。回写仅面向生产案例库（默认 `.troubleshoot/cases/`，受 `TROUBLESHOOT_HOME` 覆盖）。

步骤 7 之后写入检查点。

## 输出契约

v0.2 模式恰好包含七个顶层字段：

```yaml
status: success | partial_success | failed
summary: string
problem: string
root_cause: string
evidence: Evidence[]
restricted_info: string[]
recommendations: Recommendation[]
```

建议（Recommendation）结构：

```yaml
- level: P0 | P1 | P2
  action: string        # 具体的可执行操作
  owner: string         # 建议的执行人/角色
  verification: string  # 验收标准
  estimated_effort: string
```

证据（Evidence）结构：

```yaml
- type: code | db | log | case | user_input | tool_error
  source: string
  observation: string
  supports: string
  confidence: high | medium | low
```

### 状态规则

`success`：

- 代码与数据库证据均存在；
- 若提供了 traceId 且触发了快速路径，则必须包含链路证据；
- 证据与业务逻辑构成闭环；
- 不存在阻塞性的受限信息。

`partial_success`：

- 存在可能的原因，但缺少数据库、代码、日志、权限、业务 ID、时间范围、数据源、配置或案例验证；
- SQL 已准备但未执行；
- 历史案例相关，但最小验证失败或不可用。

`failed`：

- 无法选择或推断出系统；
- 不存在有用证据；
- 工具与回退方案均不可用；
- 任何有用结论都需编造数据。

## 失败即降级与 restricted_info

使用 `restricted_info` 准确说明缺失的内容及其如何限制置信度。

常见条目：

- `缺少业务 ID，无法执行最小验证 SQL`
- `数据库权限不可用，无法验证真实数据状态`
- `经验库路径未知，未完成历史案例预检`
- `仅有语义检索命中（semantic 类型），未定位到可验证代码行`
- `日志格式未识别，可能遗漏信息`
- `表名来源不明确，SQL 只能作为建议`

若某项缺失阻碍了 success，不要将其隐藏在正文中。将其加入 `restricted_info` 并降级状态。

### 链路驱动快速路径失败即降级矩阵

当链路驱动快速路径处于激活状态时，应用此额外的失败即降级矩阵：

| 降级触发条件 | 行为 | 状态影响 |
|---|---|---|
| Trace API permission_denied 或 not_found | 标注 `restricted_info`（“Trace 查询不可用: {reason}”），放弃快速路径，继续标准提取 | 无影响 — 标准提取仍可产出 `success` |
| 重试后 Trace API 超时 | 使用部分数据 + 标注 `restricted_info`（“Trace 查询超时，仅获取部分数据”） | 若无法确认 blackhole，降级至多 `partial_success` |
| 日志 API 溢出 | ERROR/WARN 日志完整，INFO 为采样；标注 `restricted_info`（“INFO 日志溢出，仅采样关键时间点”） | 无影响，除非溢出阻碍模式匹配 |
| 检测到 blackhole 但代码未定位 | 对 blackhole 邻近的方法名使用语义检索（code-intelligence semantic 类型）；若仍未找到 → 标注 `restricted_info`（“黑洞代码段未定位: {phase}”） | 降级为 `partial_success` — 无代码锚点的 blackhole 未经验证 |
| 未匹配任何诊断模式 | 输出基础 Trace 摘要 + 标注 `restricted_info`（“未匹配已知诊断模式”）；不要强行匹配 | 无影响 — 基础诊断仍有用 |

## 严禁编造规则

除非直接来自用户输入、代码、日志、工具输出、数据库结果或案例文件，否则绝不得将以下内容写成事实：

- SQL 查询结果；
- 文件路径或行号；
- 表名或数据源名；
- 历史案例 ID；
- 负责人、验证人或处理人；
- 配置值；
- 根因机制；
- 用户身份、租户、门店、订单或支付事实。

不确定时，将不确定性写入 `restricted_info` 并继续。

## 检查点协议

每个步骤完成后，在运行时允许的情况下写入一个检查点。

默认路径：

```text
.troubleshoot/checkpoints/<ticket-id-or-hash>.json
```

若工作区路径不可写，使用本地临时路径并上报。

检查点结构：

```json
{
  "skill_name": "online-troubleshoot",
  "skill_version": "0.2",
  "ticket_id": "...",
  "current_step": 3,
  "completed_steps": [1, 2],
  "output_schema": ["status", "summary", "problem", "root_cause", "evidence", "restricted_info", "recommendations"],
  "schema_frozen_at_step": 2,
  "trace_fast_path": {
    "triggered": true,
    "trace_id": "9a3f2b1c-d4e5-6f7a-8b9c-0d1e2f3a4b5c",
    "fetcher_source": "hera",
    "phase_a_status": "complete",
    "blackhole_ms": 5950,
    "blackhole_percent": 93,
    "matched_patterns": ["Pattern 1: Broken pipe", "Pattern 2: Blackhole"],
    "code_clues_count": 3
  },
  "tool_call_count": {
    "case_search": 2,
    "trace_query": 1,
    "log_query": 3,
    "code_search": 4,
    "database_query": 1
  },
  "step_outputs": {},
  "restricted_info": [],
  "resume_notes": []
}
```

恢复时：

1. 加载检查点。
2. 从 `current_step` 继续。
3. 若 Skill 版本或模式预期发生变化，默认不重新开始。
4. 将已完成的步骤输出标记为 `schema 已变更，结论可能需要重新校验`。
5. 继续并在最终输出前重新校验。

## 四层校验

### L1：工具返回值校验

使用工具结果前，检查：

- 数据、空结果、权限错误、超时、解析错误或数据源不匹配；
- 结果是否与查询对应；
- 结果是原始输出、标准化输出，还是模型解释。

### L2：步骤契约校验

每个步骤必须产出其必需的输出。缺失的必需输出必须在继续前写入 `restricted_info`。

### L3：业务逻辑校验

校验代码、SQL、数据、日志与业务含义相互一致。

示例：

- 某个状态值能映射到正在讨论的业务状态；
- 某个配置开关会作用于被归因的代码路径；
- 某历史案例匹配的是相同机制，而非仅相似的措辞。

### L4：最终输出校验

在最终输出前，校验：

- `status` 与证据强度相符；
- 仅含 v0.2 顶层字段；
- 每条证据均可追溯；
- 不存在编造的结果、路径、行号、案例 ID、负责人、配置或根因；
- `restricted_info` 列出阻塞项；
- 简要输出对业务可读。

## 快速执行清单

在每个工单期间使用此清单：

1. 选择或推断系统；仅在必要时询问一次。
2. 检索生产案例库两次；对置信度分级。
3. **若存在 traceId，触发链路驱动快速路径（阶段 A→B→C）；加载 `references/trace-diagnosis.md`**。
4. 提取一次上下文；在步骤 2 之后冻结七字段模式。
5. 用结构化、语义或增强 grep 检索定位代码；优先使用链路衍生的线索。
6. 带着表与数据源来源准备 SQL。
7. 数据库可用时查询；绝不编造结果。
8. 在 L4 校验下输出七字段契约；生成锚定到证据的 P0/P1/P2 建议。
9. 仅在得出结论后准备回写草稿；仅在确认后写入。

## 常见失败模式

| 失败模式 | 必需行为 |
| --- | --- |
| 找到相似历史案例 | 除非高置信度，否则仅作为假设；在 `success` 之前仍须执行最小验证 |
| 语义检索返回看似合理的代码但无文件/行号 | 作为低/中置信度使用；不能单独产出 `success` |
| SQL 已准备但数据库不可用 | `partial_success`；SQL 不是证据 |
| 缺少业务 ID 或时间范围 | 继续；记录缺口；SQL 可仅保持为建议 |
| 日志无法识别 | 保留原始文本并添加受限信息 |
| 用户要求详细报告 | 仅在简要结论之后或明确要求时使用详细模板 |
| 快速路径触发但 Trace API 不可用 | 标注 `restricted_info`；回退到标准提取；不得中止 |
| 检测到 blackhole 但步骤 3 未定位代码 | 降级为 `partial_success`；标注 `restricted_info` |
| 快速路径日志查询时日志溢出 | 缩小 pageSize/timeRange；对不完整的 INFO 时间线标注 `restricted_info` |
| recommendations 为空或泛泛 | 必须锚定到具体证据；P0 必须可由运维执行 |

## 最终响应前自检

在以下检查通过之前不得响应：

- 我是否避免了所有未经批准的阻塞性问题？
- 我是否将黄金用例（Golden Cases）与生产案例库区分开？
- 我是否保留并上报了缺失的关键字段？
- 我是否避免了编造的 SQL 结果、文件路径、行号、Trace 数据与根因？
- 当代码或数据库证据缺失时，我是否降级了？
- 当检测到 blackhole 但代码无法定位时，我是否降级了？
- 在步骤 2 之后，我是否将输出模式保持在七个顶层字段？
- 我引用的证据是否足够清晰，便于另一位工程师复核？
- 我是否生成了锚定到具体证据的 P0/P1/P2 建议？
- 我是否确保 P0 建议无需代码部署即可由运维执行？
- 若链路快速路径被触发，我是否对任何降级数据标注了 `restricted_info`？
