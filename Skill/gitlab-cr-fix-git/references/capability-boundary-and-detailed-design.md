# 能力边界与详细设计

## 目的

本文档定义 `gitlab-cr-fix-git` 收敛后的目标设计。

该 skill 是一个 GitLab MR 审查与门禁诊断工作流。它帮助 Agent 读取 GitLab Merge Request，在用户授权时发布高质量行级评论，诊断 CI / 门禁 / Sonar 失败，并输出基于证据的最终报告。

它不应修改仓库代码，不应创建 commit，不应 push 分支，不应 approve MR，不应 merge MR，也不应解决冲突。代码修复和写侧 Git 自动化应由单独的 skill 处理。

## 最终定位

推荐定位：

```text
GitLab MR Review & Gate Diagnosis Skill
```

一句话定义：

```text
审查 GitLab MR 并发布行级评论，从 GitLab、job trace、GateBot / 门禁 Bot 类评论和 Sonar 数据中诊断 CI/门禁失败，最后输出报告和 handoff package，且不修改代码或仓库状态。
```

## 能力分组

### 能力 1：GitLab MR 行级 Code Review

目标：

```text
给定 GitLab MR，读取元数据和 diff，识别具体审查问题，并在用户要求发布时将问题发布为 GitLab 行级 Diff Note。
```

必需子能力：

| 子能力 | 说明 | 归属 |
|---|---|---|
| MR URL 解析 | 从 GitLab MR URL 提取 host、project path、MR iid。 | Skill script |
| 可选只读 Git 上下文 | 从 `git remote origin` 推断项目路径，或用当前 git 用户与 MR 作者弱匹配。 | Skill script / shell 只读 |
| MR 元数据读取 | 读取标题、状态、作者、源分支、目标分支、merge 状态、pipeline、diff refs。 | GitLab MCP |
| MR changes 读取 | 读取变更文件和 unified diff hunk。 | GitLab MCP |
| Diff 行号映射 | 将 diff hunk 映射为可评论的 `new_line` / `old_line`。 | Skill script |
| 已有讨论读取 | 读取 MR discussions，避免重复评论。 | GitLab MCP |
| Finding 生成 | 基于真实 diff 内容识别具体问题。 | Agent reasoning |
| Finding 校验 | 确保每个可发布 finding 都包含文件、行号、证据、影响、建议。 | Skill workflow |
| 行级评论发布 | 发布绑定具体 diff position 的 GitLab Diff Note。 | GitLab MCP |
| Review 报告 | 汇总 finding、已发布评论、跳过项和剩余风险。 | Skill workflow |

行级评论是一等能力。普通 MR note 只能作为 fallback。

Fallback 规则：

```text
如果 finding 无法映射到稳定 diff 行，不要默认降级发布普通 MR note，除非用户明确允许 fallback。应把它放入最终报告的未发布 finding 中。
```

### 能力 2：门禁 / CI / Sonar 诊断

目标：

```text
读取并分类 MR 门禁阻塞项、CI job 失败、单测失败、覆盖率/Sonar 失败、approval 缺口和冲突状态，然后输出有证据支撑的诊断和修复建议。
```

必需子能力：

| 子能力 | 说明 | 归属 |
|---|---|---|
| GateBot / 门禁 Bot 类解析 | 解析 Bot 评论中的有效评论数、覆盖率、单测通过率、Sonar 门禁、pipeline、approval。 | Skill script |
| Pipeline 状态诊断 | 读取 MR head pipeline 状态并分类为 success / failed / running / blocked。 | GitLab MCP + skill parser |
| Job 选择 | 识别失败 job，以及可能的测试 / Sonar / build job。 | Skill script |
| Job trace 诊断 | 从日志中解析编译错误、失败测试、测试总数和通过率。 | Skill script |
| Artifact 诊断 | 在可用时读取 JUnit XML、coverage report 或自定义测试结果 artifact。 | GitLab MCP + future script |
| Sonar measures 解析 | 解析 `new_line_coverage`、`new_lines_to_cover`、`new_uncovered_lines` 等指标。 | Skill script |
| Approval 诊断 | 报告缺失 approval；不自动 approve。 | GitLab MCP / discussions |
| 冲突诊断 | 报告 GitLab merge/conflict 状态；不解决冲突。 | GitLab MCP |
| 建议生成 | 基于证据输出修复方向，并标记是否需要人工确认。 | Skill workflow |

