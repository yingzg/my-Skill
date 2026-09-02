# xiaomi-git Skill 原理与通用化改造分析

## 背景

你当前在学习和开发 Skill，重点关注源码目录：

```text
/mnt/d/测试项目/vibe-hubs
```

其中你正在学习的 Skill 是：

```text
skill/xiaomi-git
```

你主要关心：

1. `xiaomi-git` 的能力二 “MR Code Review 评论” 是怎么工作的。
2. 它如何读取 Pipeline 状态、冲突、变更文件数。
3. 它如何读取门禁信息，例如单测覆盖率、单测通过率、Sonar 质量门禁。
4. 它如何做到门禁修复。
5. 离开小米团队后，如何测试这个 Skill。
6. 后续如何改造成一个离开小米内部系统也能使用的通用 Skill。

我已经检查过本地源码，`/mnt/d/测试项目/vibe-hubs/skill/xiaomi-git` 目录里只有一个 `SKILL.md`，没有额外脚本。也就是说，这个 Skill 是一个“纯指令型 Skill”：它不是通过本地代码直接实现复杂能力，而是指导 AI Agent 按流程调用 GitLab MCP、GitLab API、CI job 日志、SonarQube API、本地 Maven 等工具来完成任务。

---

## 一、xiaomi-git Skill 的本质

`xiaomi-git` 不是一个独立程序，而是一份 Agent 操作规程。

它的能力来自几部分组合：

- Agent 的代码阅读和推理能力。
- `gitlab-mcp` 暴露的 GitLab API 工具。
- GitLab MR 元信息、diff、discussion、pipeline/job 信息。
- 小米内部 MiCR bot 在 MR discussion 中写入的门禁评论。
- CI job trace 中的单测日志。
- SonarQube API 中的覆盖率和质量门禁数据。
- 本地 Maven 测试、代码修改、commit、push。

所以它强的地方在于“流程编排”和“信息源组合”，而不是 `skill/xiaomi-git` 目录下有很多实现代码。

核心链路可以概括为：

```text
用户给 MR 链接
  ↓
解析 project_id 和 merge_request_iid
  ↓
调用 GitLab MCP
  ↓
读取 MR 元信息、diff、discussion、pipeline/job
  ↓
解析 MiCR bot 评论里的门禁状态
  ↓
根据 diff 生成 CR 评论，或根据门禁失败项做修复
```

---

## 二、它如何读取 Pipeline 状态、冲突、变更文件数

这部分主要来自 `gitlab-mcp` 对 GitLab API 的封装。

`xiaomi-git` 在能力二里要求并行调用：

```text
gitlab_get_merge_request(project_id, merge_request_iid)
gitlab_get_merge_request_changes(project_id, merge_request_iid)
gitlab_list_merge_request_discussions(project_id, merge_request_iid)
```

### 1. MR 元信息

`gitlab_get_merge_request` 负责读取 MR 元信息。GitLab MR API 通常会返回类似字段：

```json
{
  "title": "...",
  "author": {
    "username": "alice"
  },
  "source_branch": "feature/demo",
  "target_branch": "main",
  "state": "opened",
  "merge_status": "can_be_merged",
  "detailed_merge_status": "ci_must_pass",
  "head_pipeline": {
    "id": 123456,
    "status": "failed"
  }
}
```

所以：

| 信息 | 主要来源 | 原理 |
|---|---|---|
| Pipeline 状态 | `gitlab_get_merge_request` 返回的 `head_pipeline.status` | MR 当前 HEAD commit 关联的 pipeline |
| 是否冲突 | `merge_status` / `detailed_merge_status` | GitLab 后端计算 MR 是否可合并 |
| 作者、分支、标题 | MR API 字段 | GitLab 原生 MR 元数据 |
| 变更文件数 | `gitlab_get_merge_request_changes` 返回的 `changes.length` | MR diff 文件列表长度 |
| 每个文件 diff | `gitlab_get_merge_request_changes` 的 `changes[].diff` | GitLab compare / MR changes API |

