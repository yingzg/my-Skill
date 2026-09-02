# hera-slow-api-analyzer — 深度学习文档

> 对应 SKILL.md: `/root/.opencode/skills/hera-slow-api-analyzer/SKILL.md` (510行)
>
> 原实现仓库: `/mnt/d/测试项目/vibe-hubs/hera-slow-api-analyzer/`

---

## 一、功能全景

### 一句话定位
**慢接口全栈诊断器** — 浏览器自动化（Playwright）获取 Hera 可观测数据 + 本地源码分析，定位性能根因，生成 Markdown 诊断报告。

### 核心流程

```
Phase 1: 浏览器自动化（Hera 平台）
  Step 1: 登录 Hera → 导航到慢接口页面
  Step 2: 截取 Top N 慢接口列表（时段 + 排序）
  Step 3: 进入接口详情页 → 获取分布式链路追踪（Trace）
  Step 4: 获取关联日志（Logs）
  Step 5: 导出 Trace/Log 原始数据

        ↓ 数据交接点 ↓

Phase 2: 本地源码分析
  Step 6: 根据 Trace 中的类名/方法名 → 定位本地源码
  Step 7: 逐层分析代码（同 code-trace-analyzer 的追踪策略）
  Step 8: 提取关键 SQL → 分析慢 SQL 特征
  Step 9: 综合根因推断 + 优化方案

        ↓

Phase 3: 输出 — Markdown 诊断报告
  ├─ 症状摘要（慢接口名称、P99 耗时、时段）
  ├─ Trace 证据（关键 Span 耗时 + 调用关系）
  ├─ 源码分析（调用链 + SQL + 潜在问题点）
  ├─ 根因推断（具体哪段代码/哪个 SQL 导致慢）
  └─ 优化方案（短期/中长期，优先级排序，工时估算）
```

---

## 二、架构设计分析

### 2.1 文件架构

```
hera-slow-api-analyzer/
├── SKILL.md              # 510行：全流程定义
├── API_REFERENCE.md       # Hera API 参考文档
├── feishu-report-template.md  # 飞书报告模板
└── tables.md              # Hera 数据表字段说明
```

### 2.2 两阶段分离设计（核心架构决策）

```
┌──────────────────┐      ┌──────────────────┐
│  Phase 1         │      │  Phase 2          │
│  浏览器自动化     │      │  本地源码分析      │
│                  │      │                  │
│  数据源: Hera    │ ──→  │  数据源: Git Repo │
│  工具: Playwright│      │  工具: Grep/Read  │
│  产出: Trace+Log │      │  产出: 根因报告    │
└──────────────────┘      └──────────────────┘
```

**为什么分两阶段**：

1. **环境隔离** — Phase 1 需要网络访问 + 登录态（Playwright storage-state），Phase 2 只需要本地文件系统
2. **可替换性** — Phase 1 是整个 Skill 中公司依赖最重的部分。如果将来 Hera 提供 API（API_REFERENCE.md 已记录），Phase 1 可以替换为 API 调用而 Phase 2 不变
3. **失败隔离** — Phase 1 失败了（网络问题、登录过期），不影响已有 Trace 数据的 Phase 2 分析
4. **复用边界** — Phase 1 的数据可以给多个 Skill 使用（如 ticket-troubleshoot-v3 可能也需要 Trace 数据）

### 2.3 数据交接点（Phase Boundary Contract）

```
Phase 1 产出 → Phase 2 输入:

{
  "api_name": "/api/order/list",          # 慢接口路径
  "time_range": "2026-07-01 10:00-11:00", # 统计时段
  "p99_latency": 5230,                    # P99 耗时 (ms)
  "avg_latency": 1800,                    # 平均耗时
  "qps": 120,                             # QPS
  "trace_id": "abc123def456",            # 代表性 Trace ID
  "trace_data": {                         # Trace 详情
    "spans": [...],
    "errors": [...]
  },
  "logs": [                               # 关联日志
    {"level": "ERROR", "message": "...", "timestamp": "..."}
  ]
}
```

**这个数据契约的精心设计**：
- 接口名、时段、延迟等是 Phase 2 的**上下文元数据**，不加这些 Phase 2 就是盲分析
- `trace_id` 允许 Phase 2 如果本地也有 Hera CLI 访问，可以重新获取更详细的 Trace
- `spans` 必须有耗时和调用关系，Phase 2 用这些定位具体方法

---

