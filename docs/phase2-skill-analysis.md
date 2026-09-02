# 📚 Phase 2 Skill 深度分析：设计思路与学习要点

> 本文档深入分析 **mr-workflow**、**xiaomi-git**、**writer-reviewer** 三个核心 Skill 的设计思路
>
> 📅 更新时间: 2026-05-23

---

## 🎯 学习目标

通过分析这三个 Skill，掌握：

1. **流程控制 Skill** 的设计模式 (mr-workflow)
2. **API 集成 Skill** 的设计模式 (xiaomi-git)
3. **多 Agent 协作 Skill** 的设计模式 (writer-reviewer)

---

## 1. mr-workflow：强制流程控制 Skill

### 📋 概述

| 维度 | 说明 |
|------|------|
| **核心目标** | 强制执行 MR 工作流，禁止直接合并到目标分支 |
| **设计模式** | 流程控制 + 模板填充 + 异步处理 |
| **复杂度** | ⭐⭐⭐ (中) |
| **学习时长** | ~2h |

### 🧠 设计思路解析

#### 1.1 核心设计理念

```
┌─────────────────────────────────────────────────────────────┐
│                    mr-workflow 设计理念                       │
├─────────────────────────────────────────────────────────────┤
│  1. 约束优先：明确 MUST NOT DO，禁止危险操作                  │
│  2. 流程固定：6 个阶段严格按顺序执行，不可跳步                 │
│  3. 减少交互：智能判断何时需要确认，何时可自动执行              │
│  4. 异步处理：AutoRec 块是异步注入的，需要轮询等待             │
└─────────────────────────────────────────────────────────────┘
```

#### 1.2 架构分层

```
┌─────────────────────────────────────────────────────────────┐
│                    6 阶段流程架构                              │
├─────────────────────────────────────────────────────────────┤
│  阶段一：信息收集 (并行)                                      │
│    ├── git branch --show-current                            │
│    ├── git status                                           │
│    ├── git remote -v                                        │
│    ├── git fetch origin <target>                            │
│    ├── git log origin/<target>..HEAD                        │
│    └── git diff origin/<target>...HEAD                      │
│                           ↓                                 │
│  阶段二：变更分析                                             │
│    ├── 模块归属分析                                          │
│    ├── 业务目的提取                                          │
│    └── MR 标题确定                                           │
│                           ↓                                 │
│  阶段三：确认与创建                                           │
│    ├── 判断是否需要确认                                      │
│    └── gitlab_create_merge_request                          │
│                           ↓                                 │
│  阶段四：AutoRec 关联需求 (强制)                              │
│    ├── 获取最新 description                                  │
│    ├── 解析 <AutoRec> 块                                     │
│    ├── 匹配变更与需求                                        │
│    └── 更新 checkbox 状态                                    │
│                           ↓                                 │
│  阶段五：解决讨论并触发合并                                   │
│    ├── 检查 merge_status                                     │
│    ├── 解决阻塞讨论                                          │
│    └── gitlab_accept_merge_request                          │
│                           ↓                                 │
│  阶段六：输出结果                                             │
└─────────────────────────────────────────────────────────────┘
```

### 📝 关键学习点

#### 学习点 1：并行信息收集

**设计思路**：将不依赖顺序的 git 命令并行执行，提高效率

```bash
# 这些命令可以并行执行
git branch --show-current      # 获取当前分支
git status                     # 检查工作区状态
git remote -v                  # 获取远端信息
git fetch origin <target>      # 拉取目标分支
git log origin/<target>..HEAD  # 获取 commit 列表
git diff origin/<target>...HEAD # 获取变更统计
```

**复刻要点**：
- 识别哪些操作是独立的
- 使用 Agent 工具并行执行
- 合并结果后再进入下一阶段

#### 学习点 2：模块归属分析规则

**设计思路**：通过文件路径自动判断业务领域，用于 AutoRec 需求匹配

```yaml
# 按模块目录判断
intl-retail-fieldforce → 人力领域 (考勤、打卡、入转调离)
intl-retail-front → 阵地领域 (门店、阵地、陈列)
intl-retail-sales → 销售领域 (销量、库存、收货)
intl-retail-cooperation → 协同领域 (账号、权限、组织)

# 按包路径细分 (重要!)
attendance → 考勤
bpm → 审批 (需结合使用方判断)
store/front/position → 阵地
sales/inventory → 销售
```

