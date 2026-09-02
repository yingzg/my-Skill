# cr-engineer — 测验文档

> 对应学习文档: `01-cr-engineer/learning.md`
>
> 测验类型: **设计理解**（架构推理 + 场景分析 + 设计模式识别 + 权衡评估）

---

## 一、设计模式识别（5题）

### 1. cr-engineer 的 8 步流水线最适合描述为什么模式？

A. Observer Pattern — 各步骤监听上游事件，异步解耦执行
B. Pipeline Pattern — 严格顺序执行，每步有明确的输入/输出契约，步骤间强依赖
C. Chain of Responsibility — 每个步骤决定自己处理还是传递给下一步
D. Mediator Pattern — 中央调度器协调各步骤的并行执行

**答案**：B

**解析**：cr-engineer 的步骤是强依赖的（没有 diff 无法 review，没有 review 无法发布评论），每步都有明确输入/输出，这是经典的 Pipeline Pattern。A 错误因为步骤间不是事件驱动的异步关系；C 错误因为步骤不能选择"不处理"；D 错误因为流水线是顺序的而非并行的。

---

### 2. 在 Step 3（MR Ownership Detection）中，系统根据 MR 作者是否当前用户选择不同的执行路径。这体现了什么设计模式？

A. Decorator Pattern — 在原有审查逻辑上动态添加门禁修复功能
B. Factory Pattern — 根据用户类型创建不同的 reviewer 对象
C. Strategy Pattern — 在运行时根据归属条件选择 ReviewStrategy 或 FixGateStrategy
D. Template Method Pattern — 定义审查骨架，子类实现具体步骤

**答案**：C

**解析**：Step 3 的核心是在运行时根据 "MR 作者 = 当前用户？" 这个条件，从多个策略中选择一个执行。这正是 Strategy Pattern 的精髓。A 错误因为没有"包装"关系；B 不准确，Factory 关注对象的创建，而这里关注行为的选择；D 错误因为两条路径的整体结构完全不同，不是"骨架+填空"的关系。

---

### 3. `review_comments.md` 按项目分 section 存储历史评论，AI 在审查前全文加载并归纳模式。这种设计属于什么模式？

A. Repository Pattern — review_comments.md 是数据访问层
B. Knowledge Base Pattern — 将团队经验外化为可被 AI 消费的结构化知识库
C. Adapter Pattern — review_comments.md 将 GitLab API 数据适配为 Markdown 格式
D. Singleton Pattern — 全局唯一的 review 数据源

**答案**：B

**解析**：review_comments.md 的核心价值是将散落在 GitLab 各个 MR 中的 review 经验，集中存储为一个外部知识库，让 AI 在每次审查时都能"学习"团队历史风格。这是一种知识外化（Externalization）模式。A/B/C/D 中只有 B 准确描述了这种设计的本质。

---

### 4. cr-engineer 委托 xiaomi-git 处理 GitLab API 调用，委托 sonar-coverage-booster 处理覆盖率补全。这种跨 SKILL 协作的设计属于？

A. Microservices Pattern — 每个 SKILL 是独立部署的服务
B. Facade Pattern — xiaomi-git 是 cr-engineer 对外暴露的统一接口
C. Delegation Pattern — cr-engineer 作为调度者，将子任务委托给更专注的 SKILL
D. Observer Pattern — cr-engineer 订阅 xiaomi-git 和 sonar-coverage-booster 的事件

**答案**：C

**解析**：cr-engineer 本身不实现 GitLab 操作和覆盖率补全，而是通过加载其他 SKILL 来"委托"这些子任务。这是松耦合的 Delegation Pattern。A 错误因为 SKILL 不是微服务；B 反了，cr-engineer 是入口而非 xiaomi-git 是入口；D 错误因为调用是同步的加载+执行，而非事件订阅。

---