### 2. 变更文件数

变更文件数不是从门禁系统读取的，而是直接统计 MR changes 里的文件列表。

伪代码类似：

```js
const changedFileCount = mrChanges.changes.length
```

### 3. 冲突状态

冲突状态来自 GitLab MR API 的合并状态字段。

常见字段包括：

```text
merge_status
detailed_merge_status
```

GitLab 后端会判断源分支是否能合入目标分支。Skill 只是读取并展示这个结果。

---

## 三、它如何读取单测覆盖率、单测通过率、Sonar 质量门禁

这是最关键的部分。

这些信息不是 GitLab MR API 的原生结构化字段，而是通过“小米内部门禁机器人 MiCR 留在 MR discussion 里的评论文本”解析出来的。

`xiaomi-git` 的说明里写得很明确：

```text
MiCR 门禁状态从 MiCR bot 评论中解析，匹配 author.username == "MiCR" 的 discussion。
```

也就是说，Agent 先调用：

```text
gitlab_list_merge_request_discussions(project_id, merge_request_iid)
```

然后遍历 discussions / notes，找作者是 `MiCR` 的评论，再用关键词解析文本。

它关注的关键词包括：

```text
变更代码单元测试覆盖率
单测用例执行通过率
Sonar质量门禁
有效评论数
```

伪代码大概是：

```js
for (const discussion of discussions) {
  for (const note of discussion.notes) {
    if (note.author?.username === "MiCR") {
      const body = note.body

      parseCoverage(body)
      parseTestPassRate(body)
      parseSonarGate(body)
      parseValidComments(body)
    }
  }
}
```

### 门禁信息的真实来源

这里要区分“直接读取来源”和“原始产生来源”。

| 信息 | Skill 直接读取来源 | 原始产生来源 |
|---|---|---|
| MiCR 门禁展示结果 | MR discussion 里的 MiCR bot 评论 | MiCR 系统计算后写评论 |
| 单测通过率 | MiCR 评论，或 CI job 日志 | `sonar-scan+test` job 的测试结果 |
| 单测覆盖率 | MiCR 评论，或 SonarQube API | SonarQube PR 分析结果 |
| Sonar 质量门禁 | MiCR 评论，或 SonarQube API | SonarQube Quality Gate |
| 有效评论数 | MiCR 评论 | MiCR 自己统计 CR 评论有效性 |

### 两层读取方式

第一层：轻量读取。

从 GitLab MR discussion 里找 MiCR 评论，然后解析其中已经汇总好的门禁信息。这是能力二主要使用的方式。

第二层：深入诊断。

如果要修复失败项，则继续查 pipeline job 日志或 Sonar API。例如单测失败时，Skill 说明里要求：

```text
gitlab_get_merge_request → 提取 head_pipeline.id
gitlab_list_pipeline_jobs(pipeline_id) → 找 sonar-scan+test job
gitlab_get_job_trace(job_id, tail_lines=200) → 看日志尾部汇总
```

我也在本地源码里确认过，`mcp-gitlab` 实际注册了这些 CI 工具：

```text
gitlab_get_job
gitlab_get_job_trace
gitlab_retry_job
gitlab_cancel_job
gitlab_list_pipeline_jobs
```

对应源码位置包括：

```text
/mnt/d/测试项目/vibe-hubs/mcp/mcp-gitlab/src/utils/tool-registry.ts
/mnt/d/测试项目/vibe-hubs/mcp/mcp-gitlab/src/ci-cd.ts
/mnt/d/测试项目/vibe-hubs/mcp/mcp-gitlab/src/utils/tools-data.ts
```

我发现一个文档小问题：`TOOLS.md` 里没有完整展示 `gitlab_get_job_trace`、`gitlab_list_pipeline_jobs`，但源码里有。所以如果测试时 Agent 说工具不存在，要检查实际运行的 MCP server 是否是这份源码版本，而不是旧版本。

---

## 四、单测通过率是怎么来的

`xiaomi-git` 的经验教训里有一段关键说明：

