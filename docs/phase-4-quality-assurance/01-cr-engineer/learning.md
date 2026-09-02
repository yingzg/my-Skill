# cr-engineer — 深度学习文档

> 对应 SKILL.md: `/mnt/d/测试项目/vibe-hubs-fe/skill-FE/cr-engineer/SKILL.md` (198行)
>
> 关联 SKILL: xiaomi-git (GitLab 操作门面), sonar-coverage-booster (覆盖率补全)
>
> 辅助脚本: `scripts/fetch_review_comments.py`, `scripts/fetch_mr_diff.py`, `scripts/post_mr_comments.py`

---

## 一、功能全景

### 一句话定位
**GitLab MR 代码审查引擎** — 8 步流水线 + 双模式分支（Review / Fix）+ 历史评论知识库 + 评论发布，支撑 MiCR 门禁合规。

### 核心流程

```
用户提供 MR 链接
    ↓
Step 1: Input Validation（解析 MR URL，提取 project_id + IID）
    ↓
Step 2: GitLab Auto-Detect（从 git remote origin 自动检测项目路径）
    ↓
Step 3: MR Ownership Detection（判断 MR 属于自己还是他人）
    ├─ 自己的 MR → Fix Gate Mode → Step 8
    └─ 他人的 MR → Review Mode → Step 4
         ↓
Step 4: Diff Acquisition（获取 MR 完整代码变更）
    ↓
Step 5: Review Pattern Loading（加载团队历史 review 评论作为模式库）
    ↓
Step 6: AI Code Review（基于模式库 + 编码最佳实践的深度分析）
    ↓
Step 7: Comment Generation & Publishing（生成行级 diff 评论，发布到 MR）
    ↓
Step 8: Own MR Gate Fix（分析 MiCR 阻塞项：覆盖率/单测/评论数，逐一修复）
```

### 能力矩阵

| 能力 | 模式 | 触发条件 | 产出 |
|------|------|---------|------|
| **Review 他人 MR** | Review Mode | MR 作者 ≠ 当前用户，或用户明确要求 "review" | CR 评论列表（发布到 MR） |
| **修复自己 MR 门禁** | Fix Gate Mode | MR 作者 = 当前用户，且未明确要求 review | 阻塞项修复（覆盖率补全、单测修复、评论补充） |
| **补充有效评论** | 评论补量模式 | 用户明确要求 "补充评论"、"评论数不够" | 补足至 ≥5 条有效评论 |

### 在开发流程中的位置

```
开发 → commit → push → 创建 MR → CI Pipeline 运行
                                  ↓
                           MiCR 门禁检查 ← ─ ─ cr-engineer 介入
                              ↓                      ↓
                      [Review Mode]        [Fix Gate Mode]
                      审查他人代码         修复自己 MR 的门禁阻塞
                          ↓                      ↓
                      发布 CR 评论         覆盖率补全 / 单测修复
                          ↓                      ↓
                      门禁达标              门禁达标 → merge
```

---

## 二、架构设计分析

### 2.1 8 步流水线设计

cr-engineer 采用**严格顺序流水线**模式，每一步有明确的输入/输出契约：

```
Step 1                  Step 2                  Step 3
Input Validation  ──→  GitLab Auto-Detect  ──→  Ownership Detection
  in: MR URL             in: git workdir          in: project_id, IID
  out: project_id, IID   out: project_id (验证)   out: mode (review|fix)
                              ↓ (验证失败)
                              回退策略：
                              - 不在 git 仓库 → 从 MR URL 提取
                              - remote URL 非小米 GitLab → 提示用户
                              - 项目不存在 → 手动输入

Step 4                  Step 5                      Step 6
Diff Acquisition  ──→  Pattern Loading  ──→  AI Code Review
  in: project_id, IID    in: project_id              in: diffs + patterns
  out: file diffs[]      out: review patterns[]      out: findings[]
                         │                            │
                         └── fetch_review_comments   └── 双维度审查：
                             .py 自动判断缓存             维度1: 团队历史模式
                             - 已有 → 跳过获取            维度2: 通用最佳实践
                             - 没有 → API 拉取并
                               追加到 review_comments.md

Step 7                      Step 8 (Fix Mode Only)
Comment Publishing  ──→     Gate Fix
  in: findings[]              in: MiCR 门禁状态
  out: 已发布评论数            out: 阻塞项修复结果
  │                           ├── 覆盖率不足 → sonar-coverage-booster
  └── post_mr_comments.py     ├── 单测失败 → 本地诊断修复
      - 获取 diff_refs        ├── 评论不足 → 自评补充
      - 逐条发布 inline note  └── Approve/冲突 → 人工处理
      - 报告成功/失败
```

