# online-troubleshoot v0.3 完善设计

> 版本：v0.3 | 日期：2026-09-04 | 状态：待评审
> 基线：v0.2（`2026-07-14-enhanced-design.zh-CN.md` 已落地）
> 范围：① code-intelligence 适配（ICodeSearcher 落地）② SKILL.md 缺陷修复（问题 1/2/3/4/7）
> 暂缓：Golden Cases 自动化 runner（问题 6）——暂由人工复核，本设计不覆盖

---

## 背景

v0.2 落地后，通过逐行核对发现 7 项问题（详见《附录-online-troubleshoot-问题清单与优化建议.md》）。其中：

- **问题 5（抽象接口适配器未落地）** 需要「新能力设计」——用 code-intelligence 工具落地 ICodeSearcher；
- **问题 1/2/3/4/7** 是「现有设计缺陷修正」——补显式主线、内联校验、统一路径、声明优先级；
- **问题 6（Golden Cases 无 runner）** 暂缓，人工复核。

本设计文档就是这 6 项（问题 5 + 问题 1/2/3/4/7）的完整方案，用于指导 v0.3 实施。

---

# 第一部分：code-intelligence 适配设计（问题 5）

## 1.1 现状与目标

**现状**：SKILL.md 的 Step 3（Code Location）定义了抽象接口 `ICodeSearcher`，但只写「Use available code search tools behind a normalized contract」，未定义「available tools」具体是哪个、怎么调用。

**目标**：用 code-intelligence（MCP 工具）落地 ICodeSearcher，明确「每个方法调哪个 MCP 工具、返回怎么归一化成 CodeMatch」。

**code-intelligence 已注册的 5 个 MCP 工具**（`packages/mcp/src/server.ts`）：

| MCP 工具 | 作用 |
|---------|------|
| `code.search` | 通用检索，`type`：route/error/sql/table/symbol/keyword/semantic/call_chain |
| `code.locate_route` | 按接口路径 + method 定位 Controller |
| `code.trace_call_chain` | 两点之间调用链（GitNexus） |
| `code.explore_symbol` | 单点探索上下游 + main_paths（V0.4） |
| `code.index_project` | 显式索引，默认禁用 |

## 1.2 ICodeSearcher 落地方式

**决策：方案 A——SKILL.md 纯 prompt 映射，不引入脚本。**

理由：`CodeMatch` 与 `CodeLocation` 字段几乎同名，映射是「无损字段重命名」，AI 可稳定执行；保持 online-troubleshoot「纯指令型 SKILL」定位；保留「未来可换别的代码检索工具」的抽象价值。

## 1.3 五个方法定义与 MCP 工具映射

`ICodeSearcher` 从 4 个方法扩展为 5 个（新增 `searchByExplore`）：

| ICodeSearcher 方法 | code-intelligence MCP 工具 | 调用参数 |
|-------------------|---------------------------|---------|
| `searchByRoute(path, method?)` | `code.locate_route` | `{ project, route: path, method }` |
| `searchByError(errorCode)` | `code.search` | `{ project, query: errorCode, type: "error" }` |
| `searchByKeyword(query)` | `code.search` | `{ project, query, type: "keyword" 或 "symbol" }` |
| `searchBySemantics(description)` | `code.search` | `{ project, query: description, type: "semantic" }` |
| `searchByExplore(query, type?, direction?, depth?)` | `code.explore_symbol` | `{ project, query, type, direction, depth, limit }` |

**`searchByExplore` 的边界**（必须写进 SKILL.md）：`explore_symbol` 返回的 `main_paths` / `candidate_paths` 是**候选路径，不是完整调用链证明**。映射成 CodeMatch 时 confidence 降级，并在 `restricted_info` 标注「候选路径，未经 trace 验证」。

## 1.4 CodeMatch ↔ CodeLocation 字段映射

| CodeMatch（online-troubleshoot） | CodeLocation（code-intelligence） | 说明 |
|--------------------------------|----------------------------------|------|
| `file` | `file` | 直接 |
| `line` | `start_line` | 直接 |
| `snippet` | `snippet` | 直接 |
| `matchType` | `query.type` | route/error/sql/table/symbol/keyword/semantic/call_chain 同枚举 |
| `confidence` | `confidence` | high/medium/low 对齐 |
| `source` | `source` | 见下方 source 对齐 |
| `query` | `query` | 直接 |