```text
MiCR 的通过率数据来自 sonar-scan+test job 的 test_case_result.json artifact。
```

这说明小米内部 CI 大概有一个 job，名字类似：

```text
sonar-scan+test
```

这个 job 通常会做：

1. 编译项目。
2. 运行单元测试。
3. 生成测试结果统计。
4. 生成或上传 `test_case_result.json` artifact。
5. 执行 Sonar 扫描。
6. MiCR 系统读取这些结果，再回写 MR 评论。

`xiaomi-git` 不一定直接下载 artifact。它在 Skill 文档里采用的是更通用的方式：读取 job trace，也就是 CI 日志。

日志尾部可能有类似：

```text
Total Passed: 16066
Total Failed: 37
Total Test Cases: 16103
```

然后 Agent 可以计算：

```text
单测通过率 = Passed / Total Test Cases
```

如果日志里有失败用例明细，例如：

```text
FAILED: XxxServiceTest.shouldDoSomething
```

Agent 就继续提取失败测试类和方法名，再判断是不是本次 MR 引入的问题。

---

## 五、单测覆盖率和 Sonar 质量门禁是怎么来的

覆盖率主要依赖 SonarQube，而不是 GitLab 本身。

`xiaomi-git` 在门禁修复时会转调 `sonar-coverage-booster` Skill。这个 Skill 明确要求配置 `tokens.json`：

```json
{
  "sonarqube": {
    "url": "https://sonarqube.mioffice.cn",
    "token": "<squ_xxx>",
    "projects": {
      "intl-retail": "mit:new-retail:overseas-offline-sales:intl-retail"
    }
  }
}
```

然后它用 SonarQube REST API 查询：

```bash
/api/measures/component?component=<PROJECT_KEY>&pullRequest=<PR_KEY>&metricKeys=new_line_coverage,new_lines_to_cover,new_uncovered_lines
```

关键指标：

| 指标 | 含义 |
|---|---|
| `new_lines_to_cover` | 本次 PR 新增的可覆盖代码行数 |
| `new_uncovered_lines` | 本次 PR 新增但未被测试覆盖的行数 |
| `new_line_coverage` | 新代码覆盖率 |

覆盖率公式：

```text
new_line_coverage = (1 - new_uncovered_lines / new_lines_to_cover) * 100%
```

Sonar 质量门禁也是类似。能力二主要从 MiCR 评论读取 “Sonar质量门禁” 的结果；能力三如果要修复，才进一步拿 Sonar 详情链接或调用 Sonar API 查 code smell、bug、coverage 等。

真实依赖链如下：

```text
GitLab MR
  ├─ GitLab Pipeline: sonar-scan+test
  │    ├─ 单测结果
  │    ├─ 测试通过率
  │    └─ 触发 Sonar 扫描
  ├─ SonarQube PR 分析
  │    ├─ new_line_coverage
  │    ├─ bugs / vulnerabilities / code smells
  │    └─ quality gate
  └─ MiCR bot
       └─ 把门禁结果写回 MR discussion
```

---

## 六、它如何做到门禁修复

门禁修复不是一个动作，而是按阻塞项分类处理。

`xiaomi-git` 的能力三做的是：

```text
诊断 + 分派 + 局部自动修复
```

流程大致是：

```text
用户给自己的 MR 链接
  ↓
读取 MR 作者，判断是自己的 MR
  ↓
读取 MiCR discussion，解析阻塞项
  ↓
按阻塞类型分派修复策略
```

不同阻塞项的处理方式：

| 阻塞项 | 能否自动修 | 修复原理 |
|---|---|---|
| 单测覆盖率不足 | 可以尝试自动修 | 调用 `sonar-coverage-booster`，查未覆盖行，补 JUnit/Mockito 测试 |
| 单测通过率不足 | 可以尝试自动修 | 查 pipeline job 日志，定位失败测试，本地复现并修测试或源码 |
| 有效评论数不足 | 不能真正自动解决 | 可以补评论，但有效性和合规性取决于 MiCR 规则；更合理是找同事 review |
| 缺少 Approve | 不能自动修 | 需要有权限的人 approve |
| Sonar 质量门禁失败 | 可以部分自动修 | 查 Sonar issues，修 bug/code smell/覆盖率 |
| MR 冲突 | 原则上可以本地解决，但风险较高 | 拉目标分支、merge/rebase、解决冲突、跑测试、push |

