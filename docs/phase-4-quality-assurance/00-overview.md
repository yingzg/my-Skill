# Phase 4: 质量保障 — 学习总览

> 对应 [skill-learning-roadmap.md](../skill-learning-roadmap.md) Phase 4 章节
>
> 📅 生成时间: 2026-07-15

---

## 🎯 学习目标

掌握 4 个代码质量保障 Skill 的核心设计思想和可复制模式，理解如何在代码合入前建立自动化质量关卡，从"被动排障"转向"主动防御"。

---

## 🧭 Phase 4 在路线图中的地位

```
Phase 1: 元知识（造 skill 的工具）          ← 基础层
Phase 2: 核心工作流（MR/双Agent/连续执行）   ← 流程层
Phase 3: 排障诊断（线上问题定位）            ← 被动响应
Phase 4: 质量保障（合入前审查）              ← 主动防御  ← 你在这
Phase 5: Git 高级操作（冲突/worktree）       ← 工程效率
Phase 6: 专项能力（SDF/slides/登录/同步）    ← 场景层
Phase 7: 元能力（造 skill 的 skill）         ← 元能力层
```

**Phase 3 → Phase 4 的关键转变**：Phase 3 回答的是"线上出问题了怎么办"（事后修复），Phase 4 回答的是"怎么让问题根本合不进来"（事前拦截）。这是从**运维思维**到**工程思维**的跃迁。

---

## 📊 四技能对比矩阵

| 维度 | cr-engineer | code-review-plus | sonar-coverage-booster | sql-review |
|------|------------|------------------|----------------------|------------|
| **SKILL.md 行数** | 198 | 209 | 332 | 294 |
| **脚本行数** | 215 (3 Python) | 693 (4 bash + 1 ps1) | 0 (纯 Prompt 驱动) | 6,875 (10 Python) |
| **难度** | ⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ |
| **触发机制** | MR URL 正则匹配 + 关键词（review mr / 代码审查 / CR） | 关键词（code review / 交叉审查 / 帮我review）+ 文件路径/模块名 | SonarQube API 状态检测 + 关键词（覆盖率不足 / quality gate 未通过） | 关键词（sql review / 慢查询 / SQL 性能）+ Git branch diff |
| **输入** | GitLab MR 链接 | 代码文件路径 或 git diff | PR Key + Branch + tokens.json | 当前分支 vs master 的 Git diff |
| **数据源** | GitLab API (MR diff + 历史评论) | 本地源码 + Codex CLI 输出 | SonarQube REST API + 本地源码 | Git diff → MyBatis XML / Annotation / QueryWrapper |
| **核心模式** | Pipeline (8步) + Reference-based Review | Multi-Model Parallel + Diff Reconciliation | Repair Pipeline (7步) + Threshold Gating | Hybrid 3-Phase (Local Rules + LLM Analysis) |
| **自动化程度** | 半自动 (人工确认后发布评论) | 全自动 (并行执行 + 自动汇总) | 半自动 (人工确认测试后推送) | 全自动 (Step 0→4 连续执行) |
| **集成深度** | **深度集成** (调用 xiaomi-git 解析项目、调用 sonar-coverage-booster 补覆盖率) | **独立运行** (仅依赖 Codex CLI) | **被调用方** (cr-engineer/xiaomi-git 在覆盖率不足时触发) | **独立运行** (自包含升级机制) |
| **外部系统依赖** | GitLab (API + MCP) | Codex CLI (npm 全局安装) | SonarQube (REST API) + Maven + GitLab MCP | MySQL (pymysql 直连, 可选) + KeyCenter (自动解密, 可选) |
| **设计模式** | Pipeline + Strategy (ownership detection) | Composite (多模型投票) + Observer (并行回调) | Pipeline + Iterator (覆盖率阈值迭代) | Strategy (3-Phase 降级) + Template Method (local_review / ci_review) |
| **输出形式** | Markdown 报告 + GitLab MR 行内评论 | HTML 可视化报告 (暗色主题 + Tab 面板) | 覆盖率 before/after 对比 + 测试文件 | Markdown 表格 + 最差路径 SQL 导出 + IDEA 集成 |
| **独特设计** | 历史评论模式库 / MR 所有权分流 | 多模型并行 + 共性/差异交叉对比 | 迭代验证闭环 / 空 commit 触发 CI | 4-Step 严格顺序约束 / 自我升级机制 / 确定性基线 + LLM 校正双轨制 |

