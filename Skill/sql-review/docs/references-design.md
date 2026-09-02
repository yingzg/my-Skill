# Auto SQL Review — references/ 规则文件设计

> 定义 references/ 下每个文件的职责边界、被谁消费、以及扩展策略。

---

## 一、文件清单与路由

| 文件 | 类型 | 消费者 | 消费方式 | Phase |
|------|:---:|------|:---:|:---:|
| `rules/rules.json` | JSON | `match_rules.py` | 脚本加载 → 正则/模式匹配 | 4a |
| `rules/rules.json` | JSON | LLM Prompt | 注入 Prompt → LLM 参考规则语义做风险定性 | 4b |
| `explain-guide.md` | Markdown | LLM Prompt | 注入 Prompt → LLM 学习如何读 EXPLAIN | 4b |
| `degradation-matrix.md` | Markdown | SKILL.md | 编排层读取 → 决定降级还是中断 | 0~5 |
| `report-schema.md` | Markdown | `build_report.py` | 脚本加载 → 校验输出格式 | 5 |
| `report-schema.md` | Markdown | LLM Prompt | 注入 Prompt → LLM 按 Schema 输出 | 4b |

---

## 二、每个文件的详细设计

---

### 2.1 `rules/rules.json` — 静态 SQL 审查规则

#### 解决什么问题

告诉 `match_rules.py`「检查什么、怎么检查、命中后定什么级」。同时作为 LLM 的参考知识，让 LLM 在 Phase 4b 写出与规则体系一致的风险描述。

#### 谁用

| 消费者 | 怎么用 |
|--------|--------|
| `match_rules.py`（Phase 4a） | 加载 JSON → 遍历每条规则 → 对每条 SQL 执行 `pattern` 匹配 → 输出命中列表 |
| LLM Prompt（Phase 4b） | 将命中的规则描述注入 Prompt 上下文 → LLM 据此写 `rationale.static_rules` |

> **关键区分**：`match_rules.py` 消费规则的 `pattern` 字段（机械匹配），LLM 消费规则的 `name` / `description` / `risk_level` 字段（语义理解）。同一个文件，两种消费方式。

#### 应该包含

- 每条规则的唯一 ID、中文名、分类
- 匹配模式（正则或静态检测逻辑的标识符）
- 风险等级 + 适用 SQL 类型（`applicable_to`）
- 默认修复建议模板
- 规则的版本号和更新日志

#### 不应该包含

- ❌ EXPLAIN 相关的判断阈值（属于 `explain-guide.md`）
- ❌ 降级决策逻辑（属于 `degradation-matrix.md`）
- ❌ LLM 的 prompt 模板（属于 SKILL.md）
- ❌ 数据库方言相关的连接串、驱动名（属于脚本逻辑）
- ❌ 业务相关的表名、字段名白名单（这是项目级配置，不属于通用规则）

#### 初始目录和结构

```
references/
└── rules/
    └── rules.json          ← MVP 阶段一个文件即可
```

