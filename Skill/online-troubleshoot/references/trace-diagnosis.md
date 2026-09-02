# Trace 诊断规则库

本文档提供日志驱动快速路径（步骤 2 子路径）中 Phase B/C/D 的诊断方法。它假设 Trace 数据已通过 ITraceFetcher 获取并标准化。

---

## 一、数据预处理

### 1.1 从 TraceDetail 提取信号

从标准化的 TraceDetail 中提取以下诊断信号：

| 信号 | 来源 | 用途 |
|------|------|------|
| 根操作名 `rootOperation` | rootSpan.operationName | 识别接口/入口 |
| 总耗时 `totalDuration` | totalDuration 或 rootSpan.duration | 判断是否超时 |
| 根 error 标记 | rootSpan.status === "error" | 判断入口是否报错 |
| 子 span 耗时分布 | childSpans[].duration | 识别慢调用 |
| 异常类型/消息 | errors[].exceptionType / exceptionMessage | 定向搜索 |
| 线程信息 | rootSpan.tags["thread.name"] | 阻塞判断辅助 |
| HTTP 状态码 | rootSpan.tags["http.status_code"] | 错误分类 |
| DB span 信息 | childSpans 中 db.type 存在的 span | 提取表名和 SQL |
| 服务/环境/区域 | serviceName、tags | 确定排查范围 |

### 1.2 失败兜底策略

Trace/日志 API 调用失败时按以下策略降级：

| 失败类型 | 降级策略 |
|---------|---------|
| permission_denied / 401 | 标注 restricted_info → 退回原步骤 2 逻辑 |
| timeout / 504 | 缩小时间窗口重试：-360,0 → -180,0 → -60,0 |
| not_found（traceId 不存在） | 标注 restricted_info → 退回原步骤 2 逻辑 |
| parse_error | 保留原始响应 → 标注 restricted_info → 继续 |
| 日志溢出（is_overflow=true） | 缩小 pageSize 和 timeRange → 仅查 ERROR/WARN → 标注 restricted_info |

---

## 二、时间线重构

### 2.1 方法

```
起点(rootSpan.startTime) → 中段(childSpans) → 终点(异常/错误日志时间)
```

按 span.startTime 升序排列，构建时间线：
- 标注每个 span 的起止时间、耗时、操作名。
- 在时间线末端标注异常或错误日志触发时间。
- 计算 span 之间的空隙。

### 2.2 黑洞检测

**公式**：

```
blackhole_ms = totalDuration - Σ(childSpans_duration_ms)
blackhole_percent = blackhole_ms / totalDuration * 100
```

**触发条件**：

- `blackhole_percent > 50%` → 触发黑洞诊断
- `blackhole_percent > 90%` → 强黑洞信号，极高概率为未埋点逻辑或线程阻塞

**黑洞定位**：

按子 span 的时间分布判断黑洞所处位置：

| 黑洞位置 | 表现 | 倾向判断 |
|---------|------|---------|
| 根 span 起始到第一个子 span 之间 | 启动阶段黑洞 | 初始化、鉴权、参数解析等前置逻辑未埋点 |
| 两个子 span 之间 | 中间黑洞 | 该阶段业务逻辑未埋点 |
| 最后一个子 span 到根 span 结束之间 | 尾部黑洞 | 响应组装、序列化、渲染等后置逻辑未埋点 |
| 无子 span（全部黑洞） | 单段黑洞 | 整个方法体未埋点，或只有一个入口 span |

### 2.3 Thread Blocking 检测（新增）

当黑洞占比较高且伴随以下线程特征时，标记 Thread Blocking 嫌疑：

**判断条件**（满足 2 条及以上）：
- 黑洞占比 > 70%
- 黑洞集中在 span 两端（启动或结束阶段）
- 根 span 线程 ID 在日志中出现多次 wait/timed_wait 状态
- 无明显的 CPU 密集型特征（如无大量计算型 span）
- 异常类型为 Broken pipe / ClientAbort / TimeoutException

**区分规则**：

