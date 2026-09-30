# online-troubleshoot 增强设计文档

> 日期：2026-07-14
> 基线版本：`online-troubleshoot` v0.1（当前 458 行 SKILL.md）
> 增强目标：v0.2 — 集成 Trace 驱动诊断能力 + 三层修改建议系统

---

## 一、增强目标

在现有 `online-troubleshoot` v0.1 骨架（7 步流水线 + Output Contract + Checkpoint + 四层验证 + Golden Cases × 3）的基础上，注入以下两个能力：

### 能力 1：Trace 驱动日志排查快速路径

**解决问题**：v0.1 的步骤 2（上下文提取）在用户只提供日志/traceId、不提供接口路径/错误码时，代码定位线索太少，只能靠模糊关键词 grep，生效率不稳定。

**方案**：在步骤 1 和步骤 2 之间插入一条「日志驱动快速路径」。当用户输入包含 `traceId` 或可识别的 Trace 标识时：

```
步骤 1 → 步骤 2
          │
          ├─ 有 traceId? 
          │     ├─ Phase A: ITraceFetcher → 获取 Trace + Logs
          │     ├─ Phase B: Trace 诊断 → 时间线重构 + 黑洞识别 + 模式匹配
          │     └─ Phase C: 提取精准代码线索 → 喂给步骤 3
          │          ↓
          │     步骤 3: ICodeSearcher（已有精准线索，不再靠模糊grep）
          │          ↓
          │     步骤 4-7 不变
          │
          └─ 无 traceId → 原步骤 2 逻辑不变
```

**价值**：有 traceId 时，步骤 3 的搜索从"猜关键词"变成"按接口路径+异常类名+慢方法名精准搜索"。搜索精度从「可能找到」升级为「应该找到」。

### 能力 2：三层修改建议系统（P0/P1/P2）

**解决问题**：v0.1 的步骤 6 只输出根因结论，不输出修改方案。"知道了问题在哪，不知道怎么修"。

**方案**：在步骤 6 的输出中新增 `recommendations` 字段（三层结构），作为 Output Contract 的一部分。三层定义：

| 层级 | 名称 | 目标 | 执行人 | 时间 |
|------|------|------|--------|------|
| P0 | 立即止血 | 让用户不再报错 | 运维/值班 | 1-2 天 |
| P1 | 性能/逻辑治理 | 让问题能被看见、不再复发 | 业务开发组 | 1 周 |
| P2 | 架构优化 | 让同类问题不再出现 | 架构组 | 1 月+ |

每层包含：`action`（动作）、`owner`（执行人/角色）、`verification`（验收标准）。

---

## 二、文件变更清单

### 2.1 变更的文件

| 文件 | 变更类型 | 内容 |
|------|---------|------|
| `SKILL.md` | **修改** | 新增「Trace 驱动快速路径」章节（步骤 2.5 或步骤 2 的子节）；步骤 6 输出新增 `recommendations`；Output Contract 升级为 v0.2（新增 `recommendations` 字段）；新增 Thread Blocking Detection 诊断模式 |
| `templates/output.md` | **修改** | 简版/详版模板新增 `recommendations` 区块 |
| 无 | **不变** | `references/log-patterns.md`、`references/troubleshoot-examples.md` 内容仍然适用 |

### 2.2 新增的文件

| 文件 | 用途 |
|------|------|
| `references/trace-diagnosis.md` | Trace 诊断规则库：时间线重构方法、黑洞识别公式、5 种诊断模式（Broken pipe / 黑洞 / 回滚无报错 / N+1 / 日志溢出 / Thread Blocking）、模式到 P0/P1/P2 的映射表 |
| `golden-cases/GC-004-trace-driven.md` | 新增 Golden Case：有 traceId 输入时的快速路径 + P0/P1/P2 输出 |
| `golden-cases/GC-005-trace-partial.md` | 新增 Golden Case：有 traceId 但 Trace API 不可用时的降级行为 |

### 2.3 最终目录结构

