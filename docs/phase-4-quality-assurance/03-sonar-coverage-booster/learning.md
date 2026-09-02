# sonar-coverage-booster — 深度学习文档

> 对应 SKILL.md: `/mnt/d/测试项目/vibe-hubs/skill/sonar-coverage-booster/SKILL.md` (332行)
>
> 适用项目: Java / Spring Boot，遵循 intl-retail 项目测试规范

---

## 一、功能全景

### 一句话定位

**SonarQube 单元测试覆盖率自动补全引擎** — 7 步修复管线 + 迭代修复循环 + CI 闭环验证，目标是将 PR 的 `new_line_coverage` 从不足 60% 提高到通过质量门禁。

### 核心流程

```
cr-engineer 检测到 Quality Gate 未通过
    ↓
[委托 sonar-coverage-booster]
    ↓
Step 1: 确认 SonarQube 信息（token、project key、PR key、branch）
    ↓
Step 2: 找出未覆盖代码行（SonarQube API → 源码文件映射）
    ↓
Step 3: 读取目标源文件，分析可测方法（公共方法、分支条件、依赖注入）
    ↓
Step 4: 确认测试文件位置与已有测试（不得修改已有用例）
    ↓
Step 5: 编写测试代码（JUnit5 + Mockito + 模板约束）
    ↓
Step 6: 本地运行测试验证（mvn test，全部通过才提交）
    ↓
Step 7: 推送代码 → 轮询 SonarQube 验证达标
    ↓
[覆盖率 < 60%？] → 回到 Step 2，分析剩余未覆盖行，迭代修复
    ↓
[覆盖率 ≥ 60%] → 输出报告，任务完成
```

### 核心指标

| 指标 | 含义 | 公式 |
|:---|:---|:---|
| `new_lines_to_cover` | 本次 PR 新增的可覆盖行数 | — |
| `new_uncovered_lines` | 本次 PR 新增但未被测试覆盖的行数 | — |
| `new_line_coverage` | 新增代码的测试覆盖率 | `(1 - new_uncovered / new_lines_to_cover) × 100%` |

**目标**: `new_line_coverage ≥ 60%`

---

## 二、架构设计分析

### 2.1 7 步修复管线

整体架构分为三层：**信息收集层**（Step 1-3）→ **代码生成层**（Step 4-6）→ **交付验证层**（Step 7）。

#### Step 1：确认 SonarQube 信息 — 配置初始化

```
职责: 加载 tokens.json → 获取 SONAR_URL / SONAR_TOKEN / PROJECT_KEY / PR_KEY / BRANCH
```

**关键设计**：tokens.json 的自动探测机制。按优先级顺序在 3 个候选路径中搜索：

```
~/.claude/skills/sonar-coverage-booster/tokens.json     ← 优先级最高（Claude Code）
~/.agents/skills/sonar-coverage-booster/tokens.json      ← 次优先级（OpenCode）
$(pwd)/.sonar-tokens.json                                ← 兜底（项目目录）
```

这解决了"不同 AI 工具安装 Skill 到不同路径"的问题。SKILL 不需要知道自己在哪个工具下运行，只要 tokens.json 在约定的相对路径即可。

**为什么 Step 1 不中断询问用户**：敏感信息（token）绝不应在 LLM 对话中传递。通过文件加载 + Python 解析的方式，token 只在 shell 命令级别流转，不进入 LLM 上下文窗口。这是安全工程中 "secret isolation" 原则的体现。

#### Step 2：找出未覆盖代码行 — 漏洞探测

```
职责: 调用 SonarQube REST API → 解析未覆盖行 → 按未覆盖行数排序 → 优先级队列
```

使用两个 SonarQube API 端点：

```bash
# 端点 1: 获取覆盖率指标
/api/measures/component?component=<PROJECT_KEY>&pullRequest=<PR_KEY>
  &metricKeys=new_line_coverage,new_lines_to_cover,new_uncovered_lines

# 端点 2: 获取未覆盖文件列表（分页，每页 100）
/api/coverage/list?component=<PROJECT_KEY>&pullRequest=<PR_KEY>&ps=100
```

