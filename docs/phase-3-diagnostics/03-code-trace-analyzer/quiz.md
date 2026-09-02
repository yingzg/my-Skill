# code-trace-analyzer — 测验文档

> 对应学习文档: `03-code-trace-analyzer/learning.md`
>
> 测验类型: **理解 + 设计**（调用链分析 + 证据链 + 多框架适配）

---

## Part A: 分析流程理解（50分）

### A1. 填空题（每题3分，共15分）

**1.** Code-trace-analyzer 的 4 个阶段是：____ → ____ → ____ → ____。

**2.** 追踪到 ____ 调用时，标记为"外部"并停止追踪（知止原则）。

**3.** 每个输出结论必须附带的证据标注格式是：____。

**4.** ⚠️ 类校验点是指：代码中 ____ 但 SQL 中 ____。

**5.** Mermaid flowchart 优于文字描述的主要原因是：____。

---

### A2. 对错判断题（每题3分，共9分）

**6.** [ ] Code-trace-analyzer 使用 ast_grep_search 自动构建完整调用图，AI 只做语义解读。

**7.** [ ] 当追踪到 `@DubboReference` 注解时，应该继续深入追踪到下游服务的实现代码。

**8.** [ ] JSON 示例中的字段校验规则应该来源于代码中的注解（如 `@NotNull`），而不是 AI 的推测。

---

### A3. 情景分析题（每题13分，共26分）

**9.** 以下是一段代码骨架，请模拟 code-trace-analyzer 的分析过程，写出：

```java
@RestController
public class PaymentController {
    @Autowired
    private PaymentService paymentService;

    @PostMapping("/pay")
    public Result pay(@Valid @RequestBody PayRequest req) {
        return paymentService.pay(req);
    }
}

@Validated
public class PayRequest {
    @NotNull @Min(1)
    private Long orderId;
    @NotNull @DecimalMin("0.01")
    private BigDecimal amount;
    @NotBlank
    private String paymentMethod;
}

@Service
public class PaymentService {
    @Autowired
    private OrderMapper orderMapper;
    @Autowired
    private BalanceMapper balanceMapper;
    @DubboReference
    private RiskControlService riskService;

    @Transactional
    public Result pay(PayRequest req) {
        Order order = orderMapper.selectById(req.getOrderId());
        if (order == null) { throw new OrderNotFoundException(); }
        if (order.getStatus() != OrderStatus.PENDING) { throw new OrderStatusException(); }
        boolean safe = riskService.checkFraud(req.getOrderId());
        if (!safe) { throw new RiskRejectedException(); }
        int affected = balanceMapper.deduct(order.getUserId(), req.getAmount());
        if (affected == 0) { throw new InsufficientBalanceException(); }
        order.setStatus(OrderStatus.PAID);
        orderMapper.updateById(order);
        return Result.success();
    }
}
```

假设 OrderMapper.xml 和 BalanceMapper.xml 存在且内容合理。

请写出分析产物的以下部分：
- a) 校验点列表（包括 ⚠️ 类校验点）
- b) 外部调用标注
- c) 异常分支列表
- d) Mermaid flowchart 骨架

---

**10.** 阅读以下场景，判断 AI 应该如何分析：

> AI 在分析 `OrderService.createOrder()` 时发现它调用了 `redisTemplate.opsForValue().set("order:lock:"+orderId, "1", 10, TimeUnit.SECONDS)`，然后调用了 `orderMapper.insert(order)`。

请回答：
- Redis 调用是否需要作为"外部调用"标注？为什么？
- 这段代码中的分布式锁逻辑是否应该体现在 Mermaid 图中？如何体现？
- 分析产出中是否应该注明"Redis 分布式锁"是一个校验点？为什么？

---

## Part B: 通用化设计（30分）

### B1. 框架适配设计（15分）

**11.** 当前技能只支持 Java/Spring/MyBatis/Dubbo 技术栈。请设计一个 FrameAdapter 配置系统，支持 Python/Django/ORM 和 Go/Gin/GORM。

设计要求：
1. 每种框架需要声明哪些配置项
2. 分析流程如何根据框架适配器调整行为
3. 给出 Python Django 框架适配器的具体配置内容
4. 如何处理"框架检测"（自动判断项目使用什么技术栈）

---