### 5. Fix Mode 中，MiCR 门禁状态被解析为一个阻塞项清单，然后按优先级逐一修复。这一子流程最接近什么模式？

A. Iterator Pattern — 遍历阻塞项列表
B. Priority Queue + Reactor Pattern — 按优先级排序后响应式处理
C. Builder Pattern — 逐步构建修复报告
D. Command Pattern — 每个阻塞项封装为独立命令

**答案**：B

**解析**：Fix Mode 的核心逻辑是：解析 MiCR 事件（事件源）→ 生成阻塞项清单 → 按优先级排序 → 逐项触发对应修复动作（覆盖率不足 → sonar-coverage-booster，单测失败 → 本地修复）。这是典型的 Priority Queue + Reactor（事件响应）组合。A 太简单，忽略了优先级排序；C/D 不准确。

---

## 二、场景分析（5题）

### 6. 用户张三执行 `git config user.name` 返回 "zhangsan"。他提供了一个 MR 链接，MR 作者也是 "zhangsan"。用户说："帮我看看这个 MR"。系统应该走什么模式？

A. Fix Gate Mode — 因为 MR 作者是当前用户，默认走门禁修复
B. Review Mode — 因为用户说了 "看看"，隐含了审查意图
C. 先询问用户确认意图，再决定模式
D. 同时执行 Review 和 Fix，给出两份报告

**答案**：A

**解析**：根据设计规则，"MR 作者 = 当前用户 + 未明确说 review" → Fix Mode。"帮我看看"是模糊表述，不属于显式的 review 意图（如 "review"、"代码审查"、"CR"），所以默认走 Fix Mode。这也是为什么设计文档中提到需要在 Step 3 给出提示，让用户知道可以显式覆盖。

---

### 7. 用户李四提供了一个他人的 MR 链接，并说："这个 MR 的 MiCR 评论数不够，帮我补充几条有效评论"。系统应该怎么处理？

A. 走完整 Review Mode，对所有变更文件做深度审查
B. 走 Fix Gate Mode，因为涉及 MiCR 门禁
C. 走评论补量模式，快速定位高价值 review 点，补至 ≥5 条
D. 拒绝执行，因为这是别人的 MR，无权干预

**答案**：C

**解析**：用户明确说"补充评论" → 触发评论补量模式（QuickSupplementStrategy）。该模式不做全量深度审查，而是快速定位最有价值的评论点（Bug > 性能 > 设计），补足到 ≥5 条有效评论。A 过度执行了，B 错误因为 Fix Mode 只用于自己的 MR，D 错误因为帮别人补充 CR 评论是被允许的。

---

### 8. 用户王五是 MR 作者，提供了 MR 链接后说："帮我 review 一下这个 MR 的代码质量"。系统检测到 MiCR 门禁显示覆盖率只有 35%。系统应该？

A. 先做代码 Review，发布 CR 评论，然后再补覆盖率
B. 先补覆盖率（调用 sonar-coverage-booster），再做代码 Review
C. 只做代码 Review，覆盖率问题告知用户单独处理
D. 只补覆盖率，因为覆盖率是更紧急的阻塞项

**答案**：C

**解析**：用户明确说了 "review 代码质量" → 强制走 Review Mode。在 Review Mode 下，系统只做代码审查和评论发布，不执行门禁修复。覆盖率问题是 Fix Mode 的范畴。系统应在审查完成后告知用户："您的 MR 存在覆盖率不足的问题（35%），如需修复请单独触发门禁修复。" A 混淆了两种模式，B/D 违反了用户明确意图。

---

### 9. cr-engineer 在 Step 5（Review Pattern Loading）调用 GitLab API 拉取历史评论时，API 返回 500 错误。系统应该？

A. 中断流程，等待 API 恢复
B. 跳过 Pattern Loading，直接使用通用编码最佳实践进行审查
C. 重试 3 次，全部失败后中断
D. 使用 review_comments.md 中其他项目的评论作为替代