**优先级策略**：按 `new_uncovered_lines` 降序排列，优先处理未覆盖行数最多的文件。这是"收益最大化"策略 — 用最少的测试覆盖最多的行。

#### Step 3：读取目标源文件，分析可测方法 — 代码理解

```
职责: 读取源文件 → 识别公共/私有方法 → 识别分支条件 → 分析依赖注入 → 输出可测方法清单
```

分析的三个维度：

| 维度 | 分析对象 | 输出 |
|:---|:---|:---|
| 方法可见性 | `public` / `protected` vs `private` | 直接测试 vs 间接覆盖 |
| 分支条件 | `if/else`、`switch`、三目运算符 | 每个分支一个测试用例 |
| 依赖注入 | `@Autowired`、`@DubboReference` | Mock 对象清单 |

**Method-to-Test 映射规则**：
- 公共方法 → 直接为每个分支路径写测试
- 私有方法 → 找到调用它的公共方法，通过该公共方法的参数组合间接覆盖
- 空路径（如 `return null` 的早期退出）→ 也需要覆盖，属于边界条件

#### Step 4：确认测试文件位置与已有测试 — 增量规划

```
职责: 确定测试类路径 → 检查已有测试 → 规划新增用例（只追加，不修改）
```

测试文件路径约定：
```
src/test/java/<同包路径>/<ClassName>Test.java
```

**核心约束**："不得修改已有测试用例，只追加新用例"。这是"开闭原则"在测试工程中的体现 — 对扩展开放（追加新用例），对修改关闭（不碰已有用例）。如果修改已有用例导致已有断言失败，会引入回归风险。

#### Step 5：编写测试代码 — 代码生成核心

```
职责: 按模板生成测试类 → 填充 Mock 设置 → 编写 Arrange/Act/Assert → 遵守硬性规范
```

测试类模板：

```java
@ExtendWith(MockitoExtension.class)
class XxxServiceImplTest {

    @InjectMocks
    private XxxServiceImpl service;

    @Mock
    private XxxRepository repository;

    @Test
    @DisplayName("methodName: scenario -> expected behavior")
    void methodName_scenario_expectedBehavior() {
        // Arrange
        // Act
        // Assert
    }
}
```

**模板中隐含的设计决策**：

1. **`@ExtendWith(MockitoExtension.class)` 而非 `@SpringBootTest`**：不启动 Spring 容器，测试启动速度从秒级降到毫秒级。代价是无法测试 Spring 集成行为（如 AOP、事务），但覆盖率补全的核心目标是"行覆盖"而非"集成验证"。

2. **`@InjectMocks` + `@Mock` 而非手动构造**：让 Mockito 自动注入 mock，减少样板代码。对于需要部分 mock 的场景（如 `@Spy`），需要额外处理。

3. **AAA 模式（Arrange-Act-Assert）**：标准三段式结构，每个测试方法内部按 `// Arrange → // Act → // Assert` 组织。

**硬性规范及其设计理由**：

| 规范 | 原因 |
|:---|:---|
| 禁止 `@DisplayName` 使用中文弯引号 | JVM 编译时弯引号 `"` `"` 会被当作非法字符，导致编译失败 |
| 禁止直接测试私有方法 | Java 反射可访问但违反封装原则；更根本的是，私有方法的行为已由公共方法测试间接覆盖 |
| 禁止使用 MyBatis Plus | intl-retail 项目规范显式禁止，违反会导致 CI 检查失败 |
| 禁止修改已有测试用例 | 防止引入回归错误，只追加不修改确保已有行为不变 |
| 使用 `lenient()` | 当测试执行路径不经过某个 stub 时，`lenient()` 抑制 `UnnecessaryStubbingException` |

#### Step 6：本地运行测试验证 — 质量守门

```
职责: mvn test 运行生成的测试 → 全部通过 → 进入 Step 7 | 有失败 → 修复后重试
```

