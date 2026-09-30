# 预期诊断摘要

该 fixture 捕获了这个真实项目中的一次编译门禁失败：

```text
~/projects/demo-service/backend
```

Maven compile 阶段失败，原因是 `StatisticsController` 使用了 `@RequestParam`，但缺少 import：

```java
org.springframework.web.bind.annotation.RequestParam
```

诊断证据：

- 失败 job：`maven-test`
- 错误类型：`cannot find symbol`
- 缺失 symbol：`class RequestParam`
- 相关文件：`backend/src/main/java/com/example/statistics/controller/StatisticsController.java`
- 相关行：49、50、51
- Diff refs 完整，可用于行级评论定位。

建议修复方向：

```java
import org.springframework.web.bind.annotation.RequestParam;
```

建议验证命令：

```bash
cd ~/projects/demo-service/backend
mvn test -q
```

建议交接给修复流程的内容：

```json
{
  "suspected_files": [
    "backend/src/main/java/com/example/statistics/controller/StatisticsController.java"
  ],
  "compile_errors": [
    {
      "symbol": "class RequestParam",
      "message": "cannot find symbol"
    }
  ],
  "suggested_commands": [
    "mvn test -q"
  ],
  "do_not_auto_fix_reason": "本 skill 只输出诊断与建议；代码修改应交给人工或单独的代码修复流程。"
}
```

安全摘要：

- 不修改源码。
- 不修改测试。
- 不创建 commit。
- 不执行 push。
- 不执行 approval。
- 不执行 merge。
