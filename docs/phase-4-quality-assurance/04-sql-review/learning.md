# sql-review — 深度学习文档

> 对应 SKILL.md: `/mnt/d/测试项目/vibe-hubs/skill/sql-review/SKILL.md` (294行)
>
> 原实现仓库: `/mnt/d/测试项目/vibe-hubs/skill/sql-review/`

---

## 一、功能全景

### 一句话定位
**SQL 慢查询审查引擎** — 5 步流水线 + 三阶段分析（Phase 0/1/2）+ 代码级参数追踪 + 悲观最差路径策略，在上线前自动检测 SQL 性能风险。

### 核心流程

```
用户触发（sql-review / SQL 审查）
    ↓
Step 0: 自动更新检查（VERSION 对比 + 文件同步 + Codex patch）
    ↓
Step 1: 提取变更 SQL（extract_sql.py）
    ├─ git diff 对比当前分支 vs master/指定分支/HEAD~N
    ├─ 解析 MyBatis XML / Java 注解 / QueryWrapper
    ├─ 提取调用链（Controller → Service → Mapper）
    └─ 提取 @DS 注解（多数据源路由）
    ↓
Step 2: 加载提取结果 + 预查数据库上下文
    ├─ load_extract() 过滤出 SELECT/UPDATE
    ├─ try_pymysql_prefetch() 自动检测 DB 配置
    └─ 失败降级为无 DDL/EXPLAIN 模式
    ↓
Step 3: 分批 + 三阶段分析
    ├─ 3.1 分批（贪心聚类 + 大小限制 + prompt 预算）
    ├─ 3.2 每个 batch:
    │   ├─ Phase 0 (可选): LLM 调用链代码精选（长方法体 ≥30行触发）
    │   ├─ Phase 1: 确定性悲观基线 + LLM 校正
    │   │   ├─ 确定性：static/update/select 三类基线（无需 LLM）
    │   │   └─ LLM 校正：读调用链代码，7 种证据加回必传条件
    │   ├─ EXPLAIN 执行（pymysql 直连，自动去重，多数据源路由）
    │   └─ Phase 2: 最终风险评估（DDL + 行数 + EXPLAIN + 硬编码规则）
    └─ 3.3 保存报告 + 导出最差路径 SQL
    ↓
Step 4: 输出结果
    ├─ 全部 PASS → ✅ 简版输出
    └─ 有 HIGH/MEDIUM → 表格展示详情 + 最差路径 SQL 导出路径
    ↓
Step 5: IDEA 集成（可选，output_idea.py）
```

---

## 二、架构设计分析

### 2.1 文件分层架构

```
sql-review/
├── SKILL.md                   # 主控文件：5步流程 + 精确代码指令
├── VERSION                    # 版本号（自动更新比对）
├── install.py                 # 安装/裁剪工具
├── scripts/
│   ├── review_core.py         # ★ 共享核心（~2221行）：清洗/prompt构建/解析/分批/报告
│   ├── local_review.py        # 本地模式编排器（re-export + 多batch循环）
│   ├── extract_sql.py         # Git diff SQL 提取引擎（~1011行）
│   ├── db_executor.py         # pymysql 直连 + EXPLAIN 执行
│   ├── ci_review.py           # CI 模式入口
│   ├── output_idea.py         # IDEA 集成输出
│   └── kc_decrypt.py          # KeyCenter 密码解密
└── references/
    ├── sql-rules.md           # 团队 SQL 规范 + 17 条硬编码风险规则
    └── prompt-rules.md        # Prompt 结构 + 历史迭代 + 技术陷阱
```

**设计思想**: SKILL.md 是"操作手册"（精确到每行 Python 代码），review_core.py 是"共享引擎"（所有确定性逻辑），local_review.py 是"编排器"（组装 Phase 顺序 + 循环控制）。三权分立：流程定义（SKILL.md）、逻辑实现（review_core.py）、执行编排（local_review.py）。

### 2.2 三阶段分析架构（Phase 0 → Phase 1 → EXPLAIN → Phase 2）

这是整个 Skill 最核心的设计：

