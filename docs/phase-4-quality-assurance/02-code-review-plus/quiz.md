# code-review-plus — 测验文档

> 对应学习文档: `02-code-review-plus/learning.md`
>
> 测验类型: **设计理解**（架构推理 + 设计决策 + 对比分析）

---

## Part A: 双模型多模型审查模式 (30分)

### A1. 单选题（每题4分，共20分）

**1.** code-review-plus 的核心创新是什么？

A. 用 Claude 取代人工代码审查
B. 使用 Claude + Codex 两个独立 AI 模型并行审查，然后交叉对比差异
C. 用 Codex 审查代码，Claude 生成 HTML 报告
D. 自动修复代码中的所有问题

**答案**：B

**解析**：核心创新是"双模型并行审查 + 差异对比"。Claude 做一份审查，Codex 做另一份审查，然后对比两者发现。A 是传统单模型审查，C 混淆了角色（Claude 也做审查），D 是自动修复而非审查。

---

**2.** 以下关于多模型共识模式的描述，正确的是？

A. 两个模型都发现的问题可信度最低，因为可能是误报
B. 两个模型都发现的问题可信度最高，因为独立盲区不重叠
C. 两个模型给出相反结论时，自动选择 Claude 的结论
D. 差异性问题应该直接忽略，只关注共性问题

**答案**：B

**解析**：不同模型的训练数据、架构、推理偏好不同，它们同时发现同一问题的概率远高于单个模型的多次抽样。A 逻辑反了；C 无自动仲裁机制；D 差异性问题需人工判读，不应忽略。

---

**3.** 当 Claude 发现一个 Critical 问题而 Codex 没有发现时，差异对比报告应该如何处理？

A. 标记为"共性问题"，优先修复
B. 标记为"差异性问题"，标注"需人工判读"
C. 忽略该问题，因为只有单一模型发现
D. 重新运行 Codex 直到它发现该问题

**答案**：B

**解析**：只有单一模型发现的问题属于"差异性问题"，可信度低于共识但仍有价值，需标记"需人工判读"而非直接忽略。A 错误因为它不是共识；D 不合理，重复运行不可行。

---

**4.** SKILL.md 中为什么明确警告"不要调用 claude"？

A. Claude CLI 不支持非交互模式
B. 嵌套调用会导致死锁（调用自己）
C. Claude CLI 没有安装
D. Claude CLI 的审查质量比 Codex 差

**答案**：B

**解析**：Claude 自身就是当前运行的审查者，嵌套调用另一个 Claude CLI 会导致"用克劳德审查克劳德"的死锁循环。SKILL.md 写道：`不要调用 claude，因为你自己就是 Claude，嵌套调用会导致死锁`。

---

**5.** code-review-plus 中，审查结果的"共识等级"分为几级？

A. 两级：有问题 / 没问题
B. 三级：共识（高可信度）/ 差异（中可信度）/ 矛盾（需人裁决）
C. 四级：Critical / High / Medium / Low
D. 五级：P0 / P1 / P2 / P3 / P4

**答案**：B

**解析**：共识等级是三级：共识（两个模型都发现）、差异（仅一个发现）、矛盾（给出相反结论）。C 是问题的严重程度分类，D 是修复优先级分类，都不同于共识等级。

---

## Part B: 并行执行架构 (25分)

### B1. 单选题（每题4分，共12分）

**6.** review-runner.sh 中实现并行的核心机制是什么？

A. 使用 GNU Parallel 工具
B. 用 `&` 将任务放到后台子进程，用 `$!` 记录 PID，用 `wait` 等待完成
C. 使用 Python 的 asyncio 实现协程并行
D. 先跑 Codex，再跑 Claude，串行执行

**答案**：B

**解析**：`run_single_tool "$t" &` 是核心并行机制。`&` 让函数在子进程异步运行，`$!` 捕获 PID，`wait` 等待完成。A 未使用（GNU Parallel 非系统自带）；C 未使用 Python；D 是串行模式。

---

**7.** review-runner.sh 中 `run_single_tool` 函数的 watchdog 超时机制如何工作？

A. 使用系统内置的 `timeout` 命令
B. 启动审查进程 (pid) 的同时启动一个 sleep+kill 子进程 (watchdog)，sleep 到期后 kill
C. 在审查进程内部设置 `setTimeout` 定时器
D. 依赖 Codex CLI 自身的 `--timeout` 参数

**答案**：B

**解析**：watchdog 是一个独立子进程：`(sleep "$timeout_sec" && kill "$pid") &`。当 sleep 倒计时结束，它 kill 审查进程。这样兼容 macOS（无 `timeout` 命令）。A 不可用于 macOS；C 不适用于 shell；D Codex 无此参数。

---

**8.** review-runner.sh 和 cross-review.sh 的关系是什么？

