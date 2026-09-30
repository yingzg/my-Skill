# 演示仓库：demo-service

可以使用这个真实 Java 项目作为更高保真的演示仓库：

```text
~/projects/demo-service
```

## 当前评估

| 项目 | 状态 |
|---|---|
| 后端构建工具 | Maven |
| 后端路径 | `backend/` |
| Java 版本 | 17 |
| Spring Boot | 3.2.5 |
| 测试依赖 | `spring-boot-starter-test`、`spring-security-test` |
| 现有测试文件 | 无 |
| 第一次修复后的基线 | `mvn test -q` 通过 |

## 捕获到的真实门禁失败

初始执行 `mvn test -q` 时在编译阶段失败，原因是 `StatisticsController` 使用了 `@RequestParam`，但缺少 import：

```java
org.springframework.web.bind.annotation.RequestParam
```

这是一个适合演示的真实 CI 门禁失败：

```text
job trace -> 解析编译错误 -> 定位 controller -> 建议添加缺失 import -> 重新运行 mvn test
```

已捕获的 fixture 位于：

```text
fixtures/demo-service-compile-failure/gitlab_get_job_trace.txt
```

## 推荐演示流程

1. 编译门禁演示：使用已捕获的 Maven 失败日志展示门禁诊断。
2. 修复建议演示：指出 `StatisticsController` 缺少 `RequestParam` import。
3. 验证建议演示：建议在 `backend/` 下运行 `mvn test -q`。
4. 后续增强：围绕有业务逻辑的 service 增加定向单元测试建议。
5. 覆盖率演示：后续如果需要真实本地覆盖率报告，可以再引入 JaCoCo。

## 为什么这个仓库比玩具项目更适合演示

- 它是一个真实的 Spring Boot / MyBatis 业务项目。
- 它包含 controller、service、mapper、SQL resource、security 和 domain 模块。
- 它一开始没有测试文件，这符合很多真实项目的覆盖率改造场景。
- 它已经产生过一个具体、可解释的编译门禁失败。

## 注意事项

- 除非该项目已经推送到 GitLab，否则不要用它演示真实 GitLab 集成。
- 演示时避免大范围重构；保持诊断和建议足够小、足够可解释。
- 覆盖率演示应优先从一个窄 service 测试建议开始，而不是试图覆盖整个项目。
- 当前 skill 只输出诊断和修复建议，不应直接修改这个仓库的代码。