| 特征组合 | 判断 | 后续建议 |
|---------|------|---------|
| 黑洞 > 70% + 无明显 CPU 特征 | 倾向于线程阻塞（等待外部资源/锁） | P0 调整线程池/队列 → P1 加锁竞争监控 |
| 黑洞 > 70% + 伴随 CPU 升高特征 | 倾向于未埋点密集计算 | P1 补 span + 剖析计算逻辑 |
| 黑洞 > 50% + Broken pipe | 倾向于响应超时被网关断开 | P0 调超时 → P1 优化响应生成 |

---

## 三、诊断模式

### Pattern 1: Broken Pipe / ClientAbortException

**触发条件**（满足全部）：
- rootSpan.status === "error"
- 异常类型匹配：`ClientAbortException` / `Broken pipe` / `Connection reset`
- 错误发生时间接近 totalDuration 终点

**剖层策略**：
1. 确认下游是否正常响应：检查子 span 是否有 error。
2. 如果下游正常 + Broken pipe → 服务端处理完成但客户端/网关已断开。
3. 计算断开时间点：通过异常日志时间戳与 totalDuration 的关系推算。

**代码搜索线索**：无需额外搜索（Broken pipe 本身不指向业务代码缺陷）。

**常见原因**：
- 网关/负载均衡器超时配置短于服务端处理时间。
- 客户端主动断开（用户关闭页面/刷新）。
- 响应体过大导致写回超时。

**建议映射**：

| 层级 | 建议 |
|------|------|
| P0 | 调大网关超时阈值；检查上游调用方的 timeout 配置 |
| P1 | 该接口建立超时监控（P95/P99）；对响应体大小设置告警 |
| P2 | 同步改异步（耗时接口返回 taskId 而非同步等待） |

### Pattern 2: 长耗时但子调用不慢（黑洞）

**触发条件**（满足全部）：
- totalDuration 异常高（明显超过接口 SLA）
- 所有子 span 耗时均正常（none > 500ms）
- 黑洞占比 > 50%

**剖层策略**：
1. 确定黑洞位置（启动/中间/尾部）。
2. 根据黑洞位置，从根操作的调用链中定位可能的方法。
3. 用黑洞两端最近的 span 操作名作为代码搜索锚点。

**代码搜索线索**：
- 黑洞在尾部 → 搜索根操作方法的出口逻辑（如 `buildResponse`、`serialize`、`render`）。
- 黑洞在中间 → 搜索相邻 span 之间的方法名。
- 黑洞在启动 → 搜索 middleware / filter / interceptor / AOP 切入逻辑。

**建议映射**：

| 层级 | 建议 |
|------|------|
| P0 | 调大超时阈值（如网关 timeout 或接口级超时配置） |
| P1 | 在黑洞所在代码段补 ≥ 3 个子 span；逐段剖析耗时 |
| P2 | 耗时跨度的操作改异步；建立所有接口的 P95/P99 Trace 告警 |

### Pattern 3: 回滚但无显式下游错误

**触发条件**（满足全部）：
- 异常栈含 `Rollback` / `Transaction rolled back` 等回滚标记
- 所有子 span 的 status 均为 ok（无 error span）
- 日志中无 5xx / SQL 错误

**剖层策略**：
1. 确认是主动回滚还是框架触发。
2. 主动回滚 → 业务校验失败（金额、状态、权限等不满足条件）。
3. 搜索回滚附近的业务关键字日志（WARN/INFO 级别）。

**代码搜索线索**：
- 搜索异常类型 + 方法名。
- 搜索事务管理注解（@Transactional）所在方法的逻辑。

**建议映射**：

| 层级 | 建议 |
|------|------|
| P0 | 查业务关键字日志（如"余额不足""状态不允许"等业务校验文案） |
| P1 | 在回滚逻辑的前置校验处补 WARN/INFO 级别日志 |
| P2 | 事务边界 Review；区分业务失败和系统失败的事务处理策略 |

### Pattern 4: 高频重复调用（N+1）

**触发条件**：
- 相同 operationName 的子 span 出现 ≥ 3 次
- 这些 span 的累计耗时占比较大（≥ 总耗时的 30%）

**剖层策略**：
1. 统计重复 span 出现次数和单次耗时。
2. 判断是否在循环内（通过 span 的 parent 关系和时间连续性）。
3. 判断是否每次请求同一资源（通过 tags 中的 db.sql 或 http.url 字段）。

