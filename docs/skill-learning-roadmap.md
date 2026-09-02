# 🚀 Skill 从 0 到 1 复刻学习路线

> 本文档梳理了 24 个自定义 Skill 的学习优先级和复刻路径
> 
> 📅 更新时间: 2026-05-23

---

## 📊 总览

| 阶段 | 技能数量 | 预估耗时 | 核心能力 |
|------|----------|----------|----------|
| Phase 1 | 3 个 | ~5h | Skill 元知识 |
| Phase 2 | 4 个 | ~7h | 日常开发工作流 |
| Phase 3 | 4 个 | ~8h | 线上排障诊断 |
| Phase 4 | 4 个 | ~7h | 代码质量保障 |
| Phase 5 | 3 个 | ~3h | Git 高级操作 |
| Phase 6 | 4 个 | ~6h | 专项能力 |
| Phase 7 | 4 个 | ~6.5h | 元能力 (造 skill 的 skill) |
| **总计** | **24 个** | **~42h** | - |

---

## Phase 1: 基础能力 ⭐⭐⭐

> 💡 **先掌握这些，其他所有 skill 都依赖它们**
>
> 这 3 个 skill 构成了「元知识」层，理解它们就能看懂所有 skill 的底层逻辑

### 学习顺序

| 序号 | Skill | 学习要点 | 预估耗时 | 难度 |
|------|-------|----------|----------|------|
| 1.1 | **skill-creator** | YAML 结构、触发词设计、指令编写规范 | 2h | ⭐⭐ |
| 1.2 | **writing-skills** | 验证 skill 质量、调试 skill | 1h | ⭐ |
| 1.3 | **skill-design-patterns** | 10 种设计模式、三层架构 | 2h | ⭐⭐⭐ |

### 学习目标

- [ ] 理解 SKILL.md 的 YAML frontmatter 结构
- [ ] 掌握触发词 (trigger) 的设计原则
- [ ] 能独立编写一个简单的 skill
- [ ] 了解 10 种 skill 设计模式

### 关键文件

```
~/.claude/skills/skill-creator/SKILL.md
~/.claude/skills/writing-skills/SKILL.md
~/.opencode/skills/skill-design-patterns/SKILL.md
```

---

## Phase 2: 核心工作流 ⭐⭐⭐

> 💡 **日常开发必备，每天都会用到**
>
> 这些 skill 定义了你的日常编码工作流

### 学习顺序

| 序号 | Skill | 学习要点 | 预估耗时 | 难度 |
|------|-------|----------|----------|------|
| 2.1 | **mr-workflow** | MR 模板、禁止直推的 hook 机制 | 1h | ⭐ |
| 2.2 | **xiaomi-git** | GitLab API 调用、CR 评论生成逻辑 | 3h | ⭐⭐⭐ |
| 2.3 | **continuous-execution-guard** | 中断条件判断、自动推进机制 | 1h | ⭐⭐ |
| 2.4 | **writer-reviewer** | 双 Agent 协作模式 | 2h | ⭐⭐ |

### 学习目标

- [ ] 理解 MR 工作流的强制约束机制
- [ ] 掌握 GitLab API 的使用 (MR、评论、Pipeline)
- [ ] 实现端到端执行的中断控制逻辑
- [ ] 理解 Writer-Reviewer 双角色协作模式

### 关键文件

```
~/.opencode/skills/mr-workflow/SKILL.md
~/.opencode/skills/xiaomi-git/SKILL.md
~/.opencode/skills/continuous-execution-guard/SKILL.md
~/.opencode/skills/writer-reviewer/SKILL.md
```

### 实战练习

```bash
# 练习 1: 创建一个简单的 mr-workflow skill
# - 定义 MR 模板
# - 设置触发词
# - 编写指令

# 练习 2: 调用 GitLab API
# - 获取 MR 详情
# - 添加评论
# - 检查 Pipeline 状态
```

---

## Phase 3: 排障诊断 ⭐⭐

> 💡 **线上问题定位，快速止损**
>
> 这些 skill 帮你快速定位和解决线上问题

