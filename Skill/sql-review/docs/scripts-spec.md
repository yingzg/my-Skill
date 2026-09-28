# SQL Review Skill — 脚本规格

> 运行顺序 → 降级策略 → 输入验证规则。每个脚本对应一项测试。
>
> **原则**：每个脚本独立运行、自身的数据契约、标准 Unix 出口代码。没有隐藏状态，没有跨脚本变异。

---

## 概览：脚本 × 规格映射

| # | 脚本 | Phase | 输入 | 输出 | 降级 |
|:-:|------|:---:|------|------|:---:|
| 1 | `extract_changes.py` | 0 | base 分支名 | 变更文件列表 + `changed_statements`（SQL 块级 diff） | D0中断 / D1优雅退出 |
| 2 | `discover_datasource.py` | 0.5 | 项目根目录 | 数据源映射表（内存） | D4降级 |
| 3 | `parse_mapper.py` | 1 | XML 文件 + 数据源映射 | SqlRecord 列表（内存） | D2降级 / D3中断 |
| 4 | `trace_callchain.py` | 2 | 方法全限定名列表 + 源码目录 | 调用链（内存） | D8降级 |
| 5 | `resolve_dynamic_sql.py` | 3 | SqlRecord[] | resolved_sql（确定性展开，标 needs_llm） | D9降级 |
| 6 | `llm_resolve.py` | 3 | resolve 输出 + 调用链 | 最终 resolved_sql（LLM 真实路径还原） | D9降级 |
| 7 | `extract_tables.py` | 3.5a | resolved_sql[] | main_table 列表（内存） | — |
| 8 | `discover_schema.py` | 3.5c | 表名列表 | 表 DDL（columns/主键/索引） | D5降级 |
| 9 | `dml_to_select_proxy.py` | 3.5b | resolved_sql[]（仅 DML） | proxy_sql 列表（内存） | — |
| 10 | `match_rules.py` | 4a | sqls[] + rules.json + schema | 规则结果 + 风险分类（JSON） | D10中断 / D11中断 / D12中断 |
| 11 | `execute_explain.py` | 4b | sqls[] + datasource + schema | EXPLAIN 结果（JSON） | D5降级 / D6降级 / D7降级 |
| 12 | `llm_risk_analysis.py` | 4b | rules + explain + risk | 风险定性（预筛 + 分批 LLM） | D13降级 / D14降级 |
| 13 | `build_report.py` | 5 | 4a_results + 4b_results + 4b_risk | final_report + GATE + mr-comment | D16中断 |
| 14 | `run_review.py` | 0-5 | Mapper XML 文件列表 + 项目根目录 | 全链路产物 + final_report | 继承各阶段策略 |
| 15 | `post_mr_comment.py` | CI | mr-comment.md | 回贴 MR 评论（GitLab API） | 回贴失败仅告警 |

> 共 15 个脚本（12 个确定性脚本 + 2 个 LLM 脚本 + 1 个 CI 回贴脚本）+ 2 个公共模块（`db_client.py`、`llm_client.py`）。`run_review.py` 是推荐主入口。LLM 在 2 个环节介入：① `llm_resolve.py`（Phase 3，判断动态 `<if>/<choose>` 条件激活状态，真实路径还原）；② `llm_risk_analysis.py`（Phase 4b，合并规则 + EXPLAIN + 调用链，生成自然语言风险描述与分级修复建议）。两者通过 `llm_client.py`（OpenAI-compatible 客户端，默认 DeepSeek deepseek-v4-flash）调用，未配置 `LLM_API_KEY` 时自动降级为确定性分析。`discover_schema.py`（Phase 3.5c）通过 `db_client.py` 获取表 DDL，供 schema 感知规则与 EXPLAIN 参数化使用。`post_mr_comment.py` 在 CI 模式用 `GITLAB_TOKEN`（优先，PAT 需 api scope）或 `CI_JOB_TOKEN`（兜底，只读）回贴 MR 评论。

---

## 1. `extract_changes.py` — Phase 0（变更文件发现）

### 1.1 脚本职责
从当前 git 仓库检测相对于 base 分支的变更，过滤出 MyBatis Mapper XML 文件。

### 1.2 输入参数

| 参数 | 必填 | 默认值 | 说明 |
|------|:---:|--------|------|
| `--base` | ✅ | — | git diff 基准分支（如 `origin/master`） |
| `--pattern` | ❌ | `**/*Mapper.xml` | glob 模式过滤文件路径 |
| `--repo` | ❌ | cwd | git 仓库路径 |

### 1.3 输入文件
无 —— 直接从 `git diff` 读取。

### 1.4 输出文件
不落盘。以 JSON 行写入 stdout，供 SKILL.md 消费：

```jsonc
{
  "files": [
    {"path": "src/main/java/.../OrderMapper.xml", "status": "M"},
    {"path": "src/main/java/.../UserMapper.xml",  "status": "A"}
  ],
  "total_count": 2,
  "base_ref": "origin/master",
  "head_sha": "abc123"
}
```

### 1.5 产生哪些 JSON Schema
| 字段 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `files[].path` | string | ✅ | 相对于仓库根目录的路径 |
| `files[].status` | string | ✅ | `A`/`M`/`D`（新增/修改/删除） |
| `total_count` | number | ✅ | 输出中的 mapper 文件数量 |
| `base_ref` | string | ✅ | 基准分支名称 |
| `head_sha` | string | ✅ | HEAD commit SHA（用于 run_id） |

### 1.6 核心算法步骤
1. 运行 `git diff --name-only --diff-filter=AM {base}...HEAD`，或者运行 `git diff --name-only {base}...HEAD` 然后按 `NOT deleted` 过滤。
2. 只输出已被提交（已提交到 HEAD 或已暂存）的变更（使用 `{base}...HEAD` 三点的语法）。
3. 应用 `--pattern` glob（Python `pathlib.glob` 匹配），只保留 Mapper XML 文件。
4. 用 `git rev-parse HEAD` 获取当前 commit。
5. 发出 JSON。

### 1.7 失败处理
| 场景 | exit | 行为 |
|------|:---:|------|
| 非 git 仓库 | 1 | stderr：`fatal: not a git repository` |
| `--base` 分支不存在 | 1 | stderr：`branch {base} not found` |
| 0 个匹配的 mapper 文件 | 0 | `total_count=0, files=[]` |
| `git diff` 命令失败 | 2 | 将 git 错误转储至 stderr |

### 1.8 不允许做什么
- 不修改任何文件
- 不执行 `git checkout` 或 `git restore`
- 不访问远程仓库（无 `git fetch`）
- 不读取任何 Mapper XML 文件内容（仅文件名）
- 不调用 LLM API

### 1.9 对应测试样例
- **正常**：`tests/fixtures/` 仓库中包含 Mapper XML 文件 → 运行本脚本 → 验证 `files[]` 只包含 `*.xml`
- **无变更 / 没有映射器**：在没有新增/修改 mapper 的分支上运行 → 验证 `total_count=0` 且 exit 0
- **非 git 仓库**：在非 git 目录下运行 → 验证 exit 1

