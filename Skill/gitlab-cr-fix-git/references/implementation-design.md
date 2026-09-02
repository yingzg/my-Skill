# 实现设计

## 当前上下文摘要

原始 `xiaomi-git` skill 是一份面向小米 GitLab MR 的生产操作规程，不是一个独立应用。它的核心价值来自一条操作链路：

```text
MR URL
  -> gitlab_get_merge_request
  -> gitlab_get_merge_request_changes
  -> gitlab_list_merge_request_discussions
  -> 解析评论 Bot 门禁报告
  -> 审查 diff 或诊断阻塞项
  -> 必要时检查 pipeline jobs / job trace
  -> 必要时检查 Sonar 覆盖率
  -> 发布 CR 评论或输出诊断建议
```

当前通用化 skill 保留这条生产链路，但移除小米内部耦合。它不引入大型理想化数据模型。fixture 模式使用与真实工具响应同名、同结构的本地文件来替代 GitLab MCP 和 Sonar API 响应，使 skill 能在没有 GitLab、MiCR、SonarQube 或公司凭据的情况下演示。

## 最新目标定位

当前 skill 的目标应收敛为：

```text
GitLab MR Review & Gate Diagnosis Skill
```

它专注三类能力：

1. GitLab MR 行级 Code Review。
2. GitLab 门禁 / CI / Sonar 诊断。
3. 最终报告与修复 handoff package。

它不负责修改代码、修改测试、commit、push、approve、merge 或解决冲突。这些写操作和本地 Git 自动化应交给单独的 skill 或人工流程。

## 目标

1. 保留 `xiaomi-git` 中实用的 MR 审查和门禁诊断链路。
2. 替换小米硬编码假设，改为通用 Bot、job、门禁模式和配置。
3. 支持两种运行模式：
   - `真实模式`：调用 GitLab MCP 和可选 Sonar API。
   - `fixture 模式`：读取以生产工具调用命名的本地文件。
4. 使用 TypeScript 编写可复用的轻量解析脚本。
5. 不在 skill 中重写 GitLab MCP。
6. 支持行级 GitLab Diff Note 作为核心评论能力。
7. 生成可供人工或其他修复 skill 使用的最终报告和 handoff package。

## 非目标

1. 不构建 GitLab MCP 替代品。
2. 不实现完整 CI 平台或 SonarQube 替代品。
3. 不创建虚假 approval。
4. 不发布低价值评论凑数量。
5. 不修改源码或测试。
6. 不执行 checkout、merge、rebase、commit、push、force push。
7. 不依赖小米内部 host、token、项目名或 Maven settings。
8. 不管理 GitLab integrations 或 webhooks。

## 为什么不在 Skill 中重写 GitLab MCP

GitLab MCP 应负责所有传输和 API 细节：

```text
认证
GitLab API 路由
project path 编码
MR 元数据
MR changes
MR notes / discussions
行级 Diff Note
pipeline jobs
job traces
job artifacts
approval 状态
分页、限流和错误处理
```

如果把这些写进 skill，任务会从“GitLab MR 审查和诊断流程”膨胀成“GitLab MCP 平台开发”。Skill 只需要定义工具契约、调用顺序、解析逻辑、判断规则和最终报告格式。

如果某个生产 MCP 缺少必要工具，应在 MCP 项目中补工具，而不是把 GitLab API client 混进 skill。

## TypeScript 使用建议

脚本使用 TypeScript 是合理的，原因如下：

1. 现有 `mcp-gitlab` 实现也是 TypeScript。
2. GitLab / Sonar 响应以 JSON 为主，适合 typed helper。
3. 当前用户偏好 TypeScript。
4. Node 22 可以直接运行：

```bash
node --experimental-strip-types scripts/<script>.ts ...
```

这些脚本应保持无外部依赖或少依赖，方便 fixture demo 不需要 `npm install` 就能运行。

## 总体架构

### 生产链路

```text
输入解析
  -> 工具响应加载
     - 真实模式：GitLab MCP / Sonar API
     - fixture 模式：本地文件
  -> 轻量事实解析脚本
  -> Agent 基于真实 diff 和解析事实做审查/诊断
  -> 行级评论草稿或发布
  -> 最终报告与 handoff package
```

### 职责边界

| 层级 | 负责内容 |
|---|---|
| GitLab MCP | 网络请求、GitLab API、认证、分页、限流、行级评论、job trace/artifact、approval |
| Skill scripts | 本地纯解析：URL、diff line、GateBot 文本、job trace、Sonar measures |
| Skill workflow | 调用顺序、审查策略、诊断策略、发布策略、报告格式 |
| Agent reasoning | 基于 diff 和证据判断具体问题、影响和建议 |

## 离线演示数据契约

fixture 文件刻意镜像真实工具名称：

| 真实工具 / API | Fixture 文件 |
|---|---|
| `gitlab_get_merge_request` | `gitlab_get_merge_request.json` |
| `gitlab_get_merge_request_changes` | `gitlab_get_merge_request_changes.json` |
| `gitlab_list_merge_request_discussions` | `gitlab_list_merge_request_discussions.json` |
| `gitlab_list_pipeline_jobs` | `gitlab_list_pipeline_jobs.json` |
| `gitlab_get_job_trace` | `gitlab_get_job_trace.txt` |
| Sonar measures API | `sonar_measures_component.json` |
| Sonar coverage list API | `sonar_coverage_list.json` |

