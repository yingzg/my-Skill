# code-trace-analyzer — 深度学习文档

> 对应 SKILL.md: `/root/.opencode/skills/code-trace-analyzer/SKILL.md` (227行)
>
> 原实现仓库: `/mnt/d/测试项目/vibe-hubs/skills/code-trace-analyzer/`

---

## 一、功能全景

### 一句话定位
**静态代码调用链分析器** — 从用户输入的 Java 包路径或方法名出发，逐层追踪代码调用链，输出结构化文档（Mermaid 流程图 + SQL 提取 + 校验点 + JSON 示例）。

### 核心流程

```
输入：Java 包路径 / 方法全限定名
    ↓
Phase 1: 代码扫描 — 定位入口类/方法
    ↓
Phase 2: 逐层追踪调用链
    ├─ 本类内部调用
    ├─ 跨类调用（依赖注入 Bean）
    ├─ Dubbo/HTTP 外部调用
    └─ MyBatis Mapper SQL 调用
    ↓
Phase 3: 信息提取
    ├─ 业务含义描述
    ├─ 入参/出参 JSON 示例
    ├─ 核心 SQL 语句
    ├─ 异常分支 & 校验点
    └─ Mermaid 流程图
    ↓
Phase 4: 输出 — 生成飞书文档（通过 feishu MCP）
```

---

## 二、架构设计分析

### 2.1 文件架构

```
code-trace-analyzer/
└── SKILL.md          # 227行，单文件 Skill
```

**设计特点**：相比 ticket-troubleshoot-v3 的多文件架构，code-trace-analyzer 是单文件 Skill。这不代表简单 — 单文件意味着所有逻辑必须在一个文件内自洽，对组织能力要求更高。

### 2.2 分层追踪策略

```
Layer 0: Controller/Task/Listener（入口层）
    ↓
Layer 1: Service 层（业务逻辑）
    ├── 本类方法调用
    ├── 注入 Bean 调用
    ├── Dubbo Reference 调用 ——→ 外部服务
    └── Mapper 调用 ——→ 数据库
    ↓
Layer 2: 外部服务实现（如果可访问）
    ↓
Layer 3: Mapper XML — SQL 提取
```

**关键设计**：
- **追踪深度有边界** — 外部 Dubbo 调用标记为"外部"，不继续追踪（除非同仓库可访问）
- **SQL 提取是终点** — 遇到 MyBatis Mapper → 找 XML → 提取 SQL，这是调用链的自然终点
- **循环调用检测** — 隐式要求（追踪到已访问过的类时停止）

### 2.3 输出的结构化程度

一次完整的分析输出包含：

```
1. 业务含义（≤50 字一句话总结）
2. 接口路径和请求方式（HTTP method + URL）
3. 入参 JSON 示例（含字段注释 + 校验规则）
4. 出参 JSON 示例（含字段注释 + 业务含义）
5. 核心 SQL（格式化后的 SQL，标注来自哪个 Mapper XML:行号）
6. 外部调用（Dubbo 接口名 + 用途）
7. 校验点列表（必填校验 + 业务校验 + 数据库校验）
8. 异常分支说明（可能抛出的异常 + 触发条件）
9. Mermaid flowchart（可视化调用链）
```

---

## 三、设计模式深度分析

### 3.1 静态代码分析的"手动 AST"

与其他 Skill 不同，code-trace-analyzer 不使用 AST-grep 等自动化工具，而是让 AI 手动进行"逐层阅读"：

```
1. 读 Controller 代码     → 找到入口方法
2. 追踪方法调用            → 找到 Service 方法
3. 读 Service 代码         → 找到下一个调用
4. 追踪到 Mapper 接口      → 找到 Mapper XML
5. 读 Mapper XML           → 提取 SQL
6. 追踪到 Dubbo Reference  → 标记为外部调用，停止
```

**为什么不用 AST-grep**？

- AST-grep 能自动化查找方法调用关系，但无法理解**业务语义**
- "逐层阅读" 虽然慢，但每一步都有业务理解，能产出有语义的文档
- 这是一个"质量 > 效率"的权衡

### 3.2 证据链设计

每个输出结论都必须附带证据：

```
结论: "订单创建时需要校验库存"
  证据: InventoryService.java:42 → checkStock(skuId, quantity)
       → InventoryMapper.xml:18 → SELECT stock FROM t_inventory WHERE sku_id = ?
```

这不是代码的"罗列"，而是**可追溯的证据链**。下游读者可以逐行验证每个结论。

### 3.3 JSON 示例的双重作用

入参/出参 JSON 示例不是简单的数据展示，它承载两层角色：