---

## 🏗️ 贯穿四个 Skill 的三大核心设计模式

### 1. Pipeline 模式（流水线编排）

`cr-engineer` (8步) / `sonar-coverage-booster` (7步) / `sql-review` (5步)

```text
输入 → Step 1 → Step 2 → ... → Step N → 结构化输出
         ↓           ↓           ↓
      Checkpoint 2  Checkpoint 3  Checkpoint N
```

**本 Phase 的关键设计决策**：

| 对比维度 | cr-engineer | sonar-coverage-booster | sql-review |
|---------|------------|----------------------|------------|
| **步骤间可跳跃** | 否，严格顺序 | 否，但 Step 5→6 可循环迭代 | 否，"不得跳过/合并/自行增加步骤" |
| **失败处理** | Step 2 无 Token → 终止索要 | Step 7 未达标 → 回到 Step 2 重试 | DB 预查失败 → 降级为无 EXPLAIN 模式 |
| **人机交互点** | Step 8 (询问是否发布评论) | Step 6 (本地 mvn test 验证) / Step 7 (推送前确认) | 无 (全自动执行) |
| **步骤间数据传递** | 通过环境变量和临时文件 | 通过 curl 输出 + Python JSON 解析 | 通过 `.sql-review/` 目录下 JSON 文件 + `print` 输出管道 |

**与 Phase 3 的 Pipeline 对比**：

Phase 3 的 `ticket-troubleshoot-v3` 的 Pipeline 侧重**可恢复性**（Checkpoint + 续跑协议），Phase 4 的 Pipeline 侧重**质量控制闭环**——每一步的输出必须满足质量标准，否则无法进入下一步。这是一种"质量门控流水线"（Quality-Gated Pipeline）。

### 2. Multi-Model Parallel Review 模式（多模型并行审查）

`code-review-plus` 独有

```text
                    ┌─────────────────┐
                    │  确定审查目标     │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              ↓              ↓              ↓
        ┌───────────┐ ┌───────────┐ ┌───────────┐
        │  Codex    │ │  Claude   │ │  (可扩展  │
        │  (后台)    │ │  (前台)    │ │   其他模型) │
        └─────┬─────┘ └─────┬─────┘ └─────┬─────┘
              │              │              │
              └──────────────┼──────────────┘
                             ↓
                    ┌─────────────────┐
                    │  交叉对比 + 汇总  │
                    └────────┬────────┘
                             ↓
                    ┌─────────────────┐
                    │  HTML 可视化报告  │
                    └─────────────────┘
```

**核心设计思想**：

- **时间维度并行**：外部 CLI 后台异步启动，Claude 在前台同步审查——两者互不阻塞，总耗时 ≈ max(Claude耗时, Codex耗时)
- **信度维度聚合**：通过"共性问题"（两个模型都发现）和"差异性问题"（仅一个模型发现）区分信度等级，解决单一模型审查的盲区问题
- **扩展性**：并行架构天然支持增加第三个、第四个审查模型，只需在 Step 1 中增加后台启动命令

**关键实现细节**：

```
review-runner.sh (并行调度层)
  ├── 后台启动 Codex CLI → 输出到 codex-review.md
  ├── 写入 .done 标记文件
  └── 超时 180s → 写入失败标记

cross-review.sh (终端编排层)
  ├── 调用 review-runner.sh
  ├── 收集所有审查输出
  ├── 交叉对比分析
  └── 生成 report.html
```

这个模式的核心创新不是"用多个模型审查"，而是**通过并发调度机制将多模型审查的总耗时控制在单模型级别**。