**为什么选择 Pipeline 而非 Event-Driven？**

Pipeline 适合 cr-engineer 的场景：
1. **步骤间强依赖** — 没有 diff 就无法 review，没有 review 就无法发布评论
2. **线性流程可中断** — 每一步完成后可以 checkpoint，支持人工确认（如 Step 7 发布评论前需用户同意）
3. **调试友好** — 每步输出清晰可追溯，排查问题时有明确的"卡在哪一步"
4. **双模式分支** — 在 Step 3 分叉后，两条路径各自独立执行，不需要复杂的状态机

### 2.2 双模式设计 (Review vs Fix)

这是 cr-engineer 最核心的架构决策。在 Step 3（Ownership Detection）产生**两个完全不同的执行路径**：

```
Step 3: MR Ownership Detection
         │
  ┌──────┴──────┐
  │  谁的 MR？   │
  └──────┬──────┘
         │
    ┌────┴────┐
    │         │
 自己的 MR   他人的 MR
    │         │
    ▼         ▼
 Fix Gate   Review
   Mode      Mode
    │         │
    ├── 解析 MiCR 门禁         ├── 获取 diff
    ├── 覆盖率不足？             ├── 加载 review patterns
    │   └──→ sonar-coverage-   ├── 逐文件审查
    │        booster            ├── 生成评论
    ├── 单测失败？              └── 发布评论
    │   └──→ 本地诊断修复
    ├── 评论不足？
    │   └──→ 自评补充
    └── 输出修复报告
```

**分支判断逻辑（关键歧义处理）**：

| 条件 | 走向 | 原因 |
|------|------|------|
| MR 作者 = 当前用户 + 未说 "review" | Fix Mode | 用户意图是修门禁，非求审查 |
| MR 作者 = 当前用户 + 明确说 "review" | Review Mode | 用户覆盖默认行为，主动求审查 |
| MR 作者 ≠ 当前用户 | Review Mode | 无歧义，就是审查他人代码 |
| 用户说 "补充评论" | 评论补量模式 | 快速补至 ≥5 条，轻量审查 |

### 2.3 Review Pattern 系统

`reference/review_comments.md` 是一个**多项目共享的知识库文件**，按项目分 section 存储团队历史 review 评论：

```
reference/review_comments.md

<!-- PROJECT: mit/new-retail/overseas-offline-sales/mi-intl-scheme -->
# Review Comments: mi-intl-scheme

- MR !3125: # 全部达标
- MR !3114: 新增了三个字段 gtmReviewTotal...
- MR !3097: empty ？ null ： get(0)
- MR !3097: 确认中英文格式是否正确
- MR !3097: 确认异常引起原因能正常获取到值
```

**模式库的工作机制**：

```
Step 5: 执行 fetch_review_comments.py
  ├── 检查 review_comments.md 中是否已存在当前 project 的 comments
  │     ├── 已存在 → 跳过获取（缓存命中）
  │     └── 不存在 → GitLab API 拉取最近 20 个 merged MR 的 notes
  │           └── 过滤：system notes 排除，body 长度 > 10，最多 100 条
  │           └── 追加到 review_comments.md
  ↓
Step 5: 读取 review_comments.md 全文
  ↓
Step 6: AI 归纳 patterns
  ├── 参数校验与空值检查
  ├── 异常处理与错误传播
  ├── 命名规范
  ├── 日志与可观测性
  ├── 并发安全
  ├── 性能风险（SQL N+1、索引缺失、大循环）
  ├── 业务逻辑正确性
  └── 接口兼容性 / 回归风险
  ↓
Step 7: 基于 patterns + diff 生成评论
```

**为什么按项目分 section 而非全局 index？**
- 不同项目的审查风格差异大（核心交易系统关注数据一致性 vs 管理后台关注操作便利性）
- 同项目的评论有连续性（同一拨 reviewer，风格稳定）
- 缓存粒度合理（一个项目拉一次，而非每次查询）

### 2.4 GitLab Auto-Detect 设计

这是一个**跨 SKILL 可复用的基础设施模式**。从 git remote origin 自动解析 GitLab 项目路径：