```bash
# 运行单个测试类
mvn test -pl <module> -Dtest=<ClassName> -s ~/code/settings.xml

# 运行整个模块测试
mvn test -pl <module> -s ~/code/settings.xml
```

**为什么必须本地验证后再提交**：
- 如果推送了带编译错误的测试代码，CI 流水线会直接失败，浪费 CI 资源
- 如果推送了断言错误的测试代码，会阻塞 PR 的所有其他检查
- 本地验证是最快的反馈循环（秒级 vs CI 分钟级）

#### Step 7：推送代码 + 轮询验证 — 闭环收尾

```
职责: git commit + push → 轮询 SonarQube API → 检查 new_line_coverage → 达标则结束，否则回到 Step 2
```

```bash
# 常规推送
git add <test-files>
git commit -m "test(<domain>): add unit tests to boost sonar coverage for PR #<N>"
git push

# 空提交触发器（CI 未自动触发 Sonar 扫描时）
git commit --allow-empty -m "ci: trigger pipeline for sonar scan"
git push
```

**空提交设计**：当只推送了测试文件（无业务代码变更），CI 流水线可能不会触发 Sonar 扫描。此时用 `--allow-empty` 空提交触发扫描。提交信息以 `ci:` 开头表示这是 CI 管理类提交，不影响业务语义。

### 2.2 SonarQube API 集成

三个核心端点：

| 端点 | 用途 | 时机 |
|:---|:---|:---|
| `/api/measures/component` | 查询覆盖率指标 | Step 1（初始）+ Step 7（轮询） |
| `/api/coverage/list` | 获取未覆盖文件列表 | Step 2（分析） |
| `/api/issues/search` | 查询具体代码问题 | Step 2（可选，补充分析） |

**认证方式**：HTTP Basic Auth，token 作为 username，密码为空：
```bash
curl -s -u "${SONAR_TOKEN}:" "<API_URL>"
```

**响应处理**：通过 `python3 -m json.tool` 格式化 JSON，LLM 直接解析响应中的 `component.measures` 对象提取指标值。

### 2.3 迭代修复循环

```
Step 7 完成后:
    ↓
检查 new_line_coverage
    ├─ ≥ 60% → 输出报告，结束
    └─ < 60% → 回到 Step 2
                    ↓
              分析最新未覆盖行（SonarQube 已重新扫描）
                    ↓
              跳过已生成测试的方法，聚焦新暴露的未覆盖代码
                    ↓
              Step 3-7 再次执行
```

**迭代终止条件**：

1. **成功终止**：`new_line_coverage ≥ 60%`
2. **饱和终止**：无新的可测试方法（所有未覆盖行为私有方法且无法通过公共路径覆盖）
3. **最大迭代终止**：隐含上限（通常 3 轮，因为每轮都会显著减少 `new_uncovered_lines`）

**迭代状态追踪**：每轮生成的测试文件列表应在内存中维护，下一轮分析时跳过已处理的方法。

### 2.4 典型测试场景模式

SKILL 内置了基于 intl-retail 考勤规则扩展的四类测试模式：

| 模式 | 描述 | 典型用例数 |
|:---|:---|:---|
| 幂等条件变更测试 | 新增字段后，新旧字段组合相同的重复判断 | 2（相同/不同） |
| 重叠判断三角逻辑 | scope 为空 / rule 为空 / 有交集 / 无交集 | 4 |
| JSON 序列化字段 | 空列表 → null / 非空 → JSON / 去重过滤排序 | 3 |
| 分布式锁键格式 | 有值拼入 / 为空用 _all_ 占位符 | 2 |

这些模式是 **SKILL 的"领域知识"** — 不是 AI 通用推理出来的，而是从真实 PR 的覆盖率补全经验中提炼的。

---

## 三、设计模式深度分析

### 3.1 Repair Loop Pattern（修复循环模式）

```
循环结构:
  while (coverage < 60%) {
    1. 探测 (SonarQube API) → 发现未覆盖代码
    2. 分析 (读源码) → 理解业务逻辑
    3. 修复 (写测试) → 生成覆盖代码
    4. 验证 (mvn test) → 本地通过
    5. 提交 (git push) → 触发 CI
    6. 观测 (poll API) → 获取新覆盖率
  }
```