## 三、设计模式深度分析

### 3.1 Browser Automation 模式

```
// Playwright 自动化脚本的核心逻辑 (伪代码)
async function collectSlowAPIs(url: string, timeRange: string) {
  // 1. 确保登录态
  await ensureLoggedIn();   // ← 复用 dayu-cas-login Skill

  // 2. 导航 + 等待数据加载
  await page.goto(url);
  await page.waitForSelector('.slow-api-table tbody tr');

  // 3. 结构化提取
  const apis = await page.evaluate(() => {
    return Array.from(document.querySelectorAll('tr')).map(row => ({
      name: row.querySelector('.api-name').textContent,
      p99: parseFloat(row.querySelector('.p99').textContent),
      qps: parseInt(row.querySelector('.qps').textContent)
    }));
  });

  // 4. 进入详情页 → 获取 Trace
  await page.click(`tr:has-text("${targetAPI}")`);
  await page.waitForSelector('.trace-detail');

  // 5. 提取 Trace + Logs 原始数据
  const traceData = await page.evaluate(() => { /* ... */ });
  const logs = await page.evaluate(() => { /* ... */ });

  return { apis, traceData, logs };
}
```

**关键设计**：
- **登录态复用** — 通过 `dayu-cas-login` Skill 管理 Playwright storage-state，避免每次都要扫码登录
- **数据提取在浏览器 JS Context** — 用 `page.evaluate()` 在浏览器里直接提取 DOM 数据，比截屏后 OCR 高效 100 倍
- **结构化输出** — 不截屏、不 OCR、不依赖视觉识别，直接构造 JSON

### 3.2 API_REFERENCE.md — API 优先架构的萌芽

`API_REFERENCE.md` 的存在意味着：这个 Skill 的设计者有意识地**准备用 API 替换浏览器自动化**。这当前看着像"文档"，但实际上是**API 迁移计划书**： 

```
当前: Playwright → DOM 解析 → Trace 数据
目标: Hera API    → JSON 解析 → Trace 数据
```

这种"双通道设计"让 Skill 具备了渐进迁移能力。

### 3.3 根因定位的层次递进

```
1. Trace 层:  哪个 Span 最慢？延迟分布如何？
    ↓
2. Code 层:   这个 Span 对应哪个方法？代码逻辑是什么？
    ↓
3. SQL 层:    这个方法的 SQL 是什么？执行计划合理吗？
    ↓
4. 数据层:    表有多大？有索引吗？索引被用上了吗？
    ↓
5. 根因结论:  连续的因果链：表示太大 → 全表扫描 → 方法耗时增加 → 接口变慢
```

这个递进逻辑是从"现象 → 底层"的逐层深入，而不是跳层推测。每一步都为下一步提供证据。

### 3.4 优化方案的"可执行性"设计

```
❌ 不好的优化方案: "优化 SQL 性能"
✅ 好的优化方案:
  - 短期（1天内）: 为 t_order 表添加 (user_id, status) 联合索引
    (来源: OrderMapper.xml:18 的 WHERE user_id=? AND status=?)
  - 中期（1周内）: 将 getSku 调用改为批量接口，减少 N+1
    (来源: InventoryService.java:42 在循环内调用 Dubbo)
  - 长期（1月内）: 引入 Redis 缓存热门商品详情，TTL 5 分钟
```

每个优化方案都有：
- **时间窗**: 短期/中期/长期
- **具体动作**: 不是"优化"，而是"添加 X 索引" / "改为批量接口"
- **证据来源**: 每个方案都引用到具体的代码行
- **优先级**: 隐含在时间窗中

---

## 四、优秀设计亮点

### ⭐ 亮点 1：数据交接点的显式定义

Phase 1 → Phase 2 的数据 format 被设计为显式的中转契约。这是整个 Skill 最重要的架构决策：
- 替代：未来可以直接用 API 替换 Phase 1，Phase 2 代码不需要任何修改
- 测试：可以 Mock Phase 1 的输出，独立测试 Phase 2
- 复用：Phase 1 的数据可以被多个 Skill 消费（分析一次 → ticket-troubleshoot + code-trace 都可用）

### ⭐ 亮点 2：API_REFERENCE.md 的前瞻性

在一个当前还是浏览器自动化的 Skill 中，主动准备 API 参考文档，体现了"为可替换性设计"的思维。不是等需要替换时才去研究 Hera API，而是提前记录，降低未来切换成本。

