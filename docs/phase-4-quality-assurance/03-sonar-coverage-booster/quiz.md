# sonar-coverage-booster — 测验文档

> 对应学习文档: `03-sonar-coverage-booster/learning.md`
>
> 测验类型: **设计理解**（管线设计 + 迭代机制 + 架构决策 + 权衡评估 + 集成设计）

---

## Part 1: 修复管线设计（5 题，每题 5 分）

### 1. sonar-coverage-booster 的 7 步管线中，哪个步骤是管线启动的必要前提（失败则管线无法启动）？

A. Step 2：找出未覆盖代码行
B. Step 1：确认 SonarQube 信息（tokens.json 加载）
C. Step 5：编写测试代码
D. Step 6：本地运行测试验证

**答案**：B

**解析**：Step 1 中的 tokens.json 加载是管线初始化的入口。如果 tokens.json 不存在或格式不正确，SonarQube API 认证将失败，后续所有依赖 API 的步骤（Step 2、Step 7 轮询）都无法执行。Step 2 失败可以通过其他方式（如手动列出变更文件）降级，但 Step 1 的认证信息无法替代。

---

### 2. 关于 Step 5（编写测试代码）中的测试类模板，以下哪项说法是正确的？

A. 使用 `@SpringBootTest` 以确保 Spring 容器的行为被正确验证
B. 使用 `@ExtendWith(MockitoExtension.class)` 以在毫秒级完成测试启动
C. 手动构造被测对象和 mock 对象以获得最大灵活性
D. 每个测试方法使用独立的 `@BeforeEach` 设置以提升隔离性

**答案**：B

**解析**：SKILL 明确使用 `@ExtendWith(MockitoExtension.class)` 而非 `@SpringBootTest`，因为覆盖率补全的核心需求是"让代码行被执行到"而非"验证 Spring 集成行为"。不启动 Spring 容器可将测试启动时间从秒级降至毫秒级。A 错误（不使用 SpringBootTest），C 错误（使用 `@InjectMocks` + `@Mock` 自动注入），D 并非模板硬性要求。

---

### 3. Step 6（本地运行测试验证）为什么被设计为"全部通过后才提交"的硬性门禁？

A. 为了节省 CI 资源，避免推送有编译/断言错误的测试
B. 为了让开发者有机会手动 review 生成的测试代码
C. 因为 mvn test 需要在本地环境运行，CI 环境没有 Maven
D. 因为 SonarQube 要求测试必须先本地运行才能触发扫描

**答案**：A

**解析**：如果推送了带编译错误的测试代码，CI 流水线会直接失败；如果推送了断言错误的测试代码，会阻塞 PR 的所有其他检查。本地验证是最短的反馈循环（秒级），而 CI 反馈需要分钟级。B 不是 Step 6 的设计目的（代码理解在 Step 3-4），C 不成立（CI 环境中通常有 Maven），D 不成立（SonarQube 不要求本地运行才能扫描）。

---

### 4. Step 7 中设计了 `git commit --allow-empty` 空提交机制，其主要目的是什么？

A. 重置 Git 提交历史，使测试文件和业务代码合并为一个 commit
B. 当只推送测试文件而不变更业务代码时，CI 可能不会触发 SonarQube 扫描，空提交强制触发
C. 绕过 Git 分支保护规则，允许直接推送到受保护分支
D. 在提交信息中附加覆盖率报告，便于团队成员查看

**答案**：B

**解析**：CI 流水线配置通常只在有代码变更时触发 Sonar 扫描。如果只推送了测试文件（业务代码无变更），某些流水线配置可能不会触发扫描。此时使用 `git commit --allow-empty` 创建空提交强制触发。A 错误（不改变历史），C 错误（不绕过保护规则），D 错误（覆盖率报告不写到提交信息中）。

---

### 5. 以下哪项不是 Step 5 的硬性编码规范？

A. 禁止 `@DisplayName` 使用中文弯引号 `"` `"`
B. 禁止直接测试私有方法
C. 禁止在测试方法中使用 `Thread.sleep()` 等待异步操作
D. 禁止使用 MyBatis Plus

**答案**：C

**解析**：A、B、D 都是 SKILL.md 中明确列出的硬性规范。C（禁止 `Thread.sleep()`）不是该 SKILL 的规范。虽然在实际编码中不推荐 `Thread.sleep()`，但 SKILL 没有将其列入硬性约束。

---

## Part 2: 迭代修复循环（4 题，每题 5 分）

### 6. sonar-coverage-booster 采用迭代修复而非一次性生成所有测试，最根本的原因是什么？