**复刻要点**：
- 设计路径匹配规则表
- 处理公共模块的归属判断
- 处理跨模块变更的情况

#### 学习点 3：异步轮询处理

**设计思路**：AutoRec 块是 GitLab 异步注入的，需要等待

```python
# 伪代码
for retry in range(3):
    description = gitlab_get_merge_request()
    if '<AutoRec>' in description:
        # 解析并处理
        break
    else:
        wait(2-3)  # 等待异步注入
```

**复刻要点**：
- 识别异步操作
- 设计重试机制
- 设置最大重试次数

#### 学习点 4：确认策略优化

**设计思路**：减少不必要的用户交互

```yaml
# 确认策略矩阵
场景:
  - 源分支已推送 + 目标分支明确 → 跳过确认，直接创建
  - 源分支未推送 → 确认是否 push
  - 目标分支不明确 → 反问用户
  - 工作区有未提交变更 → 提醒用户先处理
```

**复刻要点**：
- 设计决策矩阵
- 识别可自动化的场景
- 保留必要的用户确认点

#### 学习点 5：MR 描述模板

**设计思路**：标准化 MR 描述格式，自动填充内容

```markdown
## 变更概述
一句话描述本次 MR 的业务目的。

## 变更内容
### 1. 变更点一标题
- 具体改动描述

## 影响模块
- **模块名** / 包路径 — 一句话说明影响范围

## 提交历史
| Commit | 说明 |
|--------|------|
| sha | commit message |
```

**复刻要点**：
- 设计模板结构
- 定义自动填充规则
- 保留手动补充空间

### 🎓 复刻练习

```markdown
# 练习 1: 设计一个简单的 MR 工作流 Skill
1. 定义触发词
2. 设计 3-4 个阶段的流程
3. 编写 MR 描述模板
4. 实现确认策略

# 练习 2: 实现模块归属分析
1. 定义路径匹配规则
2. 实现匹配算法
3. 处理边界情况
```

---

## 2. xiaomi-git：API 集成 Skill

### 📋 概述

| 维度 | 说明 |
|------|------|
| **核心目标** | 小米 GitLab 工作助手，支持 MR CR 和门禁修复 |
| **设计模式** | 多能力集成 + 条件分支 + 并行处理 |
| **复杂度** | ⭐⭐⭐⭐ (高) |
| **学习时长** | ~3h |

### 🧠 设计思路解析

#### 2.1 核心设计理念

```
┌─────────────────────────────────────────────────────────────┐
│                   xiaomi-git 设计理念                        │
├─────────────────────────────────────────────────────────────┤
│  1. 多能力集成：一个 Skill 包含 3 个独立能力                   │
│  2. 条件分支：根据 MR 作者自动切换流程                        │
│  3. 并行处理：MR 详情、变更、讨论并行获取                      │
│  4. 大数据处理：Diff >25K token 时分段读取                    │
│  5. 外部依赖：依赖 gitlab-mcp 工具                           │
└─────────────────────────────────────────────────────────────┘
```

#### 2.2 三能力架构

```
┌─────────────────────────────────────────────────────────────┐
│                    三能力架构                                 │
├─────────────────────────────────────────────────────────────┤
│  能力一：GitLab 项目自动检测                                  │
│    ├── git remote get-url origin                            │
│    ├── 解析 SSH/HTTPS URL                                    │
│    └── gitlab_get_project 验证                               │
│                           ↓                                 │
│  能力二：MR Code Review 评论                                 │
│    ├── Step 0: 判断是否自己的 MR                             │
│    ├── Step 1: 并行获取 MR 详情/变更/讨论                    │
│    ├── Step 2: 分析 MR 状态 & MiCR 门禁                     │
│    ├── Step 3: 深度分析代码变更                              │
│    ├── Step 4: 生成并发布 CR 评论                            │
│    └── Step 5: 输出汇总                                     │
│                           ↓                                 │
│  能力三：自己的 MR 门禁修复                                   │
│    ├── Step 1: 获取 MR 信息 & 门禁状态                       │
│    ├── Step 2: 解析 MiCR 门禁，列出阻塞项                    │
│    ├── Step 3: 按优先级逐一修复                              │
│    └── Step 4: 输出修复报告                                  │
└─────────────────────────────────────────────────────────────┘
```

