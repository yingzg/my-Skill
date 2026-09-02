# EXPLAIN 输出解读指南

> 本文档在 Phase 4b 注入 LLM Prompt 上下文，教 LLM 如何根据 EXPLAIN 结构化数据判定风险等级。
> 脚本不消费此文件。

---

## 一、核心字段速查

### 1.1 type — 访问类型（最重要）

| type | 含义 | 索引使用情况 | 默认风险 | 说明 |
|------|------|:---:|:---:|------|
| `ALL` | 全表扫描 | ❌ 未使用 | **HIGH** | 扫描全表每一行。若 rows > 10000，严重风险 |
| `index` | 全索引扫描 | ⚠️ 使用但全扫 | **MEDIUM** | 扫描整个索引树，未利用索引查找能力 |
| `range` | 索引范围扫描 | ✅ 使用 | LOW | 使用索引检索指定范围的行，正常 |
| `ref` | 非唯一索引查找 | ✅ 使用 | LOW | 使用非唯一索引查找，正常 |
| `eq_ref` | 唯一索引查找 | ✅ 使用 | LOW | JOIN 时使用 PRIMARY KEY 或 UNIQUE 索引，最优 |
| `const` | 主键/唯一键等值 | ✅ 使用 | LOW | 最多一行匹配，极快 |
| `system` | 单行系统表 | ✅ 使用 | LOW | 表仅一行，特殊场景 |
| `NULL` | 无表访问 | — | LOW | 如 SELECT 1，无需访问任何表 |

**风险升级规则**：

- `type=ALL` + `rows > 10000` → **HIGH**（全表扫描 + 大表）
- `type=ALL` + `rows ≤ 100` → MEDIUM（小表全扫，需确认表是否会增长）
- `type=index` + `rows > 50000` → MEDIUM（全索引扫描但行数大）

### 1.2 rows — 预估扫描行数

| rows 范围 | 默认风险 | 说明 |
|-----------|:---:|------|
| > 100000 | **HIGH** | 大量扫描，必然会慢 |
| 10000 ~ 100000 | MEDIUM | 视表的绝对大小和查询频率而定 |
| 1000 ~ 10000 | LOW | 正常范围 |
| < 1000 | LOW | 非常快 |

**注意**：rows 是优化器的统计估算值，非精确值。InnoDB 的 rows 通常比 MyISAM 更不准。

### 1.3 key — 实际使用的索引

| key 值 | 含义 | 风险 |
|--------|------|:---:|
| `PRIMARY` | 使用了主键索引 | 正常 |
| 具体索引名 | 使用了该索引 | 正常 |
| `NULL` | 没有使用任何索引 | ⚠️ 结合 type 判断 |
| 与 possible_keys 不同 | 优化器选择了非预期的索引 | ⚠️ 可能是 force index 或统计信息过期 |

### 1.4 possible_keys — 可能使用的索引

若 `possible_keys` 非 NULL 但 `key` 为 NULL → 说明有索引但优化器没选。需要人工判断：
- 是不是统计信息不准确？
- 是不是回表代价大于全表扫描？
- 是不是索引列上存在隐式类型转换？

### 1.5 Extra — 额外信息

| Extra 值 | 含义 | 风险 | 说明 |
|----------|------|:---:|------|
| `Using index` | 覆盖索引 | ✅ **最佳** | 查询只需要扫描索引，不需要回表读数据行 |
| `Using where` | 使用了 WHERE 过滤 | 正常 | |
| `Using index condition` | 索引条件下推（ICP） | ✅ 好 | MySQL 5.6+ 优化 |
| `Using filesort` | 额外排序 | **MEDIUM** | 无法用索引排序，MySQL 需要额外排序。rows 越大越严重 |
| `Using temporary` | 临时表 | **MEDIUM-HIGH** | 常见于 GROUP BY / DISTINCT / UNION。内存临时表转磁盘临时表时性能急剧恶化 |
| `Using join buffer` | JOIN 缓冲 | **MEDIUM** | JOIN 时驱动表没有走索引，使用了 Block Nested-Loop |
| `Range checked for each record` | 每行检查范围 | **HIGH** | JOIN 时对每行都做一次索引查找，极差 |

---

## 二、综合风险判定规则