**与一次性生成的对比**：

| 维度 | 一次性生成 | 迭代修复 |
|:---|:---|:---|
| 测试数量 | 可能过度生成 | 按需生成，精准 |
| 失败恢复 | 全部重来 | 只补剩余 |
| CI 时间 | 1 次扫描 | N 次（N=迭代次数） |
| 覆盖率达标率 | 不确定性高 | 逐步收敛，确定性高 |
| 策略调整 | 无法中途调整 | 每轮根据反馈调优 |

迭代修复的核心优势是**反馈驱动**：第一轮生成的测试覆盖率是多少？哪些方法虽然写了测试但 SonarQube 仍标记为未覆盖（可能是测试没真正执行到目标行）？这些反馈信息在一次性生成中无法获取。

### 3.2 Pipeline Pattern（管线模式）

7 个步骤形成严格的线性管线，每步的输入依赖上一步的输出：

```
Step 1 (配置) → Step 2 (探测) → Step 3 (分析) → Step 4 (规划) → Step 5 (生成) → Step 6 (验证) → Step 7 (交付)
```

**管线断裂点分析**：

| 断裂场景 | 发生位置 | 后果 |
|:---|:---|:---|
| tokens.json 不存在 | Step 1 | 管线无法启动 |
| SonarQube API 不可达 | Step 2 | 无法确定未覆盖行 |
| 源文件中无公共可测方法 | Step 3 | 只能覆盖私有方法，可能饱和 |
| 已有测试文件损坏 | Step 4 | 追加测试可能冲突 |
| 生成的测试编译失败 | Step 5 → 6 | 本地验证不通过 |
| mvn 配置不正确 | Step 6 | 无法本地运行 |
| CI 未触发 Sonar 扫描 | Step 7 | 无法验证最终覆盖率 |

### 3.3 Observer Pattern（观察者模式 — 门禁监控）

SonarQube 的 Quality Gate 是整个流程的触发器和终态判断器：

```
cr-engineer (观察者)
    │
    │ 轮询 SonarQube Quality Gate 状态
    │
    ├─ Gate PASS → 无需操作
    │
    └─ Gate FAIL (new_line_coverage < 60%)
            │
            └─ 委托 sonar-coverage-booster
                        │
                        └─ 修复 → 重新触发 Sonar 扫描
                                    │
                                    └─ cr-engineer 再次观察 Gate 状态
```

这是一个**闭环控制系统**：观察者检测偏差 → 执行者修正偏差 → 观察者验证修正结果。

### 3.4 Template Method Pattern（模板方法模式 — 测试代码生成）

测试类结构是固定的模板：

```
@ExtendWith(MockitoExtension.class)          ← 固定：不使用 Spring 容器
class XxxTest {                               ← 固定：类名 = 源类名 + Test
    @InjectMocks private Xxx service;         ← 可变：按依赖注入填充
    @Mock private Dependency1 dep1;           ← 可变：按依赖注入填充
    @Mock private Dependency2 dep2;

    @Test @DisplayName("...")                 ← 固定：JUnit5 结构
    void methodName_scenario() {              ← 固定：命名约定
        // Arrange                          ← 固定：AAA 三段式
        // Act
        // Assert
    }
}
```

模板中的**可变部分**由 Step 3 的代码分析结果填充：依赖注入字段决定了 `@Mock` 的数量和类型，分支条件决定了测试方法的数量。

### 3.5 Adapter Pattern（适配器模式 — tokens.json 发现）

tokens.json 的自动探测本质上是适配器模式：同一个配置接口，对应多个实现（不同工具安装路径）。优先级机制确保即使多个路径都有 tokens.json，也只加载优先级最高的那个。

```
                    配置加载
                       │
            ┌──────────┼──────────┐
            │          │          │
      ~/.claude    ~/.agents    $(pwd)
   (优先级1)     (优先级2)    (优先级3)
```

---

## 四、关键设计决策

