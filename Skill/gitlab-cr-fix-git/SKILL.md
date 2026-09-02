---
name: gitlab-cr-fix-git
description: GitLab MR 审查与门禁诊断助手。Use when asked to review GitLab merge requests, publish line-level CR comments, parse MR gate reports, diagnose failed pipelines/tests/coverage/Sonar gates, or demonstrate the same flow from fixture data. This skill does not modify code, tests, commits, branches, approvals, or merges.
---

# GitLab MR 审查与门禁诊断

## 能力概览

| 能力 | 说明 |
|---|---|
| GitLab MR 行级 Code Review | 读取 MR 元数据、changes、discussions 和 diff refs，基于真实 diff 生成具体审查问题，并在用户明确要求时发布行级 Diff Note。 |
| 门禁 / CI / Sonar 诊断 | 解析 GateBot/MiCR-like 评论、pipeline jobs、job trace、Sonar measures，识别阻塞项并给出证据和建议。 |
| 最终报告与交接包 | 每次运行都输出 MR 摘要、审查结果、门禁诊断、失败证据、下一步建议和 handoff package。 |
| Fixture 模式 | 用本地 fixture 文件模拟 GitLab MCP / Sonar API 响应，运行同一套生产链路。 |

本 skill 是 GitLab MR 的“审查与诊断大脑”，不是代码修复器，也不是 Git 写操作自动化器。

详细边界和设计见：

```text
references/capability-boundary-and-detailed-design.md
references/implementation-design.md
references/tool-contracts.md
references/review-guidelines.md
references/gate-patterns.md
```

---

## 运行模式

| 模式 | 触发条件 | 数据来源 |
|---|---|---|
| 真实模式 | 用户给 GitLab MR URL，且未要求 fixture / mock / 演示 | GitLab MCP、可选 Sonar API、只读 Git 上下文 |
| Fixture 模式 | 用户说 fixture、mock、演示，或给出 fixture 目录 | `fixtures/<case>/` 下与生产工具同名的文件 |

Fixture 文件使用这些名称：

```text
gitlab_get_merge_request.json
gitlab_get_merge_request_changes.json
gitlab_list_merge_request_discussions.json
gitlab_list_pipeline_jobs.json
gitlab_get_job_trace.txt
sonar_measures_component.json
sonar_coverage_list.json
```

Fixture 模式用于演示、回归检查，以及没有 GitLab/Sonar 权限时的开发验证。

---

## 依赖边界

| 依赖 | 用途 | 边界 |
|---|---|---|
| `gitlab-mcp` | 读取 MR、changes、discussions、pipeline、jobs、trace、artifact、approval，并发布行级评论 | GitLab API 只能由 MCP 负责，skill 不重写 API client。 |
| `git` | 只读辅助：读取 remote、user.name、user.email、status | 不允许 checkout、commit、push、merge、rebase、stash、reset。 |
| `node` 22+ | 运行 TypeScript 解析脚本 | 使用 `node --experimental-strip-types`。 |
| SonarQube 配置 | 真实模式下读取 Sonar 指标 | 可选；fixture 模式使用 mock JSON。 |

最小可用 GitLab MCP 工具：

```text
gitlab_get_project
gitlab_get_merge_request
gitlab_get_merge_request_changes
gitlab_list_merge_request_discussions
gitlab_create_merge_request_diff_note
gitlab_list_pipeline_jobs
gitlab_get_job
gitlab_get_job_trace
gitlab_download_job_artifact
gitlab_get_merge_request_approvals
```

其中行级评论必须依赖：

```text
gitlab_create_merge_request_diff_note
diff_refs.base_sha
diff_refs.start_sha
diff_refs.head_sha
```

如果 `gitlab_get_merge_request` 不能返回 `diff_refs`，MCP 应提供：

```text
gitlab_get_merge_request_diff_refs
```

---

## 输入处理

### MR URL 解析

支持标准 GitLab MR URL：

```text
https://<host>/<group>/<project>/-/merge_requests/<iid>
```

提取：

```text
host = https://<host>
project_id = <group>/<project>
merge_request_iid = <iid>
```

可使用脚本：

```bash
node --experimental-strip-types scripts/parse_mr_url.ts "https://gitlab.com/group/project/-/merge_requests/12"
```

### 只读 Git 上下文

当用户没有给完整 MR URL，或需要辅助判断当前仓库身份时，只允许执行只读 Git 操作：

```bash
git remote get-url origin
git config user.name
git config user.email
git status --short
```

可用脚本解析 remote URL：

```bash
node --experimental-strip-types scripts/parse_git_remote.ts "git@gitlab.example.com:group/project.git"
```

只读 Git 上下文只能用于辅助推断，不得触发任何仓库状态变更。

### Fixture 选择

如果用户给出 fixture 目录，使用该目录。否则默认演示 fixture：

```text
fixtures/failed-coverage-and-tests
```

---

## 标准流程

### Step 0：确定模式和 MR 身份