A. LLM 的上下文窗口有限，无法一次性分析所有未覆盖文件
B. 每轮 SonarQube 重扫后的反馈可以纠正上一轮的覆盖策略偏差
C. 一次性生成会导致测试文件过大，CI 编译时间超时
D. 迭代过程可以在每轮之间让人工介入调整测试策略

**答案**：B

**解析**：迭代的核心价值是反馈驱动。第一轮生成的测试可能"形式上覆盖了行但实际未执行到"，SonarQube 重新扫描后的最新 `new_uncovered_lines` 数据可以揭示这种偏差，让下一轮调整策略。A 部分成立但不是根本原因，C 不成立（测试文件大小通常不是瓶颈），D 不是设计意图（目标是全自动）。

---

### 7. 迭代修复循环的终止条件不包括以下哪项？

A. `new_line_coverage ≥ 60%`（成功达标）
B. 无新的可测试公共方法（饱和终止）
C. SonarQube API 返回 429 Too Many Requests（限流终止）
D. 达到最大迭代次数（通常隐含 3 轮）

**答案**：C

**解析**：A、B、D 都是正常的终止条件。C（API 限流）是错误状态而非正常的终止条件。遇到 429 限流应该等待后重试，而不是终止循环。如果 API 不可达导致迭代终止，应标记为失败而非正常结束。

---

### 8. 在迭代修复中，第二轮分析未覆盖代码时应该如何处理第一轮已经生成测试的方法？

A. 删除第一轮的所有测试，重新生成更高质量的测试
B. 修改第一轮测试的断言，增加更多边界条件
C. 跳过已生成测试的方法，聚焦新暴露的未覆盖代码
D. 在已有测试文件中追加 `@RepeatedTest` 注解以增加执行次数

**答案**：C

**解析**：迭代的核心策略是"增量覆盖"：每轮只关注 SonarQube 重新扫描后发现的尚未被覆盖的代码行。已生成测试的方法如果仍未被覆盖，说明可能是 SonarQube 尚未完成扫描或测试实际未执行到目标行，此时应分析根因而非盲目重写。A 违反"不得修改已有测试"的规范，B 同样涉及修改已有用例，D 无意义。

---

### 9. 假设一个 PR 新增了 200 行可覆盖代码（`new_lines_to_cover = 200`），第一轮测试覆盖了 100 行（`new_uncovered_lines = 100`），覆盖率 50%。第二轮目标是将覆盖率从 50% 提到 60%，还需要覆盖多少行？

A. 10 行
B. 20 行
C. 60 行
D. 120 行

**答案**：B

**解析**：达到 60% 需要总覆盖行数 ≥ 200 × 0.6 = 120 行。当前已覆盖 100 行，还需要覆盖 120 - 100 = 20 行。这是一个简单的数学问题，但意在考察对覆盖率计算公式 `(1 - new_uncovered / new_lines_to_cover) × 100%` 的理解。

---

## Part 3: 架构推理（4 题，每题 5 分）

### 10. 为什么测试类模板选择 `@ExtendWith(MockitoExtension.class)` 而不是 `@SpringBootTest`？

A. 覆盖率补全的核心目标是"行覆盖"而非"集成验证"，不需要 Spring 容器
B. `@SpringBootTest` 是 JUnit4 的注解，JUnit5 不支持
C. Mockito 比 Spring Test 更擅长模拟外部 HTTP 调用
D. intl-retail 项目禁止使用 `@SpringBootTest` 注解

**答案**：A

**解析**：覆盖率补全的核心目标是让 SonarQube 标记的未覆盖行被执行到，不需要验证 Spring 的 AOP、事务管理、自动装配等集成行为。不启动容器意味着测试启动时间从 5-15 秒降至 < 1 秒，对迭代修复场景（多轮 CI）的时间节省尤为显著。B 不成立（JUnit5 也支持 `@SpringBootTest`），C 偏离核心目的，D 不是项目规范。

---

### 11. sonar-coverage-booster 与 cr-engineer 的紧密耦合设计中，以下哪项最能体现这种耦合的实际价值？

A. cr-engineer 可以自动检测 Quality Gate 失败并无需用户干预即委托修复
B. sonar-coverage-booster 可以复用 cr-engineer 的 SonarQube 配置，减少重复配置
C. 两个 Skill 共享同一个 GitLab MCP 连接，节省资源
D. cr-engineer 失败时 sonar-coverage-booster 可以作为降级替代

**答案**：A