```jsonc
{
  "meta": {
    "version": "1.0.0",
    "name": "通用 SQL 性能审查规则",
    "description": "适用于 Java/MyBatis + MySQL 项目的默认规则集",
    "last_updated": "2026-07-29",
    "compatibility": {
      "min_skill_version": "1.0.0",
      "db_types": ["mysql"]
    }
  },

  "rules": [
    {
      // ═══ 标识 ═══
      "id": "R001",
      "name": "SELECT * 检测",
      "category": "字段选择",

      // ═══ 适用范围 ═══
      "applicable_to": ["SELECT"],
      "db_types": ["mysql"],

      // ═══ 风险等级 ═══
      "risk_level": "MEDIUM",
      // 同一规则对不同 SQL 类型的风险等级可不同
      "severity_by_type": {},

      // ═══ 匹配方式 ═══
      "match": {
        "method": "regex",
        "pattern": "(?i)\\bSELECT\\s+\\*\\s+FROM\\b"
      },

      // ═══ 描述与修复建议（LLM 消费） ═══
      "description": "使用 SELECT * 而非显式列出所需字段。会导致：1) 传输不必要的数据 2) 无法利用覆盖索引 3) 表结构变更时结果集不可控",
      "short_term_fix_template": "将 SELECT * 改为显式列出业务需要的字段",
      "long_term_fix_template": "在团队的 DAO 层编码规范中禁止 SELECT *，Code Review 阶段卡点"
    },

    {
      "id": "R010",
      "name": "WHERE 子句 OR 条件",
      "category": "查询结构",
      "applicable_to": ["SELECT", "UPDATE", "DELETE"],
      "db_types": ["mysql"],
      "risk_level": "MEDIUM",
      "severity_by_type": {
        "UPDATE": "HIGH",
        "DELETE": "HIGH"
      },
      "match": {
        "method": "regex",
        "pattern": "(?i)\\bWHERE\\b.+\\bOR\\b"
      },
      "description": "WHERE 子句中使用 OR 条件，可能导致优化器放弃索引而选择全表扫描。对于 UPDATE/DELETE 尤为危险",
      "short_term_fix_template": "将 OR 改写为 UNION ALL 或 IN 查询",
      "long_term_fix_template": "评估是否需要在 OR 涉及的列上建立复合索引"
    },

    {
      "id": "R101",
      "name": "缺失软删除状态守卫",
      "category": "数据安全",
      "applicable_to": ["UPDATE", "DELETE"],
      "db_types": ["mysql"],
      "risk_level": "HIGH",
      "match": {
        "method": "static",
        "check": "missing_status_guard"
        // 脚本内置逻辑：检查 WHERE 中是否含 status_code / is_deleted 条件
      },
      "description": "UPDATE/DELETE 缺少 status_code = 0 或 is_deleted = 0 条件，可能修改已被软删除的数据",
      "short_term_fix_template": "添加 AND status_code = 0 到 WHERE 子句",
      "long_term_fix_template": "在 BaseMapper 层引入拦截器，自动附加软删除条件"
    }
  ]
}
```

#### 规则字段说明

| 字段 | 谁用 | 说明 |
|------|:---:|------|
| `id` / `name` / `category` | 脚本 + LLM | 规则标识和分组 |
| `applicable_to` | 脚本 | 该规则对哪些 SQL 类型生效。脚本据此过滤——SELECT 规则不会对 UPDATE 执行匹配 |
| `risk_level` | 脚本 + LLM | 默认风险等级。当 `severity_by_type` 有覆盖值时，按覆盖值 |
| `severity_by_type` | 脚本 | 按 SQL 类型微调等级。如 OR 条件对 SELECT 是 MEDIUM，对 DELETE 是 HIGH |
| `match.method` | 脚本 | `regex`（正则匹配 SQL 文本）/ `static`（脚本内置检测逻辑） |
| `match.pattern` | 脚本 | 正则表达式（`method=regex` 时）或检测标识符（`method=static` 时） |
| `description` | LLM | 规则的详细说明，注入 Phase 4b Prompt，帮助 LLM 写出准确的 `rationale` |
| `short_term_fix_template` | LLM | 短期修复建议模板，LLM 根据上下文填充具体信息 |
| `long_term_fix_template` | LLM | 长期治理建议模板 |

---

### 2.2 `explain-guide.md` — EXPLAIN 解读指南

#### 解决什么问题

教 LLM 如何解读 EXPLAIN 输出。LLM 拿到结构化 EXPLAIN 结果后，参照这份指南判断「这个执行计划是否存在风险、风险等级是什么。

#### 谁用

| 消费者 | 怎么用 |
|--------|--------|
| LLM Prompt（Phase 4b） | 全文注入 Prompt 上下文 |

#### 应该包含

- EXPLAIN 各字段（type / key / rows / Extra）的含义
- 风险判断阈值（如 `rows > 10000` 视为全量扫描、`type=ALL` 直接 HIGH）
- MySQL 特有问题（如 filesort、temporary table、index merge 的坑）
- 多表 JOIN 的执行计划解读方法

#### 不应该包含

- ❌ 具体的修复代码（修复由 LLM 生成，不是指南教的）
- ❌ 规则匹配逻辑（属于 `rules.json`）
- ❌ 数据库连接的配置信息

#### 初始结构