### 学习顺序

| 序号 | Skill | 学习要点 | 预估耗时 | 难度 |
|------|-------|----------|----------|------|
| 3.1 | **ticket-troubleshoot-v3** | 工单排障流程、数据库查询模板 | 2h | ⭐⭐ |
| 3.2 | **code-trace-analyzer** | Java AST 分析、调用链提取 | 3h | ⭐⭐⭐ |
| 3.3 | **hera-slow-api-analyzer** | Playwright 自动化、Hera API | 2h | ⭐⭐⭐ |
| 3.4 | **hera-trace-doctor** | Trace 数据解析 | 1h | ⭐⭐ |

### 学习目标

- [ ] 掌握工单排障的标准流程
- [ ] 理解 Java 代码的 AST 分析方法
- [ ] 学会使用 Playwright 进行浏览器自动化
- [ ] 掌握分布式链路追踪数据的解析

### 关键文件

```
~/.opencode/skills/ticket-troubleshoot-v3/SKILL.md
~/.opencode/skills/code-trace-analyzer/SKILL.md
~/.opencode/skills/hera-slow-api-analyzer/SKILL.md
~/.claude/skills/hera-trace-doctor/SKILL.md
```

### 核心技术点

```markdown
# ticket-troubleshoot-v3
- 数据库查询模板 (MSSQL/OceanBase)
- 问题分类和定位流程
- 修复建议生成

# code-trace-analyzer
- Java AST 解析 (tree-sitter / javaparser)
- 调用链提取算法
- 外部调用识别 (Dubbo/HTTP/MQ)

# hera-slow-api-analyzer
- Playwright 浏览器自动化
- Hera 可观测平台 API
- 慢接口根因分析
```

---

## Phase 4: 质量保障 ⭐⭐

> 💡 **代码提交前的质量关卡**
>
> 这些 skill 帮你在代码提交前发现问题

### 学习顺序

| 序号 | Skill | 学习要点 | 预估耗时 | 难度 |
|------|-------|----------|----------|------|
| 4.1 | **cr-engineer** | CR 评论模板、代码质量检查点 | 2h | ⭐⭐ |
| 4.2 | **code-review-plus** | 多模型协作审查 | 2h | ⭐⭐⭐ |
| 4.3 | **sonar-coverage-booster** | SonarQube API、测试生成 | 2h | ⭐⭐⭐ |
| 4.4 | **sql-review** | SQL 解析、慢查询规则 | 1h | ⭐⭐ |

### 学习目标

- [ ] 掌握代码审查的标准流程和评论模板
- [ ] 理解多模型协作审查的架构
- [ ] 学会使用 SonarQube API 获取覆盖率数据
- [ ] 掌握 SQL 慢查询的识别规则

### 关键文件

```
~/.claude/skills/cr-engineer/SKILL.md
~/.claude/skills/code-review-plus/SKILL.md
~/.claude/skills/sonar-coverage-booster/SKILL.md
~/.claude/skills/sql-review/SKILL.md
```

### 核心技术点

```markdown
# cr-engineer
- GitLab MR Diff API
- 代码质量检查规则
- CR 评论模板设计

# code-review-plus
- 多 Agent 协作架构
- 审查结果合并算法
- 冲突处理机制

# sonar-coverage-booster
- SonarQube Web API
- 未覆盖代码识别
- JUnit5 + Mockito 测试生成
```

---

## Phase 5: Git 高级操作 ⭐

> 💡 **Git 操作的自动化和智能化**
>
> 这些 skill 帮你处理复杂的 Git 场景

### 学习顺序

| 序号 | Skill | 学习要点 | 预估耗时 | 难度 |
|------|-------|----------|----------|------|
| 5.1 | **git-conflict-resolver** | 冲突检测、CRLF 假冲突处理 | 1h | ⭐⭐ |
| 5.2 | **git-worktree-multi-task** | Worktree 管理、分支合并 | 1h | ⭐⭐ |
| 5.3 | **using-git-worktrees** | Worktree 隔离开发 | 1h | ⭐ |

