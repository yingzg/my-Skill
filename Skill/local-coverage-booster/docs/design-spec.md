# local-coverage-booster — 设计规格书

> 版本: v1  
> 阶段目标: Phase 2 生产可用  
> 目标目录: `/mnt/g/my-Skill/Skill/local-coverage-booster`  
> 设计日期: 2026-07-20

---

## 1. 背景

本工具最初的设计目标是：当 SonarQube PR 质量门禁因为新增代码覆盖率不足而失败时，自动定位未覆盖代码、补写 JUnit5 + Mockito 测试、推送后轮询 SonarQube 验证达标。

本工具不再依赖公司内部 SonarQube、GitLab CI 和固定项目配置，而是设计为一个本地覆盖率提升 Skill：

```text
当前分支代码变更
    ↓
本地 git diff 定位新增/修改 Java 行
    ↓
本地运行测试并生成 JaCoCo 覆盖率报告
    ↓
计算变更行覆盖率和未覆盖变更行
    ↓
补写有真实业务断言的 JUnit5 + Mockito 测试
    ↓
本地重新验证覆盖率
    ↓
达到本地目标后再建议 push
```

这个方向更适合生产使用：开发者在 push 前先本地修复覆盖率，减少远端流水线覆盖率门禁失败次数。

---

## 2. 一句话定位

`local-coverage-booster` 是一个本地 Java 单测覆盖率提升 Skill：对比当前分支与目标分支的变更行，结合 JaCoCo 本地覆盖率报告定位新增未覆盖代码，补写 JUnit5 + Mockito 单元测试，并强制每个新增测试验证真实业务可观察结果，目标是在一到两轮本地修复后尽量一次 push 通过流水线覆盖率门禁。

---

## 3. 设计目标

1. 在本地计算当前分支新增/修改 Java 行的覆盖率。
2. 定位新增/修改代码中未覆盖的文件、方法、行号。
3. 自动补写 JUnit5 + Mockito 单元测试。
4. 新增测试必须验证真实业务可观察结果，避免伪覆盖。
5. 本地运行测试和 JaCoCo 覆盖率验证。
6. 以本地目标阈值作为 push 前质量缓冲，减少流水线失败。
7. 支持每个项目使用独立配置，但配置文件存放在 Skill 内部，不污染业务项目仓库。
8. 达到 Phase 2 生产可用：支持配置、覆盖率计算、测试质量检查、before/after 报告、最多两轮本地迭代。

---

## 4. 非目标

V1 不做以下事情：

1. 不直接调用公司内部 SonarQube API。
2. 不依赖公司内部流水线。
3. 不要求在业务项目仓库根目录提交配置文件。
4. 不自动 push 代码，除非用户明确要求。
5. 不为了覆盖率修改 `src/main/java` 业务代码。
6. 不直接测试 private 方法。
7. 不支持多语言，V1 只支持 Java + JUnit5 + Mockito + JaCoCo。
8. 不保证本地 JaCoCo 计算结果与远端 SonarQube `new_line_coverage` 100% 一致，只提供保守的本地近似值。
9. 不实现 Phase 3 MR 增强能力，但预留设计接口。

---

## 5. Skill 名称与目录

建议 Skill 名称：

```text
local-coverage-booster
```

目录结构：

```text
/mnt/g/my-Skill/Skill/local-coverage-booster/
├── SKILL.md
├── docs/
│   └── design-spec.md
├── config/
│   ├── projects.yaml
│   └── projects.example.yaml
├── references/
│   ├── config-guide.md
│   ├── jacoco-report-format.md
│   ├── junit5-mockito-aaa.md
│   ├── observable-behavior-rules.md
│   └── troubleshooting.md
├── scripts/
│   ├── detect_project.py
│   ├── changed_lines.py
│   ├── run_coverage.py
│   ├── parse_jacoco.py
│   ├── coverage_gap.py
│   ├── test_quality_check.py
│   └── summarize_report.py
└── assets/
    └── junit5-mockito-test-template.java
```

说明：