### 单测覆盖率修复

核心来自 `sonar-coverage-booster`：

1. 通过 Sonar API 查 `new_uncovered_lines`。
2. 找出未覆盖最多的文件。
3. 读源码和现有测试。
4. 追加测试用例。
5. 本地跑 Maven 测试。
6. commit + push。
7. 轮询 Sonar API，看 `new_line_coverage >= 60%` 是否达标。

这不是“魔法修复覆盖率”，而是 Agent 根据未覆盖行反推测试场景，自动写测试。

### 单测通过率修复

核心流程：

1. 从 MR 的 `head_pipeline.id` 找到 pipeline。
2. 用 `gitlab_list_pipeline_jobs` 找到 `sonar-scan+test` job。
3. 用 `gitlab_get_job_trace` 读取日志。
4. 提取失败测试类和方法。
5. 对比 MR 变更文件，判断是不是本次 MR 引入。
6. 如果是本次引入，就读取失败测试和被测源码，本地复现。
7. 修改测试或源码。
8. 本地跑 `mvn test -Dtest=...`。
9. push 后等 pipeline 重跑。

Skill 里还有一个重要判断：全量测试失败不一定是你的 MR 造成的。

```text
失败测试类在 MR 变更文件中 → 本次 MR 引入，必须修
失败测试类不在 MR 变更文件中 → 可能是存量失败，先报告
```

这个判断不完美，但在实战里有价值。更严谨的做法是对比目标分支 pipeline 的测试结果，不过当前 Skill 文档里没有做到这一步。

---

## 七、这个 Skill 的能力边界

| 能力 | 是否可靠 | 说明 |
|---|---|---|
| 读取 MR 标题、作者、分支、状态 | 高 | GitLab MR API 原生支持 |
| 读取变更文件和 diff | 高 | GitLab MR changes API 原生支持 |
| 发布 MR 评论 | 高 | GitLab notes API 原生支持 |
| 读取 pipeline 状态 | 较高 | MR API 或 pipeline API 支持 |
| 读取 job 日志 | 较高 | 需要 MCP 暴露 `gitlab_get_job_trace` 且 token 有权限 |
| 解析 MiCR 门禁 | 中 | 依赖 MiCR 评论格式稳定 |
| 判断评论是否“有效” | 中低 | MiCR 的有效性规则未必完全公开 |
| 自动修覆盖率 | 中 | 取决于源码可测性、本地依赖、Sonar token、测试框架 |
| 自动修单测失败 | 中 | 简单 mock/断言失败可修，环境/数据/集成依赖问题不一定能修 |
| 自动解决 Approve | 不能 | 需要人 |
| 自动解决权限/组织流程 | 不能 | 需要公司内部系统权限 |

---

## 八、离开小米后如何测试

你现在不在小米团队了，大概率没有这些内部资源：

```text
git.n.xiaomi.com 权限
MiCR bot 评论
sonarqube.mioffice.cn 权限
内部 Maven 仓库 settings.xml
内部项目源码权限
内部 GitLab token
```

所以不能直接完整测试“小米真实门禁修复能力”。

但仍然可以分层测试这个 Skill 的设计能力。

### 第一层：离线 mock 测试

目标：验证 Agent 能不能按 Skill 逻辑解析数据。

可以准备几份假的 JSON：

```text
mock_merge_request.json
mock_merge_request_changes.json
mock_discussions.json
mock_pipeline_jobs.json
mock_job_trace.txt
mock_sonar_measures.json
```

然后让 Agent 根据这些 mock 数据输出：

```text
MR 基础信息
Pipeline 状态
冲突状态
变更文件数
MiCR 门禁状态
当前阻塞项
下一步修复建议
```

