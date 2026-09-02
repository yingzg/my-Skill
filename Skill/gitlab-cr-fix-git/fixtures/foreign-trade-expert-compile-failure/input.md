请使用 fixture 模式分析这个真实 Java 项目的 CI 编译门禁失败：

```text
/mnt/d/个人项目/foreign-trade-expert/backend
```

目标：

1. 从 job trace 中识别 Maven 编译失败。
2. 定位失败文件 `StatisticsController.java`。
3. 提出最小修复：补充 `RequestParam` import。
4. 验证修复后运行 `mvn test -q`。

