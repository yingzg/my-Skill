# GC-004: Trace 驱动排查 + 三层修改建议

## 目的

验证 Agent 在用户提供 traceId 时，触发「日志驱动快速路径」完成 Trace 诊断 → 代码定位 → 数据验证 → 输出 v0.2 七字段契约（含 `recommendations` 三层建议），且不跳过黑洞识别和代码搜索。

这是 Golden Case，不是经验案例库。它不得被第 1 步历史案例预检当作 `CASES_DIR/CASE-xxx.md` 使用。

## 输入场景

用户输入：

```text
traceId: 9a3f2b1c-d4e5-6f7a-8b9c-0d1e2f3a4b5c
订单详情页打开超时报错
```

## 测试环境给定事实

### Trace 数据

ITraceFetcher.getTrace 返回：

```yaml
traceId: 9a3f2b1c-d4e5-6f7a-8b9c-0d1e2f3a4b5c
totalDuration: 6400
rootSpan:
  operationName: GET /api/trade/order/detail
  serviceName: trade-web
  startTime: 1750951710000
  duration: 6400
  status: error
  tags:
    http.status_code: "500"
    thread.name: http-nio-8080-exec-42
childSpans:
  - operationName: db/order_item_snapshot/select
    serviceName: trade-service
    duration: 150
    status: ok
    tags:
      db.type: mysql
      db.table: order_item_snapshot
      db.sql: select * from order_item_snapshot where order_id=?
  - operationName: oss/upload/product_image
    serviceName: trade-service
    duration: 300
    status: ok
errors:
  - type: exception
    spanId: root
    exceptionType: ClientAbortException
    exceptionMessage: Broken pipe
```

### 日志数据

ITraceFetcher.getLogs(level=ERROR, pageSize=5) 返回：

```text
2026-07-13 10:28:37.891 ERROR [trade-web] c.x.trade.web.OrderController - detail failed, orderId=202607130001
org.apache.catalina.connector.ClientAbortException: Broken pipe
    at org.apache.catalina.connector.OutputBuffer.realWriteBytes(OutputBuffer.java:366)
```

### 代码搜索事实

（给定事实：code-intelligence 已配置并接入 GitNexus，步骤 3 通过 code-intelligence 调 GitNexus 返回，source=gitnexus）

结构搜索可定位：

```text
file: trade-web/src/main/java/com/x/trade/web/OrderController.java
line: 54
snippet: return orderDetailService.detail(orderId);
matchType: route
confidence: high
source: gitnexus
query: /api/trade/order/detail
```

```text
file: trade-service/src/main/java/com/x/trade/service/OrderDetailService.java
line: 92
snippet: public OrderDetailVO detail(String orderId) { ... }
matchType: keyword
confidence: high
source: gitnexus
query: OrderDetailService.detail
```

```text
file: trade-service/src/main/java/com/x/trade/service/ReportService.java
line: 245
snippet: public ReportData buildReportData(OrderDetail detail) {
    // 大对象序列化 + PDF 渲染，无子 span
    String json = objectMapper.writeValueAsString(detail);
    byte[] pdf = pdfRenderer.render(json);
    return new ReportData(pdf);
}
matchType: keyword
confidence: high
source: gitnexus
query: buildReportData
```

### SQL 整理事实

根因确认 SQL：

```sql
select order_id, count(*) as item_count
from order_item_snapshot
where order_id = '202607130001'
group by order_id;
```

### 数据库查询事实

根因确认查询返回：

```text
order_id: 202607130001, item_count: 3
```

## 预期行为

Agent 必须：

1. 执行第 1 步历史案例预检，并说明没有高置信跳跃路径。
2. 第 2 步识别到 traceId → 触发日志驱动快速路径：
   - 阶段 A：调用 ITraceFetcher.getTrace 和 getLogs。
   - 阶段 B：计算黑洞时间 = 6400 - 150 - 300 = 5950ms，占比 93%，标记为未埋点处理段；匹配 Pattern 2（长耗时但子调用不慢）和 Pattern 1（Broken pipe）。
   - 阶段 C：提取代码线索（接口路径 /api/trade/order/detail、异常类名 ClientAbortException）→ 交给第 3 步。
3. 第 3 步使用精准线索搜索，定位到 OrderController、OrderDetailService 和 ReportService.buildReportData。
4. 第 4 步说明 SQL 的表名来源、数据源来源和查询目的。
5. 第 5 步执行数据库查询，确认数据量正常（3 条明细），排除数据缺失原因。
6. 第 6 步输出 v0.2 **七字段**契约（status/summary/problem/root_cause/evidence/restricted_info/recommendations），状态为 `success` 或 `partial_success`。
7. `evidence` 至少包含 `code`、`db`、`log`、`user_input`、`trace` 五类证据。
8. `recommendations` 必须包含三层建议，且每层至少有一条绑定到具体代码或数据的建议。
9. P0 建议必须是运维/值班可独立执行的操作，不依赖代码发布。
10. `restricted_info` 应标注黑洞段未通过 span 验证。

## 预期输出契约