```
online-troubleshoot/
├── SKILL.md                              # ~600行（+140行）
├── references/
│   ├── log-patterns.md                   # 不变
│   ├── troubleshoot-examples.md          # 不变
│   └── trace-diagnosis.md                # 新增：Trace 诊断规则库
├── golden-cases/
│   ├── README.md                         # 更新：增加 GC-004、GC-005 说明
│   ├── GC-001-full-success.md           # 变更：预期输出新增 recommendations
│   ├── GC-002-case-reuse.md             # 变更：预期输出新增 recommendations
│   ├── GC-003-partial-success.md        # 变更：预期输出新增 recommendations
│   ├── GC-004-trace-driven.md           # 新增
│   └── GC-005-trace-partial.md          # 新增
├── templates/
│   └── output.md                         # 变更：新增 recommendations 区块
└── docs/
    ├── 2026-07-10-online-troubleshoot-design.zh-CN.md
    └── 2026-07-14-enhanced-design.zh-CN.md   # 本文档
```

---

## 三、核心设计细节

### 3.1 ITraceFetcher 抽象接口

与 ICodeSearcher / IDatabaseQuery 同模式——定义接口契约，不绑定具体实现。

```typescript
interface ITraceFetcher {
  /**
   * 根据 traceId 获取完整 Trace 数据
   * @returns 标准化的 TraceDetail，或错误信息
   */
  getTrace(traceId: string, options?: { appName?: string; area?: string; env?: string }): Promise<TraceDetail | TraceError>;

  /**
   * 根据 traceId 获取关联日志
   * 优先查 ERROR/WARN/keyword，INFO 仅在溢出时抽样
   */
  getLogs(traceId: string, options?: {
    level?: "ERROR" | "WARN" | "INFO";
    keyword?: string;
    timeRange?: string;     // e.g. "-360,0"
    pageSize?: number;
    page?: number;
  }): Promise<LogEntry[] | LogError>;
}

// 标准化 Trace 数据结构（对齐 OpenTelemetry）
interface TraceDetail {
  traceId: string;
  spans: Span[];
  totalDuration: number;    // ms
  errors: TraceError[];
}

interface Span {
  spanId: string;
  parentSpanId?: string;
  operationName: string;    // e.g. "GET /api/trade/order/detail"
  serviceName: string;
  startTime: number;        // epoch ms
  duration: number;         // ms
  status: "ok" | "error";
  tags: Record<string, string>;   // e.g. thread.name, http.status_code
  events: SpanEvent[];
}

interface SpanEvent {
  name: string;             // e.g. "exception"
  timestamp: number;
  attributes: Record<string, string>;  // e.g. exception.type, exception.message
}

interface LogEntry {
  timestamp: number;
  level: string;
  service: string;
  message: string;
  traceId: string;
  raw?: string;
}

interface TraceError {
  type: "api_error" | "timeout" | "not_found" | "permission_denied" | "parse_error";
  message: string;
  source: string;           // e.g. "hera" | "jaeger"
}
```

### 3.2 Trace 驱动快速路径流程（步骤 2 的子路径）

在步骤 2（上下文提取）识别到用户输入中有 `traceId` 或等效 Trace 标识时触发。

```
Phase A — 获取原始数据
  ├─ ITraceFetcher.getTrace(traceId) → TraceDetail
  │   失败 → 缩小时间窗口 / 重试 / 标注 restricted_info 后走原步骤 2
  ├─ 从 TraceDetail 提取信号：
  │   - 根操作名（接口路径）
  │   - 总耗时
  │   - 根 span 是否 error=true
  │   - 子 span 耗时分布（DB/HTTP 子调用）
  │   - 服务名、环境、区域
  │   - 异常字段（exception.type、exception.message）
  │   - 线程信息（thread.name、thread.id）
  └─ ITraceFetcher.getLogs(traceId, {level: "ERROR", keyword: ...})
     失败 → 降级：缩小 pageSize / 缩小时间窗口 / 只查 ERROR

Phase B — Trace 诊断（详见 references/trace-diagnosis.md）
  ├─ 时间线重构：
  │   起点(root span.start) → 中段(子span) → 终点(异常日志)
  ├─ 黑洞检测：
  │   黑洞时间 = 总耗时 - Σ(子span耗时)
  │   黑洞占比 > 50% → 标记为未埋点处理段
  │   黑洞集中在 span 两端 → Thread Blocking 嫌疑
  ├─ 模式匹配（5+1 种模式）：
  │   1. Broken Pipe / ClientAbortException
  │   2. 长耗时但子调用不慢（黑洞）
  │   3. 回滚但无显式下游错误
  │   4. 高频重复调用（N+1）
  │   5. 日志溢出
  │   6. Thread Blocking（新增：黑洞+线程特征）
  └─ 产出：诊断摘要（模式 + 根因推断 + 置信度）

Phase C — 提取精准代码线索
  ├─ 从 Trace 提取 → 塞给步骤 3 的 ICodeSearcher：
  │   - 接口路径：searchByRoute("/api/trade/order/detail")
  │   - 异常类名：searchByKeyword("IllegalStateException")
  │   - 异常消息：searchByError("item snapshot missing")
  │   - 慢方法名：searchByKeyword("buildReportData")
  │   - SQL 片段：searchByKeyword("order_item_snapshot")
  └─ 代码搜索线索来源标记为 "trace"（区别于 "user_input"）
```