```
                    ┌─────────────────────────────┐
                    │     Phase 0: 代码精选 (LLM)    │
                    │  条件：方法体 ≥ 30 行           │
                    │  输入：完整方法体 + 横向调用      │
                    │  输出：key_code 精选代码          │
                    │  失败：降级为原始 snippet         │
                    └─────────────┬───────────────┘
                                  ↓ (精选后的 snippet)
                    ┌─────────────────────────────┐
                    │     Phase 1: 基线 + 校正       │
                    │  ┌───────────────────────┐  │
                    │  │ 确定性悲观基线（无 LLM）  │  │
                    │  │ · static: 占位符替换     │  │
                    │  │ · update: → SELECT 转换 │  │
                    │  │ · select: 多链悲观清洗   │  │
                    │  └───────────┬───────────┘  │
                    │              ↓               │
                    │  ┌───────────────────────┐  │
                    │  │ LLM 校正（仅动态 SELECT）│  │
                    │  │ · 7 种必传证据加回条件   │  │
                    │  │ · 链去重减少 prompt     │  │
                    │  │ · 合并策略：取条件更多   │  │
                    │  └───────────┬───────────┘  │
                    └─────────────┬───────────────┘
                                  ↓
                    ┌─────────────────────────────┐
                    │     EXPLAIN 执行 (pymysql)    │
                    │  · 相同 SQL 自动去重          │
                    │  · 多数据源 @DS 路由          │
                    │  · 失败降级继续               │
                    └─────────────┬───────────────┘
                                  ↓
                    ┌─────────────────────────────┐
                    │     Phase 2: 最终评估 (LLM)    │
                    │  输入：DDL + 行数 + EXPLAIN    │
                    │       + 硬编码规则 + SQL 数据  │
                    │  流程：EXPLAIN 分析 → 硬编码   │
                    │       规则检查 → JSON 报告     │
                    └─────────────────────────────┘
```

**关键设计决策**:
1. **Phase 0 是可选的前置优化** — 只对长方法体触发，解决调用链 snippet 被机械截断导致遗漏关键参数赋值的问题。短方法直接跳过。
2. **Phase 1 的确定性基线不受 LLM 幻觉影响** — 即使 LLM 响应失败或超时，悲观基线仍然存在，EXPLAIN 仍可执行。
3. **Phase 2 是唯一交付点** — 所有路径最终都汇聚到 Phase 2 产出 JSON 报告。

### 2.3 数据流

```
extract_sql.py                    review_core.py
─────────────                     ──────────────
git diff                          sql_list (list[dict])
  ↓                               ├─ sql_id, file, line_number
MyBatis XML 解析                  ├─ type: select/update
  ↓                               ├─ sql: 原始 MyBatis XML
Java 注解提取                     ├─ tables: 涉及的表名
  ↓                               ├─ call_chains: [{chain_id, layers}]
调用链追踪                          │   └─ layers: [{class_name, method, snippet, full_method_body}]
  ↓                               ├─ ds: @DS 数据源名
@DS 注解提取                       └─ mapper_params: @Param 名称列表
  ↓
sql_extract_result.json ────────→ load_extract() → sql_list
                                              ↓
                                   split_into_batches(sql_list, db_context)
                                              ↓
                                   batches: list[list[dict]]
                                              ↓
                                   每个 batch → Phase 0 → Phase 1 → EXPLAIN → Phase 2
                                              ↓
                                   all_reports: list[dict]
                                              ↓
                                   sql_review_report.json
```

---

## 三、设计模式深度分析

### 3.1 悲观最差路径策略 — 最重要的设计

这不是简单的"去掉所有 `<if>` 分支"，而是一个精细的多层悲观策略：

**第 1 层：MyBatis 动态标签清洗（review_core.py 第 109-160 行）**

```
clean_mybatis_sql_worst_case():
  ├─ <trim prefixOverrides="OR"> 块内的 <if> → 保留内容（OR 分支全命中 = 最差）
  ├─ 包含 LIMIT/OFFSET 的 <if> → 保留内容（分页参数通常有兜底值）
  ├─ 包含 JOIN 的 <if> → 保留内容（去掉 JOIN 让查询变轻，不是最差）
  └─ 其余 <if>（AND 连接）→ 去掉内容（最少条件 = 最差）
```