| 路径 | 职责 |
|---|---|
| `SKILL.md` | 主流程、触发词、强制规则、停止条件、输出格式 |
| `docs/design-spec.md` | 当前设计规格书 |
| `config/projects.yaml` | Skill 内部项目配置，不提交到业务项目仓库 |
| `config/projects.example.yaml` | 配置模板，字段带注释 |
| `references/config-guide.md` | 配置字段说明和常见项目配置方式 |
| `references/jacoco-report-format.md` | JaCoCo XML 字段解释 |
| `references/junit5-mockito-aaa.md` | JUnit5 + Mockito + AAA 写法 |
| `references/observable-behavior-rules.md` | 业务可观察结果和反伪覆盖规则 |
| `references/troubleshooting.md` | 常见问题处理 |
| `scripts/` | 确定性脚本，负责 diff、覆盖率解析、质量检查、报告生成 |
| `assets/` | 测试模板 |

---

## 6. 配置策略

### 6.1 配置不放业务项目仓库

配置文件不放在业务项目根目录，不要求业务仓库提交 `.coverage-booster.yaml`。

原因：

1. 这是 Skill 的运行能力，不是业务项目的一部分。
2. 避免业务项目出现工具私有配置。
3. 避免每个项目都要发 MR 提交配置。
4. 避免不同使用者因为本地路径不同反复修改配置。

配置统一放在 Skill 内部：

```text
local-coverage-booster/config/projects.yaml
```

这个文件记录多个项目的配置。Skill 执行时根据当前 Git 项目根目录或 remote URL 匹配对应项目配置。

### 6.2 没有配置时的行为

如果没有匹配配置：

1. 先自动探测 Maven/Gradle、source root、test root、JaCoCo 报告路径。
2. 如果自动探测足够执行，则继续运行，并提示用户可以后续固化配置。
3. 如果关键配置缺失，则停止并要求用户提供最小配置。
4. 不要在业务仓库自动写配置文件。
5. 如果用户同意保存配置，则写入 Skill 内部 `config/projects.yaml`。

### 6.3 配置匹配规则

按优先级匹配：

1. `project_root` 与当前 `git rev-parse --show-toplevel` 完全匹配。
2. `remote_url_contains` 命中当前 `git remote get-url origin`。
3. `name` 与当前目录名匹配。
4. 无匹配则走自动探测。

---

## 7. 精简配置模板

配置字段必须少。用户只配置生产使用必需项，其余走默认值。

`config/projects.example.yaml` 建议内容：

```yaml
# local-coverage-booster 项目配置示例。
# 该文件放在 Skill 目录内，不放到业务项目仓库。
# 实际配置文件为 config/projects.yaml。

projects:
  - name: example-service
    # 可选。当前 Git 项目根目录。配置后匹配最准确。
    # 如果不同机器路径不同，可以不配，改用 remote_url_contains。
    project_root: /path/to/example-service

    # 可选。用于匹配 git remote origin。推荐配置项目仓库路径中稳定的一段。
    remote_url_contains: example-service

    # 当前分支对比哪个目标分支。auto 会优先尝试本地 master/main，再尝试常见远端分支。
    base_ref: auto

    # 远端流水线覆盖率门禁阈值。例如 SonarQube 要求新增代码覆盖率 >= 60。
    gate_threshold: 60

    # 本地修复目标阈值。建议比 gate_threshold 高 5-10 个点，给本地/远端统计差异留缓冲。
    local_target_threshold: 68

    # 生成 JaCoCo XML 覆盖率报告的命令。
    # Maven 单模块常用:
    # mvn org.jacoco:jacoco-maven-plugin:0.8.12:prepare-agent test org.jacoco:jacoco-maven-plugin:0.8.12:report
    # Maven 多模块可用: mvn test -pl module-name jacoco:report
    coverage_command: mvn org.jacoco:jacoco-maven-plugin:0.8.12:prepare-agent test org.jacoco:jacoco-maven-plugin:0.8.12:report

    # JaCoCo XML 报告路径。
    # Maven 单模块常用: target/site/jacoco/jacoco.xml
    jacoco_xml: target/site/jacoco/jacoco.xml

    # 可选。运行测试命令。不配置时默认使用 coverage_command。
    test_command: mvn test

    # 可选。生产代码根目录。不配置时默认 src/main/java。
    source_root: src/main/java

    # 可选。测试代码根目录。不配置时默认 src/test/java。
    test_root: src/test/java
```

### 7.1 默认值

不要求用户配置的默认值：

| 字段 | 默认值 |
|---|---|
| `base_ref` | `auto` |
| `gate_threshold` | `60` |
| `local_target_threshold` | `gate_threshold + 8` |
| `max_iterations` | `2`，固定在 Skill 内部，不暴露为常规配置 |
| `source_root` | `src/main/java` |
| `test_root` | `src/test/java` |
| `test_command` | 等于 `coverage_command` |
| `test_framework` | `junit5` |
| `mock_framework` | `mockito` |
| `exclude_paths` | 内置默认排除规则 |