### 3.3 步骤 2 的触发判断

新增如下判断逻辑（放在现有步骤 2 开头）：

```
步骤 2 — 上下文提取

IF 用户输入中包含以下任一信号：
  - 显式的 traceId 字符串
  - "trace" / "span" / "traceId" / "requestId" 关键词伴随 ID
  - 来自 Hera / Jaeger / Zipkin 链接
THEN
  触发「日志驱动快速路径」（Phase A→B→C，产出增量约 60 行上下文字段）
  快速路径产出的结构化上下文 = 原步骤 2 产出内容 + Trace 特有字段：
    - trace_fetcher_source: "hera" | "jaeger" | "unavailable"
    - trace_diagnosis: { pattern, blackhole_percent, confidence }
    - code_clues_from_trace: CodeClue[]
ELSE
  执行原步骤 2 逻辑（从用户文本/截图/日志中一次性提取）
```

### 3.4 步骤 6 — recommendations 字段设计

#### Output Contract 升级

v0.1 六字段 → v0.2 七字段：

```yaml
status: success | partial_success | failed
summary: string
problem: string
root_cause: string
evidence: Evidence[]
restricted_info: string[]
recommendations: Recommendation[]    # ← 新增
```

#### Recommendation 结构

```typescript
interface Recommendation {
  level: "P0" | "P1" | "P2";
  action: string;           // 具体可执行操作
  owner: string;            // 建议执行人/角色
  verification: string;     // 验收标准
  estimated_effort: string; // 预期工作量
}
```

#### 三层建议的生成规则

**规则**：建议必须绑定证据。不能凭空写"建议优化接口性能"。

| 证据来源 | 典型 P0 建议 | 典型 P1 建议 | 典型 P2 建议 |
|---------|------------|------------|------------|
| Trace 黑洞 >50% | 调大网关超时阈值 | 在黑洞代码段补 3+ 个子 span | 同步接口改异步 |
| Broken pipe + 下游正常 | 调大上游超时 | 下游加超时监控告警 | 引入重试/降级策略 |
| 回滚无报错 | 无（不需要 P0，因为没报错） | 在关键分支加错误日志 | 统一异常处理框架 Review |
| N+1 重复调用 | 无 | 合并为批量查询接口 | 引入 DataLoader 模式 |
| Thread Blocking | 扩线程池/调整队列大小 | 锁定争用热点加 jstack 监控 | 无锁化改造 |
| 日志溢出 | 降级日志级别/限制长度 | 建立日志采样策略 | 日志平台升级 |
| 代码证据 + DB 证据 | 数据修复脚本 | 加缺失数据的防御逻辑 | 数据完整性监控 |

**必须约束**：
- 如果证据不足以支撑某层建议，该层可以为空数组 `[]`
- 不能写"建议排查 XX"这种循环依赖——排查是 SKILL 该做的事
- P0 必须是运维/值班能独立执行的（调参数、改配置、切流量），不能依赖代码发布
- 如果是 `partial_success` 或 `failed`，`recommendations` 可以只包含 P0（如"联系 XX 团队确认数据状态"），P1/P2 不可靠时可以省略

#### 与 restricted_info 的关系