### 决策 1：为什么选择 JUnit5 + Mockito 而不是 TestNG 或 @SpringBootTest？

**选择 JUnit5**：
- intl-retail 项目的标准测试框架，所有已有测试都用 JUnit5，保持一致
- `@DisplayName` 注解提供可读的测试名称
- `@ExtendWith` 扩展机制更灵活

**选择 Mockito 而非 SpringBootTest**：
- `@SpringBootTest` 会启动完整 Spring 容器，单个测试类启动时间 5-15 秒
- `@ExtendWith(MockitoExtension.class)` 不启动容器，单个测试类运行时间 < 1 秒
- 覆盖率补全的核心目标是"让代码行被执行到"，不需要验证 Spring 集成行为
- 启动容器还需要数据库、Redis、消息队列等基础设施，在本地开发环境可能不可用

**代价**：无法测试 Spring AOP（如 `@Transactional`）、Bean 自动装配、Configuration Properties 绑定。这些场景需要手动构造测试数据。

### 决策 2：为什么迭代修复而不是一次性生成所有测试？

| 因素 | 分析 |
|:---|:---|
| **不确定性** | 未覆盖行的具体位置在执行路径中，只有 SonarQube 的精确行号报告才是权威来源 |
| **反馈价值** | 第一轮生成的测试可能"形式上覆盖了行但实际未执行到"，SonarQube 反馈可以纠正 |
| **边际收益** | 前 80% 的未覆盖行通常集中在 20% 的方法中；一轮覆盖主路径，二轮覆盖分支，三轮覆盖边界 |
| **CI 成本** | 虽然迭代会增加 CI 次数，但每轮的测试量更小，编译和测试更快 |

### 决策 3：为什么与 cr-engineer 紧密耦合而不是独立运行？

cr-engineer 已经承担了"PR 质量门禁监控"的角色，检测到覆盖率不足后直接委托给 sonar-coverage-booster 是最自然的职责划分：

```
cr-engineer 的职责: "监控 + 调度"
    ├─ 检测 Quality Gate 状态
    ├─ 判断阻塞原因（覆盖率 / 代码重复 / 安全漏洞 / ...）
    └─ 针对原因分派到对应的修复 Skill

sonar-coverage-booster 的职责: "修复"
    └─ 专注于覆盖率补全的执行
```

如果 sonar-coverage-booster 独立运行，用户需要手动告知 "PR #123 覆盖率不足"，这增加了交互成本。紧密耦合避免了用户的中间参与。

### 决策 4：为什么测试提交到同一个 PR 分支而不是独立分支？

```
同一个分支:  feature/xxx  ←── 业务代码 + 测试代码（SonarQube 扫描两者）
独立分支:    feature/xxx  ←── 业务代码
            test/xxx      ←── 测试代码（SonarQube 只扫描 feature/xxx）
```

SonarQube 的 PR 扫描是对 PR 分支的完整扫描。如果测试代码在独立分支，SonarQube 不会将其纳入覆盖率计算。只有测试代码和业务代码在同一个分支，PR 扫描才能正确反映"新增代码被测试覆盖"的事实。

---

## 五、设计权衡与局限性

### 5.1 生成测试质量 vs 人工测试质量

AI 生成的测试以"行覆盖"为目标，可能产生以下问题：

| 问题 | 表现 | 缓解措施 |
|:---|:---|:---|
| 断言弱 | `assertNotNull(result)` 代替有意义的业务断言 | SKILL 模板要求 AAA 模式，隐含了断言设计的要求 |
| 边界遗漏 | 未覆盖 null 输入、空集合、负数等边界 | 典型测试场景模式内置了边界用例（如 JSON 序列化的空列表） |
| 无业务意义 | 测试通过了但并未验证任何有价值的业务规则 | 依赖 Step 3 的代码理解 + 人类 review（cr-engineer 的后续检查） |
| Mock 过度 | 所有依赖都 mock，无法发现集成问题 | 这是设计取舍 — 行覆盖优先于集成验证 |

### 5.2 覆盖率指标博弈