#### 2.3 条件分支设计

```
┌─────────────────────────────────────────────────────────────┐
│                    条件分支决策树                              │
├─────────────────────────────────────────────────────────────┤
│  获取 MR 详情后                                              │
│    │                                                        │
│    ├─ MR 作者 == 当前用户                                    │
│    │    └─ 且用户未明确说"review"                            │
│    │         └─ 切换到能力三 (门禁修复)                      │
│    │                                                        │
│    └─ MR 作者 != 当前用户                                    │
│         └─ 或用户明确说"review"                              │
│              └─ 继续能力二 (CR 评论)                         │
└─────────────────────────────────────────────────────────────┘
```

### 📝 关键学习点

#### 学习点 1：项目路径自动检测

**设计思路**：从 git remote 自动解析项目路径，减少用户输入

```python
# 伪代码
def detect_project():
    url = git("remote get-url origin")
    
    # SSH 格式: git@git.n.xiaomi.com:mit/new-retail/.../intl-retail.git
    if url.startswith("git@"):
        project = url.split(":")[1].replace(".git", "")
    
    # HTTPS 格式: https://git.n.xiaomi.com/mit/new-retail/.../intl-retail.git
    elif url.startswith("https://"):
        project = url.split("git.n.xiaomi.com/")[1].replace(".git", "")
    
    # 验证项目存在
    gitlab_get_project(project)
    return project
```

**复刻要点**：
- 支持多种 URL 格式
- 实现回退策略
- 验证项目存在性

#### 学习点 2：并行获取 MR 数据

**设计思路**：MR 详情、变更、讨论三路并行获取

```python
# 伪代码
# 并行执行
mr_details = gitlab_get_merge_request(project, iid)  # 并行 1
mr_changes = gitlab_get_merge_request_changes(project, iid)  # 并行 2
mr_discussions = gitlab_list_merge_request_discussions(project, iid)  # 并行 3

# 合并结果
analyze(mr_details, mr_changes, mr_discussions)
```

**复刻要点**：
- 识别可并行的 API 调用
- 使用 Agent 工具并行执行
- 合并结果进行分析

#### 学习点 3：大 Diff 分段读取

**设计思路**：Diff 数据超过 25K token 时，分段读取避免超限

```python
# 伪代码
def read_large_diff(diff_data):
    if len(diff_data) > 25000:  # token 超限
        # 启动 2 个并行 Agent
        agent1 = spawn_agent(read, offset=1, limit=400)
        agent2 = spawn_agent(read, offset=400, limit=500)
        
        # 合并结果
        results = [agent1.result, agent2.result]
        return merge(results)
    else:
        return read(diff_data)
```

**复刻要点**：
- 检测数据大小
- 设计分段策略
- 合并分段结果

#### 学习点 4：代码问题识别维度

**设计思路**：多维度识别代码问题，生成有针对性的 CR 评论

```yaml
问题维度:
  正确性:
    - 空指针
    - 边界条件
    - 异常处理
  
  性能:
    - SQL N+1
    - 索引缺失
    - 循环内 IO
  
  安全性:
    - SQL 注入
    - 敏感信息泄露
  
  设计:
    - 接口兼容性
    - 方法签名变更
  
  可维护性:
    - 重复代码
    - 魔法数字
  
  回归风险:
    - 修改已有逻辑
    - 参数语义变更
  
  资源管理:
    - 连接泄露
    - 线程安全
    - 上下文清理
```

**复刻要点**：
- 定义问题维度
- 设计检测规则
- 生成评论模板

#### 学习点 5：MiCR 门禁解析

**设计思路**：从 MiCR bot 评论中提取门禁状态