---

## 2. `discover_datasource.py` — Phase 0.5（数据源发现）

### 2.1 脚本职责
扫描 Java 项目源码，找出每个 Mapper 包对应的数据源名称、类型（仅做记录）和 URL。

### 2.2 输入参数

| 参数 | 必填 | 默认值 | 说明 |
|------|:---:|--------|------|
| `--project-root` | ❌ | cwd | Java 项目根目录（包含 `src/main/java`） |

### 2.3 输入文件
Java 源文件（通过文件系统扫描，位于 `src/main/java/**/*.java`），查找：
1. `@DS("datasource_name")` 注解（MyBatis-Plus 或 dynamic-datasource）
2. `@MapperScan(basePackages = "...")` 注解，结合 `@ConfigurationProperties(prefix = "...")` 查找配置类
3. `/application*.yml` 或 `/application*.properties` 中的 Spring datasource URL

### 2.4 输出文件
不落盘。以 JSON 行写入 stdout：

```jsonc
{
  "mappings": [
    {
      "mapper_package": "com.example.mapper.order",
      "datasource_name": "order_db",
      "type": "mysql",
      "url": "jdbc:mysql://..."
    }
  ],
  "status": "FOUND",
  "unmapped_packages": ["com.example.mapper.thirdparty"]
}
```

### 2.5 产生哪些 JSON Schema
| 字段 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `mappings[].mapper_package` | string | ✅ | 完整包名 |
| `mappings[].datasource_name` | string | ✅ | @DS 值或配置键 |
| `mappings[].type` | string | ❌ | `mysql`/`postgresql` 等 |
| `mappings[].url` | string | ❌ | JDBC URL（如果可解析） |
| `status` | string | ✅ | `FOUND`/`PARTIAL`/`UNKNOWN` |
| `unmapped_packages` | array | ✅ | 找不到数据源的包列表 |

### 2.6 核心算法步骤
1. 扫描 `src/main/java` 下的所有 `.java` 文件。
2. **策略 A — @DS 直接映射**：匹配 `@DS("name")`。将**包含 `@DS` 类的包**当作键，注解值当作数据源名称。
3. **策略 B — @MapperScan 间接映射**：
   - 查找 `@MapperScan(basePackages = {"...", "..."})`。
   - 在同一个或附近的类中，检查 `@ConfigurationProperties(prefix = "...")`。
   - 在 YAML / properties 中查找对应前缀 → 解析 URL。
4. 合并策略 A 和 B（如果两者都存在则优先使用 A）。
5. 将同时使用多个数据源且找不到映射的包列入 `unmapped_packages`。

### 2.7 失败处理
| 场景 | exit | 行为 |
|------|:---:|------|
| 找不到 `src/main/java` | 0 | status=`UNKNOWN`，全部 `unmapped_packages` |
| 无 @DS 且无 @MapperScan | 0 | status=`UNKNOWN`，SKILL.md 降级 |
| YAML 解析失败 | 0 | status=`PARTIAL`，只包含有 @DS 的项 |

`discover_datasource.py` **从不断路** —— 总是返回 exit 0 并将状态写入输出。

### 2.8 不允许做什么
- 不连接数据库验证
- 不执行 Java 代码或触发 Spring Boot
- 不读取非 YAML/非 properties 配置文件
- 不调用 LLM
- 不把 URL 中的密码输出到 stdout（用 `***` 掩码）

