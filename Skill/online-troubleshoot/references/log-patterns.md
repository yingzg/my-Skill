# 日志格式模式库

当用户输入包含日志、异常栈、SQL 日志、访问日志或业务日志时，使用本文件进行结构化提取。命中模式后，将提取结果放入第 2 步上下文摘要，并把可验证片段作为 `log` evidence。

如果没有任何模式命中，不要猜测日志含义。保留原始文本，并在 `restricted_info` 中写入：

```text
日志格式未识别，可能遗漏信息
```

## 通用提取字段

尽量提取：

- `timestamp`：日志时间。
- `level`：ERROR、WARN、INFO、DEBUG 等。
- `thread`：线程名，如存在。
- `service`：服务名、应用名或日志 logger。
- `trace_id`：traceId、requestId、spanId，如存在。
- `message`：核心内容。
- `business_keys`：orderId、userId、tenantId、storeId、paymentId、settlementId 等。

缺失字段不要补造。

## Exception stack trace

### 命中信号

文本包含 Java/Python/JS 等异常栈特征，例如：

```text
java.lang.IllegalStateException: item snapshot missing
    at com.x.trade.service.OrderDetailService.buildItems(OrderDetailService.java:187)
    at com.x.trade.service.OrderDetailService.detail(OrderDetailService.java:92)
```

### 提取规则

- `exception_type`：异常类型，例如 `java.lang.IllegalStateException`。
- `exception_message`：异常信息，例如 `item snapshot missing`。
- `trigger_class`：第一条业务代码栈帧中的类名。
- `trigger_method`：第一条业务代码栈帧中的方法名。
- `trigger_file`：第一条业务代码栈帧文件名。
- `trigger_line`：第一条业务代码栈帧行号。
- `call_chain`：保留关键栈帧，最多 5 条。

### 证据用法

异常栈只能证明“错误在哪里抛出”和“错误文本是什么”。除非代码和数据验证闭环，否则不能单独证明根因。

## MyBatis SQL log

### 命中信号

文本包含 MyBatis 常见字段：

```text
==>  Preparing: select * from order_item_snapshot where order_id = ?
==> Parameters: 202607130001(String)
<==      Total: 0
```

或包含 `Preparing:`、`Parameters:`、`Total:`、`Updates:`。

### 提取规则

- `sql_template`：`Preparing:` 后的 SQL 模板。
- `parameters`：`Parameters:` 后的参数列表，保留类型。
- `result_count`：`Total:` 或 `Updates:` 后的数量。
- `duration`：如果同一段日志包含耗时，则提取耗时。
- `candidate_tables`：从 SQL 中提取表名。

### 证据用法

MyBatis 日志可作为 SQL 执行事实，但要注意：

- 如果日志来自用户粘贴，需标注来源为用户输入或日志系统。
- 如果参数缺失，不能补造完整 SQL。
- 如果只有 SQL 模板没有结果行数，不能当作数据库查询结果。

## Nginx access log

### 命中信号

文本类似：

```text
10.2.1.8 - - [13/Jul/2026:10:28:31 +0800] "GET /api/trade/order/detail?orderId=202607130001 HTTP/1.1" 500 128 "-" "Mozilla/5.0" rt=0.532 uct=0.003 uht=0.520
```

或包含 HTTP method、path、status、耗时字段。

### 提取规则

- `client_ip`：客户端 IP。
- `timestamp`：访问时间。
- `method`：GET、POST、PUT、DELETE 等。
- `path`：接口路径，不含 query 时保留 path。
- `query`：query string，如存在。
- `status_code`：HTTP 状态码。
- `response_size`：响应大小。
- `duration`：请求耗时，例如 `rt`。
- `upstream_duration`：上游耗时，例如 `uht`。

### 证据用法

Nginx access log 可证明接口、状态码和耗时。它不能单独证明业务根因，必须结合应用日志、代码或数据。

## 自定义业务日志

### 命中信号

文本包含时间戳、级别、业务内容三段，例如：

```text
2026-07-13 10:28:31.455 ERROR [trade-web] detail failed, orderId=202607130001, reason=item snapshot missing
```

### 提取规则

按以下顺序提取：

1. `timestamp`：`YYYY-MM-DD HH:mm:ss.SSS`、ISO-8601 或类似格式。
2. `level`：ERROR、WARN、INFO、DEBUG。
3. `service/logger`：中括号、logger 名或服务名前缀。
4. `message`：剩余内容。
5. `business_keys`：从 `key=value`、JSON、冒号分隔字段中提取业务 ID。

### 证据用法

业务日志可证明系统在某时间对某业务对象记录了某状态或错误。除非日志中包含查询结果或明确状态值，否则不要把日志扩展成数据库事实。

## JSON 日志补充规则

如果日志是 JSON：

```json
{"time":"2026-07-13T10:28:31+08:00","level":"ERROR","traceId":"abc","orderId":"202607130001","msg":"item snapshot missing"}
```

提取同名字段，并保留原始 JSON 作为 `raw_ref`。字段缺失时不补造。

## 未识别日志

未命中任何模式时：

1. 保留原始日志文本。
2. 提取肉眼可见的错误码、接口路径、业务 ID、时间范围。
3. 添加 `restricted_info`：`日志格式未识别，可能遗漏信息`。
4. 不基于未识别日志输出确定性根因。