```python
# 伪代码
def parse_micr_status(discussions):
    for discussion in discussions:
        if discussion.author == "MiCR":
            # 解析评论内容
            comments = discussion.comments
            for comment in comments:
                # 提取关键指标
                if "变更代码单元测试覆盖率" in comment:
                    coverage = extract_percentage(comment)
                if "单测用例执行通过率" in comment:
                    pass_rate = extract_percentage(comment)
                if "Sonar质量门禁" in comment:
                    sonar_status = extract_status(comment)
    
    return {
        "coverage": coverage,
        "pass_rate": pass_rate,
        "sonar_status": sonar_status
    }
```

**复刻要点**：
- 识别特定 bot 评论
- 解析结构化数据
- 提取关键指标

#### 学习点 6：门禁修复优先级

**设计思路**：按优先级修复，后续修复可能触发 Pipeline 重跑

```yaml
修复优先级:
  1. 单测通过率 → 先修失败测试
  2. 单测覆盖率 → 调用 sonar-coverage-booster 补写测试
  3. 有效评论数 → 最后处理，不影响代码
  4. Approve/冲突 → 需人工处理
```

**复刻要点**：
- 设计优先级矩阵
- 理解依赖关系
- 处理人工干预场景

### 🎓 复刻练习

```markdown
# 练习 1: 实现项目路径检测
1. 解析 SSH URL 格式
2. 解析 HTTPS URL 格式
3. 实现回退策略

# 练习 2: 实现并行数据获取
1. 识别可并行的 API 调用
2. 使用 Agent 工具并行执行
3. 合并结果

# 练习 3: 实现代码问题检测
1. 定义 3-5 个问题维度
2. 设计检测规则
3. 生成评论模板
```

---

## 3. writer-reviewer：多 Agent 协作 Skill

### 📋 概述

| 维度 | 说明 |
|------|------|
| **核心目标** | Writer-Reviewer 双角色循环，确保代码质量 |
| **设计模式** | 双循环 + 子 Agent 协作 + 模板驱动 |
| **复杂度** | ⭐⭐⭐⭐⭐ (极高) |
| **学习时长** | ~2h |

### 🧠 设计思路解析

#### 3.1 核心设计理念

```
┌─────────────────────────────────────────────────────────────┐
│                 writer-reviewer 设计理念                     │
├─────────────────────────────────────────────────────────────┤
│  1. 双循环机制：内循环(自审) + 外循环(提审)                  │
│  2. 角色分离：Writer 和 Reviewer 完全独立                    │
│  3. 信息隔离：Reviewer 只接收业务诉求，自行发现改动           │
│  4. 模板驱动：验收标准、Reviewer prompt、报告都有模板         │
│  5. 退出机制：内循环无新问题退出，外循环最多 3 轮             │
└─────────────────────────────────────────────────────────────┘
```

#### 3.2 双循环架构

```
┌─────────────────────────────────────────────────────────────┐
│                    双循环架构                                 │
├─────────────────────────────────────────────────────────────┤
│  Phase 0: 提炼任务摘要                                       │
│    ├── 目标：一句话描述                                      │
│    ├── 验收标准：2-5 条可检验条件                            │
│    └── 约束：技术栈/兼容性/性能                              │
│                           ↓                                 │
│  Phase 1: Writer 编码                                        │
│                           ↓                                 │
│  Phase 2: Writer 自审循环 (内循环)                           │
│    ├── 检查清单：需求符合/正确性/一致性/遗漏/可读性          │
│    ├── git diff 审查所有改动                                 │
│    ├── 如发现问题 → 修复 → 重新自审                          │
│    └── 如无新问题 → 自审通过 → 进入 Phase 3                  │
│                           ↓                                 │
│  Phase 3: Reviewer 独立审查 (外循环)                         │
│    ├── spawn 独立子 Agent                                    │
│    ├── 传递业务诉求 (不传改动文件列表)                       │
│    ├── Reviewer 自行 git diff 发现改动                       │
│    ├── 输出：阻塞问题 / 建议 / 架构级问题                    │
│    ├── 如有阻塞问题 → Writer 修复 → 重新 Phase 2            │
│    └── 如无阻塞问题 → 进入 Phase 4                          │
│                           ↓                                 │
│  Phase 4: 决策、汇总报告 & 用户验收                          │
│    ├── 呈现残留问题和架构级问题                              │
│    ├── 按模板输出汇总报告                                    │
│    └── 用户 review 最终代码                                  │
└─────────────────────────────────────────────────────────────┘
```