1. 判断是真实模式还是 fixture 模式。
2. 如果有 MR URL，解析 `project_id` 和 `merge_request_iid`。
3. 真实模式下，如果项目身份不确定，可用 `gitlab_get_project` 验证访问权限。
4. Fixture 模式下直接读取 fixture 文件，不调用真实 MCP。

### Step 1：读取生产输入

真实模式优先并行读取：

```text
gitlab_get_merge_request(project_id, merge_request_iid)
gitlab_get_merge_request_changes(project_id, merge_request_iid)
gitlab_list_merge_request_discussions(project_id, merge_request_iid)
```

Fixture 模式读取：

```text
gitlab_get_merge_request.json
gitlab_get_merge_request_changes.json
gitlab_list_merge_request_discussions.json
```

### Step 2：汇总 MR 状态

报告这些字段：

| 字段 | 来源 |
|---|---|
| 标题、作者、源/目标分支 | MR detail |
| Pipeline 状态 | `head_pipeline.status` |
| Merge / conflict 状态 | `merge_status` 和 `detailed_merge_status` |
| Diff refs | `diff_refs` |
| 变更文件数 | `changes.length` |
| 现有评论 / discussions | MR discussions |
| GateBot 状态 | parsed discussions |

可用脚本：

```bash
node --experimental-strip-types scripts/summarize_gitlab_mr.ts <gitlab_get_merge_request.json>
node --experimental-strip-types scripts/summarize_gitlab_changes.ts <gitlab_get_merge_request_changes.json>
```

### Step 3：解析门禁报告

解析 MR discussions 中的 GateBot / MiCR-like 门禁评论。默认 Bot 用户名：

```text
MiCR
MockGateBot
GateBot
QualityBot
```

默认支持中英文门禁字段：

```text
有效评论数 / effective comments
变更代码单元测试覆盖率 / 单元测试覆盖率 / coverage
单测用例执行通过率 / test pass rate
Sonar质量门禁 / sonar quality gate
Pipeline
Approve / Approval
```

可用脚本：

```bash
node --experimental-strip-types scripts/parse_gate_discussions.ts <gitlab_list_merge_request_discussions.json>
```

### Step 4：映射 Diff 行号

行级评论必须基于稳定 diff position。先解析 changes 中的 unified diff hunk：

```bash
node --experimental-strip-types scripts/map_diff_lines.ts <gitlab_get_merge_request_changes.json>
```

每条可发布评论必须能映射到：

```text
new_path / old_path
new_line 或 old_line
diff_refs.base_sha
diff_refs.start_sha
diff_refs.head_sha
```

如果 finding 无法映射到 diff 行，默认只进入最终报告，不发布普通 MR note。

### Step 5：执行 MR 审查

优先级：

| 优先级 | 文件类型 |
|---|---|
| 高 | Service、ServiceImpl、DomainService、Controller、API impl、Repository、Mapper XML、SQL |
| 中 | Helper、Util、Strategy、Entity、domain model、config |
| 低 | DTO、Request、Response、Converter、Constant、Enum、tests、docs |
| 忽略 | 图片、生成文件、本地设置、二进制资产 |

审查维度：

| 维度 | 示例 |
|---|---|
| 正确性 | null handling、边界条件、状态流转、事务行为 |
| 回归风险 | 语义变化、不兼容签名、隐藏副作用 |
| 数据 / 安全 | SQL 注入、鉴权缺口、数据泄露 |
| 性能 | N+1 查询、循环 I/O、缺少索引、低效扫描 |
| 可靠性 | 异常处理、幂等、重试、资源清理 |
| 可测试性 | 缺少分支测试、依赖未 mock、断言脆弱 |

必须读取真实 diff 内容后再生成 finding。不得凭文件名编造问题。

### Step 6：发布行级评论或生成草稿

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

发布策略：

| 用户意图 | 行为 |
|---|---|
| 只要求 review / 分析 | 只生成草稿 finding 和最终报告。 |
| 明确要求发布 / post / comment / 发评论 | 使用 `gitlab_create_merge_request_diff_note` 发布行级评论。 |
| 行级定位失败 | 默认不发布，写入最终报告的 skipped findings。 |
| 用户明确允许 fallback | 可降级为普通 MR note，但必须在报告中说明。 |

禁止发布低价值评论凑数量。

---

## 门禁诊断流程

### 阻塞项类型

| 阻塞项 | 诊断来源 | 输出建议 |
|---|---|---|
| 覆盖率不足 | Gate report、Sonar measures、coverage artifact | 指出指标差距、疑似低覆盖文件和补测方向。 |
| 单测通过率失败 | Gate report、pipeline job trace、JUnit artifact | 提取失败测试，判断与变更文件的关联，给出检查方向。 |
| 编译失败 | Job trace、artifact | 提取文件、行号、symbol、错误信息和修复方向。 |
| Sonar 质量门禁失败 | Gate report、Sonar measures/issues | 报告 issue 分类和可能修复方向。 |
| 有效评论数不足 | Gate report、discussions | 如果用户要求 review，则生成高质量行级评论；不要发 filler。 |
| 缺少 approval | Approval API、discussions、Gate report | 标记为需要人工 approve。 |
| Merge conflict | MR merge status | 标记为需要单独 Git 冲突处理流程。 |