**解析**：紧密耦合的核心价值在于自动化调度。cr-engineer 已经承担了"MR 门禁监控"的职责，检测到覆盖率不足后自动委托 sonar-coverage-booster 执行修复，用户无需手动判断"为什么 MR 被 blocked"并手动调用修复 Skill。B/C 是附带收益但不是核心价值，D 不正确（两者职责不同，不能互相替代）。

---

### 12. 为什么生成的测试代码必须 commit 到业务代码所在的同一个 PR 分支，而不是单独创建一个 `test/xxx` 分支？

A. 方便在 GitLab 上对比业务代码和测试代码的 diff
B. SonarQube 的 PR 扫描只分析 PR 分支的代码，独立分支的测试不在扫描范围
C. intl-retail 项目的分支保护规则禁止创建 `test/` 前缀的分支
D. 同一分支可以让 cr-engineer 更方便地 review 测试代码

**答案**：B

**解析**：SonarQube 在进行 PR 扫描时，分析范围是 PR 分支（source branch）相对于目标分支（target branch）的变更。如果测试代码在独立分支，SonarQube 不会将其纳入 PR 的扫描范围，覆盖率计算仍然只基于业务代码，无法达到提升覆盖率的目的。A/C/D 都不是主要的技术原因。

---

### 13. tokens.json 的自动探测采用多路径优先级策略（~/.claude → ~/.agents → $(pwd)），这个设计主要解决什么问题？

A. 防止不同 AI 工具运行同一个 SKILL 时产生配置冲突
B. 确保 SKILL 在不同 AI 工具安装到不同路径时仍能正确加载配置
C. 提供配置降级机制，当高优先级路径的配置损坏时自动回退
D. 允许多个 tokens.json 合并，组合不同来源的配置

**答案**：B

**解析**：不同 AI 工具（Claude Code、OpenCode 等）将 SKILL 安装到不同的目录（`.claude/skills/` vs `.agents/skills/` 等）。自动探测机制让 SKILL 无需硬编码路径，在所有工具下都能找到配置文件。A 的"冲突"不是主要关注点（同一台机器通常只用一种工具），C 的"降级"是附带收益，D 的"合并"不是设计意图（优先级机制明确只加载第一个找到的）。

---

## Part 4: 设计权衡评估（4 题，每题 5 分）

### 14. sonar-coverage-booster 生成的测试以"行覆盖"为目标，以下哪项是这种策略最根本的局限性？

A. 生成的测试代码可能不符合团队的代码风格规范
B. 高覆盖率不等于高质量的测试（可能存在伪覆盖：执行了行但未做有意义断言）
C. 测试运行速度比人工编写的测试慢
D. 自动生成的测试数量过多，导致 CI 队列拥堵

**答案**：B

**解析**：覆盖率指标最根本的局限性是"覆盖≠正确"。"伪覆盖"（如 `assertNotNull(result)` 让行变绿但未验证业务正确性）可以让覆盖率达标但测试价值极低。SKILL 通过内置典型测试场景模式和 AAA 结构来部分缓解，但无法从根本上解决。A 不是根本问题（生成代码可以规范），C/D 不成立（Mockito 单元测试运行很快，测试数量通常在合理范围）。

---

### 15. 关于迭代修复的 CI 时间成本，以下哪种评估最准确？

A. 迭代修复的 CI 时间与一次性生成相同，因为总测试量相同
B. 迭代修复必然比一次性生成慢，因为需要多次 CI 运行
C. 迭代修复的 CI 时间可能更长，但通过逐步收敛减少了不必要的测试生成，在 Maven 编译和测试执行层面可能更快
D. 迭代修复不需要 CI，只需要本地 mvn test，因此没有 CI 时间成本

**答案**：C

**解析**：迭代修复需要 N 次 CI 运行（每次 5-15 分钟），总 CI 时间确实可能更长。但好处是每轮只生成最必要的测试，减少了 Maven 的编译和测试执行量。且反馈驱动的策略能确保每轮都在正确的方向上，避免一次性生成大量无用测试后又需要全部重写。D 错误（Step 7 明确需要 CI + SonarQube 扫描）。

---

### 16. 以下哪种情况最能说明 SonarQube API 依赖性对 SKILL 的最严重风险？

A. SonarQube 升级后 API 响应格式中多了一些无关字段
B. 公司的 SonarQube 实例正在进行年度维护，预计 2 小时后恢复
C. SonarQube 产品线被公司弃用，迁需到新的代码质量平台（如 Codecov），API 完全不同
D. 某次网络波动导致 API 调用超时，重试后恢复正常

**答案**：C