### 7.2 内置排除规则

默认排除：

```text
**/dto/**
**/vo/**
**/bo/**
**/entity/**
**/config/**
**/constant/**
**/generated/**
**/*Mapper.java
**/*Mapper.xml
```

说明：

1. DTO/VO/Entity 通常是数据结构，补单测价值低。
2. Mapper/XML 通常由 SQL Review 或集成测试覆盖，不作为 V1 优先目标。
3. Config/Generated 类容易引入脆弱测试。
4. 用户可以后续在配置中扩展排除规则，但 V1 不强制暴露该字段。

---

## 8. 运行流程

### Step 0: 加载项目配置

执行：

```text
读取 config/projects.yaml
获取当前 git project_root 和 remote_url
匹配项目配置
如果无配置，运行 detect_project.py 自动探测
```

如果仍缺少 `coverage_command` 或 `jacoco_xml`：

```text
停止并要求用户提供最小配置：
- base_ref
- coverage_command
- jacoco_xml
```

### Step 1: 提取变更 Java 行

运行：

```bash
python3 scripts/changed_lines.py --base-ref <base_ref> --source-root <source_root>
```

输出：

```json
{
  "base_ref": "main",
  "files": [
    {
      "path": "src/main/java/com/example/OrderService.java",
      "changed_lines": [42, 43, 44, 55]
    }
  ]
}
```

要求：

1. 只统计新增/修改行。
2. 只统计 Java 文件。
3. 应用内置排除规则。
4. 未跟踪（untracked）的新 Java 文件按"全部行为新增"处理，同样纳入统计。
5. 如果没有 Java 变更，直接结束。

### Step 2: 生成本地 JaCoCo 覆盖率报告

运行配置中的：

```text
coverage_command
```

然后检查：

```text
jacoco_xml 是否存在
```

如果不存在：

1. 输出明确错误。
2. 提示用户检查 JaCoCo 插件配置或 `coverage_command`。
3. 不继续补测试。

### Step 3: 解析 JaCoCo 报告

运行：

```bash
python3 scripts/parse_jacoco.py --xml <jacoco_xml>
```

解析 JaCoCo XML 中：

```text
sourcefile name
line nr
line mi
line ci
line mb
line cb
```

基础判断：

```text
ci > 0                  -> 行已覆盖
mi > 0 and ci == 0      -> 行未覆盖
mb > 0                  -> 存在未覆盖分支
```

### Step 4: 计算变更行覆盖率缺口

运行：

```bash
python3 scripts/coverage_gap.py \
  --changed .coverage-booster/changed-lines.json \
  --jacoco .coverage-booster/jacoco-lines.json
```

输出：

```json
{
  "changed_coverable_lines": 42,
  "changed_covered_lines": 21,
  "changed_uncovered_lines": 21,
  "local_changed_line_coverage": 50.0,
  "targets": [
    {
      "file": "src/main/java/com/example/OrderService.java",
      "uncovered_lines": [43, 55],
      "priority": "HIGH"
    }
  ]
}
```

如果 `local_changed_line_coverage >= local_target_threshold`：

```text
直接输出通过报告，不补测试。
```

### Step 5: 选择补测目标

按以下优先级选择目标：

1. 未覆盖变更行最多的类。
2. Service / Domain / Application 层优先。
3. public / protected 方法优先。
4. 有明确分支、返回值、异常、外部调用的方法优先。
5. 可用 Mockito mock 掉依赖的方法优先。

暂缓处理：

1. private helper 本身，但可以通过 public 方法间接覆盖。
2. 强依赖真实数据库/Redis/MQ/HTTP 的集成路径。
3. 构造器、getter/setter、常量类。
4. 只靠反射才能触发的路径。

### Step 6: 读取源码和现有测试

必须读取：

1. 被测类完整源码。
2. 未覆盖行所在方法。
3. 依赖字段和构造器。
4. 现有测试类。
5. 相关 DTO/Enum/Exception。

分析：

```text
输入参数
业务分支
返回值
异常路径
repository/client/gateway/producer 调用
需要 mock 的依赖
可观察业务结果
```

### Step 7: 追加 JUnit5 + Mockito 测试

新增测试必须遵循 AAA：

```text
Arrange: 准备输入、mock 依赖、前置状态
Act: 调用被测 public 方法
Assert: 验证业务可观察结果
```