**答案**：B

**解析**：根据 Pipeline 的降级设计，Step 5（Pattern Loading）失败可以降级为纯通用最佳实践审查。这是"可降级"步骤的设计优势——不影响主干流程。A 过于严格，C 没有意义（因为缓存已有本项目的评论就跳过了，这里失败的是"无缓存 + 首次拉取失败"的场景），D 会引入不相关的团队风格。

---

### 10. 一个 MR 包含 80 个变更文件，diff 数据超过 25K token。cr-engineer 应该如何处理？

A. 用 Read 工具一次性读取全部 diff 文件
B. 只审查前 10 个文件，其余跳过
C. 启动多个并行 Agent，分段读取 diff（前半 + 后半），各 Agent 独立提取问题和摘要
D. 让用户手动指定要审查哪些文件

**答案**：C

**解析**：根据大 diff 处理策略，超过 25K token 的 diff 数据会被持久化到文件。此时应启动并行 Agent 分段读取，避免单个 Agent 上下文溢出。每个 Agent 负责提取变更文件路径、diff 摘要和代码问题，最后汇总。A 会导致 token 超限，B 可能遗漏关键问题，D 把负担转移给用户。

---

## 三、架构推理（4题）

### 11. 为什么 cr-engineer 选择 Pipeline 模式而不是 Event-Driven 模式？

A. Pipeline 比 Event-Driven 性能更好
B. 代码审查的步骤之间有严格的顺序依赖，且流程可线性描述，Pipeline 更直观
C. Event-Driven 模式需要消息队列，技术门槛高
D. SKILL 系统不支持 Event-Driven 模式

**答案**：B

**解析**：设计文档明确指出 Pipeline 适合"步骤间强依赖"的场景。CR 流程的每一步都需要上一步的产物（Step 4 需要 Step 3 确定的 project_id，Step 6 需要 Step 4 的 diff 和 Step 5 的 patterns），且整个流程只有 1 个分支点，非常适合 Pipeline。Event-Driven 更适合步骤间松散耦合、可并行执行的场景。

---

### 12. 为什么 cr-engineer 委托 xiaomi-git 处理 GitLab API，而不是自己直接调用？

A. GitLab API 调用需要 MCP 配置，cr-engineer 没有 MCP 权限
B. xiaomi-git 封装了 GitLab 操作的复杂细节（异常处理、大 diff 分段、diff_refs 获取、MiCR 门禁解析），cr-engineer 复用这些能力可以保持自身简洁
C. xiaomi-git 是官方 SKILL，cr-engineer 是第三方，必须通过委托调用
D. 直接调用 GitLab API 会暴露 Token

**答案**：B

**解析**：委托的核心原因是"单一职责"和"可复用性"。xiaomi-git 已经封装了 GitLab 操作的所有复杂细节（MR 状态检查、大 diff 分段策略、diff_refs 获取、MiCR 评论解析、异常处理），cr-engineer 无需重新实现。这体现了关注点分离的设计原则。A/C/D 皆非真正原因。

---

### 13. 为什么 review_comments.md 按项目分 section 而不是做全局索引？

A. 技术限制：Markdown 文件不支持全局索引
B. 不同项目的审查风格差异大，按项目分区可以保留各自风格特征，避免"平均化"
C. 减小文件体积，加快读取速度
D. 方便人工手动编辑

**答案**：B

**解析**：核心交易系统关注数据一致性和并发安全，管理后台关注操作便利性和用户体验，两者的 review 风格完全不同。按项目分区可以让 AI 在审查时准确匹配对应团队的风格特征，而不会被其他项目的评论"污染"。这也是为什么模式加载时读取全文（包含所有项目）——让 AI 理解"通用模式"的同时，也能识别"项目特有模式"。

---

### 14. Fix Mode 中，覆盖率补全通过调用 sonar-coverage-booster 实现，而不是内联到 cr-engineer。最主要的原因是什么？