覆盖率指标本身可以被"游戏化"：

- **伪覆盖**：测试执行了代码行但未做有意义的断言（`assertTrue(true)` 也能让行变绿）
- **覆盖≠正确**：代码可能有 bug，但测试也可能有对应的 bug，两者"负负得正"
- **遗留代码免疫**：只有 `new_lines_to_cover` 被关注，历史遗留的未覆盖代码不受影响

这是门禁制度（覆盖率阈值）和实际收益（测试质量）之间的根本性矛盾。SKILL 通过"典型场景模式"内置了有质量的测试模板来部分缓解，但无法从根本上解决。

### 5.3 SonarQube API 依赖性

| 风险 | 影响 | 严重程度 |
|:---|:---|:---|
| API 端点升级/废弃 | 查询失败，管线在 Step 2 断裂 | 高 — 需及时更新 |
| 响应格式变更 | 字段解析错误，数据映射失败 | 中 — 可通过 Python 解析适配 |
| SonarQube 服务不可用 | 整个流程无法执行 | 高 — 等待恢复，无降级方案 |
| token 过期 | 认证失败 | 中 — 需人工更新 tokens.json |
| PR scan 未完成（SonarQube 还在分析中） | 查询到不完整或旧数据 | 中 — 需增加状态检查 |

### 5.4 迭代的 CI 时间成本

每次迭代都需要一次完整的 CI 流水线 + SonarQube 扫描：
- 典型 CI 时间：5-15 分钟
- 典型 SonarQube 扫描：2-5 分钟
- 3 轮迭代总时间：约 21-60 分钟

对比一次性生成后单次 CI（5-20 分钟），迭代方式增加了 3-4 倍的时间成本。

### 5.5 适用范围局限

- **仅 Java/Spring Boot**：测试模板硬编码了 `@ExtendWith(MockitoExtension.class)` 和 `@InjectMocks`
- **仅 JUnit5**：不支持 JUnit4、TestNG 等其他框架
- **仅 intl-retail 规范**：MyBatis Plus 禁令、settings.xml 路径等是项目特有的
- **仅增量覆盖率**：只关注 `new_line_coverage`，不处理整体覆盖率（`line_coverage`）

---

## 六、优秀设计亮点

### 亮点 1：tokens.json 多路径自动探测

不依赖环境变量，不依赖特定工具，不硬编码路径。3 个候选路径覆盖了常见的 AI 工具安装位置，优先级机制让多工具共存时不会冲突。

### 亮点 2：空提交触发器

`git commit --allow-empty` 是解决"推送测试文件不触发 CI"的优雅方案。不修改任何文件内容，不引入合并冲突风险，仅通过创建新 commit 触发流水线。

### 亮点 3：内置领域测试模式

SKILL 不是纯通用框架，而是内置了 intl-retail 考勤规则扩展的四类测试模式（幂等变更、重叠判断、JSON 序列化、锁键格式）。这些模式来自真实 PR 的经验积累，显著提高了生成测试的业务相关性。

### 亮点 4：lenient() 的防御式设计

`UnnecessaryStubbingException` 是 Mockito 严格模式下的常见陷阱。SKILL 将其作为硬性规范写入模板，在代码生成阶段就预防了运行时异常。

### 亮点 5：管道式输出清单

任务完成的 5 条标准（覆盖率达标、本地通过、已推送、before/after 报告、场景一致性分析）构成了交付验收清单，确保不会出现"推送了测试但覆盖率实际未变化"的漏报。

---

## 七、公司依赖分析 + 通用化方案

### 7.1 依赖清单

| 依赖 | 类型 | 用途 | 通用化难度 |
|:---|:---|:---|:---|
| SonarQube REST API | 外部服务 | 覆盖率数据源 | ⭐ (标准 API，替换 SonarQube 实例即可) |
| `tokens.json` | 配置文件 | 认证信息 | ⭐ (纯配置，格式通用) |
| `gitlab-mcp` | MCP 工具 | 获取 MR 信息 | ⭐⭐ (可替换为 Github CLI / Bitbucket API) |
| `mvn` + `settings.xml` | 构建工具 | 本地测试运行 | ⭐⭐ (需替换为对应语言的构建工具) |
| JUnit5 + Mockito | 测试框架 | 测试生成目标 | ⭐⭐⭐ (框架替换影响模板) |
| intl-retail 项目路径 | 硬编码 | 模块名称、包结构 | ⭐ (配置化即可) |