诊断不是修复。输出应解释可能原因和下一步动作，不应编辑代码。

### 能力 3：最终报告与 Handoff Package

目标：

```text
始终输出最终报告，使人工、另一个 LLM 编码会话或未来的 Git 自动化 skill 可以继续处理。
```

无论是否发布评论，每次运行都必须输出最终报告。

报告应包含：

1. MR 摘要。
2. Review finding 和发布状态。
3. 门禁诊断表。
4. 失败证据。
5. 推荐下一步动作。
6. 面向代码修复或 Git 自动化的 handoff package。
7. 安全摘要，说明没有做哪些写操作。

## 明确不做的能力

该 skill 禁止执行这些动作：

| 不做的能力 | 原因 |
|---|---|
| 修改源码 | 代码修复需要业务和仓库安全上下文，应使用单独修复流程。 |
| 修改测试 | 测试改动可能编码错误业务假设，本 skill 保持诊断职责。 |
| 执行大范围本地修复循环 | 这会把 skill 变成代码修复 Agent。 |
| 创建 commit | commit 策略属于 Git 自动化 skill。 |
| push 分支 | push 是有远端副作用的写侧 Git 操作。 |
| force push | 破坏性操作，超出范围。 |
| rebase / merge 分支 | 分支变更和冲突处理属于其他流程。 |
| 解决冲突 | 需要修改本地 Git 状态和业务判断。 |
| approve MR | approval 代表人的责任和权限。 |
| merge MR | 合入策略属于发布或 ship workflow。 |
| 默认 retry/cancel CI job | CI job 变更应由单独显式流程拥有。 |
| 管理 GitLab integrations/webhooks | 与 MR 审查和门禁诊断无关。 |

允许的只读 Git 操作：

| 操作 | 目的 |
|---|---|
| `git remote get-url origin` | 在没有 MR URL project 时推断 GitLab project path。 |
| `git config user.name` | 与 MR 作者做弱匹配。 |
| `git config user.email` | 与 MR 作者邮箱做弱匹配。 |
| `git status --short` | 必要时报告本地上下文；不修改状态。 |

这些只读操作之后，不得在本 skill 内执行 checkout、commit、push、merge、rebase、stash 或 reset。

## 依赖前置检查（硬门禁）

执行任何流程前，必须先检查必需依赖。**任一缺失 → 立即停止并报告，禁止降级、禁止绕过、禁止用替代手段顶替。**

| 场景 | 必需依赖 | 缺失时的行为 |
|---|---|---|
| 真实模式 | GitLab MCP（`gitlab_get_merge_request` 等） | 停止，报告缺 GitLab MCP |
| 真实模式 + 要求发布评论 | `gitlab_create_merge_request_diff_note` + 写权限 token（`glpat-`，scope `api`） | 停止，报告需 glpat- token |
| Fixture 模式 | skill 目录、fixtures、node 22+ | 停止，报告缺项 |

**根因说明**：MR 审查的正确性完全依赖 GitLab MCP 返回的「MR 真实 diff」（含正确 target 分支）。历史教训：曾因缺少 GitLab MCP，用 SSH clone 自行推断，误把 `main`（1 commit 空分支）当成 target，将「18 个文件 +226/-38 的 MR」误判为「441 文件全量导入」，审查对象全错，产出整份无效报告。因此**依赖缺失必须硬停止，绝不允许 SSH clone / curl 等替代手段绕过 MCP**。

## GitLab MCP 边界

GitLab MCP 负责所有网络和 API 行为。Skill 不应重写 GitLab API client。

### 最小可用版本必需 MCP 工具

| 工具 | 用途 |
|---|---|
| `gitlab_get_project` | 必要时验证项目访问权限。 |
| `gitlab_get_merge_request` | 读取 MR 元数据、分支、pipeline、merge 状态和 diff refs。 |
| `gitlab_get_merge_request_changes` | 读取变更文件和 unified diff。 |
| `gitlab_list_merge_request_discussions` | 读取已有评论、Bot 报告和去重证据。 |
| `gitlab_create_merge_request_diff_note` | 发布行级 review 评论。 |

