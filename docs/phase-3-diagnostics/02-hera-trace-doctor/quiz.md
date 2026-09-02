# hera-trace-doctor — 测验文档

> 对应学习文档: `02-hera-trace-doctor/learning.md`
>
> 测验类型: **理解 + 设计**（模式识别 + 通用化设计 + 规则扩展能力）

---

## Part A: 诊断模式理解（50分）

### A1. 填空题（每题3分，共15分）

**1.** Rule Engine 的三层架构是：____ → ____ → ____。

**2.** "黑洞时间"的计算公式是：____。

**3.** Broken Pipe 模式的剖层策略第一步是检查：____。

**4.** high-freq-repeat 模式的触发条件是：同一接口在同一个 trace 内出现 ≥____ 次。

**5.** rollback-no-error 模式中，"回滚"是 ____ 发现，"无报错"是 ____ 发现。

---

### A2. 模式匹配题（每题5分，共20分）

阅读以下 Trace 描述，判断最可能触发哪个 Pattern，并说明理由：

**6.** 一个 gRPC 调用链：A → B → C。总耗时 8s。B 调用 C 只花了 150ms，B 的其他子 span 都在 100ms 以内。B 的 span 中没有 error。

**最可能 Pattern**: ______   **理由**: ______

**7.** 一个 HTTP 调用链：Gateway → OrderService → PaymentService。OrderService 调用 PaymentService 时抛出 "Connection reset by peer"。OrderService 的 span 标记为 error。PaymentService 的 span 中记录了 "write EPIPE"。

**最可能 Pattern**: ______   **理由**: ______

**8.** 一个购物车接口的 trace 中，`getProductDetail` 方法被调用了 27 次，每次传入不同的 productId。

**最可能 Pattern**: ______   **理由**: ______

**9.** 订单创建接口。创建过程中检测到库存不足，代码执行 `TransactionAspectSupport.currentTransactionStatus().setRollbackOnly()` 后返回错误码。所有 span 的 status 都是 OK。但最终数据库中没有订单记录。

**最可能 Pattern**: ______   **理由**: ______

---

### A3. 简答题（15分）

**10.** （15分）比较 hera-trace-doctor 和 ticket-troubleshoot-v3 在"输出契约"设计上的差异：

| 维度 | ticket-troubleshoot-v3 | hera-trace-doctor |
|------|----------------------|-------------------|
| 契约形式 | | |
| 终态数量 | | |
| 为什么采用这种形式？ | | |
| 哪种更适合各自的场景？ | | |

---

## Part B: 通用化设计（30分）

### B1. 接口设计题（15分）

**11.** hera-trace-doctor 当前依赖 Hera API。请设计独立的 `ITraceFetcher` 接口，使其可以适配 Jaeger、Zipkin、Grafana Tempo 等任意分布式追踪系统。

设计要求：
1. 接口定义（至少 2 个方法）
2. 标准 Trace 数据结构（TraceDetail）
3. 一个 Jaeger 适配器的 getTrace 实现伪代码
4. 配置文件如何声明适配器选择

---

### B2. 规则扩展题（15分）

**12.** 设计一个**新的诊断模式 "Pattern 6: cascade-timeout"（级联超时）**。

定义：
- **现象**: 一个调用链 A→B→C→D，D 因为 B 设置的超时太短而被中断，但 B 本身不超时
- 示例：A 调用 B（超时 3s），B 调用 C（超时 2s），C 调用 D（超时 1s）。D 耗时 1.2s，被 C 超时中断，C 返回 error，B 记录 error 但 B 本身无超时

请设计：
- 触发条件（如何在 Trace 数据中识别这种模式）
- 剖层策略（匹配后该怎么做）
- 输出模板（诊断结论的格式）
- 至少 1 个 Golden Case 的输入/预期输出

---

## Part C: 系统设计题（20分）

**13.** 假设你要将 ticket-troubleshoot-v3 和 hera-trace-doctor 合并为一个统一的"智能排障平台"。请设计：

1. 两者如何协作（架构图/流程图）
2. 共享哪些基础设施（Checkpoint、Contract、Case Store）
3. 新增一个 Adapter Layer 来屏蔽具体工具（IDatabaseQuery / ITraceFetcher）
4. 如何让用户从工单描述自动触发 Trace 分析（关联逻辑）

---

## 评分标准

| 等级 | 分数 | 要求 |
|------|------|------|
| S | 90+ | 模式识别全对 + 接口设计完整 + 新模式设计合理 |
| A | 75-89 | 模式识别正确 + 接口设计合理 |
| B | 60-74 | 基本理解 5 种模式 + 有通用化思路 |
| C | <60 | 需要回顾学习文档 |

---

## 参考答案要点

<details>
<summary>点击展开</summary>

### Part A

1. Symptom Detector, Rule Engine, Strategy Executor
2. 总耗时 - Σ(子 span 耗时)
3. 上游超时配置（connectTimeout / readTimeout）
4. 3
5. Trace 数据（rollback event 存在），Trace 数据（error span 不存在）

6. **Pattern 2: long-time-no-slow-child**
   理由：总耗时 8s，所有子 span 耗时都在 150ms 以内，黑洞时间显著

7. **Pattern 1: Broken Pipe**
   理由：Connection reset / EPIPE 是典型的 Broken Pipe 信号

8. **Pattern 4: high-freq-repeat**
   理由：同一方法调用 27 次但参数不同 → 典型的 N+1 问题

9. **Pattern 3: rollback-no-error**
   理由：setRollbackOnly 手动触发回滚，无 error span，但数据未写入

10. | 维度 | ticket-troubleshoot-v3 | hera-trace-doctor |
    |------|----------------------|-------------------|
    | 契约形式 | 统一 Output Contract（所有路径相同格式） | 每个 Pattern 独立模板 |
    | 终态数量 | 3（success/partial_success/failed） | 无显式终态（按模式输出） |
    | 为什么？ | 工单排查需要给下游系统统一的 API | Trace 诊断聚焦，不同问题需要不同字段 |
    | 适合场景 | ticket-troubleshoot 的多路径+多场景 | trace-doctor 的单 Trace 单模式 |

### Part B

11. 略（参考 learning.md §6.2）

12. 核心要点：
    - 触发: trace 中有 timeout error + 被中断的 span 耗时 < 调用者 span 耗时 + span 层级关系
    - 策略: 计算超时链（A 超时→B 超时→C 超时→D），确认 bottleneck
    - 模板: "级联超时: [A] 设置的超时 [X]s → [D] 实际需 [Y]s > [C] 超时 [Z]s"

### Part C

13. 核心要点：
    - Flow: 工单输入 → ticket-troubleshoot 做业务排查 → 发现性能问题 → 委托 trace-doctor 做 Trace 分析
    - 共享: Checkpoint 机制（统一的 RUNS_DIR）、Contract 校验（统一的 L4 层）、Case Store（统一的经验库）
    - Adapter: IDatabaseQuery + ITraceFetcher + ILogFetcher 组成 Adapter Layer
    - 关联: ticket-troubleshoot Step 3 代码定位时，自动提取接口路径 → 查询最近异常 Trace → 触发 trace-doctor
</details>