### 7.2 抽象接口设计

```typescript
// 1. 覆盖率数据源抽象
interface ICoverageDataSource {
  getCoverageMetrics(projectKey: string, prKey: string): Promise<CoverageMetrics>;
  getUncoveredFiles(projectKey: string, prKey: string): Promise<UncoveredFile[]>;
  pollUntilUpdated(projectKey: string, prKey: string, timeout: number): Promise<CoverageMetrics>;
}

// 2. 测试框架适配器
interface ITestFramework {
  generateTestClass(className: string, methods: TestableMethod[]): string;
  generateTestMethod(method: TestableMethod, branchIndex: number): string;
  validateCompile(testFile: string): Promise<ValidationResult>;
  runTest(testClass: string): Promise<TestResult>;
}

// 3. VCS 适配器（版本控制系统）
interface IVersionControl {
  getPRInfo(): Promise<PRInfo>;
  commitAndPush(files: string[], message: string): Promise<void>;
  triggerCI(): Promise<void>;
}
```

### 7.3 通用化配置结构

```yaml
# sonar-coverage-booster.yaml
coverage:
  provider: sonarqube          # sonarqube | codecov | coveralls
  threshold: 60                # 目标覆盖率百分比
  max_iterations: 3            # 最大迭代次数

source:
  project_key: "my-project"
  test_framework: junit5       # junit5 | junit4 | testng | pytest
  mock_framework: mockito      # mockito | easymock | powermock | unittest.mock

vcs:
  provider: gitlab             # gitlab | github | bitbucket
  pr_source: mcp               # mcp | cli | api

build:
  tool: mvn                    # mvn | gradle | npm | pip
  test_command: "mvn test -pl {module} -Dtest={class}"

connection:
  sonarqube_url: "https://sonarqube.example.com"
  sonarqube_token: "${SONAR_TOKEN}"  # 从环境变量读取
```

---

## 八、量化质量指标

| 维度 | 指标 | 测量方法 | 目标 |
|:---|:---|:---|:---|
| **有效性** | 覆盖率达标率 | 执行后 new_line_coverage ≥ 60% 的比例 | ≥ 90% |
| **效率** | 平均迭代轮数 | 统计从开始到达标的轮数 | ≤ 2 |
| **可靠性** | 测试编译成功率 | 生成的测试无语法/编译错误的比例 | ≥ 95% |
| **安全性** | 无 token 泄露 | tokens.json 内容是否进入 LLM 上下文 | 0 次 |
| **可迁移性** | 硬编码数量 | intl-retail 特有配置的数量 | 0 |
| **完整性** | 输出清单完成率 | 5 条任务完成标准全部满足 | 100% |

---

## 九、复刻要点 Checklist

- [ ] 理解 7 步管线的每步职责与输入/输出
- [ ] 理解 tokens.json 的自动探测机制与优先级
- [ ] 理解 SonarQube API 集成的 3 个端点和认证方式
- [ ] 理解迭代修复循环的终止条件（成功/饱和/最大迭代）
- [ ] 理解 JUnit5 + Mockito 模板的设计意图（`@ExtendWith`、AAA 模式、`lenient()`）
- [ ] 理解为什么测试提交到同一个 PR 分支
- [ ] 理解 4 类典型测试场景模式
- [ ] 理解空提交触发器的使用场景
- [ ] 能设计 `ICoverageDataSource` / `ITestFramework` / `IVersionControl` 抽象接口
- [ ] 能设计通用化配置文件结构
- [ ] 能评估生成测试的质量风险并设计缓解措施
- [ ] 理解 cr-engineer → sonar-coverage-booster 的委托关系