### 必需 MR 字段

`gitlab_get_merge_request` 必须直接暴露这些字段，或配合其他工具暴露：

```json
{
  "iid": 12,
  "title": "MR title",
  "state": "opened",
  "author": {
    "username": "alice",
    "name": "Alice",
    "email": "alice@example.com"
  },
  "source_branch": "feature/x",
  "target_branch": "main",
  "merge_status": "can_be_merged",
  "detailed_merge_status": "ci_must_pass",
  "head_pipeline": {
    "id": 88991,
    "status": "failed",
    "web_url": "https://gitlab.example.com/group/project/-/pipelines/88991"
  },
  "diff_refs": {
    "base_sha": "base",
    "start_sha": "start",
    "head_sha": "head"
  },
  "web_url": "https://gitlab.example.com/group/project/-/merge_requests/12"
}
```

如果 GitLab 需要通过另一个 endpoint 或 MR version API 返回 `diff_refs`，MCP 应为 skill 做归一化，或提供专门工具：

```text
gitlab_get_merge_request_diff_refs
```

### 行级评论工具契约

MCP 应提供：

```text
gitlab_create_merge_request_diff_note
```

期望输入：

```json
{
  "project_id": "group/project",
  "merge_request_iid": 12,
  "body": "**[CR] ...",
  "position": {
    "position_type": "text",
    "base_sha": "base",
    "start_sha": "start",
    "head_sha": "head",
    "old_path": "src/main/java/A.java",
    "new_path": "src/main/java/A.java",
    "old_line": null,
    "new_line": 42
  }
}
```

Position 规则：

| 场景 | 必需 position |
|---|---|
| 新增行 | `new_path`、`new_line`、`old_line: null` |
| 删除行 | `old_path`、`old_line`、`new_line: null` |
| 修改行 | 尽量评论在修改后的新行。 |
| 重命名文件 | 同时包含 `old_path` 和 `new_path`。 |
| 二进制 / 生成文件 | 不发布行级评论。 |

### 门禁诊断所需 MCP 工具

| 工具 | 用途 |
|---|---|
| `gitlab_list_pipeline_jobs` | 定位失败 job，以及可能的测试 / 构建 / Sonar job。 |
| `gitlab_get_job` | 必要时检查 job 元数据。 |
| `gitlab_get_job_trace` | 从日志解析编译 / 测试 / Sonar 失败。 |
| `gitlab_download_job_artifact` | 读取 JUnit XML、coverage XML、自定义测试结果 artifact。 |
| `gitlab_get_merge_request_approvals` | 诊断缺失 approval，而不是只解析评论。 |

Artifact 支持可以作为第二阶段，但没有 artifact 时生产诊断能力会弱一些。

### 可选 MCP 工具

| 工具 | 用途 |
|---|---|
| `gitlab_get_repository_file` | 当 diff 不足时读取文件上下文。 |
| `gitlab_compare_branches` | 比较分支差异或支持增量 review。 |
| `gitlab_get_file_blame` | 支持识别行作者和 @ 提醒。 |
| `gitlab_list_users` | 将 author name / email 映射为 GitLab username。 |
| `gitlab_retry_job` | 未来显式 CI retry workflow 使用，不是默认能力。 |

### 不需要的 MCP 工具

重写 GitLab MCP 时，本 skill 不需要 integrations / webhook 管理：

```text
gitlab_list_integrations
gitlab_get_integration
gitlab_update_slack_integration
gitlab_disable_slack_integration
gitlab_list_webhooks
gitlab_add_webhook
gitlab_update_webhook
gitlab_delete_webhook
gitlab_test_webhook
```

## Skill 脚本边界

Skill 脚本保持小型、轻依赖，只做事实提取，不调用 GitLab API。选型上使用 TypeScript + Node 22 `node --experimental-strip-types` 直接运行，无外部依赖，fixture 演示无需 `npm install`。

完整脚本清单与每个脚本的用途/输入/输出契约见 `scripts-contract.json`（Agent 执行前先读契约而非脚本源码）。要点：