### ⭐ 亮点 3：登录态管理独立化

不把登录逻辑嵌入 main flow，而是委托 `dayu-cas-login` Skill。这带来两个好处：
1. 登录逻辑可以独立维护和测试
2. 其他需要 Hera 登录的 Skill（如 trace-doctor）共享同一套登录态

### ⭐ 亮点 4：优化方案的"三段式"结构

短/中/长三期不是一个随意切分，而是体现了工程现实：
- 短期 = 不需要改代码的事（加索引、调配置、热修复）
- 中期 = 需要小规模改造的事（优化代码逻辑、批量化调用）
- 长期 = 需要架构变更的事（加缓存层、改表结构、服务拆分）

这种划分让技术决策者和项目经理都能各取所需。

### ⭐ 亮点 5：详细的 Table 字段说明（tables.md）

`tables.md` 记录了 Hera 数据表的字段含义。这种"外部系统数据字典"在技能库中很少见。它的价值：
- 新接手的人不需要去翻 Hera 文档
- 当 Hera 升级字段时，只需要更新 tables.md
- 可以作为"数据理解自检清单"：拿到了 Trace 数据，对照 tables.md 确认每个字段都理解了

---

## 五、公司依赖分析 + 通用化方案

### 5.1 依赖清单（四者中最重）

| 依赖 | 类型 | 用途 | 通用化难度 |
|------|------|------|-----------|
| Hera 可观测平台 | Web 应用 | 慢接口列表、Trace、日志 | ⭐⭐⭐⭐⭐ (最难) |
| Playwright MCP | MCP 工具 | 浏览器自动化 | ⭐⭐ (工具替换) |
| dayu-cas-login | Skill | 小米 CAS 登录 | ⭐⭐⭐⭐ (需替换) |
| `feishu2md` MCP | MCP 工具 | 发布诊断报告到飞书 | ⭐⭐⭐ (需替换) |
| `table.md` | 参考文档 | Hera 特定数据表字段 | ⭐⭐⭐⭐ (需替换) |
| Intl-Retail 项目 | 源码仓库 | 本地代码分析 | ⭐ (任何项目) |

### 5.2 抽象接口设计 — 最复杂的通用化

hera-slow-api-analyzer 的通用化有三层挑战：

#### 第一层：APM 平台抽象

```typescript
// APM 平台抽象 — 适配任何可观测平台
interface IAPMPlatform {
  // 获取慢接口列表
  getSlowAPIs(options: SlowAPIOptions): Promise<SlowAPI[]>;
  // 获取 Trace 详情
  getTraceDetail(traceId: string): Promise<TraceDetail>;
  // 获取关联日志
  getLogs(options: LogOptions): Promise<LogEntry[]>;
}

// 接口一: 浏览器自动化适配器（任意带 Web UI 的 APM 平台）
class WebUIBasedAPM implements IAPMPlatform {
  constructor(private page: Page, private config: WebUIPlatformConfig) {}

  async getSlowAPIs(options: SlowAPIOptions): Promise<SlowAPI[]> {
    await this.page.goto(this.config.slowAPIListUrl);
    await this.page.waitForSelector(this.config.selectors.tableRow);
    return await this.page.evaluate(this.config.extractSlowAPIsJS);
  }
  // ... getTraceDetail, getLogs 同理
}

// 接口二: API 适配器（Datadog 为例）
class DatadogAdapter implements IAPMPlatform {
  constructor(private config: DatadogConfig) {}

  async getSlowAPIs(options: SlowAPIOptions): Promise<SlowAPI[]> {
    const res = await fetch(`${this.config.apiBase}/v2/apm/traces`, {
      headers: { 'DD-API-KEY': this.config.apiKey }
    });
    return this.transformToStandardFormat(res.json());
  }
}

// 接口三: Jaeger 适配器
class JaegerAdapter implements IAPMPlatform { /* ... */ }
```

#### 第二层：平台配置的声明式描述

```yaml
# apm-platforms.yaml
platforms:
  hera:
    type: web-ui
    login: cas-auth  # 登录方式
    selectors:
      tableRow: ".slow-api-table tbody tr"
      apiName: ".api-name"
      p99: ".p99"
    extractJS: |  # 浏览器内的数据提取脚本
      () => Array.from(document.querySelectorAll('tr')).map(row => ({...}))
  
  datadog:
    type: api
    baseUrl: "https://api.datadoghq.com"
    auth: api-key
  
  jaeger:
    type: api
    baseUrl: "http://jaeger:16686/api"
    auth: none
```

