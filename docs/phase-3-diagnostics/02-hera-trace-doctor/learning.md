# hera-trace-doctor — 深度学习文档

> 对应 SKILL.md: `/root/.claude/skills/hera-trace-doctor/SKILL.md` (163行)
>
> 原实现仓库: `/mnt/d/测试项目/mi-claw-skills/hera-trace-doctor/`

---

## 一、功能全景

### 一句话定位
**单 Trace 端到端诊断器** — 症状→规则引擎→剖层分析→可执行优化方案，5 种诊断模式覆盖常见链路问题。

### 核心流程

```
输入 traceId
    ↓
[Phase 0] 获取原始 Trace（queryTrace API）
    ↓
[Phase 1] 症状识别 → 模式匹配（diagnosis-rules.md）
    ├─ Pattern 1: Broken Pipe
    ├─ Pattern 2: long-time-no-slow-child（总耗时长但子调用不慢）
    ├─ Pattern 3: rollback-no-error（回滚无报错）
    ├─ Pattern 4: high-freq-repeat（高频重复调用）
    └─ Pattern 5: log-overflow（日志淹没）
    ↓
[Phase 2] 按匹配模式的策略剖层分析
    ↓
[Phase 3] 输出诊断结论：
    症状摘要 + 根因推断 + 影响范围 + 优化方案（简短/中长期）
```

---

## 二、架构设计分析

### 2.1 极简文件架构

```
hera-trace-doctor/
├── SKILL.md                    # 163行：角色、策略、API引用、输出模板
├── agents/
│   └── trace-doctor-agent.md   # 子Agent配置
└── references/
    └── diagnosis-rules.md      # 5 种诊断模式详细规则
```

**设计哲学**: "少即是多" — 163 行 SKILL.md 定义全流程，额外规则集中在 references/ 中。这种简洁性本身就值得学习：当一个 Skill 足够聚焦时，不需要冗长的 SKILL.md。

### 2.2 Rule Engine + 策略模式

```
输入 Trace → Rule Engine 分类器
    ├── 命中 Pattern 1 → 执行 Strategy 1
    ├── 命中 Pattern 2 → 执行 Strategy 2
    ├── ...
    └── 未命中任何 Pattern → "不属于当前规则覆盖，提供基础摘要"
```

每个 Pattern 对应一个 Strategy，Strategy 内定义：
- **触发条件**: 如何识别这种模式
- **分析步骤**: 匹配后该做什么（获取Span详情、检查日志、对比耗时等）
- **输出模板**: 这种模式的诊断结论格式

---

## 三、五种诊断模式深度剖析

### Pattern 1: Broken Pipe（连接断开）

```
触发条件:
  trace_error contains "Broken pipe" OR span status = error + downstream HTTP timeout
```

**剖层策略**:
1. 检查上游超时配置（connectTimeout / readTimeout）
2. 确认下游实际处理时间 vs 上游超时阈值
3. 如果是下游慢导致 → 建议下游优化或上游放宽超时
4. 如果下游正常且快速 → 怀疑网络链路问题

**输出模板**: "Broken pipe at [服务A]→[服务B]。原因: [下游处理慢/网络抖动/超时不匹配]。建议: [具体方案]。"

### Pattern 2: long-time-no-slow-child

```
触发条件:
  总跨度耗时 >5s 且所有子 span 耗时均 <200ms
```

**剖层策略**:
1. 计算 "黑洞时间" = 总耗时 - Σ(子 span 耗时)
2. 黑洞时间 >50% 总耗时 → 开启下一步
3. 排查: 代码内同步阻塞（IO wait / thread wait / 锁等待）
4. 建议: 添加子 span 覆盖这段逻辑，或调整线程模型

**输出模板**: "总耗时 [X]ms，子调用仅占 [Y]ms，黑洞时间 [Z]ms。推测: [具体猜想]。建议: 在 [方法/位置] 添加子 span 覆盖。"

### Pattern 3: rollback-no-error

```
触发条件:
  事务回滚（rollback detected）但所有 span 状态 = OK
```

**剖层策略**:
1. 确认回滚是手动触发还是自动触发
2. 手动触发 → 查业务逻辑中 throw 非异常对象（如 return code）
3. 自动触发 → 查 Spring 事务边界和异常分类（哪些异常不回滚）
4. 建议: 升级异常处理 or 在关键分支加错误日志

**输出模板**: "事务在 [位置] 回滚但无对应 span error。根因: [无感知异常/业务标记性回滚]。建议: [方案]。"

### Pattern 4: high-freq-repeat

```
触发条件:
  同一接口在同一 trace 内出现 ≥3 次，且每次参数相似
```

**剖层策略**:
1. 统计调用次数和每次参数差异
2. 如果参数不变 → "循环内重复调用" — 建议批量接口或缓存
3. 如果参数不同但可合并 → "N+1 问题" — 建议批量查询

