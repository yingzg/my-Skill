# Auto SQL Review Skill — 设计规格书 V2

> **状态**：需求澄清阶段 ✅（已确认）| **最后更新**：2026-07-29

---

## 目录

1. [概述与定位](#1-概述与定位)
2. [使用场景总览](#2-使用场景总览)
3. [场景详细输入/输出规格](#3-场景详细输入输出规格)
4. [MVP 优先级划分](#4-mvp-优先级划分)
5. [不应支持的场景](#5-不应支持的场景)
6. [失败降级处理策略](#6-失败降级处理策略)
7. [关键架构决策记录 ✅](#7-关键架构决策记录-)
8. [SQL 审查规则文件](#8-sql-审查规则文件)

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

### 1.3 设计原则

| 原则 | 说明 |
|------|------|
| **独立性** | 全新 Skill，不依赖已有 `sql-review` 或 `code-trace-analyzer`。如有复用点，在详细设计阶段再评估 |
| **渐进降级** | 任何子步骤失败不应导致全局失败；降级输出部分结果，标注信息丢失范围 |
| **规范驱动** | 静态 SQL 分析基于可配置的规则文件，禁止 AI 自由发挥式判断 |
| **真实路径优先** | 动态 SQL 必须基于调用链真实传参还原，不枚举所有可能的参数组合 |
| **必须 EXPLAIN** | 无论本地还是 CI 模式，只要数据库可用，必须执行 EXPLAIN。数据库不可用时降级为静态规则分析 |

### 1.4 术语定义

| 术语 | 定义 |
|------|------|
| **调用链** | Controller/API → Service → Mapper 接口 → Mapper XML → SQL 的完整静态追踪链路 |
| **真实 SQL** | 基于调用链中找到的实际传参值（如方法参数、常量），将 MyBatis 动态标签（`<if>`, `<foreach>` 等）拼接后的最终 SQL |
| **静态规则轨** | 基于预定义 SQL 审查规则文件的纯文本分析，不依赖数据库连接 |
| **动态执行轨** | 在数据库上执行 EXPLAIN，基于执行计划进行风险分析 |
| **短期止血方案** | 可立即上线、低风险的修复（如加索引、加 LIMIT、改写查询条件） |
| **中长期治理方案** | 需排期架构级修改（如拆表、读写分离、异步化） |

---

## 2. 使用场景总览

| 序号 | 场景名称 | 触发方式 | 优先级 |
|------|---------|---------|--------|
| S1 | **本地提交前自查** | 开发者主动调用，push 前检查本次改动 | P0 — MVP |
| S2 | **CI/CD MR 门禁** | MR 创建/更新时 CI pipeline 自动触发 | P0 — MVP |
| S3 | **代码审查辅助** | Reviewer 审查 MR 时手动触发 | P1 — 第二版 |
| S6 | **指定 Mapper/方法分析** | 开发者指定某个 Mapper 或方法聚焦分析 | P1 — 第二版 |

> **已排除**：S4（全仓库 SQL 健康巡检）、S5（线上慢 SQL 反向定位）不在当前 scope 内。

---

## 3. 场景详细输入/输出规格

### 3.1 S1 — 本地提交前自查

| 维度 | 规格 |
|------|------|
| **触发条件** | 开发者在 git 仓库中主动调用，如 "检查我的 SQL 变更" |
| **输入** | ① `git diff <base>..HEAD`（默认 `base=origin/master`）；② 可选：指定文件/Mapper 过滤范围；③ SQL 审查规则文件路径（可选，使用默认规则文件） |
| **输出** | JSON 格式详细报告 + 终端可读表格摘要 |
| **输出内容** | 每条风险 SQL：`sql_id`、`file_path`、`line`、`mapper_method`、`call_chain: [{class, method, line}]`（完整链路到 Controller）、`resolved_sql`（真实传参还原后的 SQL）、`risk_level`（HIGH / MEDIUM / LOW）、`risk_rule_id`（匹配的规则 ID）、`risk_desc`、`explain_result`、`short_term_fix`、`long_term_fix` |
| **分析深度** | 静态规则轨 + 动态执行轨（EXPLAIN 必执行，数据库不可用时降级为纯静态规则） + 完整调用链追踪（到 Controller） |
| **分析范围** | 不仅限于 MR diff 文件；为追踪新增 Mapper 方法的调用者，需扫描**当前项目分支全部代码** |
| **耗时预期** | ≤3 分钟 |
| **失败行为** | 见第 6 章降级策略 |

### 3.2 S2 — CI/CD MR 门禁

| 维度 | 规格 |
|------|------|
| **触发条件** | MR 创建/更新 webhook → CI pipeline 自动执行 |
| **输入** | ① MR source/target 分支（GitLab/GitHub）；② 门禁阈值配置（默认 `HIGH ≥ 1 → BLOCK`，`MEDIUM ≥ 1 → BLOCK`）；③ SQL 审查规则文件路径（可选） |
| **输出** | ① **门禁结论**：PASS（通过）/ BLOCK（拦截）；② JSON 格式详细报告；③ 自动发布到 MR 的结构化评论（表格格式） |
| **门禁逻辑** | `HIGH ≥ 1` 或 `MEDIUM ≥ 1` → **BLOCK**（激进策略，宁可误拦也不漏放） |
| **分析深度** | 静态规则轨（必选）+ 动态执行轨（EXPLAIN 必执行，数据库不可用时降级为纯静态规则） + 完整调用链追踪 |
| **分析范围** | 同 S1：MR diff + 当前项目分支全部代码（追踪调用者） |
| **耗时预期** | 5–15 分钟（含 EXPLAIN 执行） |
| **特殊处理** | 如果变更文件不包含 `*Mapper.xml` 或 `*Mapper.java`，直接返回 PASS，跳过分析 |

### 3.3 S3 — 代码审查辅助

| 维度 | 规格 |
|------|------|
| **触发条件** | Reviewer 在审查 MR 时手动触发，提供 MR 链接 |
| **输入** | GitLab/GitHub MR 链接 |
| **输出** | 与 S1 相同格式的详细报告，增加 reviewer 视角标注（如 "新增查询缺少分页，疑似遗漏"） |
| **分析深度** | 与 S1 相同 |
| **耗时预期** | ≤3 分钟 |

### 3.4 S6 — 指定 Mapper/方法分析

| 维度 | 规格 |
|------|------|
| **触发条件** | 开发者指定某个 Mapper 类名或方法名进行聚焦分析 |
| **输入** | Mapper 全限定名（如 `com.example.mapper.UserMapper`）或方法名（如 `getUserById`） |
| **输出** | 该 Mapper/方法涉及的所有 SQL + 完整调用链 + 风险分析 + 分级建议 |
| **分析深度** | 与 S1 相同 |
| **耗时预期** | ≤1 分钟（范围小） |
| **与 S1 的区别** | 不依赖 git diff，直接分析指定范围的存量 SQL |

---

## 4. MVP 优先级划分

| 优先级 | 场景 | 原因 |
|--------|------|------|
| **P0 — V1.0** | S1 本地自查 | ① 不依赖外部系统（CI/GitLab），实现路径最短；② 开发者日常最高频使用；③ 能独立验证 Skill 的核心分析引擎是否有效 |
| **P0 — V1.0** | S2 CI MR 门禁 | ① 自动化的最大价值——阻止坏 SQL 合入，事后修复成本是事前拦截的 10–100 倍；② 有明确的成功标准（门禁通过率 vs 线上慢 SQL 率）；③ 倒逼分析引擎的准确率和覆盖率 |
| **P1 — V1.1** | S6 指定 Mapper 分析 | ① 复用 V1.0 的分析引擎，仅改变输入源；② 补充"非变更驱动"的分析场景，增强 Skill 的独立可用性 |
| **P1 — V1.1** | S3 审查辅助 | ① 需要 GitLab/GitHub API 集成，增加外部依赖；② Reviewer 体验打磨需要迭代（评论交互设计） |

---

## 5. 不应支持的场景

| 场景 | 原因 |
|------|------|
| **全仓库 SQL 健康巡检**（原 S4） | ① 全量分析耗时长（大型项目 1000+ SQL），远超单次 Skill 调用的合理范围；② 价值不如增量分析（变更驱动）直接——存量 SQL 通常在线上已验证过 |
| **线上慢 SQL 反向定位**（原 S5） | ① SQL 文本到代码的模糊匹配技术难度高（参数化差异、分库分表中间件改写）；② 适合作为独立的线上排障 Skill，与本 Skill 的"变更驱动 + 离线分析"定位不同 |
| **线上实时慢 SQL 监控** | 属于 APM/可观测性平台职责，不是代码审查工具 |
| **非 MyBatis 项目**（JPA/Hibernate/JOOQ） | ORM 的 SQL 生成机制完全不同，需要专门的运行时拦截方案，静态 Mapper XML 分析不适用 |
| **DDL 变更审查**（ALTER TABLE 等） | DDL 风险维度（锁表、数据迁移、回滚）与 DML 完全不同，需专门的 DBA 审核工具 |
| **SQL 业务语义正确性验证** | 需要业务上下文，静态分析无法判断"这个查询条件对不对" |

---

## 6. 失败降级处理策略

```
核心原则：渐进降级，不阻塞。宁可输出不完整的报告，也不什么都不输出。
```

| 失败场景 | 是否中断 | 降级策略 | 原因 |
|----------|---------|---------|------|
| **非 git 仓库 / 无法获取 base 分支** | ⚠️ 中断 | 提示用户：手动提供 base 分支名、文件列表，或直接粘贴变更内容 | git diff 是分析的起点，无此上下文无法继续 |
| **变更中无 Mapper 文件** | ✅ 优雅退出 | **Exit 0**。输出 "本次变更未检测到 SQL 变更" | 这是正常的边界情况，不是错误 |
| **Mapper XML 解析失败**（非标准格式、XML 语法错误） | ✅ 不中断 | ① 跳过该文件，标记 `PARSE_ERROR`；② 在报告末尾列出跳过的文件清单；③ 其余文件继续正常分析 | 部分文件失败不应阻塞整体流程 |
| **数据库连接失败**（MCP 不可用、权限不足、网络不通） | ✅ 不中断 | ① **降级为纯静态规则模式**；② 仅基于 SQL 审查规则文件进行分析；③ 报告标注 `⚠️ 数据库不可用，分析基于静态规则，未执行 EXPLAIN，可能遗漏索引相关风险` | 静态规则仍能发现大量风险。**关键约束**：静态分析必须基于预定义的规则文件，禁止 AI 自由发挥判断 |
| **EXPLAIN 执行失败**（单条 SQL 语法错误、表不存在等） | ✅ 不中断 | ① 该条 SQL 标记 `EXPLAIN_FAILED`，降级为仅静态规则分析；② 标注失败原因；③ 其余 SQL 继续执行 EXPLAIN | 个例失败不影响整体 |
| **调用链追踪断裂**（反射、动态代理、AOP 导致无法继续） | ✅ 不中断 | ① 追踪到的部分链路保留，断裂处标注 `→ [动态调用，静态追踪终止]`；② 该 SQL 的 `call_chain_complete` 标记为 `false`；③ 真实 SQL 还原可能不完整（部分动态参数无法确定），降级为分析 XML 中能确定的 SQL 部分；④ 列出无法确定的动态条件，供人工审查 | 调用链是增强信息，部分链路优于无链路 |
| **LLM 分析超时 / 输出格式异常** | ✅ 不中断 | ① 该批次标记 `ANALYSIS_FAILED`；② 输出故障批次清单；③ 其余批次继续分析。最终报告格式：`成功分析 X 条，失败 Y 条（详见 error_list）` | 部分失败优于全量失败 |
| **单条 SQL 分析超时**（极长 SQL 或复杂 EXPLAIN） | ✅ 不中断 | 跳过该 SQL，标记 `TIMEOUT`，记录在报告的 skipped 清单中 | 个别异常 SQL 不应拖垮整体流程 |
| **报告生成失败**（JSON 序列化异常等） | ⚠️ 中断 | 将已分析的原始数据写入 `/tmp/auto_sql_review_dump_{timestamp}.json`，提示用户手动查看 | 已分析数据不应丢失，这是最后的兜底 |

### 6.1 动态 SQL 处理：真实路径还原

动态 SQL **不会**枚举所有分支组合，而是基于调用链还原真实执行的 SQL：

```
步骤：
1. 从调用链中找到 Mapper 方法的实际调用者（Service 层）
2. 从调用者代码中提取传入 Mapper 方法的参数值/变量名
3. 沿调用链向上追溯到 Controller 层，确定原始入参
4. 基于原始入参值，判断 MyBatis 动态标签（<if>, <foreach>, <choose>）中哪些条件为真
5. 拼接得到最终实际执行的 SQL
6. 对这条最终 SQL 执行风险分析

示例：
  Controller.getUsersByRole("admin", ["id", "name"])
    → Service.queryUsers("admin", ["id", "name"])
      → Mapper.selectUsers(role="admin", columns=["id", "name"], orderBy=null)

  对于 <if test="orderBy != null">ORDER BY ${orderBy}</if>
  orderBy=null → 条件不激活 → 最终 SQL 不含 ORDER BY
```

### 6.2 新增 Mapper 方法的调用者追踪

当 MR 中新增了一个 Mapper 方法时，该方法的调用者可能：
- 在同一 MR 中的新 Service/Controller 文件中 → 属于 MR diff 范围，可直接追踪
- 在 MR diff 之外的项目已有代码中 → **需要扫描当前项目分支的全部代码**

**策略**：分析范围 = MR diff 文件 ∪ 当前项目分支全部 Java 代码。以满足"调用链必须到 Controller 层"的要求。

---

## 7. 关键架构决策记录 ✅

### 7.1 动态 SQL 处理策略 ✅

| 决策 | **基于调用链真实传参还原最终 SQL** |
|------|------|
| **排除方案** | 枚举所有动态分支组合 |
| **原因** | ① 枚举组合会产生大量无效 SQL（实际从不执行的路径）；② 真实风险只存在于实际执行的 SQL；③ 与"定位到具体调用链路"的产品定位一致 |

### 7.2 EXPLAIN 执行策略 ✅

| 决策 | **每次必须执行 EXPLAIN（数据库可用时）** |
|------|------|
| **排除方案** | 快速模式（仅静态规则）、可选 EXPLAIN |
| **原因** | ① 仅做静态规则检查意义不大——缺失索引、全表扫描等核心风险必须通过 EXPLAIN 发现；② 静态规则能发现的"SELECT *"、"缺失 LIMIT"等问题，EXPLAIN 能给出更精确的影响面数据（扫描行数）；③ CI 门禁的核心价值就在于深度检查，浅层检查不应成为门禁的一部分 |
| **降级逻辑** | 数据库不可用时，降级为纯静态规则，并在报告中明确标注信息丢失范围 |

### 7.3 调用链追踪深度 ✅

| 决策 | **必须追踪到 Controller/API 层** |
|------|------|
| **理由** | ① 只有到 Controller 层才能确定 HTTP 请求的原始入参，从而准确还原动态 SQL；② 调用链越完整，SQL 的"责任方"越清晰；③ 为后续的"线上慢 SQL 反向定位"预留能力 |
| **局限处理** | 反射、动态代理、AOP 导致链路断裂时，标注断裂点，输出已追踪部分 |

### 7.4 分析范围 ✅

| 决策 | **MR diff 文件 + 当前项目分支全部 Java 代码** |
|------|------|
| **理由** | 追踪新增 Mapper 方法的调用者需要扫描项目全量代码；MR diff 范围不足以覆盖所有调用者 |
| **排除方案** | 仅分析 MR diff 文件 |

### 7.5 静态分析规范驱动 ✅

| 决策 | **静态 SQL 分析必须基于预定义的审查规则文件** |
|------|------|
| **规则文件格式** | 待设计（详见第 8 章）；至少包含：规则 ID、规则名称、风险等级、匹配模式（正则/AST）、风险描述模板、短期建议模板、中长期建议模板 |
| **禁止行为** | AI 不得脱离规则文件自由判断 SQL 是否有风险 |
| **原因** | ① 可审计：基于同一份规则，结果可复现；② 可定制：不同团队维护各自规则文件；③ 可扩展：新增规则只需编辑文件 |

### 7.6 CI 门禁阈值 ✅

| 决策 | **激进门禁：HIGH ≥ 1 → BLOCK，MEDIUM ≥ 1 → BLOCK** |
|------|------|
| **排除方案** | 宽松门禁（HIGH≥3/5 → BLOCK，MEDIUM 仅告警） |
| **原因** | ① 宁可误拦让开发者确认，也不漏放一条高危 SQL 到生产；② HIGH 和 MEDIUM 都代表可量化的性能风险，PASS 仅代表分析未发现问题；③ 激进门禁倒逼开发者在本地阶段就完成自查（S1） |

### 7.7 SQL 审查规则文件来源 ✅

| 决策 | **由 Skill 设计者起草通用规范作为默认规则文件，用户可追加团队/项目专用规则** |
|------|------|
| **原因** | ① 零配置即可用（默认规则覆盖 80% 常见风险）；② 可扩展（团队追加自己的规范）；③ 规则文件独立于 Skill 代码，便于版本管理和分享 |

---

## 8. SQL 审查规则文件

### 8.1 设计目标

- 作为静态规则轨的唯一分析依据
- 规则文件独立于 Skill 代码，用户可编辑、追加、分享
- 每一条规则明确：匹配什么 SQL 模式、风险等级、修复建议

### 8.2 规则文件格式草案

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
      "risk_level": "MEDIUM",
      "category": "字段选择",
      "description": "使用 SELECT * 而非显式指定列名，可能导致：① 返回不必要的列，增加网络传输和内存开销；② 无法利用覆盖索引优化；③ 表结构变更时结果集不可预期",
      "match": {
        "type": "regex",
        "pattern": "(?i)\\bSELECT\\s+\\*\\s+FROM\\b"
      },
      "short_term_fix": "将 SELECT * 改为显式列出所需字段",
      "long_term_fix": "在 DAO 层统一规范：禁止使用 SELECT *，所有查询方法必须显式指定字段列表"
    },
    {
      "rule_id": "R002",
      "name": "查询缺失 LIMIT",
      "risk_level": "HIGH",
      "category": "结果集控制",
      "description": "SELECT 查询未使用 LIMIT 子句，可能导致：① 一次性加载全表数据，内存溢出；② 网络传输大量无用数据",
      "match": {
        "type": "regex",
        "pattern": "(?i)\\bSELECT\\b(.(?!\\bLIMIT\\b))*\\bFROM\\b",
        "negative_logic": true
      },
      "exceptions": [
        "聚合查询（含 COUNT/SUM/AVG/MAX/MIN 等）",
        "含 GROUP BY 的统计分析查询",
        "明确需要全量数据的后台任务（需代码注释说明）"
      ],
      "short_term_fix": "在 SQL 末尾添加 LIMIT 子句，根据业务需求设置合理的返回行数上限",
      "long_term_fix": "评估查询是否需要分页重构；对于确实需要全量数据的场景，在代码中显式标注原因"
    },
    {
      "rule_id": "R003",
      "name": "LIKE 左模糊/全模糊查询",
      "risk_level": "HIGH",
      "category": "索引使用",
      "description": "LIKE '%xxx' 或 LIKE '%xxx%' 以通配符开头，导致无法使用 B-Tree 索引，退化为全表扫描",
      "match": {
        "type": "regex",
        "pattern": "(?i)\\bLIKE\\s+['\"]%"
      },
      "short_term_fix": "如果业务允许，移除前置通配符改为 LIKE 'xxx%'；或使用全文索引（FULLTEXT）替代",
      "long_term_fix": "评估是否应引入 Elasticsearch 等搜索引擎处理模糊匹配场景"
    },
    {
      "rule_id": "R004",
      "name": "对索引列使用函数或表达式",
      "risk_level": "HIGH",
      "category": "索引使用",
      "description": "WHERE 条件中对索引列使用函数（如 DATE(create_time)、LOWER(name)）或表达式（如 price*1.1），导致索引失效",
      "match": {
        "type": "regex",
        "pattern": "(?i)\\bWHERE\\b.*(DATE\\(|YEAR\\(|MONTH\\(|DAY\\(|LOWER\\(|UPPER\\(|SUBSTR(ING)?\\(|CONCAT\\()"
      },
      "short_term_fix": "改写查询条件，避免在索引列上使用函数。如 DATE(create_time) = '2026-01-01' → create_time >= '2026-01-01' AND create_time < '2026-01-02'",
      "long_term_fix": "① 新增函数索引（MySQL 8.0+）或生成列；② 代码规范：禁止在 WHERE 条件下对索引列使用函数"
    },
    {
      "rule_id": "R005",
      "name": "隐式类型转换",
      "risk_level": "MEDIUM",
      "category": "索引使用",
      "description": "WHERE 条件中字符串列与数字比较（如 WHERE phone = 13800138000），MySQL 会将字符串列转为数字，导致索引失效",
      "match": {
        "type": "regex",
        "pattern": "(?i)\\bWHERE\\b.*\\w+\\s*=\\s*\\d+"
      },
      "short_term_fix": "给数字参数加引号，确保类型匹配（如 WHERE phone = '13800138000'）",
      "long_term_fix": "① 代码规范：传入 SQL 的参数必须与列类型一致；② 对于 MyBatis，检查 Mapper 接口参数类型与 XML 中字段类型是否匹配"
    },
    {
      "rule_id": "R006",
      "name": "大表 JOIN 缺少驱动表优化",
      "risk_level": "MEDIUM",
      "category": "JOIN 优化",
      "description": "多表 JOIN 查询，需通过 EXPLAIN 确认驱动表选择和 JOIN 顺序是否合理",
      "match": {
        "type": "regex",
        "pattern": "(?i)\\bJOIN\\b.*\\bJOIN\\b"
      },
      "requires_explain": true,
      "short_term_fix": "根据 EXPLAIN 结果调整 JOIN 顺序，小结果集驱动大结果集",
      "long_term_fix": "① 评估是否可以通过拆解查询 + 应用层组装替代复杂 JOIN；② 考虑反范式化设计减少 JOIN"
    },
    {
      "rule_id": "R007",
      "name": "异步/批量场景缺失分页",
      "risk_level": "HIGH",
      "category": "结果集控制",
      "description": "在循环或定时任务中执行的查询缺少分页，当数据量增长时可能导致 OOM 或长时间持锁",
      "match": {
        "type": "context_aware",
        "pattern": "需要在调用链中识别 Mapper 方法是否在循环体（for/while）或定时任务（@Scheduled）中被调用"
      },
      "short_term_fix": "为查询添加 LIMIT 分页，分批处理数据",
      "long_term_fix": "引入游标分页（基于主键或时间戳），避免 OFFSET 方式在大数据量下性能退化"
    },
    {
      "rule_id": "R008",
      "name": "NOT IN 子查询",
      "risk_level": "MEDIUM",
      "category": "子查询优化",
      "description": "NOT IN 子查询：① 当子查询结果含 NULL 时，整个 NOT IN 返回空（语义陷阱）；② 大结果集时性能极差",
      "match": {
        "type": "regex",
        "pattern": "(?i)\\bNOT\\s+IN\\s*\\(\\s*SELECT\\b"
      },
      "short_term_fix": "① 改为 NOT EXISTS 替代；② 或使用 LEFT JOIN ... WHERE ... IS NULL 模式",
      "long_term_fix": "代码规范：禁止使用 NOT IN + 子查询，统一使用 NOT EXISTS 模式"
    },
    {
      "rule_id": "R009",
      "name": "ORDER BY 使用文件排序",
      "risk_level": "MEDIUM",
      "category": "排序优化",
      "description": "ORDER BY 的列没有匹配的索引，EXPLAIN 中 Using filesort 表示需要额外排序操作",
      "match": {
        "type": "regex",
        "pattern": "(?i)\\bORDER\\s+BY\\b"
      },
      "requires_explain": true,
      "short_term_fix": "① 为 ORDER BY 列建立索引；② 或利用 WHERE 条件已有的索引来避免额外排序",
      "long_term_fix": "评估排序是否可以在应用层完成；或设计复合索引同时覆盖 WHERE 和 ORDER BY"
    },
    {
      "rule_id": "R010",
      "name": "FOR UPDATE 范围过大",
      "risk_level": "HIGH",
      "category": "锁相关",
      "description": "SELECT ... FOR UPDATE 如果没有精准的索引条件，可能锁定过多行甚至全表，导致锁等待和死锁",
      "match": {
        "type": "regex",
        "pattern": "(?i)\\bFOR\\s+UPDATE\\b"
      },
      "short_term_fix": "确保 FOR UPDATE 的 WHERE 条件命中唯一索引或高选择性索引",
      "long_term_fix": "① 评估是否可以用乐观锁替代悲观锁；② 缩小事务范围，将 FOR UPDATE 放在事务的末尾执行"
    }
  ]
}
```

### 8.3 规则分类

| 分类 | 典型规则 | 风险侧重 |
|------|---------|---------|
| **字段选择** | SELECT * | 网络/内存开销 |
| **结果集控制** | 缺失 LIMIT、批量操作无分页 | OOM、长事务 |
| **索引使用** | 左模糊 LIKE、函数包裹索引列、隐式类型转换 | 全表扫描 |
| **JOIN 优化** | 多表 JOIN 缺少驱动表优化 | 嵌套循环扫描 |
| **子查询优化** | NOT IN 子查询 | 语义陷阱 + 性能 |
| **排序优化** | ORDER BY 文件排序 | 额外排序开销 |
| **锁相关** | FOR UPDATE 范围过大 | 锁等待、死锁 |

### 8.4 规则扩展机制

用户可在默认规则文件基础上追加自定义规则：

1. 复制默认规则文件到项目目录
2. 在 `rules` 数组中追加新规则
3. 或修改已有规则的 `risk_level` / `short_term_fix` / `long_term_fix`
4. 通过 Skill 调用的参数指定自定义规则文件路径

---

## 附录 A：变更记录

| 版本 | 日期 | 变更内容 |
|------|------|---------|
| V1 | 2026-07-29 | 初始版本：场景定义、MVP 划分、降级策略、架构决策记录（含 5 个待确认问题） |
| V2 | 2026-07-29 | **全部待确认问题已收口**：① EXPLAIN 必须执行（移除快速模式）；② 调用链必须到 Controller 层；③ 分析范围 = MR diff + 项目分支全量代码；④ 默认规则文件由设计者起草；⑤ CI 门禁激进策略（HIGH≥1 且 MEDIUM≥1 → BLOCK）；⑥ 新增第 8 章 SQL 审查规则文件 |

## 附录 B：下一步计划

1. ~~需求澄清~~ ✅ 已完成
2. **待用户发起** → 进入详细设计阶段：
   - 分阶段分析 pipeline 流程设计
   - 调用链追踪算法流程定义
   - 动态 SQL 还原方案详细设计
   - EXPLAIN 执行及结果解析流程
   - 输出报告格式（JSON Schema）定义