这层不需要 GitLab、不需要 Sonar、不需要公司权限，适合学习 Skill 的“信息抽取和决策逻辑”。

可以构造一个 MiCR 风格评论：

```markdown
### MiCR 门禁检查

- 有效评论数：3 / 5
- 变更代码单元测试覆盖率：41.10% / 60%
- 单测用例执行通过率：90.50% / 100%
- Sonar质量门禁：未通过
```

然后测试 Agent 是否能解析出：

```text
有效评论数不足
覆盖率不足
单测通过率不足
Sonar 门禁未通过
```

### 第二层：用 GitLab.com 或自建 GitLab 测 GitLab MCP 基础能力

目标：测试 MR review 能力，不测小米 MiCR。

可以用：

```text
GitLab.com 私有项目
自建 GitLab CE
本地 GitLab Docker
```

创建一个小项目，开一个 MR，然后配置 gitlab-mcp token。测试：

```text
gitlab_get_merge_request
gitlab_get_merge_request_changes
gitlab_create_merge_request_note
gitlab_list_pipeline_jobs
gitlab_get_job_trace
```

这可以验证：

1. MCP 能否连 GitLab。
2. Agent 能否读取 MR diff。
3. Agent 能否生成 CR 评论。
4. Agent 能否发布评论。
5. Agent 能否读取 pipeline/job 日志。

### 第三层：用 SonarQube 模拟覆盖率

目标：测试 `sonar-coverage-booster` 的原理。

可以搭一个小 Java Maven 项目：

```text
src/main/java/Calculator.java
src/test/java/CalculatorTest.java
```

然后用 SonarQube 扫 PR 或分支，模拟低覆盖率。

注意：SonarQube 的 PR 分析功能在不同版本中支持程度不同，Community Edition 对 PR 分析支持有限。替代方案是用 branch 或普通 project metrics 模拟。

如果没有 PR 功能，可以把 Skill 里的 `pullRequest=<PR_KEY>` 改成普通分支或项目维度做实验。

### 第四层：做一个“类 MiCR bot”

目标：完整模拟小米门禁闭环。

可以写一个很小的脚本，在 GitLab MR 下自动发表评论：

```markdown
### Mock MiCR Gate

- 有效评论数：2 / 5
- 变更代码单元测试覆盖率：45.00% / 60%
- 单测用例执行通过率：98.00% / 100%
- Sonar质量门禁：未通过
```

然后让 `xiaomi-git` Skill 面对这个 MR 做解析。

这样不需要小米内部 MiCR，也能测试 Skill 的核心设计。

---

## 九、GitLab 是什么，是否收费，是否需要自建

GitLab 和 GitHub 是同一类东西，都是代码托管和协作平台，都支持：

- Git 仓库托管
- 分支
- Merge Request / Pull Request
- Code Review 评论
- Issue
- Wiki
- CI/CD Pipeline
- Webhook
- API
- Access Token

区别：

| 对比项 | GitHub | GitLab |
|---|---|---|
| MR/PR 名称 | Pull Request | Merge Request |
| CI/CD | GitHub Actions | GitLab CI/CD |
| 自建能力 | GitHub Enterprise Server，偏企业 | GitLab Self-Managed，更常见于公司内网 |
| 开源/自托管传统 | 有，但普通用户少用 | 很多人自建 GitLab CE/EE |
| API/MCP 测试 | 都可以 | 这个 Skill 已经围绕 GitLab API 写了，所以 GitLab 更合适 |

GitLab 常见使用方式：

| 方式 | 说明 | 是否适合当前阶段 |
|---|---|---|
| GitLab.com | 官方托管版，类似 github.com | 最适合先测试 |
| GitLab Self-Managed | 自己用 Docker/服务器部署 GitLab | 适合后续完整本地实验 |
| GitLab Dedicated | GitLab 官方托管的专属实例 | 企业场景，不适合当前学习 |