**第 2 层：确定性必传条件扫描（review_core.py 第 1776-2059 行）**

```
extract_select_worst_case_multi_chain():
  对每条调用链：
    1. 扫描 snippet 中无条件 setter（不在 if/三元内的 set* 调用）
    2. 扫描"null/empty 时赋默认值"模式
    3. 扫描 Mapper 方法直接传参（有 @Param 映射时按位置映射）
    4. 以上字段对应的 <if> 块 → 保留内容
    5. 其余 <if> 块 → 去掉内容
```

**第 3 层：LLM 校正加回条件（review_core.py 第 509-621 行）**

7 种必传证据 → 加回条件：
| 证据 | 描述 | 示例 |
|------|------|------|
| #1 | 显式断言 | `AssertUtil.check(xxx != null, ...)` |
| #2 | 抛异常中断 | `if (xxx == null) throw new BizException(...)` |
| #3 | 提前返回 | `if (xxx == null) return Collections.emptyList()` |
| #4 | 参数校验注解 | `@NotNull` + `@Validated` |
| #5 | 硬编码赋值 | `query.setStatus(0)`, `Collections.singletonList(x)` |
| #6 | 接口层强制 | `@PathVariable`, `@RequestParam`（无 required=false） |
| #7 | 默认值注入 | `Optional.ofNullable(x).orElse(default)` |

4 种可选证据 → 不加回（保持悲观）：
| 证据 | 描述 |
|------|------|
| #8 | request 直接透传无校验 |
| #9 | 条件赋值（if 判断后才 set） |
| #10 | BeanUtil 全量拷贝 |
| #11 | RpcContext 条件注入 |

**第 4 层：合并策略（review_core.py 第 2164-2193 行）**

```
merge_deterministic_and_llm():
  对每个 chain_id:
    ├─ 计数确定性基线的 WHERE AND 条件数
    ├─ 计数 LLM 校正的 WHERE AND 条件数
    └─ 取 AND 条件数更多的版本
```

这个四层策略的精妙之处：
- 第 1 层和第 2 层是确定性的（不依赖 LLM），保证下限
- 第 3 层是 LLM 驱动的，利用代码理解能力提升精度
- 第 4 层是安全阀，防止 LLM 校正比确定性基线更差
- 每层失败都可独立降级，不影响其他层

### 3.2 SQL 提取引擎

```
extract_sql.py（~1011 行）
├─ _resolve_ref(): 分支名 → origin/xxx, SHA → 原样, HEAD~N → 原样
├─ _diff_range(): 分支 → 三点 diff (...HEAD), SHA → 两点 diff (..HEAD)
├─ _ensure_base_reachable(): shallow clone 自动 unshallow
├─ get_changed_files(): git diff --name-only
├─ get_file_diff(): 提取新增行（+ 开头）
├─ _parse_sql_fragments(): 解析 <sql id="xxx"> 片段用于 include 展开
├─ XML 解析：
│   ├─ <select>/<update>/<insert>/<delete> 标签提取
│   ├─ <include refid="xxx"/> 展开（同文件）
│   └─ 动态标签识别（<if>/<choose>/<foreach>/<where>/<set>/<trim>）
├─ Java 注解提取：
│   ├─ @Select / @Update / @Insert / @Delete
│   └─ QueryWrapper（.eq/.in/.like 等链式调用）
├─ 调用链追踪：
│   ├─ 从 Mapper.java 方法出发
│   ├─ 搜索调用方（Service → ServiceImpl → Controller）
│   ├─ 提取每层完整方法体和 snippet
│   └─ 横向调用方法体提取（converter.normalize() 等）
├─ @DS 注解提取：Mapper.java 类级别 → 每条 SQL 的 ds 字段
└─ 输出：JSON（sql_list + project_root + 统计信息）
```

**设计亮点**:
- **三点 diff** 用于分支对比（只看分支分叉后的变更），**两点 diff** 用于 SHA 对比（精确范围）
- **shallow clone 自动修复** — CI 环境浅克隆时自动 `git fetch --unshallow`
- **include 展开** — 解析并内联 `<sql id="xxx">` 片段，避免后续清洗遗漏
- **调用链深度追踪** — 不只看直接调用方，而是追踪到 Controller 入口，获取完整参数传递路径
- **@DS 自动路由** — 从 MyBatis 注解提取数据源名，后续 EXPLAIN 自动路由到正确的数据库