`recommendations` 和 `restricted_info` 不重复。`restricted_info` 描述"排查时缺了什么"，`recommendations` 描述"修的时候该干什么"。

示例对比：
```
restricted_info: "数据库权限不可用，无法确认账单真实状态"
recommendations: P0 - 联系 DBA 确认 settlement_bill 表中该账单的状态
```

### 3.5 快速路径的 Fail-Closed 降级

Trace 驱动路径有自己的降级矩阵：

| 降级触发 | 行为 |
|---------|------|
| Trace API 不可用 | 标注 `restricted_info`："Trace 查询不可用"，退回原步骤 2 逻辑 |
| Trace API 返回 504 / 超限 | 缩小时间窗口重试（-360→-180→-60）；仍失败则取已有数据 + 标注信息不足 |
| 日志 API 溢出 | ERROR/WARN 已拿全，INFO 抽样页翻；标注"INFO 日志时间线不完整" |
| Trace 诊断发现黑洞但无法定位代码 | 步骤 3 用语义搜索（RAG）+ 黑洞相关方法名；仍失败则标注"黑洞代码段未定位" |
| 无任何模式匹配 | 基础摘要 + 标注"未匹配已知诊断模式"；不强行匹配 |

### 3.6 GC-004 设计

```
GC-004: Trace 驱动排查 + 三层建议

输入场景:
  用户只提供一个 traceId 和一句话描述：
  "traceId: 9a3f2b1c-d4e5-6f7a-8b9c-0d1e2f3a4b5c，订单详情页超时报错"

测试环境给定事实:
  - Hera API 可用
  - Trace 返回：根 span /api/trade/order/detail，总耗时 6400ms，status=error
  - 子 span：DB 查询 150ms，OSS 上传 300ms，无其他子 span
  - 黑洞时间 = 6400 - 150 - 300 = 5950ms（占比 93%）
  - 错误：ClientAbortException / Broken pipe
  - 日志：ERROR "Broken pipe" at response write
  - 代码搜索：可定位到 buildReportData() 方法，内部有大对象序列化 + PDF 渲染
  - 数据库：order_item 表数据量正常（3条明细）

预期行为:
  1. 步骤 2 识别到 traceId → 触发快速路径
  2. Phase A: 获取 Trace + Logs
  3. Phase B: 时间线重构 → 黑洞 93% → 定位 buildReportData
  4. Phase C: 提取代码线索 → 交给步骤 3
  5. 步骤 3: 精准搜索 → 定位 ReportService.buildReportData
  6. 步骤 4-5: SQL 验证数据量正常
  7. 步骤 6 输出:
     - status: success（或 partial_success，如果黑洞代码段未完全验证）
     - recommendations:
       P0: 调大网关超时阈值从 3s → 8s
       P1: buildReportData() 内补 3 个子 span；JSON 序列化改用 Kryo
       P2: 报表生成改异步；建立 Trace P95>3s 告警

失败判据:
  - 有 traceId 但没有走快速路径
  - 未进行黑洞计算
  - 输出 recommendations 为空或只有泛泛的"建议优化性能"
  - recommendations 未绑定到具体代码段
```

### 3.7 GC-005 设计

```
GC-005: Trace 驱动路径降级

输入场景:
  "traceId: abc123，营销活动页保存失败"

测试环境给定事实:
  - Hera API 返回 401 权限错误（不可用）
  - 无其他 Trace 工具可用

预期行为:
  1. 步骤 2 识别到 traceId → 尝试 ITraceFetcher
  2. getTrace 返回 permission_denied
  3. 不中止，退回原步骤 2 逻辑
  4. 从用户文本中提取"营销活动""保存失败"等信息
  5. 按原流程继续
  6. restricted_info 包含"Trace 查询权限不可用，已退回文本分析"

失败判据:
  - 因 Trace API 不可用而直接输出 failed
  - 卡在 Phase A 反复重试而不退回原步骤 2
```

### 3.8 参考文件 trace-diagnosis.md 结构