- 可执行脚本 12 个，共享模块 2 个（`config.ts`、`sonar_measures.ts`，非可执行入口）。
- 输入约定：脚本统一支持文件路径入参；`build_gate_report.ts`、`parse_junit_xml.ts`、`parse_coverage_xml.ts`、`parse_sonar_measures.ts` 额外支持 stdin（`-` 参数）；`parse_mr_url.ts` / `parse_git_remote.ts` 直接接收命令行参数字符串。禁止手拼 JSON。

`map_diff_lines.ts` 是稳定行级评论的前置条件。

期望输出结构：

```json
{
  "files": [
    {
      "old_path": "src/A.java",
      "new_path": "src/A.java",
      "commentable_lines": [
        {
          "type": "added",
          "new_line": 42,
          "old_line": null,
          "content": "added line text"
        }
      ],
      "hunks": [
        {
          "old_start": 10,
          "old_count": 5,
          "new_start": 10,
          "new_count": 8
        }
      ]
    }
  ]
}
```

## 工作流设计

### 工作流 1：MR Review 草稿

用于用户要求审查，但未要求发布评论的场景。

流程：

```text
输入 MR URL
  -> 解析 project/iid
  -> 读取 MR 元数据
  -> 读取 changes
  -> 读取 discussions
  -> 映射 diff 行号
  -> 优先分析高风险文件
  -> 生成 review findings
  -> 校验每个 finding 是否能映射到 diff 行
  -> 输出包含草稿 findings 的最终报告
```

不发布评论。

### 工作流 2：发布行级 Review 评论

用于用户明确要求发布 / post / comment 到 MR 的场景。

流程：

```text
输入 MR URL
  -> 解析 project/iid
  -> 读取 MR 元数据和 diff refs
  -> 读取 changes
  -> 读取 discussions
  -> 映射 diff 行号
  -> 生成 findings
  -> 校验 file + line + position
  -> 与已有 discussions 去重
  -> 将每个有效 finding 发布为 Diff Note
  -> 报告已发布、已跳过和发布失败的评论
```

发布规则：

```text
只发布具体、可执行、且能映射到稳定 diff 行的评论。
```

不要发布凑数量的低价值评论。

### 工作流 3：门禁诊断

用于用户询问 MR 为什么被阻塞、CI 为什么失败、覆盖率 / Sonar 为什么失败，或 MR 中存在门禁报告的场景。

流程：

```text
输入 MR URL
  -> 读取 MR 元数据
  -> 读取 discussions
  -> 解析 GateBot / 门禁 Bot 类报告
  -> 如果存在 pipeline，读取 pipeline jobs
  -> 选择失败 / 测试 / Sonar jobs
  -> 可用时读取 trace / artifacts
  -> 解析编译错误、失败测试、通过率、覆盖率、Sonar measures
  -> 分类阻塞项
  -> 输出基于证据的建议
  -> 输出最终报告和 handoff package
```

诊断应区分：

| 分类 | 含义 |
|---|---|
| 证据 | 直接从 MR / API / 日志 / Sonar 解析出的事实。 |
| 推断 | 基于证据得到的推理结论。 |
| 缺失数据 | 必需证据不可用。 |
| 需要人工 | 无法在没有人工判断或权限的情况下安全处理。 |

### 工作流 4：Fixture 模式

用于没有 GitLab / Sonar 权限时做演示、开发和回归检查。

流程：

```text
Fixture 目录
  -> 加载以生产工具响应命名的文件
  -> 运行同一套解析链路
  -> 模拟 review / 门禁诊断
  -> 输出最终报告
```

Fixture 模式应继续使用生产形态文件，而不是简化过的玩具输入。

## 审查问题模型

每个 review finding 应包含：

```json
{
  "severity": "critical|major|minor|suggestion",
  "category": "correctness|security|performance|reliability|compatibility|testability|maintainability",
  "file": "src/main/java/A.java",
  "line": 42,
  "symbol": "ClassName.methodName",
  "issue": "Concrete issue summary",
  "evidence": "What in the diff shows this issue",
  "impact": "Failure mode or regression risk",
  "suggestion": "Actionable fix direction",
  "publishable": true
}
```

发布约束：