**`source` 字段对齐**（原 CodeMatch.source = gitnexus/rag/grep/manual）：

| code-intelligence 的 source | 映射到 CodeMatch.source |
|---------------------------|----------------------|
| GitNexus 归一（`source="gitnexus"`） | `gitnexus` |
| Java 专项索引（route/sql/error 等） | `code_intel`（新增枚举值） |
| semantic-lite 语义召回 | `semantic`（新增枚举值，替代原 `rag` 语义） |
| grep 兜底 | `grep` |
| 人工提供 | `manual` |

即：CodeMatch.source 枚举从 `gitnexus/rag/grep/manual` 扩展为 `gitnexus/code_intel/semantic/grep/manual`。

## 1.5 diagnostics → restricted_info 映射

核心原则：**影响证据可信度的诊断 → restricted_info + 降 confidence；需要用户动作的诊断 → 额外提示。**

| code-intelligence 诊断码 | 映射到 online-troubleshoot |
|------------------------|--------------------------|
| `PROJECT_NOT_REGISTERED` | `restricted_info`（项目未注册）+ 走 grep 兜底 |
| `PROJECT_PATH_NOT_FOUND` | `restricted_info`（项目路径不存在） |
| `INDEX_MISSING` | `restricted_info`（索引缺失）+ 提示先注册/索引 |
| `INDEX_STALE` | `restricted_info`（索引过期）+ confidence 降级 |
| `GREP_FALLBACK_USED` | `restricted_info`（grep 兜底）+ `source=grep` + confidence 降级 |
| `LOW_CONFIDENCE` | confidence=low |
| `GITNEXUS_UNAVAILABLE` | `restricted_info`（调用链降级） |
| `ANCHOR_AMBIGUOUS` | `restricted_info` + 提示缩小查询范围 |

其余诊断码（`RELATION_LIMIT_REACHED`、`PATH_TRUNCATED` 等路径/预算类）仅在用到 `searchByExplore` 时，合并进「候选路径」的 restricted_info 说明，不逐条映射。

## 1.6 索引状态处理

**决策：方案 A——SKILL 不自动索引。** 索引是前置准备，缺失时 restricted_info 提示 + 降级 grep。

`index_status.state` 的 5 种状态处理：

| state | SKILL 处理 |
|-------|-----------|
| `ready` | 正常消费 |
| `missing` | `restricted_info`（「项目未索引，先执行注册+索引」）+ 降级 grep |
| `stale` | 可用但 confidence 降级 + `restricted_info`（「索引过期，建议重新索引」） |
| `partial` | warning（部分能力降级，如 GitNexus 不可用） |
| `failed` | `restricted_info` + 降级 grep |

## 1.7 两层降级链

```
Step 3 代码定位：
  1. 首选：调用 code-intelligence MCP（code.search / code.locate_route / code.explore_symbol）
     └─ 工具内部降级（code-intelligence 自己处理，SKILL 不用管）：
        结构化索引 → semantic-lite → grep，通过 diagnostics 上报（GREP_FALLBACK_USED）
  2. 工具级降级（SKILL 处理）：
     code-intelligence MCP 未配置 / 项目未注册 / 索引缺失
     → 走 SKILL 现有的「增强 grep」兜底
     → source=grep + restricted_info 标注「code-intelligence 不可用，走 grep 兜底」
```

---

# 第二部分：SKILL.md 缺陷修复方案

## 2.1 Step 0 流程初始化（合并问题 1 + 问题 2）

在 Seven-Step Pipeline 之前新增 Step 0，同时解决「选系统表述不一致」（问题 1）和「resume 判断缺失」（问题 2）。SKILL.md 中新增以下段落：