### 3. Hybrid Local + LLM Analysis 模式（本地规则 + AI 分析双轨制）

`sql-review` 独有

```text
                    ┌──────────────────────┐
                    │  Step 1: Git Diff     │
                    │  提取 SQL 变更         │
                    └──────────┬───────────┘
                               ↓
                    ┌──────────────────────┐
                    │  Step 2: DB 预查      │
                    │  DDL + 行数 (可选)     │
                    └──────────┬───────────┘
                               ↓
              ┌────────────────┼────────────────┐
              ↓                ↓                ↓
        ┌───────────┐  ┌───────────┐  ┌───────────┐
        │ Phase 0   │  │ Phase 1   │  │ EXPLAIN   │
        │ LLM 代码   │  │ 确定性基线  │  │ 实际执行   │
        │ 精选 (可选) │  │ + LLM 校正 │  │ (可选)    │
        └─────┬─────┘  └─────┬─────┘  └─────┬─────┘
              ↓                ↓              ↓
              └────────────────┼──────────────┘
                               ↓
                    ┌──────────────────────┐
                    │  Phase 2: LLM 最终    │
                    │  风险评估 (含硬编码规则) │
                    └──────────────────────┘
```

**核心设计思想**：

- **确定性层先行**（Phase 1 的 `extract_static_worst_case` / `extract_update_worst_case` / `extract_select_worst_case_multi_chain`）：通过硬编码规则对 SQL 进行"悲观清洗"——将所有条件视为可选，生成最坏情况 SQL。这一层完全不需要 LLM，结果可复现、可审计。
- **LLM 层校正**：在确定性基线之上，由 LLM 根据实际代码逻辑"加回必传条件"，修正过度悲观的评估。LLM 失败时自动降级为基础基线——保证永不阻塞。
- **多链去重**：`dedup_phase1_chains` 将代码片段相同的调用链合并，减少 LLM prompt 规模，这是大规模项目中的关键性能优化。

**这条模式的核心价值**：它解决了"纯 LLM 审查不稳定"和"纯规则审查覆盖不全"的矛盾——硬编码规则保证最低质量标准，LLM 提供语义理解增强，两者互补而非竞争。

---

## 🥇 推荐学习顺序

```
4.1 cr-engineer               ──→  最"规则"，建立 Pipeline 审查思维
          ↓
4.2 code-review-plus          ──→  引入"多模型并行"概念，打破单一视角局限
          ↓
4.3 sonar-coverage-booster    ──→  理解"数据驱动的质量门禁"和迭代闭环
          ↓
4.4 sql-review                ──→  最复杂，融合 Pipeline + Hybrid 双轨制
```

### 理由详解

**4.1 cr-engineer** — 入门最佳选择

这是 Phase 4 的"标准答案"。它的 8 步 Pipeline 是最经典的审查流程：获取上下文 → 获取代码 → 分析 → 输出 → 确认发布。每一步都清晰、独立、可替换。核心创新——**历史评论模式库**（`reference/review_comments.md`）——让审查从"通用最佳实践"升级为"团队定制审查"，这个思想在后续其他 Skill 中反复出现。

学完这个，你应该能回答：
- 如何设计一个可配置上下文的审查 Pipeline？
- 如何区分"原子执行"步骤和"可跳过"步骤？
- 如何设计人机交互的确认点？

**4.2 code-review-plus** — 引入并行思维

如果说 cr-engineer 教你"如何深度审查"，code-review-plus 教你"如何广度审查"。它的多模型并行架构让你看到：审查质量不仅取决于单个模型的分析深度，更可以通过交叉验证提升信度。5 步并行流水线（macOS/Linux 一个分支，Windows 另一个分支）也展示了 Skill 如何处理多平台兼容。

学完这个，你应该能回答：
- 如何设计异步并行的后台任务调度？
- 如何用标记文件（`.done`）实现进程间通信？
- 如何用"共性/差异性"分类提升审查报告的信度？