优先追加到已有测试类。

如果测试类不存在：

```text
在 test_root 下按相同 package 创建 <ClassName>Test.java。
```

默认使用：

```java
@ExtendWith(MockitoExtension.class)
class XxxServiceTest {
    @InjectMocks
    private XxxService service;

    @Mock
    private XxxRepository repository;
}
```

除非项目现有测试风格明显不同，应优先跟随项目已有风格。

### Step 8: 测试质量自检

运行：

```bash
python3 scripts/test_quality_check.py --test-files <changed-test-files>
```

检查：

1. 禁止 `assertTrue(true)`。
2. 禁止只有 `assertNotNull(result)` 作为唯一断言。
3. 禁止直接反射调用 private 方法。
4. 禁止只 `verify(mock).method(any())` 而不验证关键参数。
5. 禁止修改 `source_root` 下业务代码。
6. 新增测试必须至少有一个业务可观察断言。

如果不通过，必须修改测试后再进入 Step 9。

### Step 9: 本地验证和迭代

运行：

```text
test_command 或 coverage_command
```

然后重新解析 JaCoCo，重新计算覆盖率。

停止条件：

1. `local_changed_line_coverage >= local_target_threshold`。
2. 已完成 2 轮迭代。
3. 没有剩余可测试的未覆盖业务方法。
4. 新增测试连续两轮无法提升覆盖率。
5. 本地测试连续失败且原因不是测试代码可修复问题。
6. 继续提升必须修改业务代码。

### Step 10: 输出报告

输出：

```text
.coverage-booster/report.md
```

并在对话中总结：

1. before/after 本地变更行覆盖率。
2. 新增测试文件。
3. 每个测试覆盖的业务场景。
4. 每个测试验证的业务可观察结果。
5. 剩余未覆盖行及原因。
6. 是否建议 push。

---

## 9. 中间文件

所有运行中间文件写入被测项目根目录：

```text
.coverage-booster/
├── changed-lines.json
├── jacoco-lines-before.json
├── coverage-gap-before.json
├── jacoco-lines-after.json
├── coverage-gap-after.json
└── report.md
```

首次运行时，如果项目 `.gitignore` 没有包含 `.coverage-booster/`，只提示用户添加，不自动修改业务仓库。

原因：用户已明确不希望 Skill 能力配置污染业务项目；运行缓存也应谨慎处理。

---

## 10. MUST DO

1. 必须先计算 changed lines，再计算 JaCoCo 覆盖率，不得凭感觉补测试。
2. 必须只针对当前分支新增/修改代码提升覆盖率，除非用户明确要求补历史覆盖率。
3. 必须优先补 Service / Domain / Application 层中有业务分支的方法。
4. 必须按 AAA 结构编写测试。
5. 每个新增测试必须至少验证一个业务可观察结果。
6. 异常分支必须使用 `assertThrows`，并验证异常类型、异常消息或错误码。
7. 返回 DTO/VO/List/Map 时，必须验证关键业务字段或集合内容。
8. 调用 repository/client/gateway/producer 时，必须验证关键调用参数。
9. 必须本地运行测试通过后，才认为补测完成。
10. 必须重新生成 JaCoCo 报告并输出 before/after 覆盖率。
11. 必须保持测试确定性，不依赖真实时间、随机数、网络、数据库、Redis、MQ。
12. 如果业务依赖当前时间，必须 mock Clock、固定时间输入，或使用项目已有时间工具。
13. 必须跟随项目已有测试风格；没有现有风格时才使用默认 JUnit5 + Mockito 模板。
14. 必须在报告中列明每个新增测试验证的业务可观察结果。

---

## 11. MUST NOT DO

1. 不得为了覆盖率修改业务代码。
2. 不得直接测试 private 方法。
3. 不得删除已有测试。
4. 不得重写已有测试逻辑，除非已有测试因当前变更编译失败。
5. 不得使用 `assertTrue(true)`。
6. 不得只有 `assertNotNull(result)` 作为唯一断言。
7. 不得只 `verify(mock).method(any())` 而不验证关键参数。
8. 不得为了让测试通过而放宽业务断言。
9. 不得默认引入 `@SpringBootTest`，除非项目现有测试风格或用户明确要求。
10. 不得连接真实数据库、Redis、MQ、HTTP 服务。
11. 不得 push，除非用户明确要求。
12. 不得把本地 JaCoCo 覆盖率伪装成远端 SonarQube 覆盖率，只能称为“本地变更行覆盖率”或“本地近似新增行覆盖率”。
13. 不得为了覆盖不可测代码而使用反射、PowerMock 或修改访问修饰符，除非用户明确允许。