```markdown
# EXPLAIN 输出解读指南

## 一、核心字段速查

### type（访问类型）
| type | 含义 | 风险 | 说明 |
|------|------|:---:|------|
| ALL | 全表扫描 | HIGH | 除非表 < 1000 行，否则必须优化 |
| index | 全索引扫描 | MEDIUM | 扫描整个索引树 |
| range | 索引范围扫描 | LOW | 正常 |
| ref | 非唯一索引查找 | LOW | 正常 |
| eq_ref | 唯一索引查找 | LOW | 正常 |
| const | 主键/唯一键等值 | LOW | 最优 |

### rows（预估扫描行数）
| rows | 风险 | 说明 |
|------|:---:|------|
| > 100000 | HIGH | 大量扫描 |
| 10000 ~ 100000 | MEDIUM | 视表大小而定 |
| < 10000 | LOW | 正常 |

### Extra（额外信息）
| 值 | 含义 | 风险 |
|----|------|:---:|
| Using filesort | 额外排序操作，无法用索引排序 | MEDIUM |
| Using temporary | 使用了临时表 | MEDIUM-HIGH |
| Using index | 覆盖索引，只读索引不回表 | ✅ 最佳 |
| Using where | 使用了 WHERE 过滤 | 正常 |

## 二、综合风险判定

### 严重问题（直接 HIGH）:
- type=ALL + rows > 10000
- Using temporary + 大表
- 多表 JOIN 中驱动表 type=ALL

### 一般问题（MEDIUM）:
- Using filesort（索引不含排序列）
- 未使用索引（key=NULL）但 rows 较少
- possible_keys 有更好的索引但优化器选了差的

### 正常（LOW）:
- 所有其他情况

## 三、MySQL 特有坑
...
```

---

### 2.3 `degradation-matrix.md` — 降级决策矩阵

#### 解决什么问题

SKILL.md 编排层在每一步脚本/LLM 调用失败时需要做决策：降级继续还是中断。这个文件提供标准化的决策依据。

#### 谁用

| 消费者 | 怎么用 |
|--------|--------|
| SKILL.md（编排层） | 每次脚本/LLM 返回非零 exit code 时，查表决定下一步 |

#### 应该包含

- 每种失败场景的决策（降级 / 中断）
- 降级后的替代方案
- 复查清单记录内容

#### 不应该包含

- ❌ 具体的错误处理代码（属于 SKILL.md 或脚本内部）
- ❌ 规则匹配逻辑

#### 初始结构

```markdown
# 降级决策矩阵

## 决策速查表

| 失败场景 | Phase | 决策 | 后续行为 | 复查清单 |
|---------|:---:|:---:|---------|:---:|
| 非 git 仓库 | 0 | 中断 | 提示用户 | - |
| 无 Mapper 变更 | 0 | 优雅退出 | exit 0 | - |
| XML 解析失败 | 1 | 降级 | 跳过该文件 | parse_error |
| 数据源发现失败 | 0.5 | 降级 | 标记 UNKNOWN，跳过 EXPLAIN | datasource_unknown |
| 数据库连接失败 | 4b | 降级 | 纯静态规则模式 | explain_unavailable |
| EXPLAIN 单条失败 | 4b | 降级 | 该条 SQL 标记 explain_executed=false | explain_unavailable |
| 调用链断裂 | 2 | 降级 | 标注断裂原因，LLM 保守判断 | call_chain_broken |
| 参数不确定 | 3 | 降级 | LLM 最坏假设 | param_uncertain |
| LLM 超时 | 4b | 降级 | 该批次标记 ANALYSIS_FAILED | llm_timeout |
| 报告生成失败 | 5 | 中断 | dump 原始数据到 /tmp | - |

## 降级 vs 中断的判断原则

中断（⚠️）条件：
- 继续执行毫无意义（如非 git 仓库）
- 最终结果完全不可信（如全部脚本崩溃）
- 无法输出任何可用的报告

降级（✅）条件：
- 仍有部分 SQL 可以正常分析
- 虽然不完整，但输出的报告仍有参考价值
- 可以事后通过复查清单弥补
```

---

### 2.4 `report-schema.md` — 输出格式规范

#### 解决什么问题

