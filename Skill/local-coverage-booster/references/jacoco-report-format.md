# JaCoCo 报告格式

JaCoCo 是本 Skill 的本地覆盖率数据来源。

常见 Maven XML 路径：

```text
target/site/jacoco/jacoco.xml
```

常见 Gradle XML 路径：

```text
build/reports/jacoco/test/jacocoTestReport.xml
```

## XML 结构

JaCoCo XML 包含 package、sourcefile 和 line 记录：

```xml
<package name="com/example/order">
  <sourcefile name="OrderService.java">
    <line nr="42" mi="0" ci="4" mb="0" cb="0"/>
    <line nr="43" mi="3" ci="0" mb="1" cb="1"/>
  </sourcefile>
</package>
```

行字段：

| 字段 | 含义 |
|---|---|
| `nr` | 源码行号。 |
| `mi` | 未覆盖指令数。 |
| `ci` | 已覆盖指令数。 |
| `mb` | 未覆盖分支数。 |
| `cb` | 已覆盖分支数。 |

## 本地覆盖率判读

本 Skill 采用务实的行级判读：

```text
coverable = mi + ci + mb + cb > 0
covered = ci > 0 or cb > 0
uncovered = coverable and not covered
```

即使某行被部分执行，分支缺口也仍然重要，但 V1 优先报告变更行覆盖率。当变更行存在 `mb > 0` 时，检查其周围分支，并在远端门禁关注分支覆盖率时补充针对该分支的测试。

## 与 SonarQube 的差异

本地 JaCoCo 变更行覆盖率不保证与远端 SonarQube 新增行覆盖率完全一致。

常见原因：

- SonarQube 排除规则与本地默认规则不同。
- CI 运行了不同的模块/测试 profile。
- 生成代码或 Lombok 代码影响行映射。
- 远端流水线对目标分支的合并方式不同。

将 `local_target_threshold` 设为高于真实门禁阈值，以吸收这些差异。