---

## 12. 业务可观察结果规则

新增测试至少验证以下一种业务可观察结果：

1. 返回值字段：状态、金额、数量、国家、类型、错误码等。
2. 异常行为：异常类型、异常消息、错误码。
3. 状态变化：对象字段被正确更新。
4. 持久化输出：`repository.save` 的 entity 字段正确。
5. 外部调用：client/gateway/producer 调用参数正确。
6. 分支结果：不同输入进入不同业务分支，并产生不同结果。

不合格：

```java
assertTrue(true);
assertNotNull(result);
verify(repository).save(any());
```

合格：

```java
assertEquals(OrderStatus.PENDING, result.getStatus());
assertEquals(new BigDecimal("198.00"), result.getTotalAmount());
verify(orderRepository).save(argThat(order ->
    order.getSkuId().equals("sku-001")
        && order.getQuantity() == 2
        && order.getStatus() == OrderStatus.PENDING
));
```

---

## 13. 脚本规格

### 13.1 detect_project.py

职责：

```text
自动识别当前项目类型和默认路径。
```

输入：

```text
project_root
```

输出：

```json
{
  "build_tool": "maven",
  "source_root": "src/main/java",
  "test_root": "src/test/java",
  "jacoco_xml_candidates": [
    "target/site/jacoco/jacoco.xml"
  ],
  "coverage_command_candidates": [
    "mvn org.jacoco:jacoco-maven-plugin:0.8.12:prepare-agent test org.jacoco:jacoco-maven-plugin:0.8.12:report"
  ]
}
```

### 13.2 changed_lines.py

职责：

```text
从 git diff 提取当前分支相对 base_ref 的新增/修改 Java 行，
并通过 git ls-files --others 补充未跟踪（untracked）的新 Java 文件。
```

核心命令：

```bash
git diff -U0 <merge_base> -- ":(glob)**/*.java"
git ls-files --others --exclude-standard   # 补充未跟踪的新 Java 文件
```

输出：

```json
{
  "files": [
    {
      "path": "src/main/java/com/example/Xxx.java",
      "changed_lines": [10, 11, 25]
    }
  ]
}
```

### 13.3 run_coverage.py

职责：

```text
执行 coverage_command 或 test_command，并检查 JaCoCo XML 是否生成。
```

要求：

1. 前台执行。
2. 捕获 exit code。
3. 失败时输出最后 80 行日志摘要。

### 13.4 parse_jacoco.py

职责：

```text
解析 JaCoCo XML 为文件行覆盖映射。
```

输出：

```json
{
  "src/main/java/com/example/Xxx.java": {
    "10": {"covered": true, "mi": 0, "ci": 3, "mb": 0, "cb": 0},
    "11": {"covered": false, "mi": 2, "ci": 0, "mb": 0, "cb": 0}
  }
}
```

### 13.5 coverage_gap.py

职责：

```text
合并 changed lines 和 JaCoCo lines，计算本地变更行覆盖率。
```

输出：

```json
{
  "changed_coverable_lines": 42,
  "changed_covered_lines": 31,
  "changed_uncovered_lines": 11,
  "local_changed_line_coverage": 73.81,
  "targets": []
}
```

### 13.6 test_quality_check.py

职责：

```text
检查新增/修改测试是否违反反伪覆盖规则。
```

检查项：

1. `assertTrue(true)`
2. 唯一断言是 `assertNotNull`
3. 反射调用 private 方法
4. `verify(... any())` 且无 `argThat` / `ArgumentCaptor` / 具体参数断言
5. 修改了 `source_root` 下文件
6. 没有任何 assert 或 verify

局限（正则静态检查，无法识别语义问题）：

1. 断言值写错（代码返回 "FR" 却断言 "DE"）。
2. 测试未真正命中目标分支（断言了但没走到该分支）。
3. 断言与业务语义脱节（断言了无关字段）。

这些需要依赖代码理解与业务可观察结果规则，脚本只兜底拦截最明显的伪覆盖。

### 13.7 summarize_report.py

职责：

```text
生成 Markdown 报告。
```

---

## 14. 输出报告格式

`.coverage-booster/report.md`：