1. **文档角色** — 让读者快速理解接口的输入输出
2. **验证角色** — JSON 示例必须与代码中的校验逻辑一致（如 `@NotNull` 对应 JSON 中该字段必填）

这种双重作用是静态分析 Skill 的特有设计，是 ticket-troubleshoot 和 trace-doctor 不需要的。

### 3.4 校验点提取

```
代码中:
  @NotNull(message = "订单ID不能为空")
  private Long orderId;

  @Min(value = 1, message = "数量必须大于0")
  private Integer quantity;

输出校验点:
  ✅ orderId: 必填 (来源: OrderRequest.java:15, @NotNull)
  ✅ quantity: 必须 > 0 (来源: OrderRequest.java:18, @Min)
  ⚠️ status: 无 @NotNull 但 SQL WHERE 条件要求 (来源: OrderMapper.xml:12)
```

**注意 "⚠️" 类校验点** — 这是静态分析的"隐患检测"能力：代码没写校验但 SQL 需要，这种不一致应该暴露。

---

## 四、优秀设计亮点

### ⭐ 亮点 1：Mermaid 可视化输出的默认集成

不是"建议生成流程图"，而是**默认必须输出 Mermaid flowchart**。这是对文档读者体验的深度理解：

```
graph TD
    A[OrderController.create] --> B[OrderService.createOrder]
    B --> C[InventoryService.checkStock]
    B --> D[OrderMapper.insert]
    C --> E[Dubbo:ProductService.getSku]
    D --> F[(MySQL: t_order)]
```

**为什么 Mermaid 优于文字描述**：调用链的文字描述（"A 调用 B，然后 B 调用 C..."）对复杂的树形调用链几乎不可读，而 Mermaid 一次渲染即可展示全貌。

### ⭐ 亮点 2：SQL 来源标注（文件:行号）

```
核心 SQL 1:
  SELECT stock, reserved_stock
  FROM t_inventory
  WHERE sku_id = #{skuId}
  （来源: InventoryMapper.xml:18-22）

核心 SQL 2:
  INSERT INTO t_order (...) VALUES (...)
  （来源: OrderMapper.xml:42-50）
```

这种标注让读者（或另一个 AI Agent）可以立即定位到原始代码，无需再次搜索。

### ⭐ 亮点 3：异常分支显式化

代码分析不止看"正常路径"：

```
正常路径: 参数校验通过 → 库存充足 → 创建订单 → 扣减库存
异常路径:
  ❌ 参数校验失败 → throw ParameterException（OrderRequest.validate():35）
  ❌ 库存不足 → throw InsufficientStockException（InventoryService:50）
  ❌ 数据库插入失败 → throw DataAccessException（OrderMapper.insert:45）
```

这体现了"非功能路径分析"的能力，比单纯的调用链追踪更有价值。

---### ⭐ 亮点 4：外部调用边界意识

遇到 Dubbo 调用时，不继续追踪，而是：
```
外部调用: Dubbo:ProductService#getSku(Long skuId)
  用途: 查询商品详情（名称、价格）
  服务: product-service
  备注: 同仓库不可访问，标记为外部
```
这种"知止"的设计避免了无意义的深层追踪。

### ⭐ 亮点 5：信息提取的优先级排序

先提取核心信息（业务含义 → SQL → 校验点），再补充细节（异常分支 → Mermaid 图）。这确保了即使分析被打断，最重要的信息已经产出。

---

## 五、公司依赖分析 + 通用化方案

### 5.1 依赖清单

| 依赖 | 类型 | 用途 | 通用化难度 |
|------|------|------|-----------|
| `feishu2md` MCP | MCP 工具 | 发布到飞书文档 | ⭐⭐⭐ (需替换) |
| Java 包路径格式 | 输入约定 | 定位代码文件 | ⭐ (多语言通用) |
| MyBatis-Plus XML | 框架约定 | SQL 提取 | ⭐⭐ (框架适配) |
| Dubbo @Reference | 框架约定 | 外部调用识别 | ⭐⭐ (框架适配) |
| Spring @Service/@Controller | 框架约定 | 层级识别 | ⭐⭐ (框架适配) |

### 5.2 抽象接口设计

核心思路：将"代码分析流程"与"输出发布"解耦。

```typescript
// 输出发布抽象 — 适配飞书 / Notion / Confluence / Markdown
interface IDocPublisher {
  publish(content: AnalysisResult): Promise<string>;  // 返回文档URL
  update(docId: string, content: AnalysisResult): Promise<void>;
}

// 飞书适配器
class FeishuPublisher implements IDocPublisher {
  async publish(content: AnalysisResult): Promise<string> {
    const docUrl = await feishu.createDoc({ title: content.title, content: content.markdown });
    return docUrl;
  }
}

// Markdown 文件适配器（通用后备）
class MarkdownPublisher implements IDocPublisher {
  async publish(content: AnalysisResult): Promise<string> {
    const path = `/output/${content.title}.md`;
    await fs.writeFile(path, content.markdown);
    return path;
  }
}
```