### 学习目标

- [ ] 理解 Git 合并冲突的类型和解决策略
- [ ] 掌握 Git Worktree 的使用方法
- [ ] 实现多任务并行开发的工作流

### 关键文件

```
~/.claude/skills/git-conflict-resolver/SKILL.md
~/.claude/skills/git-worktree-multi-task/SKILL.md
~/.claude/plugins/installed/superpowers/skills/using-git-worktrees/SKILL.md
```

### 核心技术点

```markdown
# git-conflict-resolver
- 冲突标记解析 (<<<<<<< ======= >>>>>>>)
- CRLF/LF 假冲突识别
- 自动解决策略

# git-worktree-multi-task
- git worktree 命令
- 分支管理策略
- 任务目录组织
```

---

## Phase 6: 专项能力 ⭐

> 💡 **特定场景的专项 skill**
>
> 这些 skill 解决特定的业务场景

### 学习顺序

| 序号 | Skill | 学习要点 | 预估耗时 | 难度 |
|------|-------|----------|----------|------|
| 6.1 | **sdf** | TDD 流程、质量门禁 | 2h | ⭐⭐ |
| 6.2 | **frontend-slides** | HTML 动画、PPT 转 Web | 2h | ⭐⭐ |
| 6.3 | **dayu-cas-login** | CAS 登录流程、二维码截取 | 1h | ⭐ |
| 6.4 | **kb-doc-sync-mi-intl-scheme** | 知识库同步逻辑 | 1h | ⭐ |

### 学习目标

- [ ] 理解 SDF (SimpleDevFlow) 的工作原理
- [ ] 掌握 HTML 演示文稿的制作方法
- [ ] 了解 CAS 单点登录的流程
- [ ] 学会知识库文档的同步机制

### 关键文件

```
~/.claude/skills/sdf/SKILL.md
~/.claude/skills/frontend-slides/SKILL.md
~/.claude/skills/dayu-cas-login-skill/SKILL.md
~/.claude/skills/kb-doc-sync-mi-intl-scheme/SKILL.md
```

---

## Phase 7: 元能力 (造 skill 的 skill) ⭐

> 💡 **高阶能力：创建和管理 skill 的工具**
>
> 这些 skill 帮你更好地创建、管理和评估其他 skill

### 学习顺序

| 序号 | Skill | 学习要点 | 预估耗时 | 难度 |
|------|-------|----------|----------|------|
| 7.1 | **skill-design** | 端到端 skill 创建流程 | 2h | ⭐⭐ |
| 7.2 | **skill-quality-evaluator** | 质量评估框架 | 1h | ⭐⭐ |
| 7.3 | **install-skill** | 软链接安装机制 | 0.5h | ⭐ |
| 7.4 | **toolkit-inventory** | 目录扫描、MCP 解析 | 1h | ⭐ |

### 学习目标

- [ ] 掌握从零创建 skill 的完整流程
- [ ] 理解 skill 质量评估的维度和方法
- [ ] 学会 skill 的安装和分发机制
- [ ] 实现工具清单的自动扫描功能

### 关键文件

```
~/.opencode/skills/skill-design/SKILL.md
~/.opencode/skills/skill-quality-evaluator/SKILL.md
~/.claude/skills/install-skill/SKILL.md
~/.opencode/skills/toolkit-inventory/SKILL.md
```

---

## 🎯 推荐学习路径

### 快速通道 (2 周)

```
Week 1: Phase 1 + Phase 2
  Day 1-2: skill-creator → writing-skills
  Day 3-4: skill-design-patterns
  Day 5-7: mr-workflow → xiaomi-git

Week 2: Phase 3 + Phase 4
  Day 1-3: ticket-troubleshoot-v3 → code-trace-analyzer
  Day 4-5: cr-engineer → code-review-plus
  Day 6-7: 复习 + 实战练习
```

### 标准通道 (4 周)