### B2. 发布层抽象设计（15分）

**12.** 当前通过 `feishu2md` MCP 发布到飞书。请设计 `IDocPublisher` 接口，使分析结果可以发布到任意文档平台。

设计要求：
1. 接口定义（方法签名和参数）
2. 飞书适配器实现伪代码
3. Markdown 文件夹适配器实现伪代码
4. 如何处理"发布失败的 fallback"（如飞书 API 不可用 → 本地 Markdown 文件）

---

## Part C: 分析能力提升题（20分）

**13.** 当前 analyzer 忽略了两条重要的调用路径。请分析以下场景并提出增强方案：

**场景 A**：Service A 通过 `rabbitTemplate.convertAndSend("order.paid", message)` 发送消息，Service B 通过 `@RabbitListener(queues = "order.paid")` 消费消息。

**场景 B**：OrderService 保存订单后，MyBatis-Plus 的 `@TableField(fill = FieldFill.INSERT)` 自动填充 `create_time`，接着 `@Trigger` 注解触发了一个数据库触发器。

请回答：
- 场景 A 的异步链路应该如何追踪和展示？
- 场景 B 的隐式逻辑（自动填充、数据库触发器）应该如何标注？
- 这些增强对 output 结构有什么影响？需要新增哪些字段？

---

## 评分标准

| 等级 | 分数 | 要求 |
|------|------|------|
| S | 90+ | 分析流程全对 + 框架适配完整 + 增强方案可落地 |
| A | 75-89 | 分析流程正确 + 框架适配合理 |
| B | 60-74 | 基本理解分析流程 + 有适配思路 |
| C | <60 | 需要回顾学习文档 |

---

## 参考答案要点

<details>
<summary>点击展开</summary>

### Part A

1. 代码扫描, 逐层追踪调用链, 信息提取, 输出文档
2. Dubbo（或外部服务）
3. `（来源: 文件名:行号）`
4. 没有写校验逻辑，有 NOT NULL / WHERE 约束
5. 复杂树形调用链的文字描述几乎不可读，Mermaid 渲染后可一次展示全貌

6. ❌ 错误。Code-trace-analyzer 是"手动逐层阅读"，不是 AST-grep 自动化。
7. ❌ 错误。遇到外部调用应该"知止"，标记为外部即可，除非同仓库可访问。
8. ✅ 正确。这是证据链设计的基本原则：结论来源于代码，不是推测。

9. a) 校验点:
   - ✅ orderId: 必填 + 必须 ≥ 1 (来源: PayRequest.java, @NotNull @Min)
   - ✅ amount: 必填 + 必须 ≥ 0.01 (来源: PayRequest.java, @NotNull @DecimalMin)
   - ✅ paymentMethod: 必填 (来源: PayRequest.java, @NotBlank)
   - ⚠️ order.status: 代码逻辑要求 PENDING 状态但 PayRequest 未传入 (来源: PaymentService.java)
   - ⚠️ order.userId: balanceMapper.deduct 使用但 PayRequest 未传入

   b) 外部调用: Dubbo:RiskControlService#checkFraud(Long orderId)
      用途: 风控检查

   c) 异常分支:
   - 订单不存在 → OrderNotFoundException
   - 订单状态不是 PENDING → OrderStatusException
   - 风控拒绝 → RiskRejectedException
   - 余额不足 → InsufficientBalanceException

   d) 略

10. - Redis 调用应作为**外部依赖**标注，因为它不是 Java 类调用，也不属于 SQL
    - Mermaid 图中应标注为子图/判断节点: `[尝试获取分布式锁] -- 失败 --> [返回错误]`
    - 是校验点：`⚠️ 分布式锁 key="order:lock:"+orderId，TTL=10s（来源: PaymentService.java）`，这是业务关键逻辑，如果 TTL 太短会导致并发问题

### Part B

11. 略（参考 learning.md §5.3）

12. 略（参考 learning.md §5.2）

### Part C

13. 要点：
    - 场景 A: 在 Mermaid 中用虚线表示异步链路，output 新增 `async_calls` 字段
    - 场景 B: 在 output 新增 `implicit_behaviors` 字段（自动填充、触发器、AOP 增强等）
    - 影响: output 结构需要扩展，Mermaid 需要支持异步标注和隐式逻辑标注
</details>