```
git remote get-url origin
  ↓
URL 解析器
  ├── SSH:  git@git.n.xiaomi.com:mit/new-retail/.../intl-retail.git
  │          → mit/new-retail/overseas-offline-sales/intl-retail
  ├── HTTPS: https://git.n.xiaomi.com/mit/new-retail/.../intl-retail.git
  │          → mit/new-retail/overseas-offline-sales/intl-retail
  └── 其他: 提示用户手动输入
  ↓
验证: gitlab_get_project(project_id) → 确认项目存在且有权限
  ↓
回退层级:
  1. 不在 git 仓库 → 从 MR URL 中解析 project_path（兜底方案）
  2. remote 非小米 GitLab → 提示用户确认
  3. 项目不存在/无权限 → 请求用户手动输入
```

**这个模式被哪些 SKILL 复用？**
- `xiaomi-git` — 原生产地，作为能力一独立暴露
- `cr-engineer` — 通过调用 xiaomi-git 间接使用
- 理论上任何需要访问 GitLab 的 SKILL 都可以复用这套检测逻辑

### 2.5 SKILL 集成模式

cr-engineer 通过 **"任务委托"模式** 与两个外部 SKILL 协作：

```
cr-engineer
   │
   ├── 委托给 xiaomi-git
   │     ├── GitLab 操作（获取 MR 详情/diff/discussions、发布评论）
   │     ├── GitLab 项目自动检测
   │     └── CR 评论生成与发布的完整流程
   │
   └── 委托给 sonar-coverage-booster
         ├── SonarQube 覆盖率数据解析
         ├── 未覆盖代码定位
         └── JUnit5 + Mockito 测试补写
```

**委托机制详解**：

```
cr-engineer SKILL.md 不直接调用 GitLab MCP
  ↓ 而是
加载 xiaomi-git SKILL 的完整上下文
  ↓
利用其 Step 0-5 的 CR 评论流程 和 能力三的门禁修复流程
  ↓
cr-engineer 作为"审查意图的入口"，xiaomi-git 作为"GitLab 操作的门面"

同理：
Fix Mode 下覆盖率不足 → 不内联覆盖率补全逻辑
  ↓ 而是
加载 sonar-coverage-booster SKILL
  ↓
由 sonar-coverage-booster 完成：
  - 从 SonarQube 获取未覆盖代码
  - 生成测试用例
  - 本地验证 + push
```

**为什么这样设计？（松耦合多 SKILL 协作）**：
1. **单一职责** — cr-engineer 专注"审查调度"，GitLab API 调用封装在 xiaomi-git，覆盖率逻辑封装在 sonar-coverage-booster
2. **可替换性** — 未来可以换一个覆盖率工具，只需换 sonar-coverage-booster，cr-engineer 无感知
3. **独立维护** — 每个 SKILL 独立版本迭代，不影响其他

---

## 三、设计模式深度分析

### 3.1 Pipeline Pattern（流水线模式）

```
Step 1 → Step 2 → Step 3 → [分支] → Step 4-7 (Review) / Step 8 (Fix)
```

**每步的契约结构**：

| 步骤 | 输入 | 输出 | 失败处理 |
|------|------|------|---------|
| Step 1 | MR URL 字符串 | project_id, mr_iid | URL 解析失败 → 向用户索要 |
| Step 2 | git workdir | project_id (验证) | 非 git 仓库 → 从 MR URL fallback |
| Step 3 | project_id, iid, git user | mode (review/fix) | 无法判断 → 询问用户意图 |
| Step 4 | project_id, iid | file diffs[] | API 错误 → 重试或报告 |
| Step 5 | project_id | review patterns[] | API 错误 → 使用通用最佳实践 |
| Step 6 | diffs[] + patterns[] | findings[] | 无 |
| Step 7 | findings[] | 已发布评论数 | 发布失败 → 报告失败条数 |
| Step 8 | MiCR 门禁状态 | 修复结果 | 修复失败 → 告知用户需人工介入 |

**Pipeline 的关键特性**：
- **可暂停** — Step 7 发布前必须等用户确认，这是唯一的人工闸门
- **可降级** — Review Pattern 加载失败不阻断流程，退化为纯通用审查
- **可观测** — 每步产出具象化输出，方便定位问题

### 3.2 Strategy Pattern（策略模式）

在 Step 3 通过 Ownership Detection 选择执行策略：