收费方面，GitLab 有 Free、Premium、Ultimate。根据 GitLab 官方 pricing 页，Free 是 `$0`，适合个人项目和开源贡献；Premium 是付费计划；Ultimate 面向企业高级安全和合规能力。GitLab Self-Managed 也支持 Free、Premium、Ultimate。

官方来源：

- https://about.gitlab.com/pricing/
- https://docs.gitlab.com/install/docker/

### 是否建议现在自建 GitLab

不建议第一阶段自建。

第一阶段建议先用 GitLab.com 免费账号测试。原因是自建 GitLab 比建一个 GitHub 仓库重很多，需要维护：

- GitLab 服务本体。
- PostgreSQL / Redis / Gitaly 等内部组件，Docker 镜像会打包。
- GitLab Runner，用于跑 CI job。
- Token 权限。
- 邮件、域名、端口、SSH 等配置，可选但经常会碰到。
- 机器内存和磁盘，GitLab 比 Gitea/Gogs 重不少。

如果只是为了测试 Skill 的 MR 能力，用 GitLab.com 免费项目足够。

建议流程：

1. 注册 GitLab.com。
2. 创建一个 private project。
3. 本地 clone。
4. 建一个 feature branch。
5. 提交几处代码变更。
6. 创建 Merge Request。
7. 配置 GitLab access token。
8. 让 gitlab-mcp 读取 MR、diff、discussion，并发布评论。

这已经能覆盖 `xiaomi-git` 核心能力的很大一部分：MR 解析、diff review、评论发布。

自建 GitLab 适合第二阶段做完整实验，例如模拟“小米内网 GitLab + 自定义 bot + 自定义门禁”的效果。那时再用 Docker 跑 GitLab Self-Managed，并配置 GitLab Runner。

---

## 十、为什么不能直接复刻小米 MiCR

MiCR 是小米内部平台，它至少隐藏了几类规则：

```text
有效评论如何判定
覆盖率阈值如何配置
哪些 job 产生 test_case_result.json
Sonar 和 MiCR 的同步时机
Approve 规则
谁有权限 approve
哪些评论算重复/无效
```

离开公司后无法验证这些规则。

直接复刻会变成“看起来像能用，实际不可测”。更好的做法是：

```text
不要实现 MiCR。
实现一个能解析任意 bot gate report 的 adapter。
```

也就是把 MiCR 当成一种“评论型门禁报告”，只保留可观察的输入输出。

---

## 十一、建议改造成通用 Skill

建议不要直接把 `xiaomi-git` 改成通用版，而是保留旧 Skill 作为案例，再新建一个通用 Skill，例如：

```text
gitlab-mr-assistant
```

或者：

```text
portable-gitlab-review
```

目标能力：

| 能力 | 通用版本怎么做 |
|---|---|
| MR Code Review | 读取任意 GitLab MR diff，生成并发布 review comments |
| 门禁读取 | 支持多种 gate provider，而不是写死 MiCR |
| Pipeline 诊断 | 读取 GitLab pipeline jobs 和 job trace |
| 单测失败解析 | 从 job 日志中解析失败测试 |
| Sonar 覆盖率 | 可选集成 SonarQube，不强依赖小米 Sonar |
| Mock 测试 | 支持本地 fixture，不依赖真实 GitLab |
| 可迁移配置 | 用配置文件定义 host、bot 名、job 名、覆盖率阈值、评论阈值 |

建议目录结构：

```text
portable-gitlab-review/
├── SKILL.md
├── references/
│   ├── gitlab-workflow.md
│   ├── gate-adapters.md
│   ├── review-guidelines.md
│   ├── sonar-integration.md
│   └── test-fixtures.md
├── scripts/
│   ├── parse_mr_url.py
│   ├── parse_gate_report.py
│   ├── parse_job_trace.py
│   └── summarize_mr_changes.py
└── fixtures/
    ├── merge_request.json
    ├── merge_request_changes.json
    ├── discussions_micr_like.json
    ├── pipeline_jobs.json
    └── job_trace_failed_tests.txt
```

