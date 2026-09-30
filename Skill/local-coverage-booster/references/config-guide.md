# 配置指南

将项目配置保存在本 Skill 目录内：

```text
local-coverage-booster/config/projects.yaml
```

除非用户明确修改此策略，否则不要将配置写入业务仓库。

## 最小项目配置

```yaml
projects:
  - name: order-service
    remote_url_contains: order-service
    base_ref: auto
    gate_threshold: 60
    local_target_threshold: 68
    coverage_command: mvn org.jacoco:jacoco-maven-plugin:0.8.12:prepare-agent test org.jacoco:jacoco-maven-plugin:0.8.12:report
    jacoco_xml: target/site/jacoco/jacoco.xml
```

## 字段说明

| 字段 | 必填 | 默认值 | 含义 |
|---|---|---|---|
| `name` | 是 | 无 | 人类可读的项目名。也用作弱匹配的兜底条件。 |
| `project_root` | 否 | 无 | 精确的本地 Git 根目录。路径稳定时最合适。 |
| `remote_url_contains` | 否 | 无 | 来自 `git remote get-url origin` 的稳定子串。共享配置时推荐使用。 |
| `base_ref` | 否 | `auto` | 用于变更行对比的 ref。auto 会优先尝试本地 main/master，再尝试常见远端 ref。 |
| `gate_threshold` | 否 | `60` | 真实的远端门禁阈值。 |
| `local_target_threshold` | 否 | `gate_threshold + 8` | 带安全缓冲的本地目标。 |
| `coverage_command` | 是 | 自动探测 | 运行测试并生成 JaCoCo XML 的命令。 |
| `jacoco_xml` | 是 | 自动探测 | 相对项目根目录的 JaCoCo XML 路径。 |
| `test_command` | 否 | `coverage_command` | 本地测试验证命令。 |
| `source_root` | 否 | `src/main/java` | 生产 Java 根目录。 |
| `test_root` | 否 | `src/test/java` | 测试 Java 根目录。 |

## 匹配顺序

1. 精确匹配 `project_root`。
2. `remote_url_contains`。
3. `name` 等于项目目录名。
4. 自动探测。

## 多模块 Maven

使用模块专用命令和路径：

```yaml
projects:
  - name: order-service-module
    remote_url_contains: backend-platform
    base_ref: auto
    gate_threshold: 60
    local_target_threshold: 70
    coverage_command: mvn -pl order-service org.jacoco:jacoco-maven-plugin:0.8.12:prepare-agent test org.jacoco:jacoco-maven-plugin:0.8.12:report
    test_command: mvn test -pl order-service
    source_root: order-service/src/main/java
    test_root: order-service/src/test/java
    jacoco_xml: order-service/target/site/jacoco/jacoco.xml
```

当一个 MR 只改动已知模块时，建议每个模块一个配置项。这样报告更小、反馈更快。