### 3.3 Prompt 工程

**System Prompt**: 从 `sql-rules.md` 加载，包含团队规范 + 17 条硬编码风险规则 + JSON 输出格式。AI 在分析时必须遵守这些规则，不能自由裁量。

**Phase 0 Prompt**（代码精选）:
```
角色：Java 代码阅读专家
输入：每条调用链的完整方法体（长方法 ≥30行） + 横向调用方法体
任务：提取影响 SQL 查询参数的关键代码
输出：{chain_id: {ClassName.method: key_code}}
约束：宁多勿漏，不确定时保留
```

**Phase 1 Prompt**（LLM 校正）:
```
角色：MyBatis 动态 SQL 分析专家
输入：悲观基线 SQL + 完整调用链代码（Controller → Mapper）
任务：判断哪些被去掉的条件是确定必传的，加回
证据体系：7 种必传证据 + 4 种可选证据
约束：宁漏勿错，证据不充分时一律不加回
```

**Phase 2 Prompt**（最终评估）:
```
角色：MySQL 性能优化专家
输入：DDL + 行数 + EXPLAIN + 硬编码规则 + SQL 数据
任务：EXPLAIN 分析 → 硬编码规则逐条检查 → 输出 JSON 报告
约束：严格按硬编码规则，不可跳过任何规则
```

**Prompt 精简技术**:
1. **DDL 压缩**（`_compact_ddl`）: 去掉 ENGINE/CHARSET/COMMENT/AUTO_INCREMENT，从 ~3KB 降到 ~1KB
2. **SELECT 列压缩**（`_compress_select_columns`）: 保留聚合函数和 ORDER BY/GROUP BY 引用列，其余合并为一个计数
3. **Phase 2 精简**（`_slim_sql_list_for_phase2`）: 去掉调用方代码片段，只保留方法名路径
4. **横向调用摘要**（`_summarize_related_method`）: 只保留 set* 调用和断言/校验行

### 3.4 分批策略

```
split_into_batches(sql_list, db_context):
  1. _split_batches(sql_list, max_per_batch=15)
     ├─ 贪心聚类：按共享表将 SQL 聚到最小 batch
     └─ 二次拆分：单个 batch 超过 15 条强制切开
  2. _split_oversized_batches(batches, db_context, max_prompt_kb=40)
     ├─ 估算每个 batch 的 prompt 大小（SQL JSON + DDL + 固定开销）
     └─ 超限 batch 对半拆分，递归直到所有 batch 都在限制内
  3. _merge_small_batches(batches, min_per_batch=5, max_per_batch=15)
     └─ 尾部小 batch (<5条) 合并到前一个 batch，减少 API 调用次数
```

**设计目标**: 在以下三个约束中取得平衡：
- **质量**: 每个 batch 的 prompt 不能太大（≤40KB），否则 LLM 分析质量下降
- **成本**: 不能产生太多 batch（小 batch 合并），避免 API 调用次数过多
- **相关性**: 共享表的 SQL 放在同一 batch（贪心聚类），LLM 可关联分析

### 3.5 多链模式

```
单链模式（向后兼容）：sql_id → 一条 worst_case_sql
多链模式（当前主力）：sql_id → 多条调用链（chain_id），各自独立基线

示例：
  sqlId "getOrderList" 有 3 个调用入口：
    ├─ chain_0: Controller.api1() → Service.methodA() → Mapper.getOrderList()
    │   → 其中 countryCode 必传（断言校验）
    ├─ chain_1: Controller.api2() → Service.methodB() → Mapper.getOrderList()
    │   → 其中 countryCode 可选（透传无校验）
    └─ chain_2: Job.scheduledTask() → Service.methodC() → Mapper.getOrderList()
        → 其中 status 必传（硬编码 setStatus(1)）
  
  每条链独立分析，产出不同的 worst_case_sql，Phase 2 取最差的 EXPLAIN 结果。
```

