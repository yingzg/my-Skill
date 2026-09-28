# Auto SQL Review Skill — 设计规格书 V4

> **状态**：实现校准阶段 | **最后更新**：2026-08-04

---

## 目录

1. [概述与定位](#1-概述与定位)
2. [使用场景总览](#2-使用场景总览)
3. [场景详细输入/输出规格](#3-场景详细输入输出规格)
4. [MVP 优先级划分](#4-mvp-优先级划分)
5. [不应支持的场景](#5-不应支持的场景)
6. [失败降级处理策略](#6-失败降级处理策略)
7. [事后复查与持续优化记录](#7-事后复查与持续优化记录)
8. [关键架构决策记录](#8-关键架构决策记录)
9. [架构设计](#9-架构设计)
10. [Pipeline 主流程设计](#10-pipeline-主流程设计)
11. [分批策略](#11-分批策略)
12. [SQL 审查规则体系](#12-sql-审查规则体系)
13. [附录](#13-附录)

---

## 1. 概述与定位

### 1.1 一句话定位

**Auto SQL Review** 是一个面向 Java/MyBatis 项目的 SQL 性能风险审查 Skill，通过追踪代码调用链还原真实 SQL，结合静态规则库与数据库 EXPLAIN 执行计划，对 git 变更/MR 引入的 SQL 进行风险评估，并给出分级修复建议。

### 1.2 核心能力

| 能力 | 说明 |
|------|------|
| **SQL 变更提取** | 从 git diff / MR diff 中提取增删改的 Mapper XML 和 Java Mapper 方法 |
| **调用链追踪** | 从 Mapper 方法反向追踪到 Controller/HTTP API，还原完整调用路径和真实传参 |
| **真实 SQL 还原** | 基于调用链中的实际传参，拼接 MyBatis 动态 SQL 为最终执行的 SQL（非枚举组合） |
| **双轨风险分析** | ① **静态规则轨**：基于 SQL 审查规则文件做规则匹配；② **动态执行轨**：执行 EXPLAIN，分析索引使用、扫描行数、文件排序等 |
| **分级修复建议** | 每条风险 SQL 输出 **短期止血方案**（可立即上线）和 **中长期治理方案**（需排期重构） |
| **多数据源支持** | 自动发现 @DS 注解和 @MapperScan 路由配置，关联 SQL 到正确的数据库执行 EXPLAIN |
| **大增量自适应** | 两阶段预筛 + 按表分组 + 批次并行，单次最多支持 80 条变更 SQL 的审查 |

### 1.3 设计原则

| 原则 | 说明 |
|------|------|
| **独立性** | 全新 Skill，不依赖已有 `sql-review` 或 `code-trace-analyzer` |
| **渐进降级，全程不中断** | 任何子步骤失败不应导致全局流程中断；降级继续执行，事后记录降级点 |
| **规范驱动** | 静态 SQL 分析基于可配置的规则文件，禁止 AI 自由发挥式判断 |
| **真实路径优先** | 动态 SQL 必须基于调用链真实传参还原，不枚举所有可能的参数组合 |
| **必须 EXPLAIN** | 只要数据库可用，必须执行 EXPLAIN。数据库不可用时降级为静态规则分析 |
| **事后复查，不当场打断** | 调链断裂、参数不确定、解析失败等场景，不中断要求人工确认，记录到复查清单 |
| **脚本做确定性，LLM 做判断** | 确定性机械操作（解析、匹配、执行）由脚本完成；需要推理判断的环节才用 LLM |

### 1.4 术语定义

| 术语 | 定义 |
|------|------|
| **调用链** | Controller/API → Service → Mapper 接口 → Mapper XML → SQL 的完整静态追踪链路 |
| **真实 SQL** | 基于调用链中找到的实际传参值，将 MyBatis 动态标签拼接后的最终 SQL |
| **静态规则轨** | 基于预定义 SQL 审查规则文件的纯文本分析，不依赖数据库连接 |
| **动态执行轨** | 在数据库上执行 EXPLAIN，基于执行计划进行风险分析 |
| **DML → SELECT Proxy** | 将 UPDATE/DELETE 语句转换为等效 SELECT，用于统一 EXPLAIN 分析 |
| **短期止血方案** | 可立即上线、低风险的修复（如加索引、加 LIMIT、改写查询条件） |
| **中长期治理方案** | 需排期架构级修改（如拆表、读写分离、异步化） |
| **复查项** | 分析过程中因信息不完备、工具能力边界等导致的降级点，记录到报告中供人工事后复查 |
| **主表** | 多表 JOIN 语句中第一个 FROM 子句的非子查询表，用于 SQL 分组 |

---

## 2. 使用场景总览

| 序号 | 场景名称 | 触发方式 | 优先级 |
|------|---------|---------|--------|
| S1 | **本地提交前自查** | 开发者主动调用，push 前检查本次改动 | P0 — MVP |
| S2 | **CI/CD MR 门禁** | MR 创建/更新时 CI pipeline 自动触发 | P0 — MVP |
| S3 | **代码审查辅助** | Reviewer 审查 MR 时手动触发 | P1 — V1.1 |
| S6 | **指定 Mapper/方法分析** | 开发者指定某个 Mapper 或方法聚焦分析 | P1 — V1.1 |

> **已排除**：S4（全仓库 SQL 健康巡检）、S5（线上慢 SQL 反向定位）不在当前 scope 内。

---

## 3. 场景详细输入/输出规格

### 3.1 S1 — 本地提交前自查

| 维度 | 规格 |
|------|------|
| **触发条件** | 开发者在 git 仓库中主动调用 |
| **输入** | ① `git diff <base>..HEAD`（默认 `base=origin/master`）；② 可选：指定文件/Mapper 过滤范围；③ SQL 审查规则文件路径（可选）；④ 手动数据源映射 `--ds-mapping`（可选，自动发现失败时使用） |
| **输出** | JSON 格式详细报告 + 终端可读表格摘要 |
| **输出内容** | 每条风险 SQL：`sql_id`、`file_path`、`line`、`statement_type`、`mapper_method`、`datasource`、`call_chain: [{class, method, line}]`、`resolved_sql`、`risk_level`（HIGH / MEDIUM / LOW）、`risk_rule_id`、`risk_desc`、`explain_result`、`short_term_fix`、`long_term_fix`。报告末尾包含 **复查清单** |
| **分析深度** | 静态规则轨 + 动态执行轨（EXPLAIN 必执行）+ 完整调用链追踪（到 Controller） |
| **分析范围** | MR diff 文件 ∪ 当前项目分支全部代码（追踪新增 Mapper 方法的调用者） |
| **耗时预期** | ≤3 分钟 |
| **失败行为** | 见第 6 章降级策略 |

### 3.2 S2 — CI/CD MR 门禁

| 维度 | 规格 |
|------|------|
| **触发条件** | MR 创建/更新 webhook → CI pipeline 自动执行 |
| **输入** | ① MR source/target 分支；② 门禁阈值配置（默认 `HIGH ≥ 1 → BLOCK`，`MEDIUM ≥ 1 → BLOCK`）；③ SQL 审查规则文件路径（可选） |
| **输出** | ① **门禁结论**：PASS / BLOCK；② JSON 格式详细报告；③ 自动发布到 MR 的结构化评论；④ **复查清单**附在报告末尾 |
| **门禁逻辑** | `HIGH_COUNT ≥ 1` 或 `MEDIUM_COUNT ≥ 1` → **BLOCK** |
| **分析深度** | 静态规则轨（必选）+ 动态执行轨（EXPLAIN 必执行）+ 完整调用链追踪 |
| **分析范围** | 同 S1 |
| **耗时预期** | 5–15 分钟 |
| **特殊处理** | 如果变更文件不包含 `*Mapper.xml` 或 `*Mapper.java`，直接返回 PASS，跳过分析 |

### 3.3 S3 — 代码审查辅助

| 维度 | 规格 |
|------|------|
| **触发条件** | Reviewer 在审查 MR 时手动触发 |
| **输入** | GitLab/GitHub MR 链接 |
| **输出** | 与 S1 相同格式的详细报告，增加 reviewer 视角标注 |
| **分析深度** | 与 S1 相同 |
| **耗时预期** | ≤3 分钟 |

### 3.4 S6 — 指定 Mapper/方法分析

| 维度 | 规格 |
|------|------|
| **触发条件** | 开发者指定某个 Mapper 类名或方法名 |
| **输入** | Mapper 全限定名或方法名 |
| **输出** | 该 Mapper/方法涉及的所有 SQL + 完整调用链 + 风险分析 + 分级建议 |
| **分析深度** | 与 S1 相同 |
| **耗时预期** | ≤1 分钟 |
| **与 S1 的区别** | 不依赖 git diff，直接分析指定范围的存量 SQL |

---

## 4. MVP 优先级划分

| 优先级 | 场景 | 原因 |
|--------|------|------|
| **P0 — V1.0** | S1 本地自查 | ① 不依赖外部系统（CI/GitLab），实现路径最短；② 开发者日常最高频使用 |
| **P0 — V1.0** | S2 CI MR 门禁 | ① 自动化最大价值——阻止坏 SQL 合入；② 倒逼分析引擎准确率和覆盖率 |
| **P1 — V1.1** | S6 指定 Mapper 分析 | ① 复用 V1.0 分析引擎，仅改变输入源 |
| **P1 — V1.1** | S3 审查辅助 | ① 需要 GitLab/GitHub API 集成；② Reviewer 体验打磨需要迭代 |

---

## 5. 不应支持的场景

| 序号 | 场景 | 原因 |
|------|------|------|
| N1 | **全仓库 SQL 健康巡检**（原 S4） | 全量分析耗时长，价值不如增量分析 |
| N2 | **线上慢 SQL 反向定位**（原 S5） | SQL 文本到代码的模糊匹配技术难度高 |
| N3 | **线上实时慢 SQL 监控** | 属于 APM/可观测性平台职责 |
| N4 | **非 MyBatis 项目** | ORM 的 SQL 生成机制完全不同 |
| N5 | **DDL 变更审查** | 风险维度与 DML 完全不同 |
| N6 | **SQL 业务语义正确性验证** | 需要业务上下文 |
| N7 | **存储过程 / 函数调用内部 SQL** | 静态 Mapper XML 分析无法触及 |
| N8 | **多数据源：隐式目录约定路由** | 无 @DS 也无 @MapperScan 显式声明的项目，无法自动发现映射。允许用户通过 `--ds-mapping` 手动指定，不做启发式推断 |

---

## 6. 失败降级处理策略

```
核心原则：渐进降级，全程不中断。宁可输出不完整的报告，也不什么都不输出。
所有降级点记入复查清单（第 7 章），不当场中断等待人工决策。
```

### 6.1 降级策略表

| 失败场景 | 是否中断 | 降级策略 | 复查清单记录 |
|----------|:------:|---------|:----------:|
| **非 git 仓库 / 无法获取 base 分支** | ⚠️ 中断 | 提示用户：手动提供 base 分支名、文件列表，或直接粘贴变更内容 | — |
| **变更中无 Mapper 文件** | ✅ 优雅退出 | Exit 0，输出 "本次变更未检测到 SQL 变更" | — |
| **Mapper XML 解析失败** | ✅ 不中断 | 跳过该文件，其余文件继续分析 | ✅ `parse_error` |
| **数据源发现失败**（无 @DS、无 @MapperScan） | ✅ 不中断 | 标注 `UNKNOWN_DATASOURCE`；EXPLAIN 不可用，降级为纯静态规则 | ✅ `datasource_unknown` |
| **数据库连接失败** | ✅ 不中断 | 降级为纯静态规则模式；每条 SQL 标注 `explain_executed: false` | ✅ `explain_unavailable` |
| **EXPLAIN 执行失败**（单条） | ✅ 不中断 | 该条 SQL 降级为仅静态规则分析；其余 SQL 继续 | ✅ `explain_unavailable` |
| **DML EXPLAIN 不支持的数据库版本** | ✅ 不中断 | 将 DML 转换为等效 SELECT proxy 后执行 EXPLAIN | ✅ `dml_select_proxy` |
| **调用链追踪断裂** | ✅ 不中断 | 保留部分链路，断裂处标注原因；`call_chain_complete: false` | ✅ `call_chain_broken` |
| **参数值无法静态确定** | ✅ 不中断 | 标注 `param_uncertain: true`；列出不确定的参数 | ✅ `param_uncertain` |
| **LLM 分析超时 / 输出格式异常** | ✅ 不中断 | 该批次标记 `ANALYSIS_FAILED`，其余批次继续 | ✅ `llm_failure` |
| **单条 SQL 分析超时** | ✅ 不中断 | 跳过该 SQL，记录到 skipped 清单 | ✅ `analysis_timeout` |
| **报告生成失败** | ⚠️ 中断 | 将已分析的原始数据写入 `/tmp/auto_sql_review_dump_{timestamp}.json` | ✅ 最终兜底 |

### 6.2 DML → SELECT Proxy（自适应降级）

对于 UPDATE/DELETE 语句，EXPLAIN 分析统一采用 SELECT proxy 策略：

```
Phase 3.5: 如果 statement_type ∈ {UPDATE, DELETE}:
  将 DML 语句转换为等效 SELECT:
    UPDATE t SET a=1, b=2 WHERE id=123 AND status=0
    → SELECT * FROM t WHERE id=123 AND status=0

    DELETE FROM t WHERE user_id=456
    → SELECT * FROM t WHERE user_id=456

  原因:
    1. 部分 MySQL 版本（< 5.6）不支持 EXPLAIN UPDATE/DELETE
    2. 部分数据库（如 SQL Server）EXPLAIN 语法不同
    3. SELECT proxy 的 EXPLAIN 结果（type/key/rows）与 DML 完全一致
    4. 统一 EXPLAIN 分析逻辑，无需分支处理

  注意:
    - 不影响静态规则轨的 DML 专属规则执行
    - proxy_sql 仅用于 EXPLAIN，不替代 resolved_sql 的规则匹配
```

### 6.3 动态 SQL 处理：真实路径还原

```
步骤：
1. 从调用链中找到 Mapper 方法的实际调用者（Service 层）
2. 从调用者代码中提取传入 Mapper 方法的参数值/变量名
3. 沿调用链向上追溯到 Controller 层，确定原始入参
4. 基于原始入参值，判断 MyBatis 动态标签（<if>, <foreach>, <choose>）中哪些条件为真
5. 拼接得到最终实际执行的 SQL
6. 对这条最终 SQL 执行风险分析
```

### 6.4 新增 Mapper 方法的调用者追踪

策略：分析范围 = MR diff 文件 ∪ 当前项目分支全部 Java 代码。

---

## 7. 事后复查与持续优化记录

（V3 第 7 章内容完整保留，此处省略具体 JSON schema 和复查项分类表，详见 V3）

---

## 8. 关键架构决策记录

| 编号 | 决策 | 排除方案 | 原因 |
|------|------|---------|------|
| **AD1** | 动态 SQL：基于调用链真实传参还原，**不枚举组合** | 枚举所有动态分支 | 枚举产生大量无效 SQL |
| **AD2** | EXPLAIN：**每次必须执行**（数据库可用时） | 可选 EXPLAIN | 静态规则无法发现索引缺失/全表扫描 |
| **AD3** | 调用链深度：**必须追踪到 Controller/API 层** | 仅到 Service 层 | 只有到 Controller 才能确定 HTTP 原始入参 |
| **AD4** | 分析范围：**MR diff + 当前项目分支全部代码** | 仅分析 MR diff | 追踪新增 Mapper 方法的调用者需全量扫描 |
| **AD5** | 静态分析：**基于预定义审查规则文件，禁止 AI 自由发挥** | AI 自由判断 | 可审计、可定制、可扩展 |
| **AD6** | CI 门禁：**HIGH≥1 或 MEDIUM≥1 → BLOCK** | 宽松门禁 | 宁可误拦也不漏放 |
| **AD7** | 规则文件：**设计者起草通用规范，用户可追加** | 用户必须自行提供 | 零配置即可用 |
| **AD8** | 人工复查：**不当场中断，降级继续 + 事后记录复查清单** | 遇问题中断等人工确认 | 中断无益；事后记录驱动 Skill 迭代 |
| **AD9** | 架构模式：**SKILL.md 主流程编排 + scripts 确定性脚本 + references 知识底座**（方案 C） | 集中式单脚本 / 阶段拆分多脚本 | 三层分离：修改规则不改脚本，修改编排不改知识底座 |
| **AD10** | SQL 分批：**按（数据源, 主表）分组**，非按 Mapper 文件分组 | 按 Mapper 文件分组 | 同表的 SQL 在同一批次，EXPLAIN 上下文可复用；多表 JOIN 归入主表组 |
| **AD11** | 大批量 SQL：**两阶段预筛**——静态规则先行，LOW 走快速通道降低成本，HIGH/MEDIUM 走 LLM 深度分析 | 全量 LLM 分析 | 减少 LLM 调用（典型场景仅 20-30% SQL 需 LLM），降低 token 和耗时 |
| **AD12** | DML EXPLAIN：**统一使用 SELECT proxy**，DML 专属规则仅在静态规则轨执行 | DML 和 SELECT 各自独立 EXPLAIN 逻辑 | EXPLAIN 分析逻辑完全统一；只需 7 条 DML-only 静态规则 |
| **AD13** | 多数据源发现：**支持 @DS 注解 + @MapperScan 路由，不支持隐式目录约定** | 启发式推断所有路由模式 | 隐式约定推断投入产出比低，复杂度不可控 |
| **AD14** | LLM 介入时机：**仅在 Phase 3（SQL还原）和 Phase 4b（风险定性）使用 LLM**，其余全部由脚本执行 | LLM 用于全部环节 | 减少 LLM 调用次数，降低延迟和成本 |
| **AD15** | 规则引擎：**统一框架 + applicable_to 标记 + severity_by_type 自适应** | SELECT/DML 各自独立规则集 | 避免规则重复定义；同一规则对 SELECT/DML 的风险等级可不同 |
| **AD16** | 主流程：**默认使用 `run_review.py` 一键编排**，`SKILL.md` 只负责入口选择、降级解释和最终复核 | 在 `SKILL.md` 内手工拼接每个阶段命令 | 降低长会话漂移风险；端到端流程可测试、可复现 |

---

## 9. 架构设计

### 9.1 架构模式：方案 C（分层编排）

```
SKILL.md（主流程编排 — "做什么、何时做、做错了怎么办"）
│
├─ scripts/（确定性脚本层 — "怎么做"，机械执行，无 AI 判断）
│   ├── extract_changes.py       # git diff → 变更 Mapper 文件列表
│   ├── parse_mapper.py          # Mapper XML 解析 → SQL 提取 + 方法签名映射
│   ├── discover_datasource.py   # 数据源发现：@DS + @MapperScan → 数据源映射表
│   ├── trace_callchain.py       # Java AST 调用链反向追踪 → Controller
│   ├── resolve_dynamic_sql.py   # 动态标签解析 + 基于调用链参数还原最终 SQL
│   ├── extract_tables.py        # 从 resolved_sql 提取主表名
│   ├── match_rules.py           # 加载规则文件 → 正则/AST 匹配 → 输出匹配结果
│   ├── dml_to_select_proxy.py   # UPDATE/DELETE → 等效 SELECT 转换
│   ├── execute_explain.py       # 连接数据库 → 执行 EXPLAIN → 解析结果
│   ├── build_report.py          # 聚合所有结果 → 组装 JSON 报告 + 复查清单
│   └── run_review.py            # 端到端编排入口，固定产物路径和阶段顺序
│
├─ references/（LLM 知识底座 — "凭什么这么判断"，只读，按需注入）
│   ├── rules/rules.json              # 静态审查规则文件（AD5, AD7）
│   ├── explain-guide.md              # EXPLAIN 各字段含义 + 风险判断阈值
│   ├── degradation-matrix.md         # 降级策略决策矩阵（第 6 章）
│   └── report-schema.md              # 输出 JSON Schema 定义
│
├─ assets/（输出模板 — "长什么样"，纯展示）
│   ├── report-template.md            # 终端输出表格模板
│   └── mr-comment-template.md        # MR 评论格式模板
│
└─ tests/（测试，不在 Skill 运行时加载）
    └── fixtures/                     # 测试用 Mapper XML / Java 代码样本
```

### 9.2 各层职责边界

```
┌─────────────────────────────────────────────────────────┐
│                      SKILL.md                           │
│  "做什么、什么时候做、做错了怎么办"                      │
│  · 主流程编排（Phase 0 → Phase 5）                       │
│  · LLM 介入时机决策                                     │
│  · references 文件注入时机                              │
│  · 复查清单生成规范                                     │
│  · 脚本调用顺序与参数传递规范                            │
│  · 只做决策，不执行具体操作                               │
└──────────┬──────────────────────────┬───────────────────┘
           │                          │
           ▼                          ▼
┌──────────────────────┐   ┌──────────────────────────────┐
│     scripts/         │   │       references/            │
│  "怎么做（机械执行）"  │   │  "凭什么这么判断（知识底座）"│
│  · 纯函数/命令行工具   │   │  · 规则文件                  │
│  · 输入 JSON → 出 JSON│   │  · EXPLAIN 解读指南          │
│  · 可独立测试          │   │  · 降级决策矩阵              │
│  · 不做 AI 判断        │   │  · 输出 Schema               │
│  · 失败返回 error code │   │  · 用户可编辑                │
│  · 不读取 references/  │   │  · 只读，被 LLM 引用         │
└──────────────────────┘   └──────────────────────────────┘
           │                          │
           └──────────┬───────────────┘
                      │
                      ▼
           ┌──────────────────────┐
           │      assets/         │
           │  "长什么样（格式化）"  │
           │  · 输出模板           │
           │  · MR 评论格式        │
           │  · 纯展示层，无逻辑   │
           └──────────────────────┘
```

### 9.3 LLM 介入时机

在整个 pipeline 中，LLM **仅**在 2 个环节介入：

| 环节 | LLM 任务 | 注入的 references | 不使用 LLM 的原因 |
|------|---------|------------------|------------------|
| **Phase 3** SQL 还原 | 可选：基于调用链参数判断动态条件激活状态 | 无（调用链分析结果已足够） | 默认 optimistic/确定性展开，避免主流程阻塞 |
| **Phase 4b** 风险定性与建议 | 可选：合并 EXPLAIN + 规则匹配结果 → 风险描述 + 分级修复建议 | `explain-guide.md` + `rules/rules.json` | 当前主流程先输出确定性报告，LLM 作为复核增强 |

**以下环节由脚本执行，不使用 LLM**：

| 环节 | 脚本 | 原因 |
|------|------|------|
| git diff 提取 | `extract_changes.py` | 机械操作，确定性 |
| XML 解析 | `parse_mapper.py` | 机械操作，确定性 |
| 数据源发现 | `discover_datasource.py` | 注解扫描，确定性 |
| AST 调用链追踪 | `trace_callchain.py` | 机械追踪，确定性 |
| 表名提取 | `extract_tables.py` | 正则匹配，确定性 |
| 规则正则匹配 | `match_rules.py` | 规则驱动，确定性 |
| DML → SELECT | `dml_to_select_proxy.py` | 字符串替换，确定性 |
| EXPLAIN 执行 | `execute_explain.py` | MCP 数据库连接，确定性 |
| JSON 报告组装 | `build_report.py` | 数据聚合，确定性 |
| 端到端编排 | `run_review.py` | 固定流程和产物路径，确定性 |

---

## 10. Pipeline 主流程设计

### 10.1 完整流程图

```
Phase 0: 输入准备（脚本）
  │ 脚本: extract_changes.py
  │ 输入: base分支名
  │ 输出: 变更的 Mapper 文件列表
  │ 失败: git不可用 → ⚠️中断; 无Mapper文件 → ✅Exit 0
  ▼
Phase 0.5: 数据源发现（脚本）
  │ 脚本: discover_datasource.py
  │ 输入: 项目源码根目录
  │ 输出: {mapper_package → {datasource_name, type, url}}
  │ 模式: @DS注解 → 直接映射; @MapperScan + @ConfigurationProperties → 间接映射
  │ 失败: 两者都未找到 → UNKNOWN_DATASOURCE（降级为纯静态规则）
  ▼
Phase 1: SQL 提取 + 映射（脚本）
  │ 脚本: parse_mapper.py
  │ 输入: Mapper XML 文件列表 + Mapper Java 接口列表 + 数据源映射表
  │ 输出: [{sql_id, method, raw_sql, statement_type, dynamic_tags, datasource, file, line}]
  │ 失败: XML解析失败 → ✅跳过该文件, 记录 PARSE_ERROR 复查项
  ▼
Phase 2: 调用链追踪（脚本）
  │ 脚本: trace_callchain.py
  │ 输入: Mapper 方法全限定名列表 + 项目源码路径
  │ 输出: [{method, call_chain: [{class, method, line}], complete: bool}]
  │ 失败: 调用链断裂 → ✅标注断裂, 记录 call_chain_broken 复查项
  ▼
Phase 3: 动态 SQL 解析（脚本 + LLM 双模式）
  │ 脚本: resolve_dynamic_sql.py（独立 CLI，支持双模式）
  │ 输入: Phase 1+2 的 NDJSON（raw_sql + dynamic_tags + call_chain）
  │
  │ ┌─ optimistic 模式（默认）：确定性展开所有动态标签
  │ │   直接输出 resolved_sql，跳过 LLM
  │ │
  │ └─ resolve 模式：确定性部分展开，不确定标签保留 → LLM 判断
  │    Step 1: 脚本展开 <foreach>/<bind>/<include>，保留不确定的 <if>/<choose>
  │    Step 2: 输出 needs_llm=true 的 SQL，由 SKILL.md 收集后统一问 LLM
  │    Step 3: LLM 结合 call_chain 判断条件激活状态 → 返回 resolved_sql
  │    Step 4: finalize_sql() 清洗（#{xxx}→?，压缩空白）
  │
  │ 输出: resolved_sql（最终执行的完整 SQL，含 needs_llm 标记）
  │ 失败: 参数不确定 → ✅标注, 记录 param_uncertain 复查项
  ▼
Phase 3.5: 表名提取 + DML→SELECT Proxy（脚本）
  │ 脚本A: extract_tables.py
  │  输入: resolved_sql
  │  输出: main_table（主表名）
  │  规则: 单表 → 直接提取; 多表JOIN → 第一个FROM的非子查询表; UNION → 第一个SELECT的表
  │
  │ 脚本B: dml_to_select_proxy.py
  │  输入: resolved_sql (if UPDATE/DELETE)
  │  输出: proxy_sql（等效 SELECT）
  │  用于: 后续 Phase 4a/4b 的 EXPLAIN 执行
  ▼
Phase 4a: 静态规则预筛 + 分类（脚本，无 LLM）
  │ 脚本: match_rules.py（加载 references/rules/rules.json）
  │ 输入: proxy_sql（DML已转换）或 resolved_sql（SELECT）
  │ 输出: [{rule_id, matched, risk_level, applicable_to校验}]
  │
  │ 分类:
  │   - LOW: 所有匹配规则 ≤ LOW 级别 → 进入快速通道
  │   - MEDIUM/HIGH: 至少一个规则命中 MEDIUM/HIGH → 进入深度分析
  │   - UNCERTAIN: 规则无法覆盖 → 标记，进入深度分析
  │
  │ 注意: DML 专属规则（applicable_to ∈ {UPDATE, DELETE}）仅对 DML 执行
  ▼
Phase 4a.5: 分批（脚本）
  │ 输入: [{sql_id, datasource, main_table, risk_classification}]
  │ 策略:
  │   1. 按 datasource 分组（不同数据库不能合并批次）
  │   2. 同 datasource 内按 main_table 分组
  │   3. 小组(<5条)合并相邻同数据源组
  │   4. 大组(>12条)拆分为子批次
  │ 目标: 每批 8 条，范围 5-12 条
  │ 输出: [[{sql_id, ...}]]  分批列表
  ├── 快速通道（LOW 风险 SQL）────────────────┐
  │   │ 脚本: execute_explain.py              │
  │   │ 执行 EXPLAIN（使用 proxy_sql）         │
  │   │ 检查 EXPLAIN 是否推翻规则结论:          │
  │   │   EXPLAIN 确认 LOW → 直接标记 LOW      │
  │   │   EXPLAIN 发现异常(如 type=ALL)       │
  │   │   → 升级到深度分析批次                 │
  │   └── 输出: LOW 确认结果                   │
  │                                            │
  └── 深度分析（MEDIUM/HIGH/UNCERTAIN）────────┤
      │ 每批独立并行执行：                       │
      │   1. 脚本: execute_explain.py            │
      │   2. LLM: 合并 EXPLAIN + 规则匹配        │
      │      注入: references/explain-guide.md
      │      输出: [{risk_level, risk_desc, short_term_fix, long_term_fix}]
      │   失败: 见降级策略表                     │
      └── 批间并发度: 3-4 批（取决于 LLM API 限制）
  ▼
Phase 5: 报告生成（脚本）
  │ 脚本: build_report.py
  │ 输入: 所有分析结果（快速通道 + 深度分析批次）+ 复查清单
  │ 输出: JSON 报告 + 终端表格 + 门禁结论(CI模式) + MR评论(CI模式)
  │ 聚合逻辑:
  │   1. 每 SQL 级别的结果原样保留
  │   2. 全局门禁: HIGH_COUNT≥1 或 MEDIUM_COUNT≥1 → BLOCK
  │   3. 复查清单: 全局类降级去重（同类型只保留1条）; SQL类降级按(文件+类型+位置)去重
  │   4. 批间冲突: 同SQL不会出现在多个批次中（按表分组保证）
  │ 失败: JSON序列化失败 → ⚠️中断, dump原始数据到 /tmp/
```

### 10.2 各阶段输入/输出契约

| Phase | 输入 | 输出 | 执行者 | LLM？ |
|-------|------|------|--------|:---:|
| 0 | base分支名 | 变更Mapper文件列表 | extract_changes.py | ❌ |
| 0.5 | 项目源码根目录 | 数据源映射表 | discover_datasource.py | ❌ |
| 1 | Mapper文件列表 + 数据源映射表 | sql_id列表 | parse_mapper.py | ❌ |
| 2 | Mapper方法全限定名列表 | 调用链 | trace_callchain.py | ❌ |
| 3 | raw_sql + 调用链 | resolved_sql | — | ✅ |
| 3.5a | resolved_sql | main_table | extract_tables.py | ❌ |
| 3.5b | resolved_sql (DML) | proxy_sql | dml_to_select_proxy.py | ❌ |
| 4a | proxy_sql/resolved_sql | 规则匹配 + 风险分类 | match_rules.py | ❌ |
| 4a.5 | 分析结果 + 数据源 + 主表 | 分批列表 | 内联逻辑 | ❌ |
| 4b快速 | proxy_sql | EXPLAIN验证结果 | execute_explain.py | ❌ |
| 4b深度 | proxy_sql + EXPLAIN + 规则 | 风险定性 + 修复建议 | — + execute_explain.py | ✅ |
| 5 | 所有结果 + 复查清单 | JSON报告 + 终端输出 | build_report.py | ❌ |

> 实现落地时，默认由 `run_review.py` 串联 0-5 阶段，并将所有产物写入 `/tmp/sql_review/{run_id}/`。分阶段命令主要用于故障排查，不作为日常使用入口。

---

## 11. 分批策略

### 11.1 分组维度

```
核心原则：按（数据源, 主表）分组，而非按 Mapper 文件分组。

原因：
  · 同主表的 SQL 在同一数据库 → EXPLAIN 执行上下文可复用
  · 同一 Mapper 文件可能操作多张表，分到不同组反而混乱
  · 多表 JOIN 的 SQL 归入其主表组，保证相关 SQL 在一起
```

### 11.2 表名提取规则

```
extract_tables.py 的输出逻辑：

1. 单表 SQL:
   SELECT ... FROM orders WHERE ...
   → main_table = "orders"

2. 多表 JOIN:
   SELECT ... FROM orders o JOIN users u ON ...
   → main_table = "orders"  (第一个 FROM 的非子查询表)

3. 子查询驱动:
   SELECT ... FROM (SELECT ... FROM orders) t WHERE ...
   → main_table = "orders"  (穿透一层子查询)

4. UNION:
   SELECT ... FROM orders WHERE ...
   UNION
   SELECT ... FROM products WHERE ...
   → main_table = "orders"  (第一个 SELECT 的主表)

5. UPDATE/DELETE:
   UPDATE orders SET ... WHERE ...
   → main_table = "orders"
```

### 11.3 分批算法

```
参数:
  TARGET_BATCH_SIZE = 8
  MIN_BATCH_SIZE = 5
  MAX_BATCH_SIZE = 12

算法:
  Step 1: 过滤出需要深度分析的 SQL（排除快速通道的 LOW）
  Step 2: 按 (datasource, main_table) 分组
  Step 3: 对每个数据源：
    3a. 小组合并：len(group) < MIN_BATCH_SIZE 的组与同数据源的相邻组合并
    3b. 大组拆分：len(group) > MAX_BATCH_SIZE 的组拆分为 TARGET_BATCH_SIZE 的子批次
    3c. 同表拆分时保持相关 SQL 相邻（如同方法的不同重载）
  Step 4: 输出批次列表

示例（35条 MEDIUM/HIGH SQL，分布在 3 个数据源 6 张表）：
  scheme.orders: 10条  → Batch 1 (10条)
  scheme.products: 6条  → Batch 2 (6条)
  scheme.users: 3条     → 与 products 合并 → Batch 2 (6+3=9条)
  icrm.base_info: 8条   → Batch 3 (8条)
  icrm.apply_line: 4条  → 与 base_info 合并 → Batch 3 (8+4=12条)
  democrm.customers: 4条 → 独立批次 → Batch 4 (4条, 允许<MIN)
```

### 11.4 快速通道与深度分析的边界

```
快速通道条件（全部满足）：
  ✅ 所有匹配规则的 risk_level ≤ LOW
  ✅ 无 UNCERTAIN 标记（规则覆盖了所有风险维度）

快速通道处理：
  1. 执行 EXPLAIN（使用 proxy_sql）
  2. EXPLAIN 确认 LOW → 直接标记
  3. EXPLAIN 发现异常（type=ALL, key=NULL, rows>阈值）
     → 升级到深度分析批次

极端场景：
  全部 LOW → 0 次 LLM 调用 → 分析总时长 ≈ 脚本（30s）+ EXPLAIN（60s）≈ 1.5 分钟
  全部 HIGH  → 5 批 × 2 分钟（3批并发×2轮）≈ 4 分钟
```

---

## 12. SQL 审查规则体系

> **落地说明**：本节为 V4 设计草案。最终 `references/rules/rules.json` 落地时做了调整：① 规则精简为 15 条（R001-R011 性能 + R101-R104 数据安全），非草案的「40+ 通用 + 7 条 DML」；② 字段名 `rule_id`→`id`、`match.type`→`match.method`、`short_term_fix`→`short_term_fix_template`；③ 「缺失 WHERE」拆分为 R007（SELECT 无 WHERE）与 R102（UPDATE/DELETE 无 WHERE）两条独立规则，未用 severity_by_type 统一。**以 rules.json 为准。**

### 12.1 规则引擎架构

```
统一规则框架：

  ┌─────────────────────────────────────────────────┐
  │              规则引擎 (match_rules.py)            │
  │                                                  │
  │  加载: references/rules/rules.json               │
  │  输入: sql_statement + statement_type + datasource│
  │  输出: [{rule_id, matched, risk_level}]          │
  │                                                  │
  │  执行逻辑:                                        │
  │    1. 遍历所有规则                                 │
  │    2. 检查 applicable_to 是否包含此 statement_type │
  │    3. 若规则匹配，按 severity_by_type 调整等级      │
  │    4. 输出匹配结果                                 │
  └─────────────────────────────────────────────────┘

规则分类:

  ├─ 通用规则（applicable_to: ["SELECT", "UPDATE", "DELETE"]）
  │   40+ 条。例: type=ALL, key=NULL, 函数包裹索引, 子查询反模式
  │
  ├─ DML 专属规则（applicable_to: ["UPDATE", "DELETE"]）
  │   7 条。例: status_code 守卫, 物理DELETE检测, 锁提示, 审计字段
  │
  └─ 风险等级自适应（severity_by_type）
      3 条。同一规则对 SELECT/DML 的严重程度不同
      例: "缺失 WHERE 子句"
        SELECT → LOW     (慢但安全)
        UPDATE → CRITICAL (不可逆)
        DELETE → CRITICAL (不可逆)
```

### 12.2 规则文件 Schema

```json
{
  "version": "1.0",
  "meta": {
    "name": "通用 SQL 性能审查规则",
    "description": "适用于 Java/MyBatis 项目的默认 SQL 审查规则集",
    "author": "Auto SQL Review Skill"
  },
  "rules": [
    {
      "rule_id": "R001",
      "name": "SELECT * 使用检测",
      "applicable_to": ["SELECT", "UPDATE", "DELETE"],
      "risk_level": "MEDIUM",
      "severity_by_type": {},
      "category": "字段选择",
      "description": "使用 SELECT * 而非显式指定列名，可能导致不必要的数据传输和索引失效",
      "match": {
        "type": "regex",
        "pattern": "(?i)\\bSELECT\\s+\\*\\s+FROM\\b"
      },
      "short_term_fix": "将 SELECT * 改为显式列出所需字段",
      "long_term_fix": "在 DAO 层统一规范：禁止使用 SELECT *"
    },
    {
      "rule_id": "R002",
      "name": "缺失 WHERE 子句",
      "applicable_to": ["SELECT", "UPDATE", "DELETE"],
      "risk_level": "CRITICAL",
      "severity_by_type": {
        "SELECT": "LOW",
        "UPDATE": "CRITICAL",
        "DELETE": "CRITICAL"
      },
      "category": "基础安全",
      "description": "无 WHERE 子句的写操作会修改/删除全表数据",
      "match": {
        "type": "static",
        "pattern": "no_where_clause"
      },
      "short_term_fix": "对 SELECT：评估是否确实需要全表数据；对 UPDATE/DELETE：必须添加精确的 WHERE 条件",
      "long_term_fix": "启用 sql_safe_updates 防止无 WHERE 的写操作"
    },
    {
      "rule_id": "R101",
      "name": "缺失软删除状态守卫",
      "applicable_to": ["UPDATE", "DELETE"],
      "risk_level": "HIGH",
      "severity_by_type": {},
      "category": "数据安全",
      "description": "UPDATE/DELETE 语句的 WHERE 子句中未包含 status_code = 0（或 statecode = 0），可能修改已软删除的行",
      "match": {
        "type": "static",
        "pattern": "missing_status_guard"
      },
      "short_term_fix": "在 WHERE 子句中添加 AND status_code = 0",
      "long_term_fix": "在 BaseMapper/BaseService 层统一拦截，自动附加 status_code = 0 条件"
    },
    {
      "rule_id": "R102",
      "name": "物理 DELETE 检测",
      "applicable_to": ["DELETE"],
      "risk_level": "MEDIUM",
      "severity_by_type": {},
      "category": "数据安全",
      "description": "项目应使用软删除（UPDATE status_code = 1）而非物理 DELETE FROM",
      "match": {
        "type": "static",
        "pattern": "physical_delete"
      },
      "short_term_fix": "评估该表是否有软删除机制；若有，改用 UPDATE status_code = 1",
      "long_term_fix": "全局统一软删除策略，禁止物理 DELETE"
    },
    {
      "rule_id": "R103",
      "name": "动态 WHERE 可能退化为空",
      "applicable_to": ["UPDATE", "DELETE"],
      "risk_level": "CRITICAL",
      "severity_by_type": {},
      "category": "基础安全",
      "description": "<where> 标签内所有 <if> 条件可能同时不满足，导致 WHERE 子句退化为空（全表操作）",
      "match": {
        "type": "static",
        "pattern": "empty_dynamic_where"
      },
      "short_term_fix": "确保至少有一个强制条件不会被 <if> 包裹，或在最外层添加 AND 1=0 作为安全兜底",
      "long_term_fix": "在 Mapper XML 模板层面引入 must_condition 标签，保证必选过滤"
    }
  ]
}
```

### 12.3 DML 专属规则清单（7条）

| rule_id | 名称 | 级别 | 说明 |
|---------|------|:--:|------|
| R101 | 缺失软删除状态守卫 | HIGH | UPDATE/DELETE 的 WHERE 中无 status_code = 0 |
| R102 | 物理 DELETE 检测 | MEDIUM | 项目约定软删除，但使用了物理 DELETE |
| R103 | 动态 WHERE 可能退化为空 | CRITICAL | 所有 `<if>` 都不命中 → 无条件全表操作 |
| R104 | SQL Server 锁提示 | MEDIUM | WITH(ROWLOCK)/WITH(UPDLOCK) — 跨库兼容性 |
| R105 | 缺失审计字段 | LOW | UPDATE 的 SET 中缺 update_time / update_user |
| R106 | 乐观锁 affectedRows 未检查 | HIGH | WHERE 含 oldValue 条件，但调用方未检查 affectedRows |
| R107 | N+1 批量更新 | HIGH | `<foreach separator=";">` 生成多条 UPDATE 单语句 |

### 12.4 规则可扩展性

1. 复制默认规则文件到项目目录
2. 在 `rules` 数组中追加新规则，指定 `applicable_to` 和 `severity_by_type`
3. 或修改已有规则的 `risk_level` / `short_term_fix` / `long_term_fix`
4. 通过 Skill 调用的参数指定自定义规则文件路径
5. 规则文件版本化（`version` 字段），Skill 启动时校验兼容性

---

## 13. 附录

### 附录 A：变更记录

| 版本 | 日期 | 变更内容 |
|------|------|---------|
| V1 | 2026-07-29 | 初始版本：场景定义、MVP 划分、降级策略、架构决策（5 个待确认问题） |
| V2 | 2026-07-29 | 待确认问题收口：EXPLAIN 必须执行、调用链到 Controller、分析范围扩大、门禁激进策略、规则文件起草 |
| V3 | 2026-07-29 | 人工复查策略重构：降级继续 + 事后记录复查清单；新增 AD8 |
| **V4** | **2026-07-29** | **架构设计阶段收口**：① 确定方案 C 架构 + 目录结构 + 各层职责边界；② Pipeline 5+1 阶段主流程设计（含 Phase 3.5 DML proxy 和 4a.5 分批）；③ 分批策略按（数据源, 主表）分组；④ DML EXPLAIN 统一用 SELECT proxy；⑤ 规则体系升级为统一框架 + applicable_to + severity_by_type；⑥ 新增 AD9-AD15 架构决策；⑦ 数据源发现覆盖 @DS + @MapperScan，排除隐式目录约定（N8）；⑧ 明确 LLM 仅介入 Phase 3 和 Phase 4b 两个环节 |

### 附录 B：MVP 范围定义

| 维度 | MVP（V1.0） | V1.1 | 未来 |
|------|:---------:|:----:|:----:|
| **场景** | S1, S2 | +S6, S3 | — |
| **数据源发现** | @DS + @MapperScan | 手动映射 CLI | — |
| **数据库方言** | MySQL | +SQL Server | — |
| **SQL 类型** | SELECT + DML | — | — |
| **规则条数** | ~15 条（通用 + DML） | +5 条 | 社区贡献 |
| **LLM 介入环节** | Phase 3, Phase 4b | 同 | — |
| **输出格式** | JSON + 终端表格 | +MR 评论 | — |
| **调用链断裂类型** | RPC / 反射 / 动态代理 | +Dubbo / Feign | — |

### 附录 C：下一步计划

1. ~~需求澄清~~ ✅
2. ~~MVP 能力边界~~ ✅
3. ~~架构设计~~ ✅
4. **待用户发起** → 进入详细设计/实施阶段：
   - 规则文件完整 JSON Schema 及全部规则定义
   - SKILL.md 完整编排逻辑
   - scripts/ 各脚本的接口契约
   - references/ 各文件详细内容
   - 输出 JSON Schema 详细定义