**4.3 sonar-coverage-booster** — 理解质量门禁的闭环

这是 Phase 4 的"数据驱动"代表。它不依赖 LLM 审查，而是直接对接 SonarQube 的客观指标。7 步 Pipeline 的关键是**迭代验证闭环**——Step 7 达标才结束，不达标就回到 Step 2 重新分析未覆盖行。这个"检查→修复→验证"的循环是工程质量的本质。

学完这个，你应该能回答：
- 如何将外部系统的数据指标（如覆盖率）转化为 Skill 的执行决策？
- 如何设计"目标-检测-修复-验证"的闭环循环？
- 如何在 Skill 中嵌入编码规范约束（如禁止 `@DisplayName` 使用弯引号）？

**4.4 sql-review** — 融会贯通

这是 Phase 4 的集大成者。它融合了 cr-engineer 的 Pipeline 编排、code-review-plus 的分阶段分析思想、sonar-coverage-booster 的数据驱动验证，再加上自己的 Hybrid 双轨制创新。6,875 行 Python 脚本、12 个文件、4-Step 严格顺序约束、自我升级机制——这是整个学习路线中代码量最大的 Skill。

学完这个，你应该能回答：
- 如何设计"确定性规则 + LLM 校正"的双轨审查架构？
- 如何在不同数据源（MyBatis XML / Annotation / QueryWrapper）间统一 SQL 提取协议？
- 如何通过 `VERSION` 文件和 `install.py` 实现 Skill 的自动升级？

---

## 🔄 Phase 3 → Phase 4 演化分析

### 从"事后诊断"到"事前拦截"

| 对比维度 | Phase 3 (排障诊断) | Phase 4 (质量保障) |
|---------|------------------|-------------------|
| **时间点** | 代码上线后 | 代码合入前 |
| **触发方** | 用户报告异常 / 监控告警 | 开发者提交 MR / 合入分支 |
| **输入质量** | 不确定（可能描述不准、ID错误） | 相对确定（代码 diff、覆盖率数据） |
| **输出受众** | 开发者 + SRE（修复建议） | 开发者本人（修改代码） |
| **反馈循环** | 长（发现 → 修复 → 上线 → 验证） | 短（审查 → 修改 → 重新扫描） |
| **容错要求** | 低（给错建议可能导致新问题） | 中（误报可以通过忽略处理） |
| **核心挑战** | 信息不足 → 需要补充查询 | 信息充足 → 需要精准提取 |

### 设计哲学的三个关键转变

**转变 1：从"证据优先"到"规则先行"**

Phase 3 的 `ticket-troubleshoot-v3` 强调"结论必须绑证据"（代码行号 + 查询结果），因为线上排障的每一步都是在黑暗中摸索。Phase 4 的 Skill 则倾向于先定义规则和模式（cr-engineer 的历史评论模式、sql-review 的硬编码规则、sonar-coverage-booster 的覆盖阈值），再让 LLM 在规则框架内工作。

**转变 2：从"单一输入"到"多源融合"**

Phase 3 的 Skill 主要依赖单一数据源（数据库 / Hera CLI / 本地源码）。Phase 4 的 Skill 需要融合多个数据源：
- cr-engineer：GitLab Diff + 历史评论 + 团队规范
- code-review-plus：Claude 审查 + Codex 审查
- sql-review：Git Diff + MySQL EXPLAIN + KeyCenter 解密

这推动了 **Pipeline 模式中的"多阶段数据注入"设计**——每个阶段都可能注入新的数据源，改变后续阶段的判断。

**转变 3：从"人类主导"到"自动化+人类确认"**

Phase 3 的 Skill 普遍依赖人类输入（用户描述、业务 ID、traceId），因为启动排障的前提是人发现问题。Phase 4 的 Skill 有更强的自动触发能力：
- cr-engineer：自动检测 GitLab 项目路径
- sonar-coverage-booster：自动轮询 SonarQube API
- sql-review：Step 0 自动版本检查 + 自动更新