| 约束 | 要求 |
|---|---|
| 具体位置 | 必须映射到 diff 文件和行。 |
| 有证据 | 必须基于真实 diff 内容。 |
| 可执行建议 | 必须说明如何修复或调查。 |
| 不重复 | 不得重复已有 discussions。 |
| 不凑数 | 不得仅为增加评论数量而存在。 |

评论格式：

```markdown
**[CR] `<ClassOrFile>.<method>()` - <问题摘要>**

问题：
<具体说明 diff 中的风险。>

影响：
<说明可能导致的 bug、回归、性能、稳定性或安全影响。>

建议：
<给出可执行修改建议。>
```

## 门禁诊断模型

每个门禁项应归一化为：

```json
{
  "name": "coverage",
  "status": "failed",
  "current": 45,
  "required": 60,
  "evidence": "GateBot note #9001 / Sonar measure new_line_coverage",
  "recommendation": "Add targeted tests for files with uncovered new lines.",
  "human_required": true
}
```

阻塞项分类：

| 阻塞项 | 证据来源 | 建议类型 |
|---|---|---|
| 有效评论数不足 | GateBot / 门禁 Bot 类报告、discussions | 如果用户要求 review，则生成高质量行级评论；否则建议找 reviewer。 |
| Pipeline 失败 | MR head pipeline、pipeline jobs | 检查失败 jobs 和 traces。 |
| 编译失败 | Job trace / artifacts | 报告文件、行号、symbol 和修复方向。 |
| 单测失败 | Job trace / JUnit XML | 报告失败测试、错误信息、相关变更文件和验证命令。 |
| 单测通过率失败 | GateBot 报告、job trace、artifacts | 尽可能区分与本 MR 相关的失败和全局 / 存量失败。 |
| 覆盖率失败 | GateBot 报告、Sonar measures / artifacts | 报告指标差距和需要补测试的区域。 |
| Sonar 质量门禁失败 | GateBot 报告、Sonar issues / measures | 报告 issue 分类和可能修复方向。 |
| Approval 缺失 | Approval API / discussions | 需要人工 approve。 |
| Merge conflict | MR merge 状态 | 使用单独 Git 自动化 / 冲突处理 workflow。 |

## 最终报告模板

每次运行都应以这个结构输出报告。

````markdown
## GitLab MR 审查与门禁诊断报告

### 1. MR 摘要
- MR:
- 作者:
- 源分支 -> 目标分支:
- 状态:
- Pipeline:
- Merge 状态:
- 变更文件:

### 2. 审查结果
- 模式: draft | published | skipped
- 已发布评论:
  - comment_id:
  - 文件:
  - 行号:
  - 摘要:
- 草稿问题:
  - 文件:
  - 行号:
  - 严重程度:
  - 问题:
  - 建议:
- 跳过的问题:
  - 原因:

### 3. 门禁诊断
| 门禁项 | 状态 | 证据 | 建议 | 是否需要人工 |
|---|---|---|---|---|

### 4. 失败证据
- 失败 jobs:
- 编译错误:
- 失败测试:
- Sonar 指标:
- 相关变更文件:
- 缺失证据:

### 5. 推荐下一步动作
1. 人工动作:
2. 建议交接给修复流程的内容:
3. 建议验证命令:
4. 建议 Git/GitLab 后续动作:

### 6. 交接包
```json
{
  "mr": "",
  "source_branch": "",
  "target_branch": "",
  "suspected_files": [],
  "failed_tests": [],
  "compile_errors": [],
  "suggested_commands": [],
  "do_not_auto_fix_reason": ""
}
```

### 7. 安全摘要
- 已修改代码: no
- 已修改测试: no
- 已创建 commit: no
- 已执行 push: no
- 已执行 approval: no
- 已执行 merge: no
````

## 安全与授权策略

该 skill 只有两类写行为：

1. 在用户明确要求时发布行级 MR review 评论。
2. 否则不发布评论，只输出草稿报告。

所有仓库状态变更都不在范围内。