```
interface ReviewStrategy {
    execute(MrContext ctx): ReviewResult
}

class ReviewOthersStrategy implements ReviewStrategy {
    // Step 4-7: 获取 diff → 加载 patterns → 审查 → 发布评论
}

class FixOwnGateStrategy implements ReviewStrategy {
    // Step 8: 解析 MiCR → 覆盖率补全 → 单测修复 → 评论补充
}

class QuickSupplementStrategy implements ReviewStrategy {
    // 仅补足评论数至 ≥5 条，不做深度审查
}
```

**策略选择规则（运行时）**：

```
if (author == current_user) {
    if (user_explicitly_said_review) → ReviewOthersStrategy
    else if (user_said_supplement) → QuickSupplementStrategy
    else → FixOwnGateStrategy
} else {
    if (user_said_supplement) → QuickSupplementStrategy
    else → ReviewOthersStrategy
}
```

**为什么用户意图可以覆盖默认策略？**
- "review 自己的 MR" 是合法场景（自我审查，验证代码质量）
- "补充评论" 是明确的轻量操作，不应走全量审查

### 3.3 Observer/Event Pattern（门禁监控）

Fix Mode 本质是一个**事件驱动的门禁监控系统**：

```
MiCR Bot 评论（事件源）
  ↓ 解析
门禁状态快照
  ├── 单测覆盖率: 41.10% (期望 ≥60%) → 🔴 阻塞
  ├── 单测通过率: 90.50% (期望 100%) → 🔴 阻塞
  ├── 有效评论数: 3/5               → 🟡 需补充
  ├── Sonar 质量门禁: ✅             → 🟢 通过
  └── Approve: ❌                   → 🟡 需人工
  ↓ 按优先级排序
修复队列
  1. 单测通过率修复（如有本次 MR 引入的失败）
  2. 单测覆盖率补全 → 调用 sonar-coverage-booster
  3. 有效评论数补充 → 自评或找同事
  4. Approve → 告知用户找有权限的同事
  ↓ 逐项处理
修复报告
  ├── 已修复项 (action → result)
  └── 待人工项 (原因 → 建议)
```

### 3.4 Knowledge Base Pattern（知识库外化）

`review_comments.md` 是一个**外化知识库**，让 AI 获得"团队记忆"：

```
知识库架构：
  review_comments.md
    ├── PROJECT: A  → comments[0..n]  (A 团队的历史 review 风格)
    ├── PROJECT: B  → comments[0..m]  (B 团队的历史 review 风格)
    └── PROJECT: C  → comments[0..k]  (C 团队的历史 review 风格)

AI 使用方式：
  1. 读取全文 → 理解所有项目的审查风格
  2. 归纳通用模式（如：SQL 性能是大多数团队关注的重点）
  3. 匹配当前项目 → 提取专属模式
  4. 审查时优先检查匹配到的模式点

缓存策略：
  - 首次使用项目 → fetch_review_comments.py 拉取并追加
  - 已有项目 → 跳过，直接使用本地缓存
  - 没有过期机制 (可改进点)
```

---

## 四、关键设计决策

### 4.1 为什么预加载 review comments 而不是实时搜索？

**决策**：在 Step 5 一次性加载 `review_comments.md` 全文到上下文。

**原因**：
1. **上下文窗口充足** — review_comments.md 通常 <5000 行，不会超出 token 限制
2. **模式归纳需要全局视角** — 只有看到跨越多个 MR 的评论，才能归纳出真正的"团队关注点"
3. **避免 API 调用风暴** — 如果逐文件实时搜索历史评论，每个变更文件都可能触发一次 API 调用
4. **离线可用** — 缓存后无需网络也能进行基本的模式匹配

**代价**：首次加载需 API 调用，若评论量大则时间稍长；缓存无过期机制，长期不更新可能偏离最新风格。

### 4.2 为什么区分 own MR 和 others' MR 而不是统一处理？

**决策**：在 Step 3 基于 MR 归属做出分支选择。

**原因**：
1. **用户意图不同** — 对自己的 MR，默认意图是"修门禁"而非"求审查"
2. **可用信息不对称** — 对自己的 MR，你可以 push 代码修复；对别人的 MR，你只能评论建议
3. **执行路径完全不同** — Review 读代码、写评论；Fix 读门禁、修代码、跑测试、push。两套逻辑强行统一会变成"if-else 地狱"
4. **安全边界** — 自己的 MR：允许修改代码并 push；别人的 MR：只读 + 评论，绝不动代码