但**关键的"行动"仍然需要人类确认**（cr-engineer Step 8、sonar-coverage-booster Step 6/7）——这是 CI/CD 安全原则在 Skill 设计中的体现。

---

## 💡 每个 Skill 的核心创新点

### cr-engineer：历史评论模式库（Reference-based Review）

> 在 `reference/review_comments.md` 中按项目存储团队历史 review 评论，作为审查的"风格锚点"。

**为什么这是最重要的设计决策**：代码审查的最大难点不是"发现更多问题"，而是"发现的都是团队关心的问题"。一个性能优秀的代码如果不符合团队惯例，review 的价值为零。cr-engineer 通过预加载历史评论，将审查从"通用 Linter"升级为"团队定制 review"。这个设计模式——用历史数据定义上下文——在后续的 ticket-troubleshoot-v3（经验库复用）中也得到了应用。

**设计精髓**：
```
reference/review_comments.md
  <!-- PROJECT: mit/new-retail/intl-retail -->
    - "参数必做空值校验" (3次出现)
    - "异常必须打印 context" (2次出现)
  <!-- PROJECT: mit/international/xxx -->
    - "Redis key 必须设置过期时间" (5次出现)
    - "BigDecimal 比较用 compareTo 不用 equals" (4次出现)
```

脚本 `fetch_review_comments.py` 自动判断：已有该项目的评论 → 跳过获取（避免重复 API 调用）；没有 → 拉取最近 100 条追加。这个"增量 + 幂等"的数据加载策略是 Skill 集成外部数据的标准做法。

### code-review-plus：并行后台调度 + 标记文件通信

> 用 `&` 后台进程 + `.done` 标记文件实现 Claude 与 Codex 的异步并行审查。

**为什么这是最重要的设计决策**：多模型审查的天真实现是"先让 A 跑完，再让 B 跑"——总耗时 = A耗时 + B耗时。code-review-plus 通过后台进程 + 标记文件通信，将总耗时压缩到 max(A耗时, B耗时)。这个设计不仅是性能优化，更是一种**架构声明**：审查模型之间是平级的、互不依赖的，可以任意扩展。

**设计精髓**：
```bash
# review-runner.sh 核心逻辑
bash "$SKILL_DIR/scripts/review-runner.sh" "$OUTPUT_DIR" <files> &
# ← Claude 继续自己的审查，两者并行

# 等待完成 (带超时保护)
while [ ! -f "$OUTPUT_DIR/.done" ]; do sleep 2; done
```

注意：标记文件 `.done` 的设计不是简单的"完成标志"——它是**跨进程通信协议**。如果未来要支持第三个模型，只需在 `review-runner.sh` 中添加一个新的后台任务，无需修改 Claude 的审查逻辑。

### sonar-coverage-booster：迭代验证闭环（Threshold Gating Loop）

> Step 2→3→4→5→6→7 → 7 不达标 → 回到 Step 2，形成"分析→编写→验证→达标检验"的闭环。

**为什么这是最重要的设计决策**：sonar-coverage-booster 不是"一次性"生成测试的工具——它是"达到 60% 覆盖率"这个目标驱动的闭环系统。这区别于所有其他 Skill：cr-engineer 审完就结束了，sql-review 分析完就结束了，但 sonar-coverage-booster **不达到 60% 就不算完成**。

**设计精髓**：
```text
Step 2: 找未覆盖行      ←──────┐
    ↓                         │
Step 3-5: 读源码→写测试        │ 迭代循环
    ↓                         │
Step 6: mvn test 本地验证      │
    ↓                         │
Step 7: git push → poll API   │
    ↓                         │
new_line_coverage ≥ 60%? ─────┤ NO → 回到 Step 2
    │                         │
    YES → 输出 before/after 对比，结束
```

这个"目标-检测-修复-验证"的循环与 DevOps 中的 CI/CD Pipeline 思想完全一致——代码质量不是"一次做完"的，而是"迭代逼近"的。

### sql-review：确定性基线 + LLM 校正双轨制（Deterministic Baseline + LLM Correction）

