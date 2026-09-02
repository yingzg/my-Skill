# 输出模板

本文件只提供输出格式。字段含义、状态规则和证据要求以 `SKILL.md` 为准。

## 简版结论模板

默认使用此模板。除非用户要求“详细”，否则不要输出长报告。简版应使用业务语言，建议不超过 300 个中文字符。

```yaml
status: success | partial_success | failed
summary: >
  一句话说明当前结论。业务方能直接理解；不要写工具过程。
problem: >
  复述用户问题，包含系统/模块、业务对象、接口/页面、时间范围等已知信息。
root_cause: >
  根因或当前最可信判断。证据不足时必须写成"疑似/倾向"，并通过 status 降级体现。
evidence:
  - type: code | db | log | case | trace | user_input | tool_error
    source: "可追溯来源，例如文件:行号、SQL 查询、日志片段、案例 ID、Trace ID、工具错误"
    observation: "观察到的事实，禁止编造"
    supports: "该事实支持什么判断"
    confidence: high | medium | low
restricted_info:
  - "缺失信息或验证限制；无阻断项时使用 []"
recommendations:
  - level: P0 | P1 | P2
    action: "具体可执行操作"
    owner: "建议执行人/角色"
    verification: "验收标准"
    estimated_effort: "预期工作量"
```

字段来源：

- `status`：来源：`SKILL.md §Output Contract`、`§Status Rules`、`§Fail-Closed and restricted_info`
- `summary`：来源：`SKILL.md §Step 6: Root Cause Analysis and Output`
- `problem`：来源：`SKILL.md §Step 2: Context Extraction`
- `root_cause`：来源：`SKILL.md §Evidence closure`、`§Four-Layer Validation`
- `evidence`：来源：`SKILL.md §Output Contract`、`§Four-Layer Validation`
- `restricted_info`：来源：`SKILL.md §Fail-Closed and restricted_info`
- `recommendations`：来源：`SKILL.md §Step 6: Root Cause Analysis and Output`、`§Recommendations Generation`

## 详版报告模板

仅在用户要求“详细”“展开”“给排查过程”时使用。详版仍必须保留 v0.2 七字段结论，可以在七字段后追加过程说明；如果 step 2 已冻结 schema，最终机器可读结论仍只使用七字段。

````markdown
## 结论

```yaml
status: success | partial_success | failed
summary: ""
problem: ""
root_cause: ""
evidence: []
restricted_info: []
recommendations: []
```

## 排查过程

1. 历史案例预检：
   - 检索范围：
   - 命中情况：
   - 置信度：
   - 是否触发跳跃路径：

2. 上下文提取：
   - 系统/模块：
   - 接口/页面：
   - 业务 ID：
   - 时间范围：
   - 错误码/错误文案：
   - 日志结构化结果：
   - Trace 快速路径（如有 traceId）：
     - Trace ID：
     - 根操作：
     - 总耗时：
     - 黑洞时间/占比：
     - 匹配的诊断模式：
     - 代码搜索线索：

3. 代码定位：
   - 路由/入口：
   - 核心代码：
   - 调用链：
   - 候选表：
   - 搜索方式与置信度：

4. SQL 与数据验证：
   - 最小验证 SQL：
   - 根因确认 SQL：
   - 表名来源：
   - 数据源来源：
   - 查询结果或工具错误：

5. 业务逻辑闭环：
   - 代码逻辑：
   - 数据状态：
   - 用户现象：
   - 三者是否闭环：

6. 受限信息：
   - restricted_info:
````

章节来源：

- `历史案例预检`：来源：`SKILL.md §Step 1: Historical Case Precheck`
- `上下文提取`：来源：`SKILL.md §Step 2: Context Extraction`
- `代码定位`：来源：`SKILL.md §Step 3: Code Location`
- `SQL 与数据验证`：来源：`SKILL.md §Step 4: SQL Preparation`、`§Step 5: Database Query`
- `业务逻辑闭环`：来源：`SKILL.md §Four-Layer Validation`
- `受限信息`：来源：`SKILL.md §Fail-Closed and restricted_info`

## 回写草稿模板

仅在第 7 步生成。未经用户确认，不得写入经验库。

````markdown
# CASE-<待分配>: <系统/模块> - <现象摘要>

## 症状

- 系统/模块：
- 页面/接口：
- 用户可见现象：
- 错误码/错误文案：
- 首次发现时间：

## 根因

- 根因摘要：
- 触发条件：
- 影响范围：
- 置信度：

## 证据

### 代码证据

- 文件/行号：
- 观察：
- 支持：

### 数据证据

- 数据源：
- SQL：
- 查询结果：
- 支持：

### 日志证据

- 日志来源：
- 关键片段：
- 支持：

## 处理建议

### P0 立即止血
- 操作：
- 执行人：
- 验收标准：

### P1 性能/逻辑治理
- 操作：
- 执行人：
- 验收标准：

### P2 架构优化
- 操作：
- 执行人：
- 验收标准：

## restricted_info

- 未验证项：
- 权限/工具限制：
- 需要后续确认：

## 回写信息

- 验证人：
- 记录人：
- 回写时间：
- 关联工单：
````

字段来源：

- `症状`：来源：`SKILL.md §Step 2: Context Extraction`
- `根因`：来源：`SKILL.md §Step 6: Root Cause Analysis and Output`
- `证据`：来源：`SKILL.md §Output Contract`
- `处理建议`：来源：`SKILL.md §Step 7: Case Write-Back`
- `restricted_info`：来源：`SKILL.md §Fail-Closed and restricted_info`
- `回写信息`：来源：`SKILL.md §Step 7: Case Write-Back`

## 模板使用规则

- 默认输出简版结论。
- 用户要求详细时，输出详版报告。
- 只有进入第 7 步且用户确认回写时，才使用回写草稿。
- 不要把回写草稿写入 `golden-cases/`。
- 不要为了模板完整而补造未知字段；未知字段写入 `restricted_info` 或留空并标注未知。