**多链去重**（`dedup_phase1_chains`）:
- 代码片段指纹（MD5）
- 相同代码的链合并，只保留一条代表链送入 Phase 1
- LLM 校正结果展开回所有原始 chain_id
- 减少 prompt 大小和 LLM 开销

### 3.6 JSON 解析鲁棒性

LLM 输出的 JSON 可能不完整或有格式错误，`parse_llm_output` 实现了多层降级：

```
优先级 1: 从 ```json ``` 代码块提取 → _try_parse_json_array
          └─ 失败: _fix_json_unescaped_quotes 修复未转义引号 → 重试
优先级 2: 从文本中找 [ ... ] 数组 → 同优先级 1 流程
优先级 3: _fallback_parse_from_text
          ├─ 从截断 JSON 中提取 sql_id + risk_level + summary
          └─ 从 Markdown 文本中正则匹配
优先级 4: 返回 None（batch 解析失败，跳过）
```

**未转义引号修复**（`_fix_json_unescaped_quotes`）: 状态机扫描 JSON 字符串，检测字符串内部的未转义双引号并替换为中文引号 `"` → `"`。

### 3.7 自升级机制（Step 0）

```
自动更新检查：
  1. 检测 skill 安装目录（~/.claude/skills/sql-review 或 ~/.codex/skills/sql-review）
  2. 读取 .source_repo 找到源仓库路径
  3. 对比 VERSION 文件（REMOTE vs LOCAL）
  4. 版本不同 → cp 同步 scripts/*.py, references/*, SKILL.md, VERSION
  5. install.py --prune 清理已删除的旧脚本
  6. Codex 安装态：重新应用 patch（路径优先级 + 输出格式）
```

**设计思想**: 将"技能更新"从"用户手动操作"变为"每次调用自动检测"。通过 VERSION 文件实现版本控制，通过 install.py --prune 实现文件裁剪。

### 3.8 数据库连接自动检测

```
try_pymysql_prefetch():
  1. 环境变量 SQL_REVIEW_DB_*（CI 显式配置）
  2. 项目 YAML 扫描：
     ├─ **/src/main/resources/*test*/*.yml(.yaml)
     ├─ **/src/main/resources/*test*.yml(.yaml)
     ├─ 明文密码 → 直接连接
     └─ 加密密码 → 自动调 kc_decrypt 解密
  3. 失败 → 提示用户手动运行 kc_decrypt.py
  4. 全失败 → db_context = None，降级为无 DDL/EXPLAIN 模式
```

---

## 四、优秀设计亮点

### ⭐ 亮点 1：确定性 + LLM 的双层分析

Phase 1 的"确定性基线 + LLM 校正"是核心创新。确定性部分保证了**最小可用的下限**（即使 LLM 完全失败，仍有悲观基线可做 EXPLAIN），LLM 校正部分提升了**精度上限**（通过代码理解加回必传条件，减少误报）。

### ⭐ 亮点 2：多链独立分析

同一个 Mapper 方法可能被多个 Controller/Service 调用，不同入口的参数约束不同。多链模式将每条调用链独立分析，不同入口产出不同的 worst_case_sql。这避免了"一刀切"的误判。

### ⭐ 亮点 3：证据驱动的校正体系

Phase 1 的 7+4 证据体系将"必传/可选"的判断从 LLM 的主观猜测变为客观证据匹配。特别是"宁漏勿错"原则和禁止"基于业务常识推断"，防止 LLM 将"通常会传"当作"一定会传"。

### ⭐ 亮点 4：多层降级设计

整个 pipeline 的每个环节都有降级路径：
- Phase 0 失败 → 降级为原始 snippet
- Phase 1 无调用链 → 降级为纯悲观基线
- Phase 1 无动态 SELECT → 跳过 LLM 校正
- EXPLAIN 失败 → 继续 Phase 2（基于 DDL 和索引定义分析）
- Phase 2 LLM 超时 → generate_timeout_pass_report（SKIP 标记）
- JSON 解析失败 → 多层 fallback 降级提取

这确保了"总能产出结果"（fail-open），但结果中有明确的置信度标记。

### ⭐ 亮点 5：EXPLAIN 去重