### 2.1 直接判定 HIGH（不需 LLM 判断，脚本可判定）

以下情况 `match_rules.py` 或 `execute_explain.py` 可直接标记 HIGH：

| 条件 | 原因 |
|------|------|
| `type=ALL` + `rows > 10000` | 大表全表扫描 |
| `type=ALL` + `Extra` 含 `Using filesort` | 全表扫描 + 额外排序，极端情况 |
| `rows > 100000` | 任何情况下扫描超过 10 万行 |
| `Extra` 含 `Using temporary` + `rows > 10000` | 大表临时表 |
| UPDATE/DELETE 的 EXPLAIN 中 `type=ALL` | 全表扫描的写操作，锁大量行 |

### 2.2 需要 LLM 综合判断的场景

以下场景 LLM 需要结合 `static_rules`（Phase 4a 结果）+ EXPLAIN + 业务上下文综合判断：

| 场景 | 需判断什么 |
|------|-----------|
| `Using filesort` + `rows < 10000` | filesort 开销是否可接受？结合 ORDER BY 的业务必要性 |
| `possible_keys` 不空但 `key=NULL` | 为什么优化器没选索引？是否 SQL 写法问题？ |
| 多表 JOIN 中的驱动表 `type=ALL` | 驱动表大小？是否小表足够小可接受？ |
| `type=range` 但 `rows` 很高 | range 扫描的范围是否过宽？ |
| 调用链断裂（Phase 2 失败） | 在不确定调用频率的情况下，保守判定 + 标注 `call_chain_broken` |

### 2.3 直接判定 LOW（不需 LLM）

| 条件 |
|------|
| `type∈{const, eq_ref, system}` |
| `type=ref` + `rows < 1000` |
| `type=range` + `rows < 10000` + `Extra` 不含 warning 项 |
| 纯索引查询（`Extra=Using index`）且 rows < 50000 |

---

## 三、MySQL 特有注意事项

### 3.1 filesort 不一定是坏事

`Using filesort` 名字有误导性——它不一定写磁盘。MySQL 会先尝试在 `sort_buffer_size` 内存中排序，只有超过时才写磁盘。关键看 rows：rows < 1000 的 filesort 几乎可以忽略。

### 3.2 index merge 的坑

`type=index_merge` 出现时，MySQL 尝试同时使用多个索引。看似高效，但在高并发场景下可能导致死锁（因为加锁顺序不一致）。看到 `index_merge` + `Using intersect/union` 时需特别关注。

### 3.3 驱动表选择

多表 JOIN 时，MySQL 优化器会根据统计信息选择驱动表（EXPLAIN 输出的第一行）。如果驱动表 `type=ALL` 且 rows 很大，即使被驱动表用了索引，整体性能仍会很差。**驱动表的行数是 JOIN 性能的决定性因素。**

---

## 四、EXPLAIN FORMAT=JSON 补充说明

使用 `EXPLAIN FORMAT=JSON` 可获得以下额外信息（格式化输出在 `phase4b_explain.json` 的 `explain_raw_json` 字段）：

| 字段 | 含义 | 用途 |
|------|------|------|
| `query_cost` | 优化器估算的查询成本 | 横向比较不同 SQL 版本的相对成本 |
| `used_columns` | 实际使用的列 | 判断是否可以减少 SELECT 列以利用覆盖索引 |
| `attached_condition` | 附加到索引扫描的条件 | 判断哪些条件被下推到了存储引擎层 |
| `using_filesort` | 布尔值 | 比 Extra 更精确的文件排序判定 |
| `using_temporary_table` | 布尔值 | 是否使用了临时表 |

---

## 五、LLM 使用此文档的方式

Phase 4b Prompt 将注入本文档全文。LLM 在接收到每条 SQL 的结构化 EXPLAIN 结果（`phase4b_explain.json`）后：

1. **先查表 1.1**→ 根据 `type` 确定基准风险等级
2. **再查表 1.2**→ 根据 `rows` 确认是否需要升级等级
3. **再查表 1.5**→ 根据 `Extra` 确认是否有额外性能隐患
4. **参考第二节**→ 判断当前 SQL 属于『直接判定』还是『需综合判断』
5. **输出风险等级 + rationale**→ 按 `report-schema.md` 的格式输出到 `phase4b_risk.json`