#### 第三层：登录抽象

```typescript
interface IAuthenticator {
  ensureLogin(page: Page): Promise<void>;
}

class CASAuthenticator implements IAuthenticator { /* 小米 CAS */ }
class OIDCAuthenticator implements IAuthenticator { /* 通用 OIDC */ }
class APIKeyAuthenticator implements IAuthenticator { /* API Key 无需登录 */ }
```

### 5.3 三阶段迁移路径

```
阶段 1 (当前): 浏览器自动化 → 单平台
阶段 2 (近期): 浏览器自动化 + API 双通道 → 单平台
阶段 3 (远期): 纯 API → 多平台可切换
```

---

## 六、可改进点

### 6.1 ⚠️ 浏览器自动化不稳定

DOM 选择器是硬编码的，Hera 前端升级会导致 Phase 1 完全失败。改进：
- 使用 Playwright 的 `getByRole()` / `getByText()` 等语义选择器
- 添加选择器变化检测（`page.evaluate` 返回 null 时触发重试 + 通知）

### 6.2 ⚠️ Phase 1 和 Phase 2 之间缺少验证

Phase 1 提取的 `spans[].methodName` 与 Phase 2 读取的源码方法名之间只有字符串匹配，没有严格的符号解析。改进：
- 用 LSP `goto_definition` 验证方法存在
- 如果方法不存在，标注 `uncertain` 置信度降级

### 6.3 ⚠️ 缺少性能基线

当前只分析单个 Trace 的耗时，没有历史基线。改进：
- 收集同接口的历史 P50/P95/P99 数据
- 对比当前 Trace 与基线的偏差：是突增还是长期慢
- 突增 → 近期变更思路；长期慢 → 架构优化思路

### 6.4 ⚠️ 优化方案缺少量化预期

"添加 XX 索引后预计 P99 降为 Yms" — 没有这种量化。改进：
- 参考索引效果的通用估算（覆盖索引 vs 非覆盖索引）
- 标注"预估"而非"断言"，附预估依据

### 6.5 ⚠️ Golden Cases 和测试缺失

510 行的 SKILL.md 没有 Golden Case。改进：
- GC-1: 标准慢 SQL 场景（全表扫描）
- GC-2: N+1 问题场景（循环调用）
- GC-3: 网络超时场景（外部服务慢）
- GC-4: 登录失效场景（Phase 1 失败但 Phase 2 可用）

---

## 七、量化质量指标

| 维度 | 指标 | 测量方法 | 当前基准 | 目标 |
|------|------|---------|---------|------|
| **可靠性** | Phase 1 成功率（浏览器自动化） | 连续运行 10 次 | — | ≥80% |
| **准确性** | 根因定位准确率 | 人工标注 20 个案例 | — | ≥80% |
| **可操作性** | 优化方案中有代码级建议的比例 | 统计方案中"来源: 文件:行号"标注 | — | ≥70% |
| **时效性** | 完整分析耗时（从 Hera 到报告） | 计时 | — | ≤8min |
| **完整性** | 报告覆盖的指标项 | 对照报告模板 checklist | — | ≥90% |
| **可迁移性** | 平台硬编码（URL/选择器） | 全文档搜索 | ≥10 | ≤3 (配置化) |
| **测试覆盖** | Golden Cases 数量 | 统计 GC 文件 | 0 | ≥4 |

---

## 八、复刻要点 Checklist

- [ ] 理解两阶段分离的设计理由（环境隔离、可替换性、失败隔离、复用边界）
- [ ] 理解 Phase Boundary Contract 的字段设计和必要性
- [ ] 理解浏览器自动化的 Playwright 模式（登录复用 → DOM 提取 → 结构化输出）
- [ ] 理解 API_REFERENCE.md 的"API 迁移计划书"角色
- [ ] 理解根因定位的 5 层递进逻辑（Trace → Code → SQL → Data → Root Cause）
- [ ] 理解优化方案的"三段式 + 证据来源"设计
- [ ] 能设计 IAPMPlatform 抽象接口（Web UI 适配器 + API 适配器）
- [ ] 能设计 IAuthenticator 抽象接口（多种登录方式可插拔）
- [ ] 能设计平台配置的声明式 YAML 格式
- [ ] 能编写 3 个覆盖不同场景的 Golden Case