多条 SQL 可能有相同的 worst_case_sql（不同链共享同一基线），或者 UPDATE 转换后的 SELECT 与已有 SELECT 相同。EXPLAIN 去重避免了重复执行相同的 EXPLAIN，减少数据库开销。

### ⭐ 亮点 6：prompt 预算控制

`_split_oversized_batches` 估算每个 batch 的 prompt 大小（SQL JSON + DDL + 固定开销），超过 40KB 就拆分。这防止了 LLM 因 prompt 过大导致分析质量下降或超时。

---

## 五、公司依赖分析 + 通用化方案

### 5.1 依赖清单

| 依赖 | 类型 | 用途 | 通用化难度 |
|------|------|------|-----------|
| `pymysql` | Python 库 | MySQL 直连 + EXPLAIN | ⭐ (已有 MySQL 都可复用) |
| `kc_decrypt.py` | Python 脚本 | KeyCenter 密码解密 | ⭐⭐ (公司特有加密体系) |
| `sql-rules.md` | Markdown | 团队 SQL 规范 + 硬编码规则 | ⭐ (纯配置) |
| YAML 扫描路径 (`src/main/resources/*test*`) | 路径约定 | DB 配置自动发现 | ⭐⭐ (Java 项目特有) |
| MyBatis XML 语法 | 框架 | SQL 提取 + 动态标签清洗 | ⭐⭐ (Java/MyBatis 特有) |
| `@DS` 注解 | 框架 | 多数据源路由 | ⭐⭐ (dynamic-datasource 特有) |
| IDEA 集成 (`output_idea.py`) | 工具 | IDE 内展示审查结果 | ⭐⭐ (IntelliJ 特有) |

### 5.2 抽象接口设计

```python
# 核心抽象：SQL 提取器
class ISQLExtractor:
    def get_changed_files(self, base_ref: str) -> list[str]: ...
    def extract_sql(self, file_path: str) -> list[dict]: ...
    def trace_call_chain(self, method_sig: str) -> list[dict]: ...

# 适配器：MyBatis XML
class MyBatisExtractor(ISQLExtractor): ...

# 适配器：JPA/Hibernate
class JPAExtractor(ISQLExtractor): ...

# 适配器：GORM (Go)
class GORMExtractor(ISQLExtractor): ...

# 核心抽象：数据库连接
class IDatabaseConnection:
    def explain(self, sql: str) -> dict: ...
    def get_ddl(self, table: str) -> str: ...
    def get_row_count(self, table: str) -> int: ...

# 适配器：MySQL
class MySQLConnection(IDatabaseConnection): ...

# 适配器：PostgreSQL
class PostgresConnection(IDatabaseConnection): ...
```

### 5.3 规则配置通用化

当前硬编码在 `sql-rules.md` 中的 17 条规则可以抽象为：

```yaml
# rules.yaml
rules:
  - id: R001
    description: "JOIN >= 5 张表"
    applies_to: [select]
    check:
      type: join_count
      operator: gte
      threshold: 5
    severity: MEDIUM

  - id: R008
    description: "查询条件未走索引"
    applies_to: [select, update]
    check:
      type: explain_type
      values: [ALL, index]
      except_table_rows: 5000  # 小表豁免
    severity: MEDIUM
```

---

## 六、可改进点

### 6.1 ⚠️ Phase 1 证据体系的覆盖率

当前 7 种必传证据覆盖了常见模式，但仍有漏网之鱼。例如：
- Lombok `@NonNull` 注解（与 `@NotNull` 不同，编译期注入 null check）
- Kotlin 的非空类型系统（编译期保证）
- AOP 切面的前置校验（如 `@RequirePermission` 隐含了 role 字段不为空）

改进方案：增加证据 #12（Lombok @NonNull 编译期检查）和证据 #13（Kotlin 非空类型）。

### 6.2 ⚠️ 跨文件 include 展开

当前 `_parse_sql_fragments` 只展开**同文件**的 `<sql id="xxx">` 片段。如果 `<include refid="base.Column_List"/>` 引用的是另一个 XML 文件中的片段，则无法展开。

改进方案：建立 XML 文件间的引用图，跨文件搜索 `<sql>` 片段定义。

### 6.3 ⚠️ 调用链追踪的深度限制