```
Week 1: Phase 1 (基础能力)
Week 2: Phase 2 (核心工作流)
Week 3: Phase 3 (排障诊断)
Week 4: Phase 4 + Phase 5 (质量保障 + Git 操作)
```

### 深度通道 (6 周)

```
Week 1: Phase 1 (基础能力)
Week 2: Phase 2 (核心工作流)
Week 3: Phase 3 (排障诊断)
Week 4: Phase 4 (质量保障)
Week 5: Phase 5 + Phase 6 (Git 操作 + 专项能力)
Week 6: Phase 7 (元能力) + 总复习
```

---

## 💡 学习建议

### 1. 先读 Superpowers 源码

Superpowers 的 14 个开源 skill 是最佳实践的参考：

```bash
# 查看 Superpowers skill 目录
ls ~/.claude/plugins/installed/superpowers/skills/

# 阅读典型 skill
cat ~/.claude/plugins/installed/superpowers/skills/test-driven-development/SKILL.md
```

### 2. 边学边改

拿现有 skill 练手：

```bash
# 1. 复制一个 skill
cp -r ~/.claude/skills/cr-engineer ~/.claude/skills/my-cr-engineer

# 2. 修改触发词和指令
vim ~/.claude/skills/my-cr-engineer/SKILL.md

# 3. 测试效果
# 在 OpenCode 中触发你的 skill
```

### 3. 用 skill-creator 验证

每写一个 skill 都用它评估质量：

```bash
# 在 OpenCode 中
/skill-creator

# 然后描述你的 skill，让它帮你检查
```

### 4. 建立自己的 skill 库

```bash
# 创建你的 skill 目录
mkdir -p ~/my-skills

# 每完成一个 skill，就放进去
cp ~/.claude/skills/my-cr-engineer ~/my-skills/

# 定期回顾和优化
```

---

## 📚 参考资源

### 官方文档

- [OpenCode 官方文档](https://opencode.ai/docs)
- [Claude Code Skill 指南](https://docs.anthropic.com/claude-code/skills)
- [Superpowers GitHub](https://github.com/anthropics/claude-code-superpowers)

### 内部资源

- [Skill 设计模式](~/.opencode/skills/skill-design-patterns/SKILL.md)
- [Skill 质量评估](~/.opencode/skills/skill-quality-evaluator/SKILL.md)
- [工具清单](~/.opencode/skills/toolkit-inventory/SKILL.md)

---

## ✅ 学习检查清单

### Phase 1 完成标准

- [ ] 能独立编写一个 SKILL.md 文件
- [ ] 理解 YAML frontmatter 的所有字段
- [ ] 能设计有效的触发词
- [ ] 了解 10 种 skill 设计模式

### Phase 2 完成标准

- [ ] 理解 MR 工作流的约束机制
- [ ] 能调用 GitLab API 进行 MR 操作
- [ ] 实现端到端执行的中断控制
- [ ] 理解双 Agent 协作模式

### Phase 3 完成标准

- [ ] 能独立处理线上工单
- [ ] 理解 Java 调用链分析方法
- [ ] 能使用 Playwright 进行浏览器自动化
- [ ] 掌握 Trace 数据解析

### Phase 4 完成标准

- [ ] 能设计 CR 评论模板
- [ ] 理解多模型协作审查架构
- [ ] 能调用 SonarQube API
- [ ] 掌握 SQL 慢查询识别

### Phase 5 完成标准

- [ ] 能自动解决 Git 合并冲突
- [ ] 熟练使用 Git Worktree
- [ ] 实现多任务并行开发

### Phase 6 完成标准

- [ ] 理解 SDF 流程引擎
- [ ] 能制作 HTML 演示文稿
- [ ] 了解 CAS 登录流程
- [ ] 实现知识库同步

### Phase 7 完成标准

- [ ] 能从零创建完整的 skill 
- [ ] 能评估 skill 质量
- [ ] 理解 skill 安装机制
- [ ] 实现工具清单扫描

---

> 📝 本文档由 Sisyphus 生成，建议根据实际情况调整学习进度
>
> 🔄 最后更新: 2026-05-23                                                      
