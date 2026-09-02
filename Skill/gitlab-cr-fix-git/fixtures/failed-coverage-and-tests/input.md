请 review 这个 MR，并分析门禁失败原因：

```text
https://gitlab.example.com/demo/order-service/-/merge_requests/12
```

使用 fixture 模式：

```text
fixtures/failed-coverage-and-tests
```

期望流程：

1. 读取 MR 详情、changes、discussions。
2. 输出 MR 状态和变更文件数。
3. 从 MockGateBot 评论中解析门禁阻塞项。
4. 从 pipeline jobs 和 job trace 中定位失败单测。
5. 从 Sonar measures 中解析覆盖率不足。
6. 基于 diff 生成 CR 评论和修复建议。