A. sonar-coverage-booster 的代码太长，放不下
B. 覆盖率补全是"测试完备性"问题，代码审查是"代码质量"问题，概念上属于不同关注点；独立 SKILL 可以各自独立迭代，也可以被其他 SKILL 复用
C. sonar-coverage-booster 是用 Java 写的，cr-engineer 是 Python 写的
D. cr-engineer 的作者不会写覆盖率补全逻辑

**答案**：B

**解析**：这是关注点分离原则的经典应用。cr-engineer 的核心语义是"审查代码质量"，覆盖率补全是"测试完备性"的独立领域。将两者分离，sonar-coverage-booster 可以被 xiaomi-git 的门禁修复流程、CI pipeline、甚至手动触发等多种场景复用，而不需要 cr-engineer 的参与。同时，SonarQube API 变更只需要改一个 SKILL。

---

## 四、权衡评估（4题）

### 15. cr-engineer 的 Pipeline 没有 Checkpoint 机制（不像 ticket-troubleshoot）。如果在 Step 6（AI Code Review）完成后系统中断，会发生什么？

A. 系统自动恢复，从 Step 7 继续
B. 需要从 Step 1 重新执行整个流程
C. 系统检测到断开，保存当前状态到临时文件
D. Review 结果作为上下文保留在对话历史中（如果对话未丢失），否则丢失

**答案**：B/D（取决于中断类型）

**解析**：cr-engineer 没有显式的 Checkpoint 机制。如果是 LLM 对话中断但上下文可恢复（如 session 恢复），已产生的 review 结果仍在对话中。但如果是"从零开始新对话"的中断，之前的所有分析结果全部丢失，需要重新执行 Step 1-6。这是 Pipeline 刚性的一大代价，但也是因为 CR 流程比排障流程短得多（通常几分钟 vs 排障可能需要数小时）。

---

### 16. 如果 review_comments.md 中某个项目的评论 90% 来自 MiCR 机器人的自动化评论（"全部达标"、"变更摘要"等），这对 Review 质量有什么影响？

A. 没有影响，AI 可以自动过滤机器评论
B. 正面影响，MiCR 评论也是有效的审查依据
C. 负面影响，机器评论不包含真实的代码审查意见，会稀释人工 review 模式，降低模式归纳的准确性
D. 正面影响，机器评论提供了门禁标准化模板

**答案**：C

**解析**：review_comments.md 中混入大量 MiCR 机器人的自动化评论（如"全部达标"、"变更摘要"、门禁检查结果表格），这些内容不是真实的代码审查意见，不包含"这里可能 NPE"、"这个 SQL 缺少索引"等有价值的 review 模式。AI 在归纳模式时，会被这些噪声干扰，降低真实模式的信噪比。这是当前模式库的一个显著问题。

---

### 17. 以下哪种场景是 cr-engineer 的双模式设计无法优雅处理的？

A. 用户是自己的 MR，想先让系统 review 代码质量，再修复门禁
B. 用户是他人的 MR，MiCR 门禁评论数不足，用户要求补充
C. 用户提供了一个不存在的 MR 链接
D. 用户在自己的 MR 上，既想 review 代码质量，又想修复覆盖率

**答案**：A/D（单次调用无法同时执行两种模式）

**解析**：当前设计是"互斥的二选一"：Review Mode 和 Fix Mode 不能同时运行。如果用户想"先 review 再 fix"，需要两次独立调用（第一次说"review"走 Review Mode，第二次不说明确意图走 Fix Mode）。这是一次策略选择 vs 两阶段组合执行的限制。可以考虑未来增加"Full Mode"：先深度审查 → 输出 review 报告 → 再修复门禁阻塞项。

---

### 18. cr-engineer 强依赖小米 GitLab 平台（`git.n.xiaomi.com`）。如果要适配 GitHub，最困难的迁移点是什么？