主 `SKILL.md` 不要写得像现在这么大。它只负责：

```text
1. 判断用户意图
2. 解析 MR 链接
3. 选择数据源：真实 GitLab / 本地 fixture
4. 选择 gate adapter：none / comment / sonar / pipeline / mock
5. 执行 review 或 gate diagnosis
6. 输出报告或发布评论
```

详细规则放到 `references/`。确定性解析逻辑放到 `scripts/`。

---

## 十二、最重要的抽象：Gate Adapter

`xiaomi-git` 最大的问题是把 MiCR 写死了。

通用版应该把“门禁系统”做成可插拔。

建议设计 5 种 gate adapter：

| Adapter | 用途 | 依赖 |
|---|---|---|
| `none` | 只做 MR review，不看门禁 | GitLab MR API |
| `comment-bot` | 从 MR discussion 的 bot 评论解析门禁 | GitLab discussions |
| `gitlab-pipeline` | 从 pipeline/job 状态判断门禁 | GitLab pipeline API |
| `sonarqube` | 从 SonarQube API 读取覆盖率/质量门禁 | Sonar token |
| `mock` | 从本地 fixture 读取门禁，用于离线测试 | 本地 JSON/文本 |

小米的 MiCR 就是 `comment-bot` adapter 的一种配置，而不是通用 Skill 的核心。

示例配置：

```json
{
  "gitlab": {
    "host": "https://gitlab.com",
    "default_project": null
  },
  "review": {
    "min_effective_comments": 5,
    "max_comments_per_run": 5
  },
  "gate": {
    "provider": "comment-bot",
    "bot_usernames": ["MiCR", "MockGateBot"],
    "patterns": {
      "effective_comments": "有效评论数[:：]\\s*(\\d+)\\s*/\\s*(\\d+)",
      "coverage": "单元测试覆盖率[:：]\\s*([0-9.]+)%\\s*/\\s*([0-9.]+)%",
      "test_pass_rate": "单测用例执行通过率[:：]\\s*([0-9.]+)%\\s*/\\s*([0-9.]+)%",
      "sonar_gate": "Sonar质量门禁[:：]\\s*(通过|未通过)"
    }
  },
  "pipeline": {
    "test_job_name_patterns": ["test", "unit-test", "sonar-scan+test"],
    "failed_test_patterns": ["FAILED:", "Failures:", "Tests run:"]
  },
  "sonarqube": {
    "enabled": false,
    "url": null,
    "project_key": null
  }
}
```

这样离开小米之后，可以把 `bot_usernames` 改成 `MockGateBot`，把正则换成自己的格式，整个 Skill 仍然能跑。

---

## 十三、通用 Skill 的核心工作流

建议保留两个主模式。

### 模式一：review

```text
输入 MR URL
  ↓
读取 MR metadata + changes + discussions
  ↓
分类变更文件
  ↓
阅读关键 diff
  ↓
生成 CR 评论
  ↓
根据用户要求决定是否发布
```

### 模式二：gate-diagnose

```text
输入 MR URL 或 fixture
  ↓
读取 MR metadata
  ↓
选择 gate adapter
  ↓
解析门禁状态
  ↓
如 pipeline failed，读取 job trace
  ↓
输出阻塞项和修复建议
```

后面再加第三个模式：`gate-fix`。

但第一版不建议直接做全自动 `gate-fix`。建议先做成半自动诊断：

```text
- 覆盖率不足：输出应补测试的文件和未覆盖行
- 单测失败：输出失败测试和可能原因
- Sonar failed：输出 issues 和建议
- 评论不足：输出建议找 reviewer，不默认自评刷评论
```

等诊断稳定后，再增加自动修复。

---

## 十四、推荐测试顺序

你希望测试重点是“把整个 Skill 改造成可迁移、可测试版本”。建议按这个顺序。

### 阶段 1：离线 mock 测试

目标：不用 GitLab，不用 Sonar，不用 token，也能验证 Skill 决策逻辑。

准备 fixture：

