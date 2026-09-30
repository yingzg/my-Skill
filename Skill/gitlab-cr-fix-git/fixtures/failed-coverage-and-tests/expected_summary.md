# 预期诊断摘要

该 fixture 表示一个门禁失败的 MR：

- Pipeline 失败。
- MR 结构上可以合并，但 CI 必须先通过。
- 变更文件数：3。
- 高优先级文件：`src/main/java/com/demo/order/OrderService.java`。
- Diff refs 完整，可用于行级评论定位。
- 有效评论数：2 / 5，未通过。
- 覆盖率：45.00% / 60%，未通过。
- 单测通过率：97.67% / 100%，未通过。
- Sonar 质量门禁未通过。
- Approval 缺失。
- 失败测试：`com.demo.order.OrderServiceTest.createOrder_shouldRejectWhenStockInsufficient`。

预期审查 finding：

`OrderService.createOrder` 读取了库存，但没有在 `stock < quantity` 时拒绝创建订单，仍然执行 `decreaseStock` 并保存订单。这可能导致负库存或超卖。

建议交接给修复流程的内容：

```json
{
  "suspected_files": [
    "src/main/java/com/demo/order/OrderService.java",
    "src/test/java/com/demo/order/OrderServiceTest.java"
  ],
  "failed_tests": [
    "com.demo.order.OrderServiceTest.createOrder_shouldRejectWhenStockInsufficient"
  ],
  "suggested_commands": [
    "mvn test -Dtest=OrderServiceTest"
  ],
  "do_not_auto_fix_reason": "需要确认库存不足时的业务语义和异常类型，本 skill 只输出诊断与建议。"
}
```

安全摘要：

- 不修改源码。
- 不修改测试。
- 不创建 commit。
- 不执行 push。
- 不执行 approval。
- 不执行 merge。