#### 3.3 信息隔离设计

```
┌─────────────────────────────────────────────────────────────┐
│                    信息隔离原则                               │
├─────────────────────────────────────────────────────────────┤
│  Writer 传递给 Reviewer 的信息：                             │
│    ✅ 任务摘要 (目标、验收标准、约束)                        │
│    ✅ 上轮 Review 意见及处理 (第 2+ 轮)                      │
│    ❌ 改动文件列表                                           │
│    ❌ 修改说明                                               │
│    ❌ 自审过程                                               │
│                                                             │
│  Reviewer 必须自行：                                         │
│    → 使用 git diff 发现改动范围                              │
│    → 独立判断实现方案是否合理                                │
│    → 基于业务诉求审查代码                                    │
└─────────────────────────────────────────────────────────────┘
```

### 📝 关键学习点

#### 学习点 1：验收标准编写规范

**设计思路**：验收标准是用户视角的业务结果，不是开发者视角的实现细节

```yaml
# 禁用词表 (出现即判定为实现细节)
类名/方法名/变量名:
  - BatchRerunRequest
  - selectPhotosForRerun
  - batchInsertIgnore

表名/字段名/SQL关键词:
  - file_ai_check
  - ai_check_version=2
  - INSERT ON DUPLICATE KEY UPDATE

具体数值/策略:
  - 分批200条
  - 游标分页500条
  - 10QPS限流

技术方案描述:
  - 用 UPDATE JOIN 代替 INSERT ON DUPLICATE
  - 去掉分流查询
```

**正确 vs 错误对照**：

| 错误（实现细节） | 正确（业务结果） |
|-----------------|-----------------|
| `copyDetectionResult` SQL 从 INSERT ON DUPLICATE KEY UPDATE 简化为 UPDATE JOIN | 结果同步的代码简洁易读 |
| 去掉 `selectExistingImageIds` 分流查询，统一用 INSERT IGNORE + UPDATE | 记录准备逻辑简洁，不做多余查询 |
| `file_ai_check` 记录被重置且 `ai_check_version=2` | 重跑后照片的AI检核结果被正确更新 |

**复刻要点**：
- 设计禁用词表
- 设计自检流程
- 提供正确/错误对照表

#### 学习点 2：Reviewer Prompt 模板

**设计思路**：标准化 Reviewer 的输入，确保独立审查

```markdown
# Code Review 任务

## 业务诉求
{任务摘要}

## 上轮 Review 意见及处理 (仅第 2+ 轮)
| # | 上轮阻塞问题 | Writer 处理方式 |
|---|-------------|---------------|
| 1 | 问题描述 | 修复说明 |

## 审查指引

作为独立 Reviewer，请基于以上业务诉求，对本次代码改动进行全面审查。

**第一步：自行发现改动范围。** 使用 `git diff` 查看本次所有改动...

**第二步：按以下维度审查（按优先级）：**
1. **实现思路**：Writer 选择的实现方案是否合理？
2. **需求符合**：对照验收标准，是否有未满足或理解偏差的条目
3. **正确性**：bug、边界条件、并发安全、异常处理
4. **设计合理性**：接口设计、职责划分、扩展性
5. **性能与资源**：N+1 查询、内存泄露、不必要的 IO
6. **安全性**：注入、敏感信息、权限校验
```

**复刻要点**：
- 设计 Prompt 模板
- 定义审查维度
- 要求独立发现改动

#### 学习点 3：子 Agent Spawn 模式

**设计思路**：每轮 Reviewer 必须 spawn 独立子 Agent

```python
# 伪代码
def spawn_reviewer(task_summary, previous_feedback=None):
    prompt = f"""
    # Code Review 任务
    
    ## 业务诉求
    {task_summary}
    
    ## 上轮 Review 意见及处理
    {previous_feedback if previous_feedback else "无"}
    
    ## 审查指引
    ...
    """
    
    # spawn 独立子 Agent
    reviewer = task(
        subagent_type="unspecified-high",
        prompt=prompt,
        run_in_background=False
    )
    
    return reviewer.result
```

