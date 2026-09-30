# 常见问题排查

## JaCoCo XML 缺失

症状：

```text
命令执行成功但未找到 JaCoCo XML
```

检查：

1. Maven 可以下载并运行 `jacoco-maven-plugin`，或 Gradle 存在 JaCoCo 插件。
2. `coverage_command` 在测试前挂载 JaCoCo agent，随后生成 XML。
3. `jacoco_xml` 路径与被测模块匹配。

常见 Maven 命令：

```bash
mvn org.jacoco:jacoco-maven-plugin:0.8.12:prepare-agent test org.jacoco:jacoco-maven-plugin:0.8.12:report
```

常见 Gradle 命令：

```bash
./gradlew test jacocoTestReport
```

## 覆盖率没有变化

可能原因：

- 测试没有执行到变更的方法。
- 测试类命名不符合 Surefire includes。
- Maven 命令运行了错误的模块。
- JaCoCo XML 路径指向了过期报告。
- 未覆盖行不是可覆盖的字节码。
- 代码路径需要不同的分支输入。

处理步骤：

1. 运行具体的测试类。
2. 确认测试出现在测试日志中。
3. 删除旧 JaCoCo 报告并重新生成。
4. 检查 `coverage_command`、模块路径和 `jacoco_xml`。
5. 检查 `mb/cb` 分支计数器是否存在部分分支覆盖。

## Mockito UnnecessaryStubbingException

将 stub 移到实际使用它的测试方法内，或对有意可选的 stub 使用 `lenient()`。

优先：

```java
lenient().when(client.query(any())).thenReturn(response);
```

仅在相同 setup 支持多个分支时使用。

## 测试需要真实基础设施

不要连接真实 DB/Redis/MQ/HTTP。

可选方案：

1. Mock repository/client/gateway/producer。
2. 通过更小的 public 方法测试该分支。
3. 在报告中标记该行不适合 V1 本地单元测试。

## 本地通过但远端失败

常见原因：

- SonarQube 排除规则不同。
- CI 运行了另一个 Maven profile。
- CI 目标分支与本地 `base_ref` 不同。
- 多模块报告路径不同。

提高 `local_target_threshold`，并将 `coverage_command` 与 CI 对齐。