> 先通过硬编码规则生成"最坏情况 SQL"（100% 可复现），再由 LLM 根据实际代码逻辑"加回必传条件"修正。

**为什么这是最重要的设计决策**：纯 LLM 审查 SQL 有根本性问题——同一条 SQL 今天审查通过、明天审查不通过（因为 LLM 的不确定性）。sql-review 的解决思路是：**让机器的归机器，人类的归人类**。

- `extract_static_worst_case`：纯静态分析，结果永不变化，建立质量底线
- `extract_select_worst_case_multi_chain`：多调用链 SQL 的悲观语义展开
- `generate_batch_phase1`：LLM 校正——不是在"生成分析结果"，而是在"修正机器结果的过度悲观"
- `merge_deterministic_and_llm`：取条件更多的版本——"宁可误报，不可漏报"

**设计精髓**：
```python
# 确定性基线：将所有条件视为可选，最悲观估计
static_worst = extract_static_worst_case(batch)
update_worst = extract_update_worst_case(batch)
select_worst_chains = extract_select_worst_case_multi_chain(batch)

# 合并为基线
worst_case_sqls = dict(static_worst) | dict(update_worst) | dict(select_worst_chains)

# LLM 校正：只加回"实际必传"的条件
corrections = parse_phase1_output(phase1_output, filtered_batch)
worst_case_sqls = merge_deterministic_and_llm(worst_case_sqls, corrections)
# merge 逻辑：取条件更多的版本 → 保证不因 LLM 错误而漏报
```

这种双轨制架构的普适价值在于：任何需要"稳定底线 + 智能增强"的场景都可以用这个模式——不仅限于 SQL 审查。

---

## 🔌 集成关系图

Phase 4 四个 Skill 之间存在明确的调用关系：

```text
                    ┌──────────────────────────┐
                    │       cr-engineer         │
                    │  (MR 审查入口, 判断所有权)  │
                    └───────────┬──────────────┘
                                │
              ┌─────────────────┼─────────────────┐
              │ 自己的 MR?      │                  │ 他人的 MR?
              ↓                 │                  ↓
    ┌──────────────────┐       │        ┌──────────────────┐
    │ 检查 MiCR 门禁    │       │        │  标准 CR 审查     │
    └────────┬─────────┘       │        │  (8-step pipeline)│
             │                 │        └──────────────────┘
    ┌────────┴─────────┐       │
    │ 覆盖率不足?        │       │
    ↓                  ↓       │
┌──────────────┐  单测失败     │
│ sonar-       │  → 自动修复   │
│ coverage-    │              │
│ booster      │              │
└──────────────┘              │
                              │
                    ┌─────────┴──────────┐
                    │    xiaomi-git       │
                    │  (GitLab 项目检测    │
                    │   + API 调用封装)    │
                    └────────────────────┘
```

```
code-review-plus:  独立运行, 不依赖其他 Skill
sql-review:        独立运行, 自包含版本升级机制
```

**关键设计观察**：cr-engineer 通过"MR 所有权检测"将审查分为两条路径——自己的 MR 触发门禁修复（调用 sonar-coverage-booster），他人的 MR 触发标准审查。这种"一个入口、两个分支"的设计是 Skill 间协调的典范。

---

## 📏 量化 Skill 质量的维度

### 结构质量（可审计）

| 指标 | 测量方法 | 本 Phase 参考值 |
|------|---------|----------------|
| Pipeline 完整性 | 步骤间的数据传递是否明确 | cr-engineer: 8 步全有明确的输入/输出定义 |
| 失败降级路径 | 每步失败后是否有备选方案 | sql-review: DB 预查失败→降级为无 EXPLAIN；Phase 0 失败→降级为原始 snippet |
| 安全约束遵守 | 敏感信息是否在 Skill 层面被保护 | cr-engineer: Token 获取后不得展示；sonar-coverage-booster: tokens.json 不得提交 |

### 功能质量（可回放）