A. GitLab API v4 改为 GitHub REST API v3 — API 路径和数据结构完全不同
B. 双模式中的 MiCR 门禁解析 — MiCR 是小米独有的门禁系统，GitHub 没有对应物
C. MR URL 解析正则需要适配
D. review_comments.md 的格式需要改变

**答案**：B

**解析**：GitLab API 和 GitHub API 之间的差异是可以通过 Adapter 层解决的（A/C 都是技术适配问题）。但 MiCR 门禁系统（覆盖率检查、评论数检查、单测通过率检查、Approve 检查）是小米 GitLab 特有的 CI/CD 质量管控体系，GitHub 的 Branch Protection Rules + Required Checks 语义完全不同。Fix Mode 的整个解析逻辑（从 MiCR Bot 评论中提取覆盖率、通过率等指标）需要完全重写。这是单平台依赖中最"硬"的部分。

---

## 五、集成设计（3题）

### 19. cr-engineer 委托给 xiaomi-git 时，传递的最小必要信息是什么？

A. 完整的 SKILL.md 上下文 + 用户对话历史
B. MR URL（从中可解析 project_id + IID）+ 用户意图标记（review / fix / supplement）
C. project_id + merge_request_iid + GITLAB_TOKEN
D. 只需要 MR URL，其他信息 xiaomi-git 自己获取

**答案**：B

**解析**：根据 Delegation Pattern 的"上下文传递最小化"原则，cr-engineer 需要传递：MR URL（供 xiaomi-git 解析 project_id 和 IID）+ 用户意图标记（让 xiaomi-git 知道走 Review 还是 Fix 或补量模式）。至于 GITLAB_TOKEN、项目路径 auto-detect 等，xiaomi-git 有自己的获取逻辑。A 传递过多，造成耦合；C 遗漏了意图标记；D 遗漏了意图，xiaomi-git 无法区分三种模式。

---

### 20. 如果 sonar-coverage-booster 不可用（SKILL 文件缺失或前置条件不满足），Fix Mode 中覆盖率不足的处理应该怎么降级？

A. 直接跳过覆盖率修复，告知用户手动处理
B. 尝试内联实现一个简化的覆盖率补全逻辑
C. 抛出错误，中断整个 Fix Mode
D. 将覆盖率不足标记为"待处理"，继续修复其他阻塞项，最后统一报告

**答案**：A/D

**解析**：松耦合设计允许被委托 SKILL 不可用时优雅降级。最佳实践是：将覆盖率不足标记为"需人工处理"，继续修复其他可自动处理的阻塞项（单测修复、评论补充），最后在报告中列出"自动修复结果"和"仍需人工处理项"。A 是简化版，D 是完整版（两者不矛盾）。B 违反了"不内联"原则，C 过于刚性。

---

### 21. 假设未来要新增一个 "自动修复代码 bug" 的能力（不只是评论建议，而是直接 push 修复代码到 MR 分支）。从集成设计的角度，最佳做法是什么？

A. 在 cr-engineer 的 Step 6 中增加修代码的逻辑
B. 在 xiaomi-git 中增加自动修复能力
C. 创建独立的 `auto-fix-bug` SKILL，cr-engineer 在 Review Mode 发现 bug 后委托给它
D. 创建独立的 `auto-fix-bug` SKILL，但只在 Fix Mode（自己的 MR）中触发

**答案**：C

**解析**：根据关注点分离原则，"审查"和"修复"是两个不同关注点。创建独立 SKILL 可以让修复能力被多种场景复用（cr-engineer 发现 bug 后触发、单独运行修复、CI 中自动修复）。D 的限制过于严格——对于别人的 MR，理论上有 "suggest edit" 和 "create MR to fix" 两种不直接 push 的修复方式。关键原则：新能力 = 新 SKILL，通过委托模式集成，而不是在现有 SKILL 中膨胀。