**反例**：如果统一处理，对别人的 MR 也会执行"覆盖率补全"，但你无权 push 到别人分支。

### 4.3 为什么委托给 xiaomi-git 而不是直接调用 GitLab API？

**决策**：通过加载 xiaomi-git SKILL 间接使用 GitLab 能力。

**原因**：
1. **GitLab API 封装** — xiaomi-git 已经处理了各种异常（MR 状态异常、大 diff 分段读取、diff_refs 获取等），cr-engineer 无需重复实现
2. **责任边界清晰** — cr-engineer = 审查调度 + 意图解析；xiaomi-git = GitLab 操作门面。变更 GitLab API 只需改 xiaomi-git
3. **GitLab Auto-Detect 复用** — 项目路径自动检测在 xiaomi-git 中实现，cr-engineer 直接受益
4. **MiCR 门禁解析** — xiaomi-git 内部有完整的 MiCR 评论解析逻辑，cr-engineer 无需重新实现

### 4.4 为什么调用 sonar-coverage-booster 而不是内联覆盖率处理？

**决策**：在 Fix Mode 下，覆盖率不足时委托给独立的 sonar-coverage-booster SKILL。

**原因**：
1. **覆盖率补全是重流程** — 涉及 SonarQube API 查询、未覆盖代码分析、测试代码生成、本地 Maven 编译验证、push 触发 CI。这些逻辑如果内联到 cr-engineer，SKILL.md 会膨胀到 800+ 行
2. **独立维护周期** — SonarQube API 变更、项目测试规范调整，只需更新 sonar-coverage-booster
3. **可复用** — sonar-coverage-booster 也可以被其他 SKILL（如 xiaomi-git 的门禁修复）调用
4. **关注点分离** — cr-engineer 的核心语义是"审查代码质量"，覆盖率是"测试完备性"，两者概念不同

---

## 五、设计权衡与局限性

### 5.1 Pipeline 刚性

**问题**：8 步流水线严格顺序执行，Step 4 失败（GitLab API 不可用）会导致整条 Review 路径无法继续。

**影响**：
- 没有"跳过某步"的机制（不同于 ticket-troubleshoot 的快速路径）
- 中断后无法从中间恢复（无 checkpoint 机制）

**可能的缓解**：
- Step 5（Pattern Loading）失败可降级：用通用最佳实践替代
- Step 4（Diff Acquisition）失败无法降级：diff 是 review 的唯一原料

### 5.2 Pattern 匹配精度

**问题**：AI 从 review_comments.md 归纳模式后，能否真正匹配到当前 diff 中的问题？

**影响因素**：
- review_comments.md 包含大量 MiCR 机器人的自动化评论（"全部达标"、"变更摘要"），这些不是人类 review 模式
- 不同项目、不同 reviewer 的风格差异大，模式可能被"平均化"
- 有些模式依赖于上下文（如特定业务的约定），AI 难以从评论摘要中推断

**实际表现**：模式库主要起到"方向性引导"作用（提醒 AI 关注哪些维度），而非精确的规则匹配。

### 5.3 单平台依赖

**问题**：整个流程强依赖小米 GitLab（`git.n.xiaomi.com`）。

**硬编码点**：
- MR URL 解析正则依赖 GitLab URL 格式
- GitLab API v4 端点路径
- MiCR Bot 评论格式（小米特有）
- review_comments.md 中的项目标记格式

**通用化难度**：中等。GitLab API v4 是标准协议，理论上支持任何 GitLab 实例，但 MiCR 门禁是小米特有的。

### 5.4 Review 质量依赖 review_comments.md 完整性

**问题**：如果 review_comments.md 为空或不完整，review 模式退化到纯通用最佳实践。

**退化路径**：
```
review_comments.md 无当前项目的 comments
  → Step 5 调用 GitLab API 拉取
    → API 返回空（该项目没有历史评论）
      → Step 6 只能使用通用最佳实践
        → review 质量下降，缺少团队特有的关注点
```

### 5.5 双模式之间的"灰色地带"

**问题**：自己的 MR 但有真实的审查需求时，默认走 Fix Mode 会跳过代码审查。

**用户需要明确说 "review" 才能覆盖默认行为**。但新用户可能不知道这个规则，导致：
- 给了自己的 MR 链接，期望得到代码审查
- 系统走 Fix Mode，只检查门禁、补覆盖率
- 用户困惑"为什么不帮我看代码"