A. review-runner.sh 是 cross-review.sh 的替代品
B. cross-review.sh 调用 review-runner.sh 做外部工具审查，自己负责流程图生成 + 差异对比 + HTML 生成
C. 两者互斥，只能选一个运行
D. review-runner.sh 负责 HTML 生成，cross-review.sh 负责审查

**答案**：B

**解析**：cross-review.sh 的第 [1/3] 步就是 `bash review-runner.sh "$OUTPUT_DIR" &`。review-runner.sh 只负责外部工具并行审查，cross-review.sh 在其基础上增加了流程图、差异对比、HTML 报告。

---

### B2. 简答题（13分）

**9.** 假设 Codex CLI 审查一个 5000 行的文件需要 200 秒，Claude 审查同一文件需要 80 秒。请计算：
(1) 串行执行（先 Claude 后 Codex，先 Codex 后 Claude 无区别）的总耗时？(3分)
(2) 并行执行的总耗时？(2分)
(3) 并行比串行快多少百分比？(2分)
(4) 如果 Claude 审查在 Codex 审查完成后才完成（即 Claude > Codex），并行模式的总耗时由哪个模型决定？这说明了并行模式的什么限制？(6分)

**参考答案**：

(1) 串行总耗时 = 200 + 80 = 280 秒

(2) 并行总耗时 = max(200, 80) = 200 秒

(3) 加速比 = (280 - 200) / 280 × 100% = 28.6%

(4) 并行模式的总耗时由**最慢的模型**决定（短板模型）。这说明了并行模式的限制：即使有 N 个并行任务，最终等待时间是 max(T1, T2, ..., Tn)，瓶颈在最慢的那个任务。所以并行模式下的加速收益取决于"是否存在明显的快慢比"。

---

## Part C: 架构设计推理 (25分)

### C1. 单选题（每题4分，共12分）

**10.** code-review-plus 选择 Shell 脚本而非 Python 做编排，最核心的原因是什么？

A. Shell 脚本更流行
B. Shell 脚本的 `&`/`$!`/`wait` 对于并行子进程管理的表达力远超 Python 的 subprocess
C. Python 不能在 macOS 上运行
D. Shell 脚本支持 HTML 生成

**答案**：B

**解析**：核心需求是"并行启动子进程 + 等待多个子进程完成"。Shell 的 `&`、`$!`、`wait` 是为此场景原生设计的，表达力极强且零依赖。Python 的 subprocess 也能做到，但 api 更复杂。C 错误（Python 跨平台）；D 错误（HTML 生成由 python3 完成）。

---

**11.** 为什么选择 HTML 报告而非 Markdown 或终端输出？

A. HTML 更炫酷
B. 双模型审查结果是多维数据集（模型来源、严重程度、共识程度、优先级），HTML 最适合展现多维数据
C. Markdown 不支持暗色主题
D. 终端输出无法展示代码

**答案**：B

**解析**：审查结果有四个维度 — 问题来源（哪个模型）、严重程度（C/H/M/L）、共识程度（共识/差异/矛盾）、修复优先级（P0-P3）。HTML 的 Tab 切换、颜色编码、统计卡片是表达多维数据的最佳方式。A 肤浅；C 错误；D 终端也能展示代码。

---

**12.** 为什么选择 Codex 作为外部审查工具，而不是其他 LLM？

A. Codex 完全免费
B. Codex CLI 有最成熟的非交互模式 (`codex exec`)，支持直接传递 prompt，且 Claude 不能嵌套调用自己
C. Codex 的代码审查质量远高于 Claude
D. Codex 是唯一支持 `--print` 模式的 CLI

**答案**：B

**解析**：Codex CLI 的 `exec` 子命令提供了成熟的非交互模式，`--skip-git-repo-check` 处理非 git 目录。Claude CLI 不能自我嵌套调用会死锁。C 无证据；D `--print` 是 Claude CLI 的特性。

---

### C2. 简答题（13分）

**13.** 代码审查结果的"适配器模式"在 code-review-plus 中是如何实现的？它和其他 System Design 中常见的适配器模式有什么不同？（13分）

**参考答案**：

**实现方式**：code-review-plus 使用 **prompt 前置约束** 而非 **输出后置解析**。review-runner.sh 在调用 Codex 前，在 prompt 中明确要求 Codex 按特定格式输出（代码概述 → 问题清单 → 优点 → 改进建议）。Codex 的输出直接就是标准化格式，无需 post-processing。

**与其他适配器模式的不同**：
- 传统适配器模式：接收原始输出 → 解析 → 转换 → 标准化格式（后置适配）
- code-review-plus 的模式：在 prompt 中注入格式约束 → AI 直接按标准格式输出（前置适配）

**优势**：省去了复杂的后置解析逻辑，利用 AI 自身的指令遵循能力来做格式适配。**风险**：如果 AI 没有严格遵循格式要求，输出可能不符合预期，但 SKILL.md 在 Step 3 会读取并正常处理失败情况。

