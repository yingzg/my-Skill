# Observable Behavior Rules

Every new test must verify at least one business-observable result.

## Valid Observable Results

| Type | Examples |
|---|---|
| Return value | status, amount, count, country, type, error code, collection content |
| Exception | exception class, message, business error code |
| State change | field updated, object status transitioned |
| Persistence output | saved entity has expected business fields |
| External call | client/gateway/producer called with expected request values |
| Branch behavior | different inputs lead to different outputs or calls |

## Pseudo-Coverage

Pseudo-coverage means a test executes code lines without proving behavior.

Forbidden examples:

```java
assertTrue(true);
assertNotNull(result);
verify(repository).save(any());
```

## Better Patterns

For return DTOs:

```java
assertEquals("DE", result.getCountryCode());
assertEquals(StoreType.MI_HOME, result.getStoreType());
assertEquals(2, result.getItems().size());
```

For repository writes:

```java
verify(repository).save(argThat(entity ->
    "DE".equals(entity.getCountryCode())
        && entity.getStatus() == Status.ENABLED
));
```

For client calls:

```java
verify(priceClient).queryPrice(argThat(req ->
    "sku-001".equals(req.getSkuId())
        && req.getQuantity() == 2
));
```

For exceptions:

```java
BizException ex = assertThrows(BizException.class, () -> service.handle(request));
assertEquals("country required", ex.getMessage());
verify(repository, never()).save(any());
```

## Decision Rule

If removing the assertion would not reduce confidence in business correctness, the assertion is probably too weak.