```text
MR 元信息 JSON
MR changes JSON
discussion JSON
pipeline jobs JSON
job trace 文本
Sonar measures JSON
```

测试问题：

```text
请使用 portable-gitlab-review 分析 fixtures/mr_failed_gate，输出门禁阻塞项和建议修复动作。
```

预期输出：

```text
- Pipeline failed
- 覆盖率 41.1%，低于 60%
- 单测通过率 90.5%，低于 100%
- 有效评论数 3/5，不足
- Sonar quality gate failed
- 变更文件 8 个
- 高风险文件 3 个
```

这一步验证的是 Skill 的“脑子”。

### 阶段 2：GitLab.com 免费项目测试 MR review

目标：验证真实 GitLab API/MCP 链路。

创建一个 GitLab.com 项目，然后开 MR。测试：

```text
- 解析 MR URL
- 获取 MR metadata
- 获取 changes
- 获取 discussions
- 发布普通 MR note
```

这一步验证的是 Skill 的“手”。

### 阶段 3：GitLab CI job 日志测试

目标：验证 pipeline/job trace 解析。

在项目里加 `.gitlab-ci.yml`：

```yaml
stages:
  - test

unit-test:
  stage: test
  image: python:3.12
  script:
    - python -m unittest discover -s tests
```

故意写一个失败测试，让 pipeline failed。然后测试：

```text
- 获取 head pipeline
- list pipeline jobs
- 找到 unit-test job
- 读取 job trace
- 提取失败测试
```

这一步验证的是 Skill 的“诊断能力”。

### 阶段 4：Mock Gate Bot

目标：模拟 MiCR，不依赖小米。

可以手动或用脚本在 MR 下发一条评论：

```markdown
### Mock Gate Report

- 有效评论数：2 / 5
- 单元测试覆盖率：45.00% / 60%
- 单测用例执行通过率：98.00% / 100%
- Sonar质量门禁：未通过
```

然后让 Skill 用 `comment-bot` adapter 解析它。

这一步验证的是“MiCR 能力可迁移”。

### 阶段 5：SonarQube 可选集成

目标：只在确实需要覆盖率修复时再做。

SonarQube 本地或云端都可以，但这一步成本比前面高。尤其 PR analysis 在不同版本里支持程度不同，所以不要放在第一优先级。

通用 Skill 应该把 Sonar 设计成 optional，而不是 hard dependency。

---

## 十五、推荐的改造路线

建议分 4 个交付物：

### 1. `portable-gitlab-review` Skill 骨架

包含：

```text
SKILL.md
触发说明
模式选择
依赖说明
```

### 2. `references/` 设计

把下面这些内容拆出去：

```text
GitLab workflow
gate adapter
review 规则
Sonar 可选集成
fixture 测试说明
```

### 3. `scripts/` 解析器

先做三个确定性脚本：

```text
parse_mr_url.py
parse_gate_report.py
parse_job_trace.py
```

### 4. `fixtures/` 测试样例

构造一组不依赖小米的 mock MR 数据，用来验证 Skill 是否能解析门禁、输出阻塞项。

第一版完成后，可以离线测试：

```text
请使用 portable-gitlab-review 分析 fixtures/mock-mr-failed-gate
```

再接 GitLab.com 测真实 MR：

```text
请使用 portable-gitlab-review review 这个 GitLab MR: https://gitlab.com/xxx/yyy/-/merge_requests/1
```

---

## 十六、当前建议

先不要自建 GitLab。

下一步最合理的是基于现有 `xiaomi-git`，设计一个通用版 Skill 的文件结构和第一版 `SKILL.md` 草案，重点支持：

```text
- fixture 离线测试
- GitLab.com MR review
- comment-bot gate adapter
- pipeline job trace 解析
```

暂时不做：

```text
- 自动 push 修复
- 自动补覆盖率
- SonarQube 强依赖
- 自建 GitLab
- Approve 自动化
```

这样可以先把 Skill 原理和通用化设计真正掌握住，再逐步接入真实 GitLab 和 CI。