**代码搜索线索**：
- 搜索 operationName 对应的方法名。
- 搜索循环体（for/while/forEach/stream）和调用点。

**建议映射**：

| 层级 | 建议 |
|------|------|
| P0 | 无（N+1 通常无法通过改配置解决） |
| P1 | 合并为批量查询；在循环外预取数据 |
| P2 | 引入 DataLoader / 批量查询中间件 |

### Pattern 5: 日志溢出

**触发条件**：
- `LookQueryResult.is_overflow === true`
- 或 ERROR/WARN 日志数量超过 pageSize 但实际总量未知

**剖层策略**：
1. 只依赖 ERROR/WARN 级别全部可用的日志。
2. INFO 日志按时间戳采样，覆盖关键时间点。
3. 标注 INFO 日志时间线不完整。

**代码搜索线索**：与正常流程一致，日志溢出不改变搜索方向。

**建议映射**：

| 层级 | 建议 |
|------|------|
| P0 | 缩小时间窗口重试；优先看 ERROR/WARN 日志 |
| P1 | 建立日志采样策略；限制单请求日志量 |
| P2 | 日志平台升级（增加采样、索引优化、冷热分离） |

### Pattern 6: Thread Blocking（新增）

**触发条件**（满足 ≥ 2 条）：
- 黑洞占比 > 70%
- 黑洞集中在 span 两端
- 根 span 线程 ID 出现 wait/timed_wait
- 伴随 Broken pipe / ClientAbortException / TimeoutException

**剖层策略**：
1. 综合时间线黑洞分布和线程等待信号判断阻塞类型。
2. 检查是否存在锁竞争——关注 `synchronized` / `ReentrantLock` / 分布式锁。
3. 检查是否等待外部资源回调——关注 HTTP 回调、消息队列等待。

**代码搜索线索**：
- 搜索黑洞附近代码段中的锁使用（`synchronized`、`lock`、`tryLock`）。
- 搜索线程池配置（`ThreadPoolExecutor`、`@Async`）。
- 搜索外部回调/异步等待（`CompletableFuture.get()`、`CountDownLatch.await()`）。

**建议映射**：

| 层级 | 建议 |
|------|------|
| P0 | 调整线程池大小或队列容量；对同步等待加超时 |
| P1 | 锁定争用热点（加 jstack 定时采集）；引入锁竞争监控 |
| P2 | 无锁化改造；拆分共享资源减少竞争粒度 |

---

## 四、模式匹配优先级

当多个模式同时触发时，按以下优先级处理：

1. **Pattern 5（日志溢出）** → 先处理降级，确保后续分析不依赖不完整的 INFO 日志。
2. **Pattern 1（Broken pipe）** → 最外显的信号，优先判断是否为网关/超时配置问题。
3. **Pattern 2（黑洞）** → 核心诊断，黑洞位置决定代码搜索方向。
4. **Pattern 6（Thread Blocking）** → 当黑洞位置特征匹配时，追加阻塞诊断。
5. **Pattern 4（N+1）** → 在子 span 分析时附带检查。
6. **Pattern 3（回滚但无报错）** → 仅当出现回滚标记时触发。

---

## 五、模式 → 建议映射表

| 诊断模式 | P0（立即止血） | P1（治理） | P2（架构优化） |
|---------|--------------|-----------|---------------|
| Pattern 1: Broken pipe | 调大网关/上游超时阈值 | 建立接口超时告警 | 时效要求高的接口改异步；引入降级策略 |
| Pattern 2: 黑洞 | 调大超时阈值 | 在黑洞段补 ≥ 3 个 span；逐段剖析 | 耗时逻辑异步化；P95 Trace 告警 |
| Pattern 3: 回滚无报错 | 查业务 WARN/INFO 日志确认失败原因 | 前置校验补日志 | 统一异常处理框架 Review |
| Pattern 4: N+1 | 无 | 合并为批量查询；循环外预取 | 引入 DataLoader / 批量中间件 |
| Pattern 5: 日志溢出 | 缩窗重试；优先 ERROR/WARN | 建立日志采样策略 | 日志平台升级 |
| Pattern 6: Thread Blocking | 调大线程池/队列 | jstack 监控；锁定争用热点 | 无锁化改造；拆分资源 |
