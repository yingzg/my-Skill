# JUnit5 + Mockito + AAA

AAA 的含义：

```text
Arrange: 准备输入、mock 和状态。
Act: 调用被测 public 方法。
Assert: 验证业务可观察结果。
```

## 默认结构

```java
@ExtendWith(MockitoExtension.class)
class OrderServiceTest {

    @InjectMocks
    private OrderService orderService;

    @Mock
    private OrderRepository orderRepository;

    @Test
    void createOrder_validRequest_shouldCreatePendingOrder() {
        // Arrange
        OrderRequest request = new OrderRequest();
        request.setSkuId("sku-001");
        request.setQuantity(2);

        // Act
        OrderResult result = orderService.createOrder(request);

        // Assert
        assertEquals(OrderStatus.PENDING, result.getStatus());
        verify(orderRepository).save(argThat(order ->
            "sku-001".equals(order.getSkuId())
                && order.getQuantity() == 2
                && order.getStatus() == OrderStatus.PENDING
        ));
    }
}
```

## 异常分支

```java
@Test
void createOrder_missingSku_shouldThrowBizException() {
    // Arrange
    OrderRequest request = new OrderRequest();
    request.setSkuId(null);

    // Act + Assert
    BizException ex = assertThrows(
        BizException.class,
        () -> orderService.createOrder(request)
    );

    assertEquals("sku required", ex.getMessage());
    verify(orderRepository, never()).save(any());
}
```

`assertThrows` 可将 `Act` 与 `Assert` 合并，因为断言必须包裹动作。

## Mockito 规则

- 重要参数优先使用精确值或 `argThat`。
- 当保存/发布的对象字段很多时，使用 `ArgumentCaptor`。
- 仅当某个 stub 有意不被每条路径使用时，才使用 `lenient()`。
- 除非项目现有测试已使用或用户要求，否则避免 `@SpringBootTest`。

## Mockito 高级用法

| 场景 | 用法 |
|---|---|
| 捕获复杂参数后逐字段断言 | `ArgumentCaptor<Order> captor = ArgumentCaptor.forClass(Order.class); verify(repo).save(captor.capture()); assertEquals(..., captor.getValue().getSkuId());` |
| stub 抛异常（测下游异常分支） | `doThrow(new BizException("...")).when(client).queryPrice(any());` |
| 处理 void 方法 | `doNothing().when(service).notify(any());` 或 `doReturn(value).when(mock).method();` |
| 约束调用次数 | `verify(repo, times(2)).save(any());` / `verify(repo, never()).save(any());` / `verify(repo, atMostOnce()).save(any());` |
| 验证调用顺序 | `InOrder inOrder = inOrder(repo, client); inOrder.verify(repo).findById(any()); inOrder.verify(client).notify(any());` |
| 可选 stub（非每条路径都用到） | `lenient().when(client.query(any())).thenReturn(resp);` |
| 时间可控 | `when(clock.instant()).thenReturn(fixedInstant);` |

## 好的断言

- 返回状态、金额、数量、国家、类型、错误码。
- 异常类型和消息/错误码。
- Repository 保存实体的字段。
- Client/gateway 请求字段。
- Producer 消息的 topic/key/body。

## 弱断言

避免：

```java
assertTrue(true);
assertNotNull(result);
verify(repository).save(any());
```

这些虽然可能执行了代码，但无法证明业务行为。