### Pipeline / 测试失败诊断

1. 从 MR detail 提取 `head_pipeline.id`。
2. 真实模式调用：

   ```text
   gitlab_list_pipeline_jobs(project_id, pipeline_id)
   ```

   Fixture 模式读取：

   ```text
   gitlab_list_pipeline_jobs.json
   ```

3. 按名称模式选择失败测试 / 构建 job：

   ```text
   sonar-scan+test
   unit-test
   test
   maven-test
   npm-test
   build
   compile
   ```

4. 读取 job trace：

   ```text
   gitlab_get_job_trace(project_id, job_id, tail_lines=200)
   ```

   或 fixture：

   ```text
   gitlab_get_job_trace.txt
   ```

5. 解析失败：

   ```bash
   node --experimental-strip-types scripts/parse_pipeline_jobs.ts <gitlab_list_pipeline_jobs.json>
   node --experimental-strip-types scripts/parse_job_trace.ts <gitlab_get_job_trace.txt>
   ```

6. 可用时优先读取 artifact，例如 JUnit XML、coverage XML、test result JSON。

### Sonar / 覆盖率诊断

Fixture 模式读取：

```text
sonar_measures_component.json
sonar_coverage_list.json
```

解析 measures：

```bash
node --experimental-strip-types scripts/parse_sonar_measures.ts <sonar_measures_component.json>
```

优先使用：

```text
new_line_coverage
new_lines_to_cover
new_uncovered_lines
```

如果只有 generic coverage，必须明确标记为非 PR 新代码覆盖率。

---

## 最终报告

每次运行都必须输出最终报告。推荐结构：

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

---

## Fixture 演示

默认 fixture：

```bash
node --experimental-strip-types scripts/summarize_gitlab_mr.ts fixtures/failed-coverage-and-tests/gitlab_get_merge_request.json
node --experimental-strip-types scripts/summarize_gitlab_changes.ts fixtures/failed-coverage-and-tests/gitlab_get_merge_request_changes.json
node --experimental-strip-types scripts/map_diff_lines.ts fixtures/failed-coverage-and-tests/gitlab_get_merge_request_changes.json
node --experimental-strip-types scripts/parse_gate_discussions.ts fixtures/failed-coverage-and-tests/gitlab_list_merge_request_discussions.json
node --experimental-strip-types scripts/parse_pipeline_jobs.ts fixtures/failed-coverage-and-tests/gitlab_list_pipeline_jobs.json
node --experimental-strip-types scripts/parse_job_trace.ts fixtures/failed-coverage-and-tests/gitlab_get_job_trace.txt
node --experimental-strip-types scripts/parse_sonar_measures.ts fixtures/failed-coverage-and-tests/sonar_measures_component.json
```

真实 Java 编译失败 fixture：

```text
fixtures/foreign-trade-expert-compile-failure
```

常用命令：

```bash
node --experimental-strip-types scripts/map_diff_lines.ts fixtures/foreign-trade-expert-compile-failure/gitlab_get_merge_request_changes.json
node --experimental-strip-types scripts/parse_job_trace.ts fixtures/foreign-trade-expert-compile-failure/gitlab_get_job_trace.txt
node --experimental-strip-types scripts/summarize_gitlab_changes.ts fixtures/foreign-trade-expert-compile-failure/gitlab_get_merge_request_changes.json
```

---

## MUST DO

1. 即使在 fixture 模式，也要遵循真实生产调用链。
2. 使用生产工具响应形态的 fixture，不使用理想化自定义输入。
3. 生成 review finding 前必须读取真实 diff 内容。
4. 发布评论前必须解析 discussions，避免重复。
5. 行级评论优先使用 `gitlab_create_merge_request_diff_note`。
6. 发布评论必须有稳定 diff position 和 `diff_refs`。
7. 每次运行必须输出最终报告。
8. 明确区分证据、推断、缺失数据和需要人工的动作。
9. 缺少真实工具或配置时，必须清楚报告缺失项。
10. 评论必须具体、可执行，并基于文件 / 方法 / 行号。

## MUST NOT DO

1. 不要在本 skill 中重写 GitLab MCP。
2. 不要硬编码小米 host、MiCR-only 用户名、内部项目路径或内部 Maven settings。
3. 不要在缺少证据时声称门禁通过。
4. 不要把评论数不足、缺少 approval、冲突视为可自动修复。
5. 不要发布 filler comments。
6. 不要修改源码。
7. 不要修改测试。
8. 不要 checkout、merge、rebase、stash、reset。
9. 不要 commit。
10. 不要 push。
11. 不要 approve。
12. 不要 merge MR。
13. 不要默认 retry 或 cancel CI jobs。
