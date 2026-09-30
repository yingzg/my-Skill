---
name: local-coverage-booster
description: 本地 Java 单元测试覆盖率提升技能。当用户希望在 push 前提升变更 Java 代码的本地测试覆盖率、生成有意义的 JUnit5 + Mockito 测试、分析 JaCoCo 报告、通过 git diff 计算变更行覆盖率，或在试图通过 CI/SonarQube 覆盖率门禁时避免伪覆盖时使用。
---

# 本地覆盖率提升

提升当前分支新增/修改 Java 代码的本地单测覆盖率。用 git diff 定位变更行，用 JaCoCo XML 判断变更行是否被覆盖，补写 JUnit5 + Mockito 测试，并强制测试验证业务可观察结果。

## 核心原则

以通过真实流水线覆盖率门禁为目标，但先在本地验证：

```text
changed Java lines -> JaCoCo line coverage -> uncovered changed lines
  -> meaningful tests -> local verification -> before/after report
```

V1 不调用 SonarQube。将本地 JaCoCo 变更行覆盖率视为 push 前的保守信号，而非远端门禁的精确值。

## 参考文件

- 先读取 `config/projects.yaml`。若没有匹配的项目配置项，则自动探测并仅询问缺失的必要信息。
- 当配置缺失或不明确时，读取 `references/config-guide.md`。
- 在手动解读 JaCoCo XML 之前，先读取 `references/jacoco-report-format.md`。
- 在新建或大幅修改测试之前，先读取 `references/junit5-mockito-aaa.md`。
- 在判断测试是否有意义之前，先读取 `references/observable-behavior-rules.md`。
- 当命令失败、JaCoCo XML 缺失或覆盖率没有变化时，读取 `references/troubleshooting.md`。

## 工作流程

### Step 0: 加载配置

按以下顺序将当前项目与 `config/projects.yaml` 匹配：

1. 精确匹配 `project_root`。
2. 用 `remote_url_contains` 匹配 `git remote get-url origin` 的结果。
3. 用 `name` 匹配项目目录名。
4. 用 `scripts/detect_project.py` 自动探测。

必需的运行时值：

```text
base_ref
coverage_command
jacoco_xml
source_root
test_root
local_target_threshold
```

若无法探测到必需值，则停止并向用户询问这些值。不要将配置写入业务仓库。若用户要求持久化配置，则写入本 Skill 的 `config/projects.yaml`。

### Step 1: 提取变更 Java 行

在业务项目根目录运行：

```bash
python3 <skill_dir>/scripts/changed_lines.py \
  --project-root <project_root> \
  --base-ref <base_ref> \
  --source-root <source_root> \
  --output .coverage-booster/changed-lines.json
```

变更行来源包括：已提交（committed）、已暂存（staged）、未暂存（unstaged）的修改，以及未跟踪（untracked）的新 Java 文件（通过 `git ls-files --others` 单独枚举，按全部行为新增处理）。

若经过默认排除规则后已无变更 Java 行，则报告无需本地覆盖率提升。

### Step 2: 生成 JaCoCo 报告

运行：

```bash
python3 <skill_dir>/scripts/run_coverage.py \
  --project-root <project_root> \
  --command "<coverage_command>" \
  --jacoco-xml <jacoco_xml>
```

若命令失败或 XML 缺失，则读取 `references/troubleshooting.md`，说明确切的缺失配置，然后停止。

### Step 3: 解析 JaCoCo

运行：

```bash
python3 <skill_dir>/scripts/parse_jacoco.py \
  --xml <project_root>/<jacoco_xml> \
  --source-root <source_root> \
  --output .coverage-booster/jacoco-lines-before.json
```

### Step 4: 计算覆盖率缺口

运行：

```bash
python3 <skill_dir>/scripts/coverage_gap.py \
  --changed .coverage-booster/changed-lines.json \
  --jacoco .coverage-booster/jacoco-lines-before.json \
  --threshold <local_target_threshold> \
  --output .coverage-booster/coverage-gap-before.json
```

若 `passed=true`，则报告本地目标已通过，不再补测试。

### Step 5: 选择补测目标

优先处理：

1. Service / Domain / Application 层类。
2. 未覆盖变更行最多的文件。
3. 有明确分支、返回值、异常或依赖调用的 public/protected 方法。
4. 无需真实 DB/Redis/MQ/HTTP 即可用 mock 测试的代码路径。