```yaml
status: partial_success
summary: 订单详情接口超时是因为 buildReportData() 内部大对象序列化和 PDF 渲染耗时约 5900ms，超过网关超时阈值导致 Broken pipe，但子调用（DB 150ms、OSS 300ms）均不慢。
problem: 用户反馈订单详情页打开超时报错，接口 /api/trade/order/detail 总耗时 6400ms 后返回 500 错误。
root_cause: ReportService.buildReportData() 方法内 JSON 序列化和 PDF 渲染无子 span 埋点，实际耗时约 5900ms 导致接口总耗时超过网关超时阈值，触发 ClientAbortException。
evidence:
  - type: user_input
    source: 用户输入
    observation: 提供 traceId 和问题描述。
    supports: 明确排查对象为订单详情接口。
    confidence: high
  - type: trace
    source: ITraceFetcher.getTrace(traceId=9a3f2b1c)
    observation: 根 span /api/trade/order/detail 总耗时 6400ms，子 span DB 150ms + OSS 300ms，剩余 5950ms 无法归属子 span（黑洞占比 93%）。
    supports: 接口超时由未埋点的处理逻辑导致，非子调用缓慢。
    confidence: high
  - type: log
    source: ERROR 日志
    observation: ClientAbortException: Broken pipe，触发时间 10:28:37.891。
    supports: 网关/客户端在服务端完成响应前断开连接。
    confidence: high
  - type: code
    source: trade-service/src/main/java/com/x/trade/service/ReportService.java:245
    observation: buildReportData() 内 objectMapper.writeValueAsString + pdfRenderer.render，无子 span 埋点。
    supports: 黑洞段对应的代码逻辑为 JSON 序列化和 PDF 渲染。
    confidence: high
  - type: code
    source: trade-web/src/main/java/com/x/trade/web/OrderController.java:54
    observation: 根路由入口调用 orderDetailService.detail(orderId)。
    supports: 代码链路与 Trace 根操作一致。
    confidence: high
  - type: db
    source: 交易中心订单库
    observation: order_item_snapshot 查询订单 202607130001 返回 3 条商品明细，数据量正常。
    supports: 排除数据缺失导致超时。
    confidence: high
restricted_info:
  - "黑洞 5950ms 内具体耗时分布未通过子 span 验证（JSON 序列化 vs PDF 渲染各自耗时未知）"
recommendations:
  - level: P0
    action: 调大网关超时阈值从当前值（推测 3s）调整到至少 8s；或对该接口设置单独超时策略。
    owner: 运维/值班
    verification: 该接口 5xx 错误率归零，用户不再反馈超时。
    estimated_effort: 30 分钟
  - level: P1
    action: 在 buildReportData() 内部补 3 个子 span：json_serialize、pdf_render、total_report_build；同步验证 JSON 序列化是否有循环引用或深层嵌套导致的性能问题。
    owner: 业务开发组
    verification: Trace 黑洞时间从 5900ms 降至可观测（每个子 span 单独可见耗时）。
    estimated_effort: 1 天
  - level: P2
    action: 报表生成改异步：订单详情接口只返回核心数据，PDF 报表通过异步任务生成后通知用户下载；建立 Trace P95 > 3s 的报警规则。
    owner: 架构组
    verification: 同步接口耗时降低到 1s 以内；同类超时客诉量下降 80%。
    estimated_effort: 2-4 周
```

## 失败判据

出现任一情况即判定失败：

- 有 traceId 但未触发日志驱动快速路径（仍只用文本关键词搜索）。
- 未进行黑洞时间计算或未识别 Pattern 2。
- 未从 Trace 提取代码线索交给步骤 3。
- 输出 `success` 但未标注黑洞段未经 span 验证。
- `recommendations` 为空或只有泛泛的"建议优化性能"。
- `recommendations` 三层建议未绑定到具体代码段或数据事实。
- P0 建议依赖代码发布（如"修改 buildReportData 方法"）。
- 输出 schema 为 v0.1 六字段（缺少 `recommendations`）。
- 编造未给定的 Trace 数据、SQL 查询结果、文件路径或行号。
- summary 不是业务可读语言，或超过 300 个中文字符。

## 对 SKILL.md 的反向要求

为通过此 GC，`SKILL.md` 必须明确：

- 步骤 2 有 traceId 时触发日志驱动快速路径，包含阶段 A（获取 Trace）、阶段 B（黑洞计算 + 模式匹配）、阶段 C（提取代码线索）。
- 黑洞时间计算公式 = 总耗时 - Σ(子span耗时)，阈值 ≥ 50% 触发诊断。
- Pattern 2（长耗时但子调用不慢）的触发条件和代码搜索线索。
- v0.2 Output Contract 包含七字段，`recommendations` 为新增必填字段。
- `recommendations` 三层定义：P0 运维/值班可独立执行，P1 代码治理，P2 架构优化。
- `restricted_info` 不覆盖 `recommendations` 该做的事——前者说排查时缺了什么，后者说修的时候该干什么。
- L4 最终验证必须检查 `recommendations` 不为空且每层建议有证据锚点。