### 2.9 对应测试样例
- **fixtures/java/**：一个带有 `@DS` 的 Mapper 接口，一个带有 `@MapperScan` 的 Config 类，以及一个 `application.yml` → 验证有效 JSON
- **无注解**：一个没有任何数据源注解的 Java 包 → 验证 status=`UNKNOWN`

---

## 3. `parse_mapper.py` — Phase 1（SQL 提取）

### 3.1 脚本职责
解析 MyBatis Mapper XML 文件，提取所有 SQL 语句并附上元数据（语句类型、动态标签、数据源、文件位置）。

### 3.2 输入参数

| 参数 | 必填 | 默认值 | 说明 |
|------|:---:|--------|------|
| `--file` | ❌ | — | 单文件路径（便捷模式，与 `--files` 互斥） |
| `--files` | ❌ | — | JSON 字符串：文件路径数组（与 `--file` 互斥，必须指定一个） |
| `--datasource-map` | ❌ | — | JSON 字符串：来自 Phase 0.5 的输出（SKILL.md 始终传入） |
| `--format` | ❌ | `json` | 输出格式：`json`（数组）或 `ndjson`（每行一条 JSON，管道模式） |
| `--strict` | ❌ | — | 解析失败时 exit 1 而非跳过（默认：静默跳过失败文件） |

### 3.3 输入文件
MyBatis Mapper XML 文件（由 `--files` 指定）。

### 3.4 输出文件
默认以 JSON 数组写入 stdout。管道模式使用 `--format ndjson` 输出每行一条 JSON：

```jsonc
// --format json（默认）：JSON 数组
[{"sql_id":"OrderMapper.xml:findById:0",...}, {"sql_id":"OrderMapper.xml:selectByCondition:0",...}]

// --format ndjson：每行一条 JSON，供管道消费
{"sql_id":"OrderMapper.xml:findById:0","mapper_namespace":"com.example.mapper.OrderMapper","method_name":"findById","statement_type":"SELECT","raw_sql":"SELECT id, order_no FROM orders WHERE id = #{id}","dynamic_tags":[],"datasource":"order_db","file":"src/.../OrderMapper.xml","line_start":7,"line_end":0}
{"sql_id":"OrderMapper.xml:selectByCondition:0","mapper_namespace":"com.example.mapper.OrderMapper","method_name":"selectByCondition","statement_type":"SELECT","raw_sql":"SELECT id, order_no FROM orders WHERE 1=1 <if test=\"status != null\">AND status = #{status}</if>","dynamic_tags":[{"tag":"if","raw":"<if test=\"status != null\">AND status = #{status}</if>"}],"datasource":"order_db","file":"src/.../OrderMapper.xml","line_start":15,"line_end":22}
```

### 3.5 产生哪些 JSON Schema
| 字段 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `sql_id` | string | ✅ | 唯一标识：`{file}:{方法}:{索引}` |
| `mapper_namespace` | string | ✅ | XML namespace（完整接口限定名） |
| `method_name` | string | ✅ | `<select id="...">` 的值 |
| `statement_type` | string | ✅ | `SELECT`/`UPDATE`/`DELETE`/`INSERT` |
| `raw_sql` | string | ✅ | 原始 SQL 文本（含 MyBatis `#{var}` 和动态标签） |
| `dynamic_tags` | array | ✅ | 每个 XML 标签一个 `{tag, raw}` |
| `datasource` | string | ✅ | 数据源名称（通过从数据源映射表中匹配包名解析得出） |
| `file` | string | ✅ | 文件路径 |
| `line_start` | number | ✅ | SQL 语句起始行号 |
| `line_end` | number | ✅ | SQL 语句结束行号 |

### 3.6 核心算法步骤
1. 解析 `--datasource-map` JSON，构建 `{包名 → datasource_name}` 查找表。
2. 对于 `--files` 中的每个 XML 文件：
   - 用 XML 解析器（`lxml.etree` 或 `xml.etree.ElementTree`）解析。
   - 提取 `namespace` 属性。
   - 查找所有 `<select>`、`<update>`、`<delete>`、`<insert>` 节点。
3. 对于每个语句节点：
   - 提取 `id`。
   - 提取内部文本作为 `raw_sql`（保留 `<if>`、`<foreach>` 等元素标签）。
   - 将 `<if test="...">text</if>` 之类的子元素识别为 `dynamic_tags`。
   - 根据 namespace 匹配数据源（`com.example.mapper.order` → `order_db`，前缀匹配）。
4. 每一条发出 JSON 行。

### 3.7 失败处理
| 场景 | exit | 行为 |
|------|:---:|------|
| 单个文件 XML 解析失败 | — | stderr 记录错误，跳过该文件，继续处理其余文件 |
| 全部文件 XML 解析失败 | 1 | 中断，不输出任何内容 |
| `--files` 为空 | 0 | 无输出（stdout 返回 0 行） |

### 3.8 不允许做什么
- 不连接数据库
- 不执行 / 验证 SQL（仅提取文本）
- 不修改 XML 文件
- 不调用 LLM
- 不将 `#{var}` 替换为实际值

### 3.9 对应测试样例
**Golden file**：`tests/expected/parse-output.json`
- **静态 SQL**：`findById`、`findAll` 等 → 验证 type、raw_sql、dynamic_tags=[]
- **动态 SQL**：`selectByCondition`、`selectByIds` 等 → 验证 dynamic_tags 包含正确的标签名
- **DML 类型检测**：`updateStatus`、`deleteById`、`insertOrder` → 验证 statement_type
- **datasource 解析**：`com.example.mapper.order.*` 命名空间 → 验证 datasource=`order_db`
- **XML 损坏**：放一个无效 XML 文件 → 验证其余文件仍被处理

---

## 4. `trace_callchain.py` — Phase 2（调用链追踪）

### 4.1 脚本职责
给定 Mapper 方法列表，通过静态分析 Java 源码反向追踪调用链直至 Controller 层。

### 4.2 输入参数

| 参数 | 必填 | 默认值 | 说明 |
|------|:---:|--------|------|
| `--methods` | ✅ | — | JSON 字符串：方法全限定名数组（如 `["com.example.mapper.OrderMapper.findById"]`） |
| `--project-src` | ❌ | `src/main/java` | 相对于 `--project-root` 的 Java 源码路径 |

### 4.3 输入文件
`src/main/java/**/*.java` 下的 Java 源文件。

### 4.4 输出文件
不落盘。以 JSON 写入 stdout：

```jsonc
{
  "chains": [
    {
      "method": "com.example.mapper.OrderMapper.findById",
      "call_chain": [
        {"class": "com.example.controller.OrderController", "method": "getOrder", "line": 45},
        {"class": "com.example.service.OrderService", "method": "findById", "line": 33}
      ],
      "complete": true
    }
  ]
}
```

### 4.5 产生哪些 JSON Schema
| 字段 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `method` | string | ✅ | Mapper 方法全限定名 |
| `call_chain[].class` | string | ✅ | 包含方法调用的类的完整限定名 |
| `call_chain[].method` | string | ✅ | 调用此 mapper 方法的方法名 |
| `call_chain[].line` | number | ✅ | 该调用发生的行号 |
| `complete` | boolean | ✅ | 是否到达 @RestController/@Controller 节点 |

### 4.6 核心算法步骤
1. 在 `src/main/java/` 下构建方法 ↔ 文件的索引表。
2. 对于 `--methods` 中的每个方法：
   - 解析 `类.方法`。
   - 在 `.java` 文件中搜索 `{methodName}(`（grep 方式，非 AST）。
   - 如果目标类是 `XxxImpl implements Xxx`，同时把接口短名和接口全限定名作为上层引用别名。
   - 对于每个匹配项，提取所在类、该方法所处的方法、以及行号。
   - 继续递归搜索，直到：
     - 到达一个带有 `@RestController`、`@Controller` 或 `@RequestMapping` 注解的类（**成功结束**），或者
     - 找不到更多调用者（记录为 `complete: false`，**降级结束**）。
   - **保护机制**：路径缓存，避免在有两个类互相调用时发生循环。
3. 发出结果 JSON。

### 4.7 失败处理
| 场景 | exit | 行为 |
|------|:---:|------|
| Mapper 方法未找到（类文件缺失） | — | 该条目标记为 `complete: false`（降级） |
| 中间 Service/Helper 类缺失 | — | 该条目标记为 `complete: false`（降级） |
| `src/main/java` 目录不存在 | 0 | `chains: []`，SKILL.md 按降级处理 |
| 循环检测触发（A→B→A） | — | 安全终止，`complete: false` |
| 方法计数太高（> 50 个） | 1 | 拒绝追踪（避免扫描时间爆炸式增长） |

`trace_callchain.py` **从不断路** —— 总是返回 exit 0。不完整的链条会标记出来。

### 4.8 不允许做什么
- 不执行 Java 代码（不反射，不 classpath 加载）
- 不解析 Java AST（使用 grep/regex，简单且可单步调试）
- 不连接数据库
- 不调用 LLM
- 不将方法体当作字符串遍历（只匹配调用者名称）

### 4.9 对应测试样例
- **fixtures/java/**：Controller → Service → Mapper 链
  - 输入 `["com.example.mapper.OrderMapper.findById"]`
  - 期望：`call_chain` 包含 OrderController.getOrder 和 OrderService.findById
- **中断链**：一个 Service 上没有相应源文件的 Mapper → 验证 `complete: false`
- **循环引用**：两个互相调用的 Service → 验证不会陷入无限循环

---

## 5. `resolve_dynamic_sql.py` — Phase 3（动态 SQL 解析）

独立 CLI 脚本，支持 `--mode optimistic` 和 `--mode resolve` 两种运行模式。脚本内部通过 `resolve_dynamic_sql()` 处理 MyBatis 动态 SQL 标签（`<if>` / `<where>` / `<foreach>` / `<choose>`），并输出增强后的 JSON 行（NDJSON）。

当用户在任意一种模式中启用 LLM、或手动触发从 SKILL.md 的 Phase 3 分析步骤时，会调用该脚本；然后 SKILL.md 对 `needs_llm == true` 项通过对条件标签进行判断，决定最终 `resolved_sql` 再经过 `finalize_sql()` 清洗输出。

### 5.1 职责

| 输入 | 输出 |
|------|------|
| Phase 1+2 产出的 NDJSON（SqlRecord，含 `raw_sql` + `dynamic_tags` + `call_chain`），通过 stdin 读入 | 增强后的 NDJSON，每行新增 `needs_llm`、`unresolved_tags` 字段。`resolved` 模式下存在 `final_resolved_sql` 经过 `finalize_sql()` 清洗 |

### 5.2 命令行接口

```bash
python3 resolve_dynamic_sql.py [--mode optimistic|resolve] [--skip-finalize]
```

| 参数 | 说明 |
|------|------|
| `--mode optimistic` | **默认**。对所有动态标签采用乐观固化（默认参数都有值），直接输出 `resolved_sql` |
| `--mode resolve` | 保留不确定的动态标签，输出 `needs_llm` + `unresolved_tags`，留待 SKILL.md 的 LLM 判断 |
| `--skip-finalize` | 仅在 `resolve` 模式下有效。跳过 `finalize_sql()` 清洗（为 LLM 保留原始动态 SQL） |

**stdin/stdout 格式**：NDJSON（每行一个 JSON 对象）。数据从 stdin 读入，处理结果逐行写入 stdout。

### 5.3 模式行为

#### `optimistic` 模式（默认）

对所有 `<if>` / `<choose>` 条件标签采用乐观假设（`test` 表达式结果为 `true`），直接展开标签内容。
`<foreach>` 标签展开为 `open + body + close`（如 `IN (#{id})`），body 内 `#{...}` 后续统一参数化为 `?`（不展开为多个 `?`）。
`<bind>` / `<include>` 保留原样（确定性脚本已有展开逻辑）。

不适合需考虑实际参数是否传值的场景；适合快速静态分析。

#### `resolve` 模式

1. 确定性部分（`<foreach>` / `<include>` / `<bind>` / 不带参数的 `<if>`）→ 脚本直接展开
2. 剩余不确定的动态标签 → 保留原样，标记 `needs_llm: true`
3. SKILL.md 收集所有 `needs_llm == true` 的 SQL，结合调用链上下文向 LLM 询问条件是否激活
4. LLM 返回 `resolved_sql` 后，调用 `finalize_sql()` 完成最终清洗（移除 `#{}` → `?` 等）

### 5.4 `finalize_sql()` 函数

脚本内提供 `finalize_sql()` 帮助函数，用于将 `resolved_sql` 做最终清洗：

- `#{param}` / `${param}` → `?`
- 移除多余空白和换行（压缩空白）
- 标准化 `WHERE 1=1` 尾随空 `AND`

```python
from resolve_dynamic_sql import finalize_sql
clean = finalize_sql("SELECT * FROM t WHERE id = #{id}")
# → "SELECT * FROM t WHERE id = ?"
```

### 5.5 输出 Schema

**optimistic 模式**，每行输出：

```jsonc
{"sql_id": "...", "resolved_sql": "SELECT ... WHERE ...", "needs_llm": false, "unresolved_tags": []}
```

**resolve 模式**（需 LLM 判断），每行输出：

```jsonc
{"sql_id": "...", "resolved_sql": "SELECT ... WHERE 1=1\n<if test=\"status != null\">AND status = #{status}</if>", "needs_llm": true, "unresolved_tags": [{"tag": "if", "test": "status != null"}]}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `sql_id` | string | ✅ | 对应 Phase 1 的 SqlRecord |
| `resolved_sql` | string | ✅ | 解析后的 SQL（`resolve` 模式下可能仍含动态标签） |
| `needs_llm` | boolean | ✅ | 是否需要 LLM 进一步判断动态条件 |
| `unresolved_tags` | array | ✅ | 保留的动态标签列表（optimistic 模式下为空） |

### 5.6 故障处理

| 场景 | 行为 |
|------|------|
| `<foreach>` 无 `collection` 或无 `item` | 展开为 `()` 占位 |
| 未知标签类型 | 保留原样并返回码 `exit 2`，其余 SQL 继续 |
| 参数值无法静态确定（resolve 模式） | 标记 `needs_llm: true`，由 SKILL.md 升级为 LLM 判断 |

### 5.7 不允许做什么
- 不在残留的 `#{...}` 占位符上执行 EXPLAIN（`finalize_sql()` 会先将占位符替换）
- `optimistic` 模式不将不确定的 SQL 标记为已确定

### 5.8 对应测试样例
- **静态 SQL**：`findById` → 验证 `resolved_sql` 用 `?` 替换了 `#{id}`
- **`<if>` 标签（optimistic）**：`selectByCondition` → 验证 `resolved_sql` 包含所有分支的 SQL 片段
- **`<if>` 标签（resolve）**：`selectByCondition` → 验证 `needs_llm: true` 且 `unresolved_tags` 包含对应条件
- **`<foreach>` 展开**：`selectByIds` → 验证 IN 子句中有占位符 `(?, ?, ?)`

---

## 6. `extract_tables.py` — Phase 3.5a（表名提取）

### 6.1 脚本职责
从每个 `resolved_sql` 中提取**主表**。主表指关联 SQL 中 `FROM` 后第一个非子查询表，用于后期分批（按主表分组）。

### 6.2 输入参数

| 参数 | 必填 | 默认值 | 说明 |
|------|:---:|--------|------|
| `--input` | ❌ | —（stdin） | JSON 字符串，或通过 stdin 管道传入 NDJSON |

### 6.3 输入文件
无 —— 从 stdin/`--input` 参数读取。

### 6.4 输出文件
不落盘。以 JSON 行写入 stdout：

```jsonc
{"sql_id":"OrderMapper.xml:findById:0","main_table":"orders"}
{"sql_id":"OrderMapper.xml:selectByCondition:0","main_table":"orders"}
```

### 6.5 产生哪些 JSON Schema
| 字段 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `sql_id` | string | ✅ | 对应 resolved_sql 条目 |
| `main_table` | string | ✅ | 主表名称，或 `UNKNOWN` |

### 6.6 核心算法步骤
1. 遍历输入。
2. 对于每一条 `resolved_sql`：
   - 用不区分大小写的正则匹配第一个 `FROM` 子句：
     ```
     FROM\s+(\w+(?:\.\w+)?)
     ```
   - 如果是 JOIN：提取**第一个** `FROM` 后的表名（JOIN 左边的表）。
   - 如果是子查询：跳过 `FROM (` 部分，按递归方式继续解析。
   - 如果不匹配：返回 `UNKNOWN`。
3. 发出结果。

### 6.7 失败处理
| 场景 | exit | 行为 |
|------|:---:|------|
| 正则无匹配 | — | `main_table: "UNKNOWN"`，该条目不阻塞 |
| 输入无效 JSON | 1 | 中断 |

### 6.8 不允许做什么
- 不连接数据库验证表是否存在
- 不解析 SQL AST（只用正则）

### 6.9 对应测试样例
- **单表**：`SELECT * FROM orders` → `main_table: "orders"`
- **多表 JOIN**：`SELECT * FROM orders o JOIN users u ON ...` → `main_table: "orders"`
- **子查询 FROM**：`SELECT * FROM (SELECT ...) t` → 尽力而为，`main_table: "UNKNOWN"` 可接受

---

## 7. `dml_to_select_proxy.py` — Phase 3.5b（DML → SELECT 代理）

### 7.1 脚本职责
将 `UPDATE`/`DELETE` 语句转换为等效的 `SELECT` 语句，以便执行 `EXPLAIN`（大多数数据库不允许对非 SELECT 语句执行 EXPLAIN）。

### 7.2 输入参数

| 参数 | 必填 | 默认值 | 说明 |
|------|:---:|--------|------|
| `--input` | ❌ | —（stdin） | JSON 字符串，或通过 stdin 管道传入 NDJSON |
| `--output` | ❌ | stdout | 输出文件路径 |

### 7.3 输入文件
无 —— 从 stdin/`--input` 参数读取。

### 7.4 输出文件
不落盘。以 JSON 行写入 stdout：

```jsonc
{"sql_id":"OrderMapper.xml:updateStatus:0","original_sql":"UPDATE orders SET status = 'CANCEL' WHERE id = 1","proxy_sql":"SELECT id, status FROM orders WHERE id = 1"}
```

### 7.5 产生哪些 JSON Schema
| 字段 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `sql_id` | string | ✅ | 对应条目 |
| `original_sql` | string | ✅ | 原始 DML |
| `proxy_sql` | string / null | ✅ | 用于 EXPLAIN 的等效 SELECT，无法转换时为 null |

### 7.6 核心算法步骤
1. 遍历输入。只处理 `UPDATE`/`DELETE`/`INSERT` 语句。
2. 对于每一条 DML：
   - **UPDATE** → `SELECT {cols_from_SET} FROM {table} WHERE {clause}`
   - **DELETE** → `SELECT * FROM {table} WHERE {clause}`
   - **INSERT … SELECT** → 将 `SELECT` 子句直接作为代理。
   - **INSERT … VALUES** → `proxy_sql = null`（没有 WHERE 子句可解释）
3. 对于 SELECT 语句：跳过（`proxy_sql = null`，不需要转换）。
4. 如果 WHERE 子句解析失败：`proxy_sql = null`。
5. 发出结果。

### 7.7 失败处理
| 场景 | exit | 行为 |
|------|:---:|------|
| 无法重构 WHERE 子句 | — | `proxy_sql: null`，该条目不降级 |
| 输入无效 JSON | 1 | 中断 |

### 7.8 不允许做什么
- 不在真实数据库上执行 SQL
- 不修改原始 SQL 文件
- 不尝试验证代理 SQL（那是 execute_explain 的职责）

### 7.9 对应测试样例
- **UPDATE → SELECT**：`UPDATE orders SET status='X' WHERE id=1` → 验证 `proxy_sql` 以 `SELECT` 开头并保留 WHERE 子句
- **DELETE → SELECT**：`DELETE FROM orders WHERE id=1` → 验证 `proxy_sql` 以 `SELECT * FROM orders` 开头
- **INSERT … VALUES**：→ 验证 `proxy_sql: null`
- **SELECT（无 DML）**：→ 验证 `proxy_sql: null`

---

## 8. `match_rules.py` — Phase 4a（静态规则匹配）

### 8.1 脚本职责
根据 `references/rules/rules.json` 对每条 SQL 执行静态规则匹配，输出匹配结果和总体风险分类。

### 8.2 输入参数

| 参数 | 必填 | 默认值 | 说明 |
|------|:---:|--------|------|
| `--input` | ✅ | — | JSON 字符串：SQL 列表，或 `-` 表示 stdin |
| `--rules` | ❌ | `references/rules/rules.json` | 规则文件路径 |
| `--output` | ❌ | — | 输出文件路径（默认 stdout） |
| `--run-id` | ❌ | `golden` | 运行标识，嵌入输出中 |

### 8.3 输入文件
- `references/rules/rules.json`（规则定义）
- 来自 stdin 或 `--input` 的 SQL 列表

### 8.4 输出文件
默认写入 stdout。通过 `--output` 参数**落盘到**指定路径（SKILL.md 使用 `/tmp/sql_review/{run_id}/phase4a_rules.json`）：

```jsonc
{
  "run_id": "run_20260730_...",
  "generated_at": "2026-07-30T...",
  "rules_version": "1.0.0",
  "results": [
    {
      "sql_id": "OrderMapper.xml:findAll:0",
      "statement_type": "SELECT",
      "rule_matches": [
        {"rule_id": "R001", "matched": true, "severity": "HIGH"},
        {"rule_id": "R002", "matched": false, "severity": "NONE"}
      ],
      "overall_risk": "HIGH",
      "risk_reason": "SELECT * without WHERE → R001: 全表扫描"
    }
  ]
}
```

### 8.5 消费哪些 JSON Schema
- `references/rules/rules.json`（加载时自动验证）
- `references/report-schema.md §二（phase4a_rules.json）`（用于输出 Schema）

### 8.6 产生哪些 JSON Schema
| 字段 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `run_id` | string | ✅ | 与 session 的 run_id 一致 |
| `generated_at` | string | ✅ | ISO 8601 时间戳 |
| `rules_version` | string | ✅ | 加载的 rules.json 版本 |
| `results[].sql_id` | string | ✅ | SQL 标识 |
| `results[].statement_type` | string | ✅ | 供 applicable_to 过滤使用 |
| `results[].rule_matches[].rule_id` | string | ✅ | 规则 ID |
| `results[].rule_matches[].matched` | boolean | ✅ | SQL 是否命中 |
| `results[].rule_matches[].severity` | string | ✅ | 当前 severity_by_type 下的严重等级 |
| `results[].overall_risk` | string | ✅ | `LOW`/`MEDIUM`/`HIGH`/`CRITICAL`/`UNCERTAIN` |
| `results[].risk_reason` | string | ✅ | 简明可读的说明 |

### 8.7 核心算法步骤
1. 从 `--rules` 文件加载并验证 JSON。
2. 对于输入中的每条 SQL：
   - 确定 `statement_type`。
   - 对于每一条规则，检查 `applicable_to` → 如果不适用则跳过。
   - 对 `resolved_sql`（解析后、保留 DML 类型语义）执行 `pattern` 正则匹配。`proxy_sql`（DML 转 SELECT）仅用于 EXPLAIN，不参与规则匹配。
   - 如果匹配：在 `severity_by_type` 中按该语句类型查阅严重等级（如果没找到条目则使用 `default_severity`）。
   - 汇总：在所有匹配的规则中取最高严重等级。
   - 分类：`LOW` / `MEDIUM` / `HIGH` / `CRITICAL` / `UNCERTAIN`（无匹配）。
3. 写入 `phase4a_rules.json` 并返回结果的副本。

### 8.8 失败处理
| 场景 | exit | 行为 |
|------|:---:|------|
| `--rules` 文件缺失 | 1 | D10：中断 |
| 规则文件为空（`rules: []`） | 1 | D11：中断 |
| 单条规则 JSON 损坏 | 1 | 终止并说明错误 |
| 脚本内部崩溃 | 1 | D12：中断 |

### 8.9 不允许做什么
- 不调用 LLM
- 不连接数据库
- 不修改 rules.json
- 不用正则匹配 SQL 以外的内容
- 不因单条 SQL 失败而丢弃所有结果

### 8.10 对应测试样例
**Golden file**：`tests/expected/rules-output.json`
- **SELECT * 无 WHERE**：触发 R001（全表扫描）→ `overall_risk: HIGH`
- **WHERE col=%s 无索引前缀**：触发 R002（隐式类型转换）→ 验证 severity
- **UPDATE 无 WHERE**：触发 R102（无 WHERE DML）→ `overall_risk: CRITICAL`
- **规则不被 applicable_to 触发**：在 SELECT 上检查 R102 → 验证 `matched: false`
- **规则未被触及**：对安全的 SELECT 验证 `overall_risk: UNCERTAIN`

---

## 9. `execute_explain.py` — Phase 4b（EXPLAIN 执行）

### 9.1 脚本职责
对一批 SQL（按 main_table 分组，使用 proxy_sql 或 resolved_sql）连接数据库执行 `EXPLAIN`，返回结构化查询计划数据。

### 9.2 输入参数

| 参数 | 必填 | 默认值 | 说明 |
|------|:---:|--------|------|
| `--batch` | ❌ | —（stdin） | JSON 字符串，或通过 stdin 管道传入 NDJSON |
| `--output` | ❌ | /tmp/sql_review/{run_id}/phase4b_explain.json | 输出路径 |
| `--timeout` | ❌ | `10` | 单条 EXPLAIN 超时秒数 |
| `--dry-run` | ❌ | `false` | 使用模拟 EXPLAIN 结果代替真实数据库连接（测试/CI 模式，不产生真实查询计划） |

### 9.3 输入文件
- stdin 或 `--batch` 中的 SQL 批次
- `references/report-schema.md §3`（输出 Schema）

### 9.4 输出文件
**落盘到** `/tmp/sql_review/{run_id}/phase4b_explain.json`：

```jsonc
{
  "run_id": "run_20260730_...",
  "generated_at": "2026-07-30T...",
  "total": 5,
  "executed": 4,
  "failed": 1,
  "results": [
    {
      "sql_id": "OrderMapper.xml:findAll:0",
      "executed": true,
      "type": "ALL",
      "key": null,
      "key_len": null,
      "rows": 15823,
      "extra": "Using where",
      "raw_explain": "..."
    },
    {
      "sql_id": "OrderMapper.xml:findById:0",
      "executed": false,
      "error": "Connection timeout after 10s",
      "type": null,
      "key": null,
      "key_len": null,
      "rows": null,
      "extra": null,
      "raw_explain": null
    }
  ]
}
```

### 9.5 消费哪些 JSON Schema
- `references/report-schema.md §3`

### 9.6 产生哪些 JSON Schema
| 字段 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `run_id` | string | ✅ | Session run_id |
| `generated_at` | string | ✅ | ISO 8601 |
| `total` | number | ✅ | 批次 SQL 总数 |
| `executed` | number | ✅ | 成功执行的 EXPLAIN 条数 |
| `failed` | number | ✅ | 失败的 EXPLAIN 条数 |
| `results[].sql_id` | string | ✅ | SQL 标识 |
| `results[].executed` | boolean | ✅ | EXPLAIN 是否成功 |
| `results[].type` | string / null | ✅ | MySQL EXPLAIN join 类型（`ALL`/`ref`/`range` 等） |
| `results[].key` | string / null | ✅ | 实际使用的索引 |
| `results[].rows` | number / null | ✅ | 预估扫描行数 |
| `results[].extra` | string / null | ✅ | `Using filesort` / `Using temporary` / `Using index` |
| `results[].raw_explain` | string / null | ✅ | 完整 EXPLAIN 输出（用于 LLM 深度分析的原始数据） |
| `results[].error` | string / null | ✅ | 失败时的错误消息 |

### 9.7 核心算法步骤
1. 按 datasource 对批次 SQL 分组（每个连接执行一组）。
2. 对于每个数据源连接：
   - 建立数据库连接（通过 JDBC URL 或 MCP）。
   - 对于该组中每条 SQL：执行 `EXPLAIN FORMAT=JSON {proxy_sql}`。
   - 解析 JSON 输出 → 提取 `type`、`key`、`rows`、`extra`。
   - 如果连接断开：为该数据源下剩余所有 SQL 标记 `executed: false`。
3. 写入 `phase4b_explain.json`。

### 9.8 失败处理
| 场景 | exit | 行为 |
|------|:---:|------|
| 无法连接到数据库 | — | 全部结果标记为 `executed: false`（D5 降级） |
| 单条 SQL 的 EXPLAIN 失败 | — | 该条目标记为失败（D6 降级） |
| 全部 SQL 的 EXPLAIN 失败 | — | 全部标记为失败（D7 降级） |

`execute_explain.py` **从不断路** —— 总是返回 exit 0 并写入文件。

### 9.9 不允许做什么
- 不执行原始 SQL（非 EXPLAIN）
- 不在生产数据库上执行 EXPLAIN（用户必须预先配置只读副本）
- 不存储或泄露数据库凭证（来自环境变量或安全配置）
- 不修改数据
- 不执行跨批次 SQL 合并

### 9.10 对应测试样例
- **正常 EXPLAIN**：需要数据库连接。可以用 `--dry-run` 模式配合预录制 JSON 做集成测试。
- **连接失败**：给出无效的 datasource URL → 验证全部 `executed: false`
- **超时**：设置 `--timeout 1` 并对大表执行 EXPLAIN → 验证错误消息

---

## Phase 4b 风险上下文与可选深度复核

> 当前端到端主流程由 `run_review.py` 生成 `phase4b_risk.json`，其中至少包含每条 SQL 的调用链上下文。LLM 深度复核是可选增强，不再由 `SKILL.md` 内联强制执行。

### 10.1 职责
为 `build_report.py` 提供规则/EXPLAIN 之外的上下文覆盖信息，例如调用链、调用链是否断裂，以及人工或 LLM 生成的风险结论覆盖。

### 10.2 输入参数
由 `run_review.py` 从 `phase1_parse.json` 和 `phase2_trace.json` 合并生成：

```jsonc
[
  {
    "sql_id": "OrderMapper.xml:findById:0",
    "mapper_namespace": "com.example.mapper.OrderMapper",
    "method_name": "findById",
    "call_chain": [
      {"class": "com.example.controller.OrderController", "method": "getOrder", "line": 45}
    ]
  }
]
```

如果后续引入 LLM 深度复核，应从 `phase4a_rules.json`、`phase4b_explain.json`、`phase2_trace.json` 读取输入，并输出同一个 `phase4b_risk.json` schema。

### 10.3 输入文件
- `phase1_parse.json`
- `phase2_trace.json`
- 可选：`phase4a_rules.json`、`phase4b_explain.json`（仅 LLM 深度复核需要）

### 10.4 输出文件
**落盘到** `/tmp/sql_review/{run_id}/phase4b_risk.json`：

```jsonc
{
  "results": [
    {
      "sql_id": "OrderMapper.xml:findById:0",
      "call_chain": [
        {"class": "com.example.controller.OrderController", "method": "getOrder", "line": 45}
      ],
      "call_chain_broken": false,
      "level": "LOW",
      "summary": "可选：人工或 LLM 风险覆盖摘要",
      "short_term_fix": "可选：短期建议",
      "long_term_fix": "可选：长期建议"
    }
  ]
}
```

`level`、`summary`、`short_term_fix`、`long_term_fix` 是可选字段。缺省时，`build_report.py` 会回退到 `phase4a_rules.json` 的 `overall_risk` 和 `risk_reason`。

### 10.5 消费哪些 JSON Schema
- `references/report-schema.md §四（phase4b_risk.json）`
- 可选：`references/explain-guide.md`
- 可选：`references/rules/rules.json`

### 10.6 产生哪些 JSON Schema
依据 `references/report-schema.md §四（phase4b_risk.json）`。当前主流程保证每条 SQL 至少输出 `sql_id`、`call_chain`、`call_chain_broken`。

### 10.7 故障处理
| 场景 | 行为 |
|------|------|
| 调用链缺失 | `call_chain: []` 且 `call_chain_broken: true` |
| 可选 LLM 复核失败 | 不覆盖风险等级，继续使用规则和 EXPLAIN 结果 |
| 可选 LLM 输出不含有效等级 | 丢弃该条覆盖，继续使用规则和 EXPLAIN 结果 |

### 10.8 对应测试样例
- **调用链合并**：端到端 dry-run 后验证最终 report 中对应 SQL 有 `call_chain`。
- **调用链断裂**：源码目录不存在时验证 `call_chain_broken=true`。
- **风险覆盖缺省**：`phase4b_risk.json` 仅包含调用链时，最终风险等级仍由规则和 EXPLAIN 生成。

---

## 10. `build_report.py` — Phase 5（报告生成）

# ## 10. 1 脚本职责
聚合所有累积结果 → 生成结构化 JSON 报告，输出终端表格，在 CI 模式下写入 MR 评论并返回门禁结论。

# ## 10. 2 输入参数

| 参数 | 必填 | 默认值 | 说明 |
|------|:---:|--------|------|
| `--rules-file` | ✅ | — | phase4a_rules.json 路径 |
| `--explain-file` | ✅ | — | phase4b_explain.json 路径 |
| `--risk-file` | ✅ | — | phase4b_risk.json 路径 |
| `--mode` | ❌ | `local` | `local` / `ci` |
| `--mr-url` | ❌ | — | CI 模式下的 MR URL |
| `--base-branch` | ✅ | — | git diff base 分支（用于报告元数据） |
| `--run-id` | ✅ | — | 唯一的 session run_id |
| `--output` | ❌ | /tmp/sql_review/{run_id}/phase5_report.json | 输出路径 |

# ## 10. 3 输入文件
- `phase4a_rules.json`
- `phase4b_explain.json`
- `phase4b_risk.json`

# ## 10. 4 输出文件
**落盘到** `/tmp/sql_review/{run_id}/phase5_report.json`（schema 参见 `report-schema.md §五（phase5_report.json）`）。

同时在 stdout 输出终端表格：

```
┌──────┬──────────────────────────────────┬──────────┬───────┬──────────────────────────────────┐
│ #    │ SQL ID                           │ 等级     │ 类型   │ 摘要                             │
├──────┼──────────────────────────────────┼──────────┼───────┼──────────────────────────────────┤
│ 1    │ OrderMapper.xml:findAll:0        │ HIGH     │ SELECT │ 全表扫描 15823 行                │
│ 2    │ OrderMapper.xml:updateStatus:0   │ CRITICAL │ UPDATE │ 无 WHERE DML                     │
└──────┴──────────────────────────────────┴──────────┴───────┴──────────────────────────────────┘
```

CI 模式（`--mode ci`）额外：
- 在 GitLab MR 上写入评论（通过 `--mr-url` 对应的 MCP 调用）
- 标准输出最终门禁结论：`GATE: BLOCK` 或 `GATE: PASS`

# ## 10. 5 消费哪些 JSON Schema
- `references/report-schema.md §五（phase5_report.json）`（最终报告）
- `references/report-schema.md §二（phase4a_rules.json）`（验证 rules 输入）
- `references/report-schema.md §三（phase4b_explain.json）`（验证 explain 输入）
- `references/report-schema.md §四（phase4b_risk.json）`（验证 risk 输入）

# ## 10. 6 产生哪些 JSON Schema
`references/report-schema.md §五（phase5_report.json）`：report_id、context、gate、findings、review_checklist、degradation_notes。

# ## 10. 7 核心算法步骤
1. 加载并验证全部 3 个输入 JSON。
2. 逐 SQL 合并（按 sql_id）：
   - 从 phase4a 复制规则匹配结果。
   - 从 phase4b 复制 EXPLAIN 结果。
   - 从 risk 文件复制风险定性结论。
3. 聚合门禁结论：
   - `HIGH ≥ 1` → **BLOCK**
   - `MEDIUM ≥ 1` → **BLOCK**
   - 其余 → **PASS**
4. 遍历降级标记 → 构建复查清单：
   - 全局级降级：同类型只保留 1 条（如 `datasource_unknown`）。
   - SQL 级降级：按 `(file + type + line_start)` 去重。
5. 按 `risk_level` 降序排列 `findings`（先高后低风险，方便阅读）。
6. 写入 `phase5_report.json`。
7. 终端输出格式化的彩色表格。
8. 如果 `--mode ci`：通过 GitLab API 写入 MR 评论，标准输出门禁结论。

# ## 10. 8 失败处理
| 场景 | exit | 行为 |
|------|:---:|------|
| 输入文件缺失 | 1 | 中断，并给出缺失文件清单 |
| JSON 解析失败 | 1 | 列出无法解析的文件 |
| Schema 校验不匹配 | 1 | D16：中断并打印 `$WORK_DIR` 路径，中间文件保留在 work_dir 供人工排查 |
| 无 SQL 可报告（全部降级失败） | 0 | 输出空报告，`gate: PASS`，`review_needed` 非空 |

# ## 10. 9 不允许做什么
- 不调用 LLM —— 纯聚合
- 不连接数据库
- 不修改输入文件
- 不在 CI 模式下静默通过 —— `gate.decision` 必须可见
- 不在 MR 评论中 dump 完整 SQL（只放摘要）

# ## 10. 10 对应测试样例
- **聚合正确性**：将 sample rules + explain + risk JSON 文件输入 → 验证 report.json schema
- **门禁 BLOCK**：含至少一条 HIGH 的 risk 文件 → 验证 `gate.decision=BLOCK`
- **门禁 PASS**：全部 LOW → 验证 `gate.decision=PASS`
- **去重**：将两条重复的降级标记输入 → 验证 `review_needed` 中仅出现一次
- **缺失输入**：运行但不给 `--explain-file` → 验证 exit 1
- **格式不合格的 JSON**：给出一个被截断的 phase4b_risk.json → 验证 D16 中断且打印 work_dir 路径

---

## 11. `run_review.py` — Phase 0-5（一键编排）

### 11.1 脚本职责

把 Mapper 解析、调用链追踪、动态 SQL 展开、表名提取、DML proxy、规则匹配、EXPLAIN 和报告生成串成单个可测试流程。`SKILL.md` 默认只调用这个脚本，避免长会话里手工维护多阶段中间状态。

### 11.2 输入参数

| 参数 | 必填 | 默认值 | 说明 |
|------|:---:|--------|------|
| `--files` | ✅ | — | JSON 字符串：Mapper XML 文件路径数组 |
| `--project-root` | ❌ | `.` | Java 项目根目录 |
| `--project-src` | ❌ | `src/main/java` | 相对于 `--project-root` 的 Java 源码目录 |
| `--base-branch` | ❌ | `origin/master` | 报告上下文中的基准分支 |
| `--run-id` | ❌ | `manual` | 本次运行标识 |
| `--work-dir` | ❌ | `/tmp/sql_review/{run_id}` | 阶段产物目录 |
| `--dry-run` | ❌ | false | 使用 mock EXPLAIN，适合本地验收和 CI smoke test |
| `--mode` | ❌ | `local` | `local` / `ci` |
| `--output` | ❌ | `$WORK_DIR/phase5_report.json` | 最终报告路径 |

### 11.3 输出文件

`run_review.py` 会写入以下产物：

| 文件 | 内容 |
|------|------|
| `phase1_parse.json` | Mapper XML 解析结果 |
| `phase2_trace.json` | Java 调用链追踪结果 |
| `phase3_resolve.jsonl` | 动态 SQL 展开结果 |
| `phase3_5_tables.jsonl` | 主表提取结果 |
| `phase3_5_proxy.jsonl` | DML → SELECT proxy 结果 |
| `phase4b_batch.json` | 合并后的 EXPLAIN 输入 |
| `phase4a_rules.json` | 静态规则匹配结果 |
| `phase4b_explain.json` | EXPLAIN 或 dry-run EXPLAIN 结果 |
| `phase4b_risk.json` | 调用链上下文与可选风险覆盖信息 |
| `phase5_report.json` | 最终报告 |

### 11.4 核心算法步骤

1. 解析 `--files`，拒绝空数组或非法 JSON。
2. 调用 `parse_mapper.py` 提取 SQL。
3. 从解析结果生成 Mapper 方法全限定名，调用 `trace_callchain.py`。
4. 调用 `resolve_dynamic_sql.py` 做确定性动态 SQL 展开。
5. 调用 `extract_tables.py` 和 `dml_to_select_proxy.py` 生成 EXPLAIN 上下文。
6. 合并解析结果、resolved SQL、主表、proxy SQL，生成 `phase4b_batch.json`。
7. 调用 `match_rules.py` 生成 `phase4a_rules.json`。
8. 调用 `execute_explain.py`；带 `--dry-run` 时使用 mock EXPLAIN。
9. 将调用链写入 `phase4b_risk.json`，供 `build_report.py` 合并。
10. 调用 `build_report.py` 生成最终报告。
11. 在最终 JSON 中补充 `artifacts`，记录所有阶段产物路径。

### 11.5 失败处理

| 场景 | 行为 |
|------|------|
| `--files` 为空或不是 JSON 数组 | exit 1 |
| 子脚本返回非 0 | exit 1，并在 stderr 输出失败命令和错误 |
| Java 源码目录不存在 | 调用链为空，继续生成报告 |
| 未配置数据库且未使用 `--dry-run` | EXPLAIN 阶段标记失败，最终报告进入静态规则降级 |
| 多模块整仓扫描耗时过长 | 优先缩小 `--project-src` 到相关模块；需要完整链路时再扩大范围 |

### 11.6 对应测试样例

- **端到端 dry-run**：输入 `tests/fixtures/e2e/DemoCommonMapper.xml`，验证最终报告包含 3 条 finding。
- **调用链合并**：验证 `selectByCnId` 的 `call_chain` 进入最终 report，且 `call_chain_broken=false`。
- **接口注入链路**：实现类 `implements` 接口、上层按接口注入时，仍能追到更完整的调用链。
- **产物路径**：验证 `artifacts.rules_file`、`artifacts.explain_file` 指向对应阶段文件。

---

## 附录 A：脚本间数据流总览

```
extract_changes ──→ parse_mapper ──→ trace_callchain ──→ (LLM) resolve_dynamic_sql
                     │                                            │
                     │  (内存)                                     │
                     │             ┌──────────────────────────────┤
                     │             ▼                              │
                     │          extract_tables                    │
                     │          dml_to_select_proxy               │
                     │             │                              │
                     │             │  (内存)                      │
                     │             ▼                              ▼
                     └────────→ match_rules ──────────────────┐
                                   │   ║                      │
                                   │   ║                execute_explain
                                   ▼   ║                      │
                           phase4a_rules.json                  │
                                   │                           │
                                   └───────────┬───────────────┘
                                               │
                                               ▼   (LLM: SKILL.md §10)
                                      build_report ←── phase4b_risk.json
                                              │
                                              ▼
                                     phase5_report.json

run_review.py 作为主入口顺序执行以上脚本，并把所有阶段产物固定写入同一个 work_dir。
```

**图例**：
- 实线箭头（─→）：内存/管道传递，不落盘
- 虚线箭头（→）：输出落盘，JSON 文件存储至 `/tmp/sql_review/{run_id}/`

## 附录 B：出口代码契约

| exit | 含义 | 示例 |
|:---:|------|------|
| `0` | 成功，全部正常 | 所有 SQL 处理完毕，即使在探索性步骤中无匹配 |
| `0` | 成功，部分降级 | 某些 EXPLAIN 失败，其余已处理（降级矩阵 ℹ️ 标记） |
| `1` | 中断，用户必须修复 | 规则文件损坏、git 仓库缺失、全部 XML 解析失败 |
| `2` | 内部脚本错误 | 依赖缺失、异常未被捕获 |
| `3+` | 保留，留给 CI 管线扩展 | 管道失败、磁盘满、权限拒绝 |

**检查模式**（手动运行脚本）需输出可读错误，**CI 模式**需输出机器可解析日志格式。