```
# Trace 诊断规则库

## 数据预处理
  - 提取信号（根操作、总耗时、错误标记、子span分布、异常字段、线程信息）
  - 失败兜底策略（超时→缩窗、溢出→降级、不可用→标注）

## 时间线重构
  - 起点 → 中段 → 终点的组织方法
  - 黑洞时间计算公式与阈值（>50% 总耗时触发诊断）

## 诊断模式
  1. Broken Pipe / ClientAbortException
  2. 长耗时但子调用不慢（黑洞）
  3. 回滚但无显式下游错误
  4. 高频重复调用（N+1）
  5. 日志溢出
  6. Thread Blocking（新增）

  每个模式包含：
    - 触发条件（在 TraceDetail 上怎么判断）
    - 剖层策略（触发后做什么）
    - 代码搜索线索（该模式应该搜什么关键词）
    - 到 P0/P1/P2 的建议映射

## 模式 → 建议映射表
  一张矩阵表，行是模式，列是 P0/P1/P2，单元格是典型建议文本
```

---

## 四、SKILL.md 变更概要

### 4.1 需要修改的章节

| 章节 | 变更内容 | 行数增量 |
|------|---------|---------|
| 开头声明 | description 和 Core Positioning 同步更新，提及 Trace 能力 | +2 |
| Non-Negotiable Principles | 不变 | 0 |
| Resource Loading | 新增：有 traceId 时加载 `references/trace-diagnosis.md` | +3 |
| 步骤 2 | 在开头新增 Trace 快速路径触发判断 + Phase A/B/C 子流程 | +80 |
| 步骤 3 | 代码搜索线索来源新增 `trace` 类型；搜索策略中提及从 Trace 提取的精准线索优先级最高 | +5 |
| 步骤 6 | 新增 recommendations 字段说明和三层建议生成规则 | +25 |
| Output Contract | v0.1 → v0.2；六字段 → 七字段；新增 Recommendation 结构定义 | +15 |
| Fail-Closed | 新增 Trace 路径的降级矩阵 | +10 |
| 自检清单 | 新增 Trace 路径自检项 | +5 |

**总增量**：约 +140 行（458 → 600 行）

### 4.2 不变的部分

以下章节完全不动：
- 步骤 1（历史案例预检）
- 步骤 4（SQL 整理）
- 步骤 5（数据库查询）
- 步骤 7（案例回写）
- No Invention Rules
- Checkpoint Protocol（可能需要加 `trace_fetcher_source` 字段）
- Four-Layer Validation
- Common Failure Modes

---

## 五、实施顺序

按以下顺序实施：

1. **先写 GC-004 + GC-005**（30 分钟）
   - 定义"我想要的行为是什么"
   - 写完 GC 后，用 GC 反推 SKILL.md 需要哪些规则

2. **写 references/trace-diagnosis.md**（20 分钟）
   - 6 种诊断模式 + 模式→建议映射表

3. **修改 SKILL.md**（30 分钟）
   - 步骤 2 插入快速路径
   - 步骤 6 新增 recommendations
   - Output Contract v0.2
   - Trace 路径降级矩阵

4. **修改 templates/output.md**（10 分钟）
   - 简版/详版模板新增 recommendations 区块

5. **更新 GC-001/002/003/README**（15 分钟）
   - 预期输出补上 recommendations 字段
   - GC-001/002 的 recommendations 不为空（有证据支撑）
   - GC-003 的 recommendations 可仅有 P0（证据不足）

6. **对照 GC 验证**（15 分钟）
   - 检查 SKILL.md 的每条规则是否能通过所有 5 个 GC

---

## 六、自检标准

实施完成前必须确认：

- [ ] 无 traceId 输入时，行为与 v0.1 完全一致（向后兼容）
- [ ] 有 traceId 时，快速路径在 Phase A/B/C 各阶段失败时都能正确降级
- [ ] `recommendations` 的 P0 建议不做代码发布假设（运维/值班能独立执行）
- [ ] `recommendations` 和 `restricted_info` 不重复
- [ ] 快速路径不会在 Trace API 不可用时卡死（必须退回原步骤 2）
- [ ] GC-001/002/003 在加入 recommendations 后仍能通过
- [ ] GC-004/005 定义了明确的失败判据
- [ ] Output Contract 字段数 = 7（不是 6，不是 8）
- [ ] SKILL.md 行数 ≤ 650（目标 600）