---

## Part D: 设计权衡与对比 (20分)

### D1. 单选题（每题4分，共12分）

**14.** 以下哪项是 code-review-plus 最关键的"单点故障"风险？

A. Claude 服务器宕机
B. Codex CLI 未安装 — 系统优雅降级为单模型审查，丧失多模型共识
C. HTML 文件过大导致浏览器崩溃
D. 文件路径中包含空格

**答案**：B

**解析**：Codex CLI 是唯一的外部审查工具。如果未安装，review-runner.sh 会静默退出（`touch .done && exit 0`），审查退化为 Claude 单模型审查。虽然不阻塞流程，但失去了"多模型交叉验证"的核心价值，这是 code-review-plus 最核心的差异化能力。A 会导致任何 Claude 功能不可用，但不特定于本 Skill。

---

**15.** 对于以下场景，code-review-plus 和 cr-engineer 哪个更合适？

> "开发者刚完成一个 feature 分支的开发，准备推送到 GitLab 创建 Merge Request。想要在推送前对代码做一次审查。"

A. cr-engineer — 因为它可以自动创建 MR 并审查
B. code-review-plus — 因为它审查本地代码文件，适合 Git 推送前的预提交审查
C. 两个都不需要，直接推送代码即可
D. 两个都需要，先 cr-engineer 后 code-review-plus

**答案**：B

**解析**：code-review-plus 的审查对象是本地代码文件和 git diff 变更，适合开发者在推送/MR 创建前做本地预审查。cr-engineer 的审查对象是 GitLab 上已创建的 MR，用于 MR 门禁和团队 review。场景是"推送前"，所以 B 更合适。A 的逻辑反了（先推送到 GitLab 创建 MR 才能用 cr-engineer）。

---

**16.** code-review-plus 和 cr-engineer 的关系是？

A. 替代关系 — code-review-plus 可以完全取代 cr-engineer
B. 互补关系 — code-review-plus 做本地预审查，cr-engineer 做线上 MR 审查，覆盖开发全流程
C. 无关 — 两者功能完全不同
D. 冲突关系 — 不能同时使用

**答案**：B

**解析**：两者是开发流程中前后两个阶段的工具：
```
本地开发 → [code-review-plus] → 推送/创建 MR → [cr-engineer] → 合并
```
code-review-plus 覆盖本地审查阶段（多模型交叉审查 + HTML 报告），cr-engineer 覆盖 MR 阶段（GitLab 评论 + CI 门禁）。两者互补，共同覆盖代码质量保障的完整流程。

---

### D2. 简答题（8分）

**17.** 当前 code-review-plus 只支持 Codex 作为外部审查工具。如果要新增一个 Gemini CLI 作为第三个审查模型，需要在 review-runner.sh 的哪些位置做修改？请列出具体的修改点。（8分）

**参考答案**：

需要修改 3 个位置：

**1. 工具检测循环** (review-runner.sh:27-29):
```bash
# 原始
for t in codex; do
# 修改为
for t in codex gemini; do
```

**2. `run_single_tool` 函数的 switch/case 分支** (review-runner.sh:93-97):
```bash
# 新增
gemini)
  gemini run "$prompt" 2>/dev/null
  ;;
```

**3. prompt 适配**（可选但推荐）: 如果 Gemini CLI 的命令行参数格式与 Codex 不同（如不支持 `exec`），需要在 prompt 传递方式上做适配。另外在 `cross-review.sh` 的 `LABEL_*` 和 `COLOR_*` 字典中也要新增 Gemini 的标签和颜色:
```bash
LABEL_gemini="Gemini"; COLOR_gemini="33"
```

---

## 评分标准

| 等级 | 分数 | 要求 |
|------|------|------|
| S | 90+ | 深入理解多模型共识 + 并行架构 + 设计权衡 + 能设计扩展方案 |
| A | 75-89 | 理解核心流程 + 架构推理正确 + 对比分析合理 |
| B | 60-74 | 基本理解双模型审查 + 知道主要设计决策 |
| C | <60 | 需要回顾学习文档 |

---

## 参考答案速查表

| 题号 | 题型 | 答案 |
|------|------|------|
| 1 | 单选 | B |
| 2 | 单选 | B |
| 3 | 单选 | B |
| 4 | 单选 | B |
| 5 | 单选 | B |
| 6 | 单选 | B |
| 7 | 单选 | B |
| 8 | 单选 | B |
| 9 | 简答 | 见解析 |
| 10 | 单选 | B |
| 11 | 单选 | B |
| 12 | 单选 | B |
| 13 | 简答 | 见解析 |
| 14 | 单选 | B |
| 15 | 单选 | B |
| 16 | 单选 | B |
| 17 | 简答 | 见解析 |

(End of file - total 269 lines)