**解析**：C 是架构级风险 — 整个数据源被替换，所有 API 端点、认证方式、响应格式、指标名称都可能改变，SKILL 的 Step 1、2、7 都需要重写。A 的"多余字段"通常向后兼容不影响解析，B 的"维护窗口"是临时中断，D 的"网络波动"属于常规异常处理范畴。C 的"平台迁移"意味着 SKILL 的核心数据依赖被切断。

---

### 17. 以下哪项不是 sonar-coverage-booster 的设计局限？

A. 仅支持 Java/Spring Boot 项目
B. 仅关注 `new_line_coverage`（增量覆盖率），不处理整体覆盖率
C. 无法处理需要数据库连接的集成测试
D. 要求开发者手动指定需要测试的类和方法

**答案**：D

**解析**：sonar-coverage-booster 通过 SonarQube API 自动发现未覆盖代码（Step 2），并通过源码分析自动识别可测方法（Step 3），不需要开发者手动指定。A（仅 Java/Spring Boot）、B（仅增量覆盖率）、C（不使用 Spring 容器，不启动数据库）都是真实的设计局限。

---

## Part 5: 集成设计（3 题，每题 5 分）

### 18. 在 cr-engineer → sonar-coverage-booster 的委托关系中，cr-engineer 扮演的角色最接近以下哪种设计模式？

A. Factory 模式 — 根据不同阻塞原因创建不同的修复 Skill 实例
B. Strategy 模式 — 在运行时选择不同的覆盖率提升策略
C. Chain of Responsibility 模式 — 将检测到的问题沿责任链传递直到被处理
D. Mediator 模式 — 作为中心协调者，将 Quality Gate 失败事件路由到对应的修复 Skill

**答案**：D

**解析**：cr-engineer 是最接近 Mediator（中介者）模式的角色。它监控 Quality Gate 状态，检测到不同的阻塞原因（覆盖率不足、代码重复、安全漏洞等），然后将修复任务路由到对应的专门 Skill（sonar-coverage-booster、其他修复 Skill）。A 的 Factory 只负责创建，B 的 Strategy 侧重同一问题的不同解法，C 的 Chain of Responsibility 是线性传递，都不如 Mediator 精准描述这种"检测+分派"的中心化协调关系。

---

### 19. 如果要将 sonar-coverage-booster 从与 cr-engineer 的紧密耦合中解耦为独立可运行的 Skill，最需要增加的机制是什么？

A. 增加对 GitHub PR 的支持，扩大使用场景
B. 增加用户输入接口，让用户手动提供 PR 编号、分支名等信息
C. 增加对 Python/Go 等多语言的支持
D. 增加自动 merge 功能，覆盖率达标后自动合并 PR

**答案**：B

**解析**：紧密耦合的核心价值是 cr-engineer 自动提供上下文（PR 编号、分支名、Quality Gate 状态）。解耦后，这些信息需要由用户手动输入 — 即增加一个"触发入口"，让用户告知"哪个 PR 的覆盖率不足"。A（GitHub 支持）、C（多语言支持）、D（自动 merge）是其他维度的增强，但不解决"如何触发 Skill 运行"的根本问题。

---

### 20. cr-engineer 与 sonar-coverage-booster 的紧密耦合设计中，以下哪项是最主要的缺点？

A. sonar-coverage-booster 无法被其他 Skill 复用
B. cr-engineer 出现 bug 时会影响 sonar-coverage-booster 的正常运行
C. 两个 SKILL 共享同一个 SonarQube token，存在安全风险
D. cr-engineer 的变更可能导致 sonar-coverage-booster 的调用协议变化，增加了维护耦合

**答案**：D

**解析**：紧密耦合意味着两个 SKILL 之间存在隐式的"调用协议"（cr-engineer 传递什么信息、期望什么返回值）。当 cr-engineer 的输出格式或调用约定变化时，sonar-coverage-booster 可能需要同步修改。A 不完全正确（sonar-coverage-booster 的测试生成核心逻辑是独立的），B 是单向依赖的自然结果而非紧密耦合特有的缺点，C 的"共享 token"不是紧密耦合带来的（独立运行时也需要 token）。

---

## 评分标准

| 等级 | 分数 | 要求 |
|:---|:---|:---|
| S | 90-100 | 深入理解管线设计 + 迭代机制 + 架构决策 + 能评估权衡 |
| A | 75-89 | 全面理解管线设计 + 迭代机制 + 架构决策 |
| B | 60-74 | 基本理解管线设计和关键决策 |
| C | <60 | 需要回顾学习文档，重点关注 Part 3-5 |