| 动作 | 默认策略 |
|---|---|
| 读取 MR 元数据 | 允许 |
| 读取 MR changes | 允许 |
| 读取 discussions | 允许 |
| 读取 pipeline / jobs / trace / artifacts | 允许 |
| 生成草稿 findings | 允许 |
| 发布行级评论 | 仅当用户要求发布 / post / comment 时允许 |
| 修改代码 | 禁止 |
| 修改测试 | 禁止 |
| commit | 禁止 |
| push | 禁止 |
| approve | 禁止 |
| merge | 禁止 |
| retry / cancel jobs | 禁止，除非未来由单独显式 workflow 拥有 |

## 实施阶段

### 阶段 1：文档与边界对齐

交付物：

1. 更新 `SKILL.md` 能力概览。
2. 增加明确的非能力和安全策略。
3. 更新行级评论和 diff refs 的工具契约。
4. 增加最终报告模板 reference。

### 阶段 2：行级评论基础

交付物：

1. 新增 `map_diff_lines.ts`。
2. 更新 fixture，加入 `diff_refs`。
3. 增加预期行级评论 fixture case。
4. 验证当前 fixture diff 的行号映射。

### 阶段 3：GitLab MCP 契约集成

交付物：

1. 确保重写后的 GitLab MCP 暴露 `gitlab_create_merge_request_diff_note`。
2. 确保 MR 元数据暴露 `diff_refs`。
3. 确保 discussions 可用于重复评论检测。
4. 在真实 GitLab MR 上做行级评论 smoke test。

### 阶段 4：门禁诊断硬化

交付物：

1. Bot 名称、job patterns、阈值可配置。
2. 增加 JUnit XML 和 coverage report 的 artifact 契约。
3. 改进门禁诊断报告结构。
4. 增加 fixture 回归命令。

### 阶段 5：报告与交接包打磨

交付物：

1. 标准化最终报告输出。
2. 产出 repair handoff package。
3. 清晰区分证据、推断、缺失数据和需要人工的动作。
4. 说明如何交接给单独的 Git 自动化或代码修复 skill。

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

## 待决问题

1. 行级定位失败时，是否允许降级为普通 MR note。
2. 发布评论是否必须要求用户说出类似“发布行级评论”的一次性明确指令。
3. @ 作者 / blame：**v1 不做，v2 规划**（需接入 `gitlab_get_file_blame` + `gitlab_list_users`）。
4. GitLab MCP 应在 `gitlab_get_merge_request` 中归一化 `diff_refs`，还是暴露单独工具。
5. job artifact：**已支持** JUnit XML 与 JaCoCo coverage XML 解析（`parse_junit_xml.ts` / `parse_coverage_xml.ts`）。
6. 增量 review（`gitlab_compare_branches`）：**v1 不做，v2 规划**。

## 已收敛的设计决策

1. Sonar 真实模式数据**由外部提供**，本 skill 只解析，不内置 Sonar API 调用与 token 管理。
2. 代码规范门禁（bugs / code smells / 漏洞）**本 skill 不解析**，缺失时在报告中显式标注，不得把覆盖率达标偷换成 Sonar 质量门禁通过。
3. 门禁 Bot 为**内部一等能力**：聚合 CI 已产出数据（不本地跑构建），生成门禁报告并**默认自动发布到 MR**（唯一例外：discussions 已存在门禁报告，此时跳过发布只引用）。
4. 覆盖率数据源优先级：Sonar `new_line_coverage`（新增代码）> JaCoCo coverage XML（全量，须标注）。
5. 单测通过率数据源优先级：job trace 全局 `Total` 数字 > JUnit XML（单个类）。
6. **脚本契约文件**：`scripts-contract.json` 描述每个脚本的用途/输入/输出，agent 读契约而非脚本源码。
7. **脚本输入方式**：脚本统一支持文件路径入参；`build_gate_report.ts`、`parse_junit_xml.ts`、`parse_coverage_xml.ts`、`parse_sonar_measures.ts` 额外支持 `-` 参数读 stdin；真实模式下 MCP 内存数据用 write 落盘到固定目录 `/tmp/gitlab-cr-fix-git/`（数据可复用、可调试，用完清理）或对支持 stdin 的脚本用 stdin 直传。
8. **关键环节强制用脚本**：行号映射（`map_diff_lines.ts`）、trace 解析（`parse_job_trace.ts`）、门禁聚合（`build_gate_report.ts`）为 MUST DO，禁止 agent 手工推理替代。