### 5.3 多语言/多框架适配

当前技能深度依赖 Java + Spring + MyBatis + Dubbo 的技术栈：

```yaml
# 框架检测配置
frameworks:
  java_spring:
    entry_patterns: ["@RestController", "@Controller", "@KafkaListener", "@Scheduled"]
    injection_patterns: ["@Autowired", "@Resource", "private.*Service"]
    external_call_patterns: ["@DubboReference", "@FeignClient"]
    sql_extraction: "Mapper.xml"
  
  python_django:
    entry_patterns: ["class.*ViewSet", "class.*APIView"]
    injection_patterns: ["self\\..*service"]
    external_call_patterns: ["requests\\."]
    sql_extraction: "models.py + raw SQL"
  
  go_gin:
    entry_patterns: ["func.*gin\\.Context"]
    injection_patterns: ["type.*Service struct"]
    external_call_patterns: ["http\\.Client"]
    sql_extraction: "GORM tag + query builder"
```

**设计原则**：框架适配器定义了"在这个框架下，什么算入口、什么算外部调用"。分析流程不变，适配器改变搜索模式。

---

## 六、可改进点

### 6.1 ⚠️ 手动追踪效率低

AI 逐层阅读代码在大型项目（>500 类）中效率极低。改进：
- 先用 `ast_grep_search` 自动构建调用图
- AI 只看调用图中需要"业务解读"的关键节点
- 这是"ast-grep 做结构 → AI 做语义"的分工

### 6.2 ⚠️ 只追踪 Java 调用，忽略了中间件链路

`a.someMethod() → MQ.send() → b.handleMessage()` 这种异步链路被忽略了。
改进：识别 Kafka/RocketMQ Topic 的 publish/consume 对，产出异步调用子图。

### 6.3 ⚠️ 缺少增量分析

每次都是全量分析，即使只改了一个方法。改进：
- 支持 diff-based 分析（只分析变更方法的上下游 2 层影响范围）
- 标注"本次影响: 新增校验点" / "本次影响: SQL 变更"

### 6.4 ⚠️ 校验点提取不够系统化

校验点的识别依赖于 AI 对注解和 SQL 的阅读理解，缺乏确定性规则。改进：
- Bean Validation 注解 → 自动提取，不对 AI 理解做依赖
- SQL WHERE 条件的 NOT NULL 列 → 自动与入参 Bean 比对

### 6.5 ⚠️ 单 Skill 文件缺乏模块化

227 行的单文件 Skill 已经接近可维护性边界。如果新增框架支持，SKILL.md 会迅速膨胀。改进：
- 参考 ticket-troubleshoot-v3 的多文件架构
- 核心分析流程放在 SKILL.md，框架适配规则放在 `references/frameworks/` 下

---

## 七、量化质量指标

| 维度 | 指标 | 测量方法 | 当前基准 | 目标 |
|------|------|---------|---------|------|
| **完整性** | 调用链覆盖率（实际覆盖/应覆盖的调用） | 对照代码手动验证 | — | ≥90% |
| **准确性** | SQL 提取准确率 | 逐个 SQL 与源码对照 | — | ≥95% |
| **准确性** | 校验点遗漏率 | 已知校验点总集 vs 检出集 | — | ≤10% |
| **可追溯性** | 有证据的行数 / 总输出行数 | 统计 `来源:` 标注 | — | ≥50% |
| **可用性** | 输出的 Mermaid 图可直接渲染 | 粘贴到 Mermaid Live | — | 100% |
| **效率** | 平均分析时间（中等复杂度接口） | 计时 | — | ≤5min |
| **可迁移性** | 支持的语言/框架数 | 统计框架配置文件 | 1 | ≥3 |

---

## 八、复刻要点 Checklist

- [ ] 理解 4 阶段分析流程（扫描 → 追踪 → 提取 → 输出）
- [ ] 理解"逐层手动阅读" 与 AST-grep 的取舍
- [ ] 理解证据链设计：每个结论必须带 `来源: 文件:行号`
- [ ] 理解 Mermaid flowchart 的默认输出要求
- [ ] 理解"知止"原则：外部调用不追踪
- [ ] 理解 JSON 示例的双重作用（文档 + 验证）
- [ ] 能设计 IDocPublisher 抽象接口
- [ ] 能设计多框架适配器（至少 Java + 一种其他语言）
- [ ] 能识别"⚠️ 类校验点"（代码 vs SQL 不一致）
- [ ] 能编写达到 227 行规模的可维护单文件 Skill