**缓解**：在 Step 3 最好输出一个简短的确认提示："检测到这是您的 MR，我将执行门禁修复。如需代码审查，请明确说明 'review'。"

---

## 六、实用启示

### 6.1 何时使用 Pipeline 模式设计 SKILL

Pipeline 适合以下场景：
- ✅ 步骤间有严格的顺序依赖（B 需要 A 的产物）
- ✅ 流程可线性描述，分支点少（1-2 个）
- ✅ 每步输出可验证（有明确的成功/失败标准）
- ✅ 需要支持中途暂停和人工确认

Pipeline 不适合：
- ❌ 步骤间松散耦合，可并行执行（应使用事件驱动或并行 Agent）
- ❌ 分支点过多，状态爆炸（应使用状态机 + 规则引擎）
- ❌ 需要频繁回退和重试（应使用 Workflow Engine）

cr-engineer 处于 Pipeline 的"舒适区"：8 步，1 个分支点，强依赖。

### 6.2 如何设计 SKILL 间委托

cr-engineer → xiaomi-git → sonar-coverage-booster 展示了三层松耦合委托：

**关键原则**：
1. **接口语义化** — 委托基于"能力名称"（如 "覆盖率补全"）而非"技术调用"（如 "调用 SonarQube API"）
2. **允许降级** — 被委托 SKILL 不可用时，委托方应有降级路径（如跳过错略补全，告知用户）
3. **单向依赖** — xiaomi-git 不知道 cr-engineer 的存在，sonar-coverage-booster 不知道 xiaomi-git 的存在
4. **上下文传递** — 委托时传递最小必要信息（MR 链接、项目路径），而非全量状态

**委托模式 vs 直接调用**：

| 维度 | 委托模式 | 直接调用 |
|------|---------|---------|
| 耦合度 | 低（仅依赖能力名） | 高（依赖具体 API） |
| 可替换性 | 高（换一个 SKILL 名即可） | 低（需改代码） |
| 调试难度 | 中（需追踪跨 SKILL 流转） | 低（单线程） |
| 可复用性 | 高（被委托方独立复用） | 低（调用逻辑内嵌） |

### 6.3 知识库管理策略

review_comments.md 的设计启示：

1. **文件 > 数据库** — 对于 SKILL 级别的知识库，Markdown 文件比数据库更合适（可 Git 版本控制、可人工编辑、可跨工具共享）
2. **按维度分 Section** — 按 project 分区，局部更新不影响全局
3. **缓存 > 实时查询** — AI 上下文足够大时，预加载全文比实时搜索更高效
4. **增量追加** — 新数据追加到文件末尾，不重写全文（降低风险）
5. **需要过期机制** — 当前缺失，长期运行后缓存可能过时

### 6.4 双模式设计的推广

"基于角色/归属的运行时策略选择" 可以推广到其他 SKILL：

```
判断维度 → 选择策略
  ├── 用户身份（自己 vs 他人）→ cr-engineer 的 Review vs Fix
  ├── 问题紧急程度（P0 vs P1）→ ticket-troubleshoot 的快速 vs 完整路径
  ├── 数据规模（大 vs 小）→ 分段处理 vs 直接处理
  └── 环境可用性（在线 vs 离线）→ 完整流程 vs 降级流程
```

**设计检查清单**：
- [ ] 分支条件是否可自动判断？（避免每步都问用户）
- [ ] 默认策略是否符合大多数场景？（减少用户认知负担）
- [ ] 用户是否可以显式覆盖默认策略？（保留灵活性）
- [ ] 两条路径的输出契约是否一致？（调用方无需关心内部路径）

---

## 七、复刻要点 Checklist

- [ ] 理解 8 步流水线的每一步输入/输出和失败处理
- [ ] 理解双模式分支的核心逻辑：Owner Detection → Review / Fix
- [ ] 理解用户意图如何覆盖默认策略
- [ ] 理解 review_comments.md 作为知识库的加载和缓存机制
- [ ] 理解 fetch_review_comments.py 的"已有则跳过"缓存策略
- [ ] 理解 post_mr_comments.py 的 diff_refs 获取和 inline note 发布
- [ ] 理解 SKILL 间委托的松耦合设计（cr-engineer → xiaomi-git → sonar-coverage-booster）
- [ ] 能设计类似的 GitLab Auto-Detect 模式
- [ ] 能设计类似的 "基于归属的运行时策略选择"
- [ ] 能评估一个流程是否适合 Pipeline 模式