```text
### Step 0: Process Initialization

Before Step 1, complete two things:

1. Select system (选系统):
   - Default: infer `system/module` from user input; do not ask.
   - Only ask (blocking question) when: multiple systems are plausible AND choosing
     wrong makes code/data access unsafe.
   - If uncertain but safe to infer/attempt: record in `restricted_info` and continue.

2. Determine process type (fresh vs resume):
   - Check `.troubleshoot/checkpoints/` for a checkpoint matching the current ticket-id.
   - Found + user intent is "continue" → resume path (load checkpoint, continue from current_step).
   - Not found → fresh path (start from Step 1).
   - ticket-id ownership uncertain → ask user (blocking question).
```

## 2.2 L1/L2/L3 校验内联（问题 3）

把文末集中的校验层内联到对应步骤：

| 校验层 | 内联位置 | 内联方式 |
|--------|---------|---------|
| L1 工具返回验证 | Step 3 / Step 5 | 调工具后加：「Before using a tool result, check: empty result, permission error, timeout, parse error, datasource mismatch; whether result is raw output or model interpretation.」 |
| L2 步骤契约验证 | 每个 Step 末尾 | 复用现有「Checkpoint after step N」，把「本步必需输出」写入 checkpoint 的 step_outputs |
| L3 业务逻辑验证 | Step 6 | 根因分析前加：「Verify code / SQL / data / logs / business meaning agree (e.g. status value maps to discussed business status).」 |
| L4 最终输出验证 | Step 6 | 已有（`Run L4 final validation`），保留 |

文末的 `Four-Layer Validation` / `Self-Check Before Final Response` 保留作为「完整定义 + 人读兜底」，但执行触发点已上移到对应步骤。

## 2.3 文件路径统一约定（问题 4）

统一为一个根目录 + 两个子目录，替代当前分散的 `.troubleshoot-checkpoints/` 和 `CASES_DIR`：

```text
TROUBLESHOOT_HOME（环境变量，可选）
  ├─ 默认值：工作区根目录下的 .troubleshoot/
  ├─ checkpoints/   ← 原 .troubleshoot-checkpoints/<ticket-id>.json
  └─ cases/         ← 原 CASES_DIR/CASE-xxx.md
```

SKILL.md 中相关改动：

1. Checkpoint Protocol 的默认路径改为 `.troubleshoot/checkpoints/<ticket-id-or-hash>.json`。
2. Step 1 / Step 7 的案例库路径改为 `.troubleshoot/cases/`（受 `TROUBLESHOOT_HOME` 覆盖）。
3. Step 1 的「CASES_DIR 未知就到处 search」收窄为：「先查 `TROUBLESHOOT_HOME/cases/`（默认 `.troubleshoot/cases/`），找不到就记入 restricted_info（`经验库路径未知或未找到`），不再无边界搜索。」

## 2.4 trace-diagnosis.md 诊断优先级声明（问题 7）

在 `references/trace-diagnosis.md` 开头（数据预处理之前）新增：

```text
## 零、诊断优先级（先于模式匹配）

1. 有明确异常（rootSpan.status === "error" + 异常类型/消息）→ 直接走 Phase C 提取异常线索，
   不强制匹配 Pattern；
2. 异常不明确（无显式报错 / 黑洞 / N+1 / 回滚无报错等）→ 才用 6 个 Pattern 做进阶诊断；
3. Pattern 都不匹配 → 输出基础 trace 摘要 + 标注 restricted_info（未匹配已知诊断模式），
   不强行套用。
```

---

## 实施顺序

```
Phase 1（SKILL.md 缺陷修复，先做，风险低）
  1. 2.1 Step 0 流程初始化（选系统 + fresh/resume 判断）
  2. 2.2 L1/L2/L3 校验内联
  3. 2.3 文件路径统一约定
  4. 2.4 trace-diagnosis.md 诊断优先级

Phase 2（code-intelligence 适配，依赖 code-intelligence 已构建）
  5. 1.3 ICodeSearcher 五个方法定义 + MCP 映射
  6. 1.4 字段映射 + source 枚举扩展
  7. 1.5 diagnostics 映射
  8. 1.6 索引状态处理
  9. 1.7 两层降级链

Phase 3（暂缓）
  - Golden Cases 自动化 runner —— 人工复核
```

Phase 1 可独立先行，不依赖 code-intelligence；Phase 2 需确认 code-intelligence 已构建（`npm run build`）且目标项目已注册+索引。