**复刻要点**：
- 使用 task 工具 spawn 子 Agent
- 传递必要信息 (不传改动文件)
- 等待子 Agent 完成

#### 学习点 4：双循环退出机制

**设计思路**：明确的退出条件，避免无限循环

```yaml
内循环 (自审) 退出条件:
  - 一轮审查未发现任何新问题
  - 无次数限制

外循环 (提审) 退出条件:
  - Reviewer 无阻塞问题
  - 达到 3 轮上限
  - 如达到上限，将残留问题交由用户决策
```

**复刻要点**：
- 设计退出条件
- 设置轮次上限
- 处理残留问题

#### 学习点 5：汇总报告模板

**设计思路**：标准化报告格式，包含所有必要信息

```markdown
# 汇总报告

## 1. 任务摘要
- 目标：...
- 验收标准：...

## 2. 代码改动概览
### 2.1 改动文件列表
| # | 文件路径 | 改动类型 | 说明 |
|---|---------|---------|------|

### 2.2 改动统计
- 新增文件：X 个
- 修改文件：Y 个
- 删除文件：Z 个

## 3. Review 过程
### 3.1 内循环自审
- 轮次：N 轮
- 修复问题：M 个

### 3.2 外循环 Review
#### 3.2.1 第 1 轮
- 阻塞问题：X 个
- 建议：Y 个

## 4. Review 核心收获
- ...

## 5. 给用户 Review 的思路
- 改动全景：...
- 审查顺序：...
- 重点关注项：...
```

**复刻要点**：
- 设计报告模板
- 定义必填字段
- 要求层级编号

### 🎓 复刻练习

```markdown
# 练习 1: 设计验收标准编写规范
1. 定义禁用词表
2. 设计自检流程
3. 提供正确/错误对照表

# 练习 2: 实现双循环机制
1. 设计内循环 (自审) 流程
2. 设计外循环 (提审) 流程
3. 实现退出条件

# 练习 3: 实现子 Agent Spawn
1. 设计 Reviewer Prompt 模板
2. 使用 task 工具 spawn 子 Agent
3. 处理子 Agent 返回结果
```

---

## 🎯 三个 Skill 的设计模式对比

| 维度 | mr-workflow | xiaomi-git | writer-reviewer |
|------|-------------|------------|-----------------|
| **核心模式** | 流程控制 | API 集成 | 多 Agent 协作 |
| **复杂度** | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| **并行处理** | 信息收集阶段 | MR 数据获取 | Reviewer spawn |
| **条件分支** | 确认策略 | MR 作者判断 | 退出条件判断 |
| **模板驱动** | MR 描述模板 | CR 评论模板 | 验收标准/报告模板 |
| **外部依赖** | gitlab-mcp | gitlab-mcp | task 工具 |
| **异步处理** | AutoRec 轮询 | 无 | 无 |
| **信息隔离** | 无 | 无 | Reviewer 独立发现改动 |

---

## 📚 学习路径建议

### 阶段 1：理解流程控制 (mr-workflow)

```
1. 理解 6 阶段流程架构
2. 掌握并行信息收集
3. 设计模块归属分析规则
4. 实现异步轮询机制
```

### 阶段 2：掌握 API 集成 (xiaomi-git)

```
1. 理解三能力架构
2. 实现项目路径自动检测
3. 掌握并行数据获取
4. 设计代码问题检测维度
```

### 阶段 3：精通多 Agent 协作 (writer-reviewer)

```
1. 理解双循环机制
2. 设计验收标准编写规范
3. 实现子 Agent Spawn
4. 设计汇总报告模板
```

---

## 🔗 关键文件路径

```bash
# mr-workflow
~/.opencode/skills/mr-workflow/SKILL.md

# xiaomi-git
~/.opencode/skills/xiaomi-git/SKILL.md

# writer-reviewer
~/.opencode/skills/writer-reviewer/SKILL.md
```

---

> 📝 本文档由 Sisyphus 生成，建议结合实际 Skill 文件进行学习
>
> 🔄 最后更新: 2026-05-23