这样可以保证 demo 接近真实生产链路，避免只服务玩具输入格式。

行级评论能力需要 fixture 增强：

1. `gitlab_get_merge_request.json` 应包含 `diff_refs`。
2. `gitlab_get_merge_request_changes.json` 应包含真实 unified diff hunk。
3. 后续可增加 `expected_line_comments.json`，验证行级定位结果。

## 解析脚本

| 脚本 | 输入 | 输出用途 |
|---|---|---|
| `parse_mr_url.ts` | GitLab MR URL | `host`、`project_id`、`merge_request_iid` |
| `summarize_gitlab_mr.ts` | `gitlab_get_merge_request` JSON | MR 状态事实 |
| `summarize_gitlab_changes.ts` | `gitlab_get_merge_request_changes` JSON | 文件数量、风险分组、高优文件 |
| `parse_gate_discussions.ts` | `gitlab_list_merge_request_discussions` JSON | Bot 门禁事实 |
| `parse_pipeline_jobs.ts` | `gitlab_list_pipeline_jobs` JSON | 失败 job / 测试 job 候选 |
| `parse_job_trace.ts` | `gitlab_get_job_trace` 文本 | 编译错误、失败测试、测试统计 |
| `parse_sonar_measures.ts` | Sonar measures JSON | 覆盖率指标和达标判断 |

建议新增：

| 脚本 | 输入 | 输出用途 |
|---|---|---|
| `parse_git_remote.ts` | git remote URL 字符串 | 只读解析 host/project path |
| `map_diff_lines.ts` | GitLab changes JSON | 将 diff hunk 转成可评论行位置 |
| fixture runner | fixture 目录 | 聚合解析结果，生成 demo / 回归报告 |

脚本只提取事实。上下文审查和诊断仍由 Agent 读取真实 diff、源码片段和解析结果后完成。

## 门禁解析策略

原始 `xiaomi-git` 解析 MiCR 评论。通用版解析 GateBot / MiCR-like 评论。

默认 Bot 用户名：

```text
MiCR
MockGateBot
GateBot
QualityBot
```

默认支持字段：

```text
effective comments
coverage / new line coverage
test pass rate
Sonar quality gate
Pipeline status
approval status
```

如果生产 Bot 文本不同，应扩展 `parse_gate_discussions.ts` 或配置项，不应在 `SKILL.md` 中硬编码单一公司格式。

## 代码审查策略

优先级沿用原 `xiaomi-git` 的实用经验：

1. 优先审查 service、domain、controller、repository、SQL。
2. 新增文件重点看整体设计和边界处理。
3. 修改文件重点看语义变化和回归风险。
4. 忽略 generated、binary、本地配置文件。
5. 不发布纯风格或凑数评论。

行级评论是核心能力：

1. 每个可发布 finding 必须能映射到 diff 中的 `new_line` 或 `old_line`。
2. 发布前必须检查已有 discussions，避免重复。
3. 定位失败的 finding 默认只进入报告，不降级发布普通 MR note。

## 门禁诊断策略

默认输出不是修复动作，而是诊断建议：

```text
blocker -> evidence -> likely root cause -> files to inspect -> recommended fix direction -> verification command
```

示例：

```text
阻塞项：单测失败
证据：job #77101，OrderServiceTest.createOrder_shouldRejectWhenStockInsufficient 失败
推断：失败测试与本次修改的 OrderService 直接相关
建议：检查库存不足分支是否遗漏异常抛出
验证命令：mvn test -Dtest=OrderServiceTest
是否需要人工确认：是，业务规则需确认
```

Skill 不修改代码，也不修改测试。

## 最终报告策略

每次运行必须输出最终报告，无论是否发布评论。

报告应包含：

1. MR 基础信息。
2. Review 结果：已发布评论、草稿 finding、跳过 finding。
3. 门禁诊断表：门禁项、状态、证据、建议、是否需要人工。
4. 失败证据：失败 job、编译错误、失败测试、Sonar 指标、相关变更文件。
5. 下一步动作建议。
6. Handoff package：供人工、代码修复 skill 或 Git 自动化 skill 使用。
7. 安全说明：未修改代码、未 commit、未 push、未 approve、未 merge。

## 演示流程

1. 运行 fixture 解析器。
2. 展示 MR 摘要：作者、分支、pipeline、merge 状态、变更文件。
3. 展示从 `MockGateBot` 解析出的阻塞项。
4. 展示从 job trace 解析出的编译错误或失败测试。
5. 展示从 mock Sonar response 解析出的覆盖率。
6. 基于 fixture diff 生成审查 finding。
7. 输出最终报告和 handoff package。

## 生产迁移路径

1. 配置或重写 GitLab MCP。
2. 确保 MCP 支持 `gitlab_create_merge_request_diff_note`。
3. 确保 MR 元数据能返回 `diff_refs`，或提供 `gitlab_get_merge_request_diff_refs`。
4. 真实模式读取 MR detail / changes / discussions。
5. 增加生产 Bot 名称和门禁文本模式。
6. 配置测试 job 名称模式。
7. 配置 Sonar token / project key 查询方式。
8. 增加 large diff、分页、artifact、去重和错误处理硬化。
9. 在真实 GitLab MR 上做行级评论 smoke test。

生产迁移重点是接入 MCP 和硬化诊断流程，不应把本 skill 改成代码修复器或 Git 自动化器。