**输出模板**: "[接口名] 在本次 trace 内被调用 [N] 次。原因: [N+1/循环调用]。建议: [批量接口/缓存/改写逻辑]。"

### Pattern 5: log-overflow

```
触发条件:
  日志条数 >500 条 或日志总大小 >10KB
```

**剖层策略**:
1. 统计日志密度（条/秒）
2. 识别高频重复日志（相同模式连续出现 ≥5 次）
3. 建议: 降级日志级别 / 采样策略 / 限制日志长度

---

## 四、设计模式分析

### 4.1 Symptom → Rule → Strategy 三层架构

```
┌────────────────────────────────────────────┐
│  Layer 1: Symptom Detector                 │
│  读 trace summary → 提取特征向量           │
│  (errors, latencies, patterns, anomalies)  │
├────────────────────────────────────────────┤
│  Layer 2: Rule Engine                      │
│  特征向量 → 匹配 diagnosis-rules.md        │
│  返回: pattern_id + confidence             │
├────────────────────────────────────────────┤
│  Layer 3: Strategy Executor                │
│  按 pattern_id 选择策略 → 执行剖层分析     │
│  产出: 诊断结论                            │
└────────────────────────────────────────────┘
```

这种分层的优势：
- **可扩展**: 新增 Pattern 只需加一条规则 + 一个 Strategy，不影响现有逻辑
- **可降级**: Rule Engine 未匹配时，Strategy Executor 可输出基础摘要
- **可量化**: 每条规则的命中率、准确率可以独立统计

### 4.2 策略模式的实际体现

虽然 Skill 中没有显式使用策略模式的代码，但规则定义的方式天然就是策略模式：

```
Rule 1 → Strategy 1: broken_pipe_strategy(trace)
Rule 2 → Strategy 2: long_time_no_slow_strategy(trace)
Rule 3 → Strategy 3: rollback_no_error_strategy(trace)
...
```

### 4.3 Output Template（每 Pattern 有独立模板）

与 ticket-troubleshoot-v3 的通用 Output Contract 不同，hera-trace-doctor 的每个 Pattern 有专属输出模板。这是合理的：
- trace-doctor 的输出是对**单一 Trace 的诊断**，比工单排查更聚焦
- 不同 Pattern 的核心字段不同（Broken Pipe 需要超时对比，N+1 需要调用次数统计）

---

## 五、优秀设计亮点

### ⭐ 亮点 1：极简但完整

163 行 SKILL.md + 1 份 rules 文件 = 完整诊断引擎。这种紧凑性源于精准的职责边界：只诊断**一个 Trace 的异常**，不覆盖系统化问题。

### ⭐ 亮点 2：Rule Engine 显式声明

诊断规则并非隐藏在 Skill 描述中，而是独立存储在 `references/diagnosis-rules.md`。这意味着：
- 规则可以独立维护、diff、review
- 新增规则不需要修改 SKILL.md
- 可以发展出规则的版本管理和 A/B 测试

### ⭐ 亮点 3：黑洞时间分析（Pattern 2）

"黑洞时间 = 总耗时 - Σ(子 span)" 是一个优雅的诊断概念：
- 无需代码，仅凭 Trace 数据就能定位"缺少可观测性覆盖"的区域
- 将"不可见"的问题量化为"可度量的差距"
- 输出"建议添加子 span 覆盖"是可执行的行动项

### ⭐ 亮点 4：回滚无报错检测（Pattern 3）

这个 Pattern 体现了对**分布式系统隐性故障**的敏锐洞察。事务回滚但有报错是常见 bug — 框架捕获了异常但用户未感知。诊断引擎通过 Trace 的结构化对比（rollback event 存在但 error span 缺失）发现了这一不一致。

### ⭐ 亮点 5：日志淹没检测（Pattern 5）

高频/大量日志不是 bug，但它是**系统健康信号**。日志淹没会：
- 掩盖真正的错误日志
- 增加存储成本
- 降低 Trace 查询性能

在 Trace 级别自动检测日志密度，是一个前瞻性的设计。

---

## 六、公司依赖分析 + 通用化方案

### 6.1 依赖清单

| 依赖 | 类型 | 用途 | 通用化难度 |
|------|------|------|-----------|
| Hera queryTrace API | HTTP API | 获取原始 Trace 数据 | ⭐⭐ (协议抽象) |
| Hera queryLogs API | HTTP API | 获取关联日志 | ⭐⭐ (协议抽象) |
| hera CLI 工具 | CLI | 命令行方式获取 Trace | ⭐⭐ (协议抽象) |

**注意**: SKILL.md 明确"只使用 Hera API/CLI，不使用浏览器" — 这是一个好的约束。虽然 Hera 是公司特有，但这个约束体现了"API优先"的设计原则。

### 6.2 抽象接口设计

```typescript
// Trace 获取抽象 — 适配 Jaeger / Zipkin / Grafana Tempo / Datadog
interface ITraceFetcher {
  getTrace(traceId: string): Promise<TraceDetail>;
  getLogs(traceId: string, options?: LogOptions): Promise<LogEntry[]>;
}

// Trace 数据结构 — 标准 OTEL 兼容
interface TraceDetail {
  traceId: string;
  spans: Span[];
  totalDuration: number;
  errors: TraceError[];
}
```