1. `build_report.py` 用这个文件校验最终报告的字段和格式
2. LLM 在 Phase 4b 输出 `risk.json` 时，用这个文件约束输出格式

#### 谁用

| 消费者 | 怎么用 |
|--------|--------|
| `build_report.py`（Phase 5） | 读取 → 校验 `risk.json` 的字段 → 组装报告 |
| LLM Prompt（Phase 4b） | 注入 Prompt → LLM 按字段输出 |

#### 应该包含

- `risk.json` 的输出字段定义
- 每个字段的类型、必填、可选值
- 风险等级的枚举定义和判定标准
- 输出示例

#### 不应该包含

- ❌ 报告的渲染模板（属于 `assets/`）
- ❌ 具体的规则内容

---

## 三、规则文件的扩展策略

### 什么时候拆分？

```
rules.json < 100 条规则 → 单文件，够用

rules.json > 100 条规则 → 按以下维度拆分：
```

#### 拆分维度

```
references/rules/
├── rules.json              ← 索引文件：声明有哪些子文件、加载顺序
├── rules-select.json       ← SELECT 专属规则
├── rules-dml.json          ← UPDATE/DELETE 专属规则
├── rules-ddl.json          ← DDL 专属规则（未来）
├── rules-mysql.json        ← MySQL 方言规则
└── rules-sqlserver.json    ← SQL Server 方言规则（未来）
```

#### 索引文件结构

```jsonc
{
  "meta": { "version": "2.0.0" },
  "includes": [
    { "file": "rules-select.json", "applicable_to": ["SELECT"] },
    { "file": "rules-dml.json",    "applicable_to": ["UPDATE", "DELETE"] },
    { "file": "rules-mysql.json",  "db_types": ["mysql"] }
  ]
}
```

`match_rules.py` 启动时读索引文件 → 按 `applicable_to` 和 `db_types` 加载需要的子文件 → 合并为一个规则列表。

### 为什么按 SQL 类型 + 数据库方言拆分？

- `match_rules.py` 运行时可只加载当前场景需要的规则子集（SELECT 规则不加载给 DML、MySQL 规则不加载给 SQL Server）
- 不同团队的 DBA 可以维护自己负责的规则文件，减少合并冲突
- 新增数据库方言时不需要改已有规则

---

## 四、SKILL.md 中的加载时机说明

SKILL.md 不需要写详细的规则内容，只需要声明「什么时候加载哪个文件」。

```markdown
## references 加载时机

### Phase 4a — 规则匹配阶段
match_rules.py 启动时:
  1. 加载 references/rules/rules.json（或索引文件）
  2. 按当前场景过滤规则（applicable_to + db_types）
  3. 对每条 SQL 执行匹配
  4. 输出 phase4a_rules.json

### Phase 4b — LLM 风险定性阶段
LLM Prompt 注入以下 references:
  1. references/rules/rules.json → 规则描述部分（不含 match 字段）
     注入方式: 提取 id + name + category + description + short_term_fix_template
     目的: 让 LLM 理解规则语义，写出与规则体系一致的 rationale
  2. references/explain-guide.md → 全文注入
     目的: 让 LLM 知道如何判定 EXPLAIN 风险等级
  3. references/report-schema.md → 输出字段定义部分
     目的: 约束 LLM 按指定 JSON Schema 输出

### 全局 — 降级决策
SKILL.md 编排层在每次脚本/LLM 返回非零 exit code 时:
  查询 references/degradation-matrix.md → 决定降级还是中断

### Phase 5 — 报告生成
build_report.py 启动时:
  加载 references/report-schema.md → 校验所有输入文件的字段
```

---

## 五、references/ 完整目录结构

```
references/
│
├── rules/
│   └── rules.json                 ← MVP 阶段：所有规则（< 100 条）
│   // 未来拆分：
│   // ├── rules-select.json
│   // ├── rules-dml.json
│   // └── rules-mysql.json
│
├── explain-guide.md               ← EXPLAIN 字段解读 + 风险阈值
├── degradation-matrix.md          ← 降级决策表
└── report-schema.md               ← 输出格式定义
```

> `references/` 下所有文件都是**纯数据和知识**，不含代码逻辑。修改规则不需要改脚本，修改阈值不需要改 Prompt 模板。