暂缓处理：

- DTO/VO/entity/config/generated/mapper 类代码。
- private 辅助方法，除非能通过 public 方法间接覆盖。
- 需要真实基础设施的路径。

### Step 6: 补写有意义的测试

读取目标源码、现有测试、依赖的 DTO/Enum/Exception，以及可 mock 的协作者。

优先追加到已有测试类。若不存在测试类，则在 `test_root` 下按相同 package 创建 `<ClassName>Test`。

使用 AAA：

```text
Arrange: prepare inputs, mocks, and state.
Act: call the public method under test.
Assert: verify observable business behavior.
```

### Step 7: 测试质量检查

运行：

```bash
python3 <skill_dir>/scripts/test_quality_check.py \
  --project-root <project_root> \
  --source-root <source_root> \
  --test-files <changed_test_file_1> <changed_test_file_2> \
  --output .coverage-booster/test-quality.json
```

在验证前修复所有 `ERROR` 项。审查 `WARNING` 项并在合适处改进测试。

### Step 8: 验证与迭代

再次用 `coverage_command` 运行测试和覆盖率。重新解析 JaCoCo 生成：

```text
.coverage-booster/jacoco-lines-after.json
.coverage-booster/coverage-gap-after.json
```

满足以下任一条件时停止：

1. `local_changed_line_coverage >= local_target_threshold`。
2. 已完成两轮本地覆盖率提升迭代。
3. 没有剩余可测试的业务方法。
4. 测试反复失败，且原因无法在测试内修复。
5. 继续提升需要修改业务代码。

### Step 9: 输出报告

运行：

```bash
python3 <skill_dir>/scripts/summarize_report.py \
  --before .coverage-booster/coverage-gap-before.json \
  --after .coverage-booster/coverage-gap-after.json \
  --quality .coverage-booster/test-quality.json \
  --test-files <changed_test_files> \
  --output .coverage-booster/report.md
```

在最终回答中总结：

- before/after 本地变更行覆盖率。
- 变更的测试文件。
- 每个测试验证的业务行为。
- 剩余未覆盖的变更行及原因。
- 是否建议 push 以进行流水线验证。

## 必须做（MUST DO）

1. 在决定补哪些测试之前，先计算变更行和 JaCoCo 覆盖率。
2. 只针对当前分支变更的 Java 代码提升覆盖率，除非用户要求补历史覆盖率。
3. 优先补有意义的 service/domain/application 层测试，而非结构化的 DTO/config 测试。
4. 使用 AAA 结构。
5. 每个新增测试至少验证一个业务可观察结果。
6. 异常分支使用 `assertThrows`，并验证异常类型、消息或错误码。
7. 对 DTO/VO/List/Map 返回值，断言关键字段。
8. 验证重要的 repository/client/gateway/producer 调用参数。
9. 在宣称成功之前，本地运行测试并重新生成 JaCoCo。
10. 保持测试确定性；mock 时间、随机数、网络、DB、Redis、MQ 和 HTTP。
11. 优先遵循项目已有测试风格，再考虑默认模板。

## 禁止做（MUST NOT DO）

1. 不得为了提升覆盖率修改生产代码。
2. 不得直接测试 private 方法。
3. 不得删除已有测试。
4. 不得重写已有测试行为，除非当前变更导致编译失败。
5. 不得使用 `assertTrue(true)`。
6. 不得只把 `assertNotNull(result)` 作为唯一断言。
7. 对于重要的协作者调用，不得只验证 `any()` 参数。
8. 不得引入 `@SpringBootTest`，除非项目已使用或用户要求。
9. 不得连接真实的 DB/Redis/MQ/HTTP 服务。
10. 不得 push，除非用户明确要求。
11. 不得把本地 JaCoCo 覆盖率描述为精确的远端 SonarQube 覆盖率。

## 输出约定

始终区分：

```text
local_changed_line_coverage: local JaCoCo + git diff approximation
remote_gate_coverage: CI/SonarQube value, only known after remote scan
```

使用以下完成措辞：

```text
Local target passed. Safe to push for pipeline validation.
```

不要这样说：

```text
SonarQube gate will pass.
```