### 6.3 适配器示例

```typescript
// Jaeger 适配器
class JaegerAdapter implements ITraceFetcher {
  async getTrace(traceId: string): Promise<TraceDetail> {
    const res = await fetch(`http://jaeger:16686/api/traces/${traceId}`);
    // 转换为标准 TraceDetail
  }
}

// Zipkin 适配器
class ZipkinAdapter implements ITraceFetcher {
  async getTrace(traceId: string): Promise<TraceDetail> {
    const res = await fetch(`http://zipkin:9411/api/v2/trace/${traceId}`);
    // 转换为标准 TraceDetail
  }
}

// Grafana Tempo 适配器
class TempoAdapter implements ITraceFetcher {
  async getTrace(traceId: string): Promise<TraceDetail> {
    const res = await fetch(`http://tempo:3100/api/traces/${traceId}`);
    // 转换为标准 TraceDetail
  }
}
```

### 6.4 关键挑战

与 ticket-troubleshoot-v3 不同，hera-trace-doctor 的最大通用化挑战不是"替换一个工具"，而是：
1. **没有统一的 Trace 查询标准** — Jaeger/Zipkin/Datadog 的 API 格式完全不同
2. **Semantic Convention 差异** — "rollback" 在不同框架中的 tag 名可能不同
3. **日志关联方式不同** — 有些平台通过 traceId 自动关联，有些需要手动 join

**解决思路**: 定义 `TraceDetail` 作为内部标准格式（对齐 OpenTelemetry），所有适配器负责"外部 API → TraceDetail"的转换。诊断规则只读 `TraceDetail`，不关心数据来源。

---

## 七、可改进点

### 7.1 ⚠️ 仅支持 5 种模式

163 行的 SKILL.md 只覆盖了 5 种模式，很多常见的链路问题（如级联超时、熔断触发、限流拒绝）未覆盖。这是精简的代价。改进：
- 将 diagnosis-rules.md 做成社区贡献的"模式库"
- 支持自定义规则（用户编写自己的 Pattern + Strategy）

### 7.2 ⚠️ 缺少历史对比能力

当前只看单个 Trace，没有历史 Trace 的对比。很多诊断需要"这个 Trace 为什么比平时慢"的对比分析。改进：
- 支持查询最近 N 个同接口 Trace 的 P50/P95/P99 耗时
- 自动标注当前 Trace 在这些分位数中的位置

### 7.3 ⚠️ 没有关联工单排查

`ticket-troubleshoot-v3` 和 `hera-trace-doctor` 是互补的，但目前是两个独立 Skill。一个 Trace 诊断结果应该能自动作为工单排查的证据输入。

### 7.4 ⚠️ 输出格式单一

只有文本格式的诊断报告，未考虑机器可读的输出（JSON schema）。工单系统可能需要结构化字段（cause_type、severity、affected_service）。

### 7.5 ⚠️ 缺少 Golden Cases

`ticket-troubleshoot-v3` 有 3 个 GC，但 `hera-trace-doctor` 没有。对于规则引擎，Golden Cases 更重要——需要验证每一条规则在真实 Trace 上是否正确匹配。

---

## 八、量化质量指标

| 维度 | 指标 | 测量方法 | 当前基准 | 目标 |
|------|------|---------|---------|------|
| **覆盖率** | 规则引擎命中率 | 真实 Trace 样本中匹配到任一 Pattern 的比例 | ~5 种 | ≥20 种 |
| **准确率** | 诊断结论准确率 | 人工标注 100 个 Trace，对比诊断结论 | — | ≥85% |
| **时效性** | 从获取 Trace 到输出结论时间 | 计时 | — | ≤30s |
| **完备性** | 每个 Pattern 的 Golden Case 数 | 统计 GC 文件 | 0 | ≥2/Pattern |
| **可迁移性** | 适配器接口数 | 统计抽象层接口 | 0 | ≥1 (ITraceFetcher) |

---

## 九、复刻要点 Checklist

- [ ] 理解 5 种诊断模式各自的触发条件和剖层策略
- [ ] 理解 Rule Engine 的三层架构（Symptom → Rule → Strategy）
- [ ] 理解黑洞时间分析的原理和前提条件
- [ ] 理解 rollback-no-error 模式背后的分布式事务原理
- [ ] 能设计 ITraceFetcher 抽象接口
- [ ] 能编写 Jaeger 适配器（从 Jaeger API → TraceDetail 的转换）
- [ ] 能新增一个诊断模式（含触发条件 + 剖层策略 + 输出模板）
- [ ] 理解为什么每个 Pattern 有独立输出模板（vs ticket-troubleshoot 的统一 Contract）
- [ ] 能为每种模式编写至少 1 个 Golden Case
