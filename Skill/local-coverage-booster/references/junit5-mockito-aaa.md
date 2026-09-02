# JUnit5 + Mockito + AAA

AAA means:

```text
Arrange: prepare inputs, mocks, and state.
Act: call the public method under test.
Assert: verify observable business behavior.
```

## Default Shape

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

## Exception Branch

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

`Act` and `Assert` can be combined for `assertThrows`, because the assertion must wrap the action.

## Mockito Rules

- Prefer exact values or `argThat` for important parameters.
- Use `ArgumentCaptor` when the saved/published object has many fields.
- Use `lenient()` only when a stub is intentionally not used by every path.
- Avoid `@SpringBootTest` unless existing project tests already use it or the user asks.

## Good Assertions

- Return status, amount, count, country, type, error code.
- Exception type and message/code.
- Repository saved entity fields.
- Client/gateway request fields.
- Producer message topic/key/body.

## Weak Assertions

Avoid:

```java
assertTrue(true);
assertNotNull(result);
verify(repository).save(any());
```

These may execute code but do not prove business behavior.