当前调用链追踪从 Mapper 方法出发向上搜索调用方，但可能因为以下原因中断：
- 接口实现（Interface → Impl）跨越多个模块
- 反射调用（`Method.invoke()`）
- 动态代理（Spring AOP、MyBatis Plugin）

改进方案：支持 Spring Bean 依赖图分析，通过 `@Autowired` 注解追踪注入链。

### 6.4 ⚠️ 缺少 EXPLAIN 结果缓存

相同 SQL + 相同表结构的 EXPLAIN 结果在多次运行中可能重复执行。特别是 CI 环境中，每次 MR 触发都会重新 EXPLAIN。

改进方案：引入 EXPLAIN 缓存（key = MD5(SQL + DDL)），存储在 `.sql-review/explain_cache.json` 中，24h TTL。

### 6.5 ⚠️ 硬编码规则的可扩展性

当前 17 条硬编码规则写在 `sql-rules.md` 的 Markdown 中，程序无法解析规则结构。新增规则需要修改 Markdown 文本 + 确保 LLM 正确理解。

改进方案：将规则结构化（YAML/JSON），既可供 LLM 阅读，也可供程序做预检（如 JOIN 计数、SELECT * 检测可以在 Python 侧完成，不消耗 LLM token）。

### 6.6 ⚠️ 多数据库方言支持

当前仅支持 MySQL（pymysql + EXPLAIN 语法）。PostgreSQL 的 `EXPLAIN ANALYZE` 语法和输出格式不同。

改进方案：`IDatabaseConnection` 接口支持方言，`MySQLConnection.explain()` → `EXPLAIN SELECT ...`，`PostgresConnection.explain()` → `EXPLAIN (ANALYZE, BUFFERS) SELECT ...`。

---

## 七、量化质量指标

| 维度 | 指标 | 测量方法 | 当前基准 | 目标 |
|------|------|---------|---------|------|
| **完整性** | 所有 SQL 类型覆盖 | 检查支持的类型 | SELECT, UPDATE | 全部 DML |
| **准确性** | Phase 1 校正准确率 | 人工验证加回条件是否正确 | - | ≥90% |
| **可靠性** | Pipeline 完成率 | 有产出的运行占比 | - | ≥95% |
| **鲁棒性** | JSON 解析成功率 | parse_llm_output 成功次数 | - | ≥90% |
| **效率** | 平均 batch 数 | 统计 batches 长度 | ≤N/15+1 | ≤N/15+1 |
| **效率** | Prompt 大小控制 | 单 batch prompt ≤40KB | - | 100% |
| **成本** | Phase 1 去重节省 | 去重前后链数差异 | - | ≥20% |
| **可迁移性** | 公司特有代码行数 | 搜索 kc_decrypt, @DS 等 | ~200 行 | 0 |
| **可配置性** | 硬编码规则可配置比例 | 结构化规则数 / 总规则数 | 0/17 | 17/17 |

---

## 八、复刻要点 Checklist

- [ ] 理解 5 步 Pipeline 的每一步输入/输出
- [ ] 理解 Phase 0/1/2 三阶段分析的顺序、触发条件、降级路径
- [ ] 理解悲观最差路径策略的四层设计（清洗 → 确定性扫描 → LLM 校正 → 合并）
- [ ] 理解 7+4 证据体系的每条证据含义和判断逻辑
- [ ] 理解多链模式（chain_id）vs 单链模式（sql_id）的区别
- [ ] 理解分批策略的三个约束（质量/成本/相关性）和三种操作（聚类/拆分/合并）
- [ ] 理解 MyBatis XML 动态标签清洗逻辑（if/choose/foreach/trim/where/set）
- [ ] 理解 SQL 提取引擎支持的三种来源（XML/Java 注解/QueryWrapper）
- [ ] 理解调用链追踪的深度和横向调用提取
- [ ] 理解 JSON 解析的四层降级策略
- [ ] 理解 EXPLAIN 去重（相同 SQL 文本）和多数据源路由（@DS 注解）
- [ ] 能设计 ISQLExtractor 和 IDatabaseConnection 抽象接口
- [ ] 能设计结构化规则配置替代 Markdown 硬编码规则
- [ ] 能设计 EXPLAIN 结果缓存机制
