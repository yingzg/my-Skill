# 业务可观察结果规则

每个新增测试必须至少验证一个业务可观察结果。

## 有效的可观察结果

| 类型 | 示例 |
|---|---|
| 返回值 | 状态、金额、数量、国家、类型、错误码、集合内容 |
| 异常 | 异常类型、消息、业务错误码 |
| 状态变化 | 字段被更新、对象状态发生流转 |
| 持久化输出 | 保存的实体具有预期的业务字段 |
| 外部调用 | client/gateway/producer 以预期请求值被调用 |
| 分支行为 | 不同输入产生不同输出或调用 |

## 伪覆盖

伪覆盖是指测试执行了代码行却没有证明其行为。

禁止示例：

```java
assertTrue(true);
assertNotNull(result);
verify(repository).save(any());
```

## 更好的写法

对于返回 DTO：

```java
assertEquals("DE", result.getCountryCode());
assertEquals(StoreType.MI_HOME, result.getStoreType());
assertEquals(2, result.getItems().size());
```

对于 repository 写入：

```java
verify(repository).save(argThat(entity ->
    "DE".equals(entity.getCountryCode())
        && entity.getStatus() == Status.ENABLED
));
```

对于 client 调用：

```java
verify(priceClient).queryPrice(argThat(req ->
    "sku-001".equals(req.getSkuId())
        && req.getQuantity() == 2
));
```

对于异常：

```java
BizException ex = assertThrows(BizException.class, () -> service.handle(request));
assertEquals("country required", ex.getMessage());
verify(repository, never()).save(any());
```

对于状态变化：

```java
order.approve();
assertEquals(OrderStatus.APPROVED, order.getStatus());
assertEquals("alice", order.getApprovedBy());
```

对于分支行为（同一方法不同输入命中不同分支，并产生不同结果）：

```java
// 库存充足 → 正常下单
OrderResult ok = service.createOrder(sufficientStockReq);
assertEquals(OrderStatus.PENDING, ok.getStatus());

// 库存不足 → 抛异常
assertThrows(StockInsufficientException.class,
    () -> service.createOrder(insufficientStockReq));
```

对于 producer 消息：

```java
verify(producer).send(argThat(msg ->
    "order.created".equals(msg.getTopic())
        && "sku-001".equals(msg.getKey())
        && msg.getBody() != null
));
```

## 补充断言维度

除了断言"值是否正确"，还应覆盖以下维度，让测试更贴近真实业务约束：

| 维度 | 示例 |
|---|---|
| 调用次数 | 用 `times(2)` / `never()` / `atMostOnce()` 约束 `verify` 的调用次数 |
| 调用顺序 | 用 `InOrder` 验证"先查后写"等顺序依赖 |
| 时间 | mock `Clock` 或注入固定时间，验证有效期/过期等时间逻辑 |
| 边界值 | 覆盖 null、空集合、0、负值、超长字符串等边界输入 |

## 伪覆盖检查的局限

`test_quality_check.py` 是正则静态检查，只能拦截硬伤（`assertTrue(true)`、私有反射、唯一断言 `assertNotNull`、`verify(any())` 无 `argThat`）。它无法识别：

1. 断言值本身写错（代码返回 "FR" 却断言 "DE"）。
2. 测试未真正命中目标分支（断言了但被测方法没走到那个分支）。
3. 断言与业务语义脱节（断言了无关字段）。

因此"写对有业务价值的单测"仍依赖代码理解 + 可观察结果规则，脚本只兜底拦截最明显的伪覆盖。

## 决策规则

如果删除该断言不会降低对业务正确性的信心，那么这个断言很可能太弱。