```markdown
# Local Coverage Booster Report

## Summary

| Metric | Before | After |
|---|---:|---:|
| Changed coverable lines | 42 | 42 |
| Changed covered lines | 21 | 31 |
| Changed uncovered lines | 21 | 11 |
| Local changed-line coverage | 50.00% | 73.81% |

Result: PASS local target 68%

## Added Tests

| Test Class | Scenario | Observable Assertion |
|---|---|---|
| OrderServiceTest | valid order creates pending order | status, amount, saved entity fields |
| OrderServiceTest | missing sku throws exception | exception type/message, repository never called |

## Remaining Uncovered Lines

| File | Lines | Reason |
|---|---|---|
| XxxService.java | 88-91 | private helper only reachable through integration path |

## Recommendation

Local target passed. Safe to push for pipeline validation.
```

---

## 15. Phase 2 生产可用验收标准

Phase 2 必须满足：

1. 可从 Skill 内部 `config/projects.yaml` 匹配项目配置。
2. 无配置时可以自动探测；探测失败时能给出最小配置要求。
3. 可提取当前分支 Java 变更行。
4. 可运行本地覆盖率命令并解析 JaCoCo XML。
5. 可计算本地变更行覆盖率。
6. 可定位补测目标并指导生成测试。
7. 可检查新增测试是否存在伪覆盖风险。
8. 可执行最多 2 轮本地覆盖率提升。
9. 可输出 before/after Markdown 报告。
10. 默认不修改业务代码、不 push。

---

## 16. Phase 3 MR 增强设计

Phase 3 暂不实现，但保留设计：

```text
mr mode:
  使用 /mnt/g/my-Skill/Mcp 获取 MR 上下文
```

增强能力：

1. 自动获取 MR iid、source branch、target branch。
2. 自动设置 `base_ref` 为 MR target branch。
3. 只分析 MR changed files。
4. 可选将 `.coverage-booster/report.md` 评论到 MR。
5. 可选读取流水线覆盖率失败信息作为下一轮本地修复输入。

Phase 3 不改变核心覆盖率计算方式：

```text
覆盖率仍然以本地 JaCoCo 为主。
GitLab MCP 只提供 MR 上下文和协作输出。
```

---

## 17. 主要风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| 本地 JaCoCo 与远端 SonarQube 统计口径不同 | 本地通过但远端仍失败 | `local_target_threshold` 比 `gate_threshold` 高 5-10 个点 |
| 多模块项目报告路径复杂 | 找不到 JaCoCo XML | Skill 内部项目配置支持 `jacoco_xml` 和 `coverage_command` |
| 生成测试可能伪覆盖 | 覆盖率提升但业务价值低 | 强制业务可观察断言 + `test_quality_check.py` |
| Mockito 过度 mock | 测试脱离真实行为 | 要求验证关键参数，禁止只有 `any()` |
| 私有方法难覆盖 | 覆盖率无法达标 | 只能通过 public 方法间接覆盖，不用反射硬测 |
| 本地测试命令耗时 | 影响效率 | 支持 `test_command`，后续可扩展 `test_single` |
| Skill 内部配置路径随机器不同 | project_root 不可复用 | 支持 `remote_url_contains` 匹配 |

---

## 18. 实施建议

建议按以下顺序实现：

1. 创建 Skill 骨架。
2. 创建 `config/projects.example.yaml`。
3. 实现 `changed_lines.py`。
4. 实现 `parse_jacoco.py`。
5. 实现 `coverage_gap.py`。
6. 编写 `SKILL.md` 主流程和 MUST 规则。
7. 实现 `run_coverage.py`。
8. 实现 `test_quality_check.py`。
9. 实现 `summarize_report.py`。
10. 用真实 Java Maven 项目做一次前向测试。

---

## 19. 最小触发示例

用户可以这样触发：

```text
帮我提升当前分支新增代码的单测覆盖率
```

```text
使用 local-coverage-booster，补一下这个 Java 项目的本地覆盖率
```

```text
当前 MR 覆盖率可能不过，先本地补单测并验证 JaCoCo 覆盖率
```

---

## 20. 推荐结论

`local-coverage-booster` 的核心设计是保留完整的闭环能力，但去掉公司内部 SonarQube 依赖：

```text
SonarQube API 门禁修复
    ↓
本地 git diff + JaCoCo 覆盖率修复
```

生产使用时，以更高的本地目标阈值作为远端门禁缓冲，并通过测试质量规则防止伪覆盖。

V1 直接做到 Phase 2 生产可用；Phase 3 的 GitLab MCP 增强仅作为后续扩展，不阻塞当前实现。