| 指标 | 测量方法 | 本 Phase 参考值 |
|------|---------|----------------|
| 确定性输出 | 相同输入产生相同输出 | sql-review: Phase 1 确定性基线 100% 可复现 |
| 自动化完成度 | 从输入到输出是否需要人工干预 | code-review-plus: 全自动（仅需用户提供文件） |
| 跨平台能力 | 是否支持多操作系统 | code-review-plus: macOS + Linux + Windows PowerShell |

### 泛化质量（可迁移）

| 指标 | 测量方法 | 本 Phase 参考值 |
|------|---------|----------------|
| 平台假设显式化 | 有多少硬编码的平台 URL/参数 | cr-engineer: GitLab URL 由用户输入提供，仅正则格式假设 |
| 审查规则可配置 | 规则是否从指令中抽离 | cr-engineer: 部分可配置（历史评论模式库），通用规则仍硬编码 |
| 适配器接口数量 | 每个外部调用 → 一个接口方法 | sql-review: 理论上 DB 连接 / SQL 提取 / EXPLAIN 执行都是可替换的适配点 |

---

## 💻 技术栈全景图

```text
Phase 4 质量保障 — 技术栈分布

┌─────────────────────────────────────────────────────┐
│                    LLM / AI 层                       │
│  Claude (审查分析)  │  Codex CLI (code-review-plus)  │
│  GPT/DeepSeek (sql-review Phase 1/2)                │
└─────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────┐
│                  脚本执行层                           │
│  Python 3 (cr-engineer: 3 scripts, sql-review: 10)   │
│  Bash (code-review-plus: 4 scripts)                  │
│  PowerShell (code-review-plus: 1 script)             │
└─────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────┐
│                  外部系统层                           │
│  GitLab REST API  │  SonarQube REST API              │
│  pymysql (MySQL)  │  Maven (test)  │  KeyCenter      │
└─────────────────────────────────────────────────────┘
```

---

## 📁 文档结构

```
phase-4-quality-assurance/
├── 00-overview.md                           ← 你在这
├── 01-cr-engineer/
│   ├── learning.md                          # 深度分析学习文档
│   └── quiz.md                              # 问题验证文档
├── 02-code-review-plus/
│   ├── learning.md
│   └── quiz.md
├── 03-sonar-coverage-booster/
│   ├── learning.md
│   └── quiz.md
└── 04-sql-review/
    ├── learning.md
    └── quiz.md
```

---

## ⏱️ Phase 4 学习时间规划

| 天 | 内容 | 预估 |
|----|------|------|
| Day 1 | cr-engineer: Pipeline 审查模式 + 历史评论库 | 2h |
| Day 2 | code-review-plus: 多模型并行 + HTML 报告生成 | 2h |
| Day 3 | sonar-coverage-booster: 覆盖率闭环 + JUnit5 测试生成 | 2h |
| Day 4 | sql-review: 三层分析架构 + 确定性基线双轨制 | 1.5h |
| Day 5 | 复习 + Phase 3 vs Phase 4 对比 + 设计模式总结 | 0.5h |

> 注：Phase 4 总耗时约 8h，与 roadmap 中的 7h 接近。

---

## 🎓 学完 Phase 4 你应该能回答的问题

1. Pipeline 模式的"质量门控"变体与 Phase 3 的"可恢复"变体有什么本质区别？
2. code-review-plus 如何通过标记文件实现跨进程通信？这个模式有什么局限性？
3. sonar-coverage-booster 的迭代闭环为什么不能合并为"一次性生成所有测试"？
4. sql-review 的"确定性基线 + LLM 校正"双轨制如何保证"宁可误报、不可漏报"？
5. cr-engineer 的 MR 所有权检测（自己的 MR vs 他人的 MR）为什么要拆成两条路径？
6. 如果要把 code-review-plus 扩展为支持 5 个模型的并行审查，哪些设计需要改动？哪些不需要？
7. 如何设计一个 Skill 的"自我升级"机制？（参考 sql-review 的 Step 0）
