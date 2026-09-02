# SKILL 设计模式深度学习 — 从 hera-slow-api-analyzer + dayu-cas-login 提取的可复用模式

> 学习日期：2026-07-15
>
> **修订日期：2026-07-15（v2 — 模式 3 重构）**
>
> 源技能：`hera-slow-api-analyzer`（510 行）、`dayu-cas-login-skill`（48 行 SKILL.md + 136 行 JS）
>
> 目标：提取去公司化的通用设计模式，用于从零构建独立 SKILL
>
> **v2 变更**：模式 3 从"DOM 提取技巧"重构为"浏览器 = API 发现引擎"——新增三层架构（API 发现 / HAR 回放 / DOM 兜底）、决策框架、DOM 不稳定性证据。模式 1、2 保持不变。

---

## 一、导论：为什么是这三个模式

在分析了 `hera-slow-api-analyzer` 和 `dayu-cas-login` 的源码后，可以提取出 **7 个可复用设计模式**。经过筛选，以下三个模式最具通用性和组合价值：

| 模式 | 解决的问题 | 来源技能 | 去公司化难度 |
|------|-----------|---------|------------|
| 模式 1：独立登录态管理 | "怎么进入需要认证的系统？" | `dayu-cas-login` | ⭐⭐（中等） |
| 模式 2：重试 + 优雅降级 | "数据不完整时怎么处理？" | `hera-slow-api-analyzer` | ⭐（容易） |
| 模式 3：浏览器 = API 发现引擎 | "怎么稳定地获取 Web 系统数据？" | 两者兼有 + 全网研究 | ⭐⭐⭐（需要思维转变） |

这三个模式是正交且可组合的：
- **模式 1** 解决"进门"问题（认证态供给）
- **模式 3** 解决"取数据"问题（API 发现优先，DOM 提取兜底）
- **模式 2** 解决"出错了怎么办"（多层降级容错）

> ⚠️ **重要纠正**：本文档初版将模式 3 定位为"DOM 提取技巧集"，这是根本性误读。正确理解是：**浏览器自动化的核心价值是 API 发现 + 网络拦截，DOM 提取仅作为最后手段**。详见第四章。

任何一个需要浏览器自动化 + 处理不稳定数据源的 SKILL，都可以通过组合这三个模式来构建骨架。

---

## 二、模式 1：独立登录态管理（Login-as-a-Service）

### 2.1 设计哲学：登录是依赖，不是功能

`dayu-cas-login` 全技能只有 **184 行代码**（48 行 SKILL.md + 136 行 JS），却能支撑 `hera-slow-api-analyzer`、`hera-trace-doctor` 等多个技能。核心哲学是：

> 登录技能不应该嵌入目标技能的业务逻辑中，而应该作为**可调用的依赖服务**存在。

```
❌ 错误：在每个技能中重复写登录逻辑
hera-slow-api-analyzer/SKILL.md:
  Step 1: 打开浏览器 → 检测 CAS → 截取二维码 → 等待扫码 → ...
  Step 2: 导航到慢接口页面...

✅ 正确：登录是独立服务，业务技能只关心"已登录"这个前置条件
hera-slow-api-analyzer/SKILL.md:
  Step 1: 调用 ensureAuth(targetUrl) → 返回 AuthResult
  Step 2: 如果 AuthResult.status === 'success' → 导航到慢接口页面...
```

### 2.2 完整流程解剖

```
┌─────────────────────────────────────────────────┐
│            ensureAuth(targetUrl)                 │
│                                                  │
│  ┌────────────────────────────────────────┐     │
│  │ STEP 1: 预检缓存（零开销）              │     │
│  │                                        │     │
│  │ ls ~/.auth/mi-auth.json               │     │
│  │  ├─ 文件不存在 → 跳到 STEP 2           │     │
│  │  ├─ 文件存在 → 启动 headless 浏览器    │     │
│  │  │    ├─ 未被重定向到 CAS → 有效！返回  │     │
│  │  │    └─ 被重定向到 CAS → 已过期，删文件 │     │
│  │  └─ 决定：用缓存 or 重新登录           │     │
│  └──────────────┬─────────────────────────┘     │
│                 │ 缓存失效                       │
│  ┌──────────────▼─────────────────────────┐     │
│  │ STEP 2: 启动浏览器 + 等待 CAS 重定向   │     │
│  │                                        │     │
│  │ page.goto(targetUrl)                   │     │
│  │ page.waitForURL('**cas.mioffice.cn**') │     │
│  └──────────────┬─────────────────────────┘     │
│                 │                                │
│  ┌──────────────▼─────────────────────────┐     │
│  │ STEP 3: 语义化检测二维码               │     │
│  │                                        │     │
│  │ // ❌ 不要这样做：                      │     │
│  │ page.locator('#qrcode > img')          │     │
│  │ // ✅ 应该这样做：                      │     │
│  │ page.locator('img[src*="qrcode"],      │     │
│  │               img[alt*="QR"],          │     │
│  │               img[alt*="scan"]')       │     │
│  │                                        │     │
│  │ 截屏保存 → 展示给用户                   │     │
│  └──────────────┬─────────────────────────┘     │
│                 │                                │
│  ┌──────────────▼─────────────────────────┐     │
│  │ STEP 4: 双信号轮询等待完成             │     │
│  │                                        │     │
│  │ Promise.race([                         │     │
│  │   page.waitForURL(非CASURL, 120s),      │     │
│  │   page.waitForSelector(                 │     │
│  │     'img[src*="qrcode"]',              │     │
│  │     { state: 'detached', timeout: 120s }│     │
│  │   )                                     │     │
│  │ ])                                      │     │
│  └──────────────┬─────────────────────────┘     │
│                 │                                │
│  ┌──────────────▼─────────────────────────┐     │
│  │ STEP 5: 持久化 storageState            │     │
│  │                                        │     │
│  │ context.storageState() → 写入文件      │     │
│  │ 返回结构化 AuthResult                  │     │
│  └────────────────────────────────────────┘     │
│                                                  │
│  输出：{ status, storageStatePath, timestamp }   │
└─────────────────────────────────────────────────┘
```

### 2.3 五大关键设计决策

#### 决策 1：预检缓存（Pre-flight Validation）

```javascript
// 在任何浏览器启动之前，先检查缓存
const storageStatePath = path.join(authDir, 'mi-auth.json');
if (fs.existsSync(storageStatePath)) {
    // 只为了验证而启动 headless 浏览器（用户无感知）
    const browser = await chromium.launch();
    const context = await browser.newContext({ storageState: storageStatePath });
    const page = await context.newPage();
    await page.goto(targetUrl);
    if (!page.url().includes('cas.mioffice.cn')) {
        await browser.close();
        return { status: 'already_logged_in', storageStatePath };
    }
    await browser.close();
}
```

**设计意图**：避免在不必要的时候弹出浏览器窗口打断用户。先静默检测，只在缓存失效时才让用户介入。

**通用化要点**：
- 检测逻辑需可配置（不同系统的登录页面 URL 不同）
- 验证策略可扩展（不仅检测 URL 重定向，还可以检测 cookie 是否存在、特定元素是否出现）

#### 决策 2：语义化定位（Semantic Selector）

```javascript
// 定位策略优先级：
// 1. 按属性语义：img[alt="QR Code"], img[src*="qrcode"]
// 2. 按 ARIA 角色：role=img[name="QR Code"]
// 3. 按文本内容：text="扫码登录"
// 4.（最后手段）按 CSS class：.qrcode-img
```

**设计意图**：DOM 结构变化（div 变 section、嵌套层级变）不影响定位。只要"这是个二维码图片"的语义不变，定位就不变。

**通用化要点**：
- 将选择器定义为声明式配置，不硬编码
- 支持多选择器 fallback 链（试 selector1 → 失败试 selector2 → ...）

#### 决策 3：双信号完成检测（Dual-Signal Completion）

```javascript
// 两个信号竞争，谁先触发算谁完成：
// 信号 1：URL 变化（登录成功跳转）
// 信号 2：QR 元素消失（登录失败、超时重新显示）

await Promise.race([
    page.waitForURL(url => !url.includes('cas.mioffice.cn'), { timeout: 120000 }),
    page.waitForSelector('img[src*="qrcode"]', { state: 'detached', timeout: 120000 })
]);
```

**设计意图**：单信号有盲区。
- 只等 URL 变化：如果登录失败，QR 重新出现但 URL 不变 → 超时
- 只等 QR 消失：如果登录成功但页面异步加载慢，QR 已消失但页面未加载完 → 提前判断"完成"

双信号覆盖了所有情况，且 `Promise.race` 保证了哪个先到取哪个。

#### 决策 4：结构化返回契约

```typescript
interface AuthResult {
    loginStatus: 'success' | 'already_logged_in' | 'timeout' | 'error';
    storageStatePath: string | null;
    timestamp: number;
    method: 'qr_scan' | 'cached';
    error?: string;
}
```

**设计意图**：调用方不需要知道登录是怎么完成的——扫码、缓存、OAuth——它只需要检查 `loginStatus`。这是"信息隐藏"在技能间通信中的体现。

#### 决策 5：SKILL.md 与脚本分离

```
dayu-cas-login-skill/
├── SKILL.md              # 48 行：什么情况下触发、有什么权限、产出什么
└── scripts/
    └── cas_login_checker.js  # 136 行：具体怎么做的全部逻辑
```

**设计意图**：SKILL.md 是"契约文档"（what + when），脚本是"实现"（how）。这种分离让：
- AI 阅读 SKILL.md 就知道要不要触发这个技能
- 实现变更不影响触发逻辑
- 脚本可以独立测试和替换

### 2.4 去公司化蓝图：IAuthProvider 接口

```typescript
// ============================================
// 核心抽象：认证提供者接口
// ============================================
interface IAuthProvider {
    // 检测：是否需要登录？（不需要则直接返回）
    detectAuthRequired(page: Page): Promise<boolean>;

    // 检测：有没有可用缓存？
    detectCachedState(): Promise<string | null>;

    // 获取：执行登录流程
    acquireAuth(page: Page): Promise<AuthResult>;

    // 验证：缓存的 session 是否还有效？
    validateCachedState(statePath: string): Promise<boolean>;

    // 持久化：保存 session 到文件
    persistState(context: BrowserContext): Promise<string>;
}

// ============================================
// 实现 1：二维码认证（当前 dayu-cas-login 模式）
// ============================================
class QRCodeAuthProvider implements IAuthProvider {
    constructor(private config: QRCodeConfig) {}

    async detectAuthRequired(page: Page): Promise<boolean> {
        await page.goto(this.config.targetUrl);
        return page.url().includes(this.config.loginPagePattern);
    }

    async acquireAuth(page: Page): Promise<AuthResult> {
        // 定位二维码 → 截屏 → 轮询等待 → 持久化
        const qrSelector = this.config.qrSelectors.join(', ');
        const qrElement = page.locator(qrSelector).first();
        await qrElement.screenshot({ path: this.config.qrOutputPath });

        await Promise.race([
            page.waitForURL(url => !url.includes(this.config.loginPagePattern), { timeout: 120000 }),
            page.waitForSelector(qrSelector, { state: 'detached', timeout: 120000 })
        ]);

        return {
            loginStatus: 'success',
            storageStatePath: '',
            timestamp: Date.now(),
            method: 'qr_scan'
        };
    }

    async validateCachedState(statePath: string): Promise<boolean> {
        const browser = await chromium.launch();
        try {
            const context = await browser.newContext({ storageState: statePath });
            const page = await context.newPage();
            await page.goto(this.config.targetUrl);
            return !page.url().includes(this.config.loginPagePattern);
        } finally {
            await browser.close();
        }
    }

    // ...其他方法
}

// ============================================
// 实现 2：OAuth 认证（GitHub / Google / 企业 SSO）
// ============================================
class OAuthProvider implements IAuthProvider {
    constructor(private config: OAuthConfig) {}

    async detectAuthRequired(page: Page): Promise<boolean> {
        await page.goto(this.config.targetUrl);
        // 检测是否被重定向到 OAuth 授权页面
        return page.url().includes(this.config.authorizeUrl);
    }

    async acquireAuth(page: Page): Promise<AuthResult> {
        // 自动填写凭据 or 等待用户手动授权
        if (this.config.credentials) {
            await page.fill(this.config.usernameSelector, this.config.credentials.username);
            await page.fill(this.config.passwordSelector, this.config.credentials.password);
            await page.click(this.config.submitSelector);
        } else {
            // 等待用户手动完成 OAuth 流程
            await page.waitForURL(url => !url.includes(this.config.authorizeUrl), { timeout: 300000 });
        }
        return { loginStatus: 'success', storageStatePath: '', timestamp: Date.now(), method: 'oauth' };
    }

    // ...其他方法
}

// ============================================
// 实现 3：API Key 认证（Datadog / Grafana）
// ============================================
class APIKeyProvider implements IAuthProvider {
    constructor(private config: APIKeyConfig) {}

    async detectAuthRequired(_page: Page): Promise<boolean> {
        // API Key 方式不需要浏览器登录
        return false;
    }

    async detectCachedState(): Promise<string | null> {
        // API Key 本身不需要缓存，但可以缓存 token
        return this.config.tokenPath || null;
    }

    async acquireAuth(_page: Page): Promise<AuthResult> {
        // 直接用 API Key 请求 token
        const response = await fetch(this.config.tokenUrl, {
            headers: { 'Authorization': `Bearer ${this.config.apiKey}` }
        });
        const { token } = await response.json();
        return { loginStatus: 'success', storageStatePath: '', timestamp: Date.now(), method: 'api_key' };
    }

    // ...其他方法
}

// ============================================
// 工厂：根据配置创建认证提供者
// ============================================
function createAuthProvider(config: AuthConfig): IAuthProvider {
    switch (config.type) {
        case 'qr_code': return new QRCodeAuthProvider(config);
        case 'oauth':   return new OAuthProvider(config);
        case 'api_key': return new APIKeyProvider(config);
        default: throw new Error(`Unknown auth type: ${config.type}`);
    }
}
```

### 2.5 模式总结

| 维度 | 要点 |
|------|------|
| **核心思想** | 登录 = 独立服务，不是嵌入式的功能 |
| **关键机制** | 预检缓存 → 语义定位 → 双信号轮询 → 结构化返回 |
| **文件结构** | SKILL.md（契约）+ scripts/（实现）分离 |
| **通用化接口** | `IAuthProvider` — 三种认证方式可插拔 |
| **适用场景** | 任何需要浏览器登录态的技能 |

---

## 三、模式 2：重试 + 优雅降级（Retry + Graceful Degradation）

### 3.1 设计哲学：数据不完整 ≠ 任务失败

传统编程思维：操作要么成功，要么失败（boolean）。

hera-slow-api-analyzer 的思维：**数据可能"部分可用"**。这不是失败，而是一种需要被记录和传递的状态。

```typescript
// ❌ 传统二值思维
try {
    const data = await extractData();
    analyze(data);  // 假设 data 是完整的
} catch (e) {
    console.error('失败:', e);
}

// ✅ 三态思维
const result = await extractDataWithResilience();
// result.completeness: 'full' | 'partial' | 'unavailable'
// result.gaps: ['缺少日志数据', 'SQL 执行计划未获取']
analyzeWithCaveats(result);  // 根据 completeness 调整分析深度
```

### 3.2 在 hera-slow-api-analyzer 中的实际表现

```
Phase 1 数据提取的容错逻辑（SKILL.md 原文提炼）：

尝试 1: 浏览器提取 Trace 数据
  ├─ 完整提取 → 进入 Phase 2
  ├─ 部分提取（如 Trace 有但日志缺失）→ 重试
  └─ 完全无法提取（如 Hera 不可达）→ 重试

尝试 2: 重试浏览器提取
  ├─ 完整提取 → 进入 Phase 2
  ├─ 部分提取 → 重试
  └─ 完全无法提取 → 重试

尝试 3: 最后一次重试
  ├─ 完整提取 → 进入 Phase 2
  ├─ 部分提取 → 标记 "partial, continue analysis"
  └─ 完全无法提取 → 跳过 Phase 1，直接进入 Phase 2（询问用户提供 trace_id）
```

### 3.3 核心概念：DataAvailability 三态枚举

```typescript
enum DataCompleteness {
    FULL = 'full',             // 所有预期数据已获取，正常分析
    PARTIAL = 'partial',       // 部分数据缺失，带缺口的分析
    UNAVAILABLE = 'unavailable' // 完全无数据，跳过该分析步骤
}
```

**为什么必须是三态而不是二态？**

因为 `PARTIAL` 状态支撑了最重要的行为——**渐进式分析**：

```
有 Trace 数据 + 有日志 → 完整分析（最可信）
有 Trace 数据 + 无日志 → 基于 Trace 分析 + 标注"日志缺失"
无 Trace 数据 + 用户提供 trace_id → 用 API 查询 + 分析
无任何数据 → 告知用户"数据不足，无法诊断"
```

每一步都尽力分析已有的数据，而不是因为缺了一部分就放弃全部。

### 3.4 降级链（Degradation Chain）设计

降级不是"出错时的单一备选方案"，而是一个**有序的策略链**：

```typescript
interface ResilienceConfig {
    // 最大重试次数
    maxAttempts: number;              // 默认 3

    // 重试间隔（毫秒）
    backoffMs: number;                // 默认 1000（建议递增）

    // 降级链：按顺序尝试的提取策略
    degradationChain: DegradationStrategy[];

    // 每种状态的策略
    onPartial: 'retry' | 'proceed' | 'degrade';
    onUnavailable: 'retry' | 'skip' | 'degrade';
}

interface DegradationStrategy {
    name: string;                     // 策略名称（用于日志和报告）
    extractor: () => Promise<AttemptResult<any>>;
}

// ============================================
// 典型降级链示例
// ============================================
const slowAPIExtractionConfig: ResilienceConfig = {
    maxAttempts: 3,
    backoffMs: 2000,
    degradationChain: [
        {
            name: '浏览器直接提取',
            extractor: async () => extractTraceFromBrowser(page)
        },
        {
            name: 'Hera API 查询',
            extractor: async () => extractTraceFromAPI(traceId, apiConfig)
        },
        {
            name: '缓存数据回退',
            extractor: async () => loadCachedTrace(traceId)
        },
        {
            name: '用户手动提供',
            extractor: async () => askUserForTraceData()
        }
    ],
    onPartial: 'proceed',    // 部分数据也继续（不做无谓重试）
    onUnavailable: 'degrade' // 完全不可用则降级到下一个策略
};
```

**降级链的执行逻辑**：

```
策略 1: 浏览器提取
  ├─ FULL → 直接返回 ✅
  ├─ PARTIAL → onPartial='proceed' → 直接返回，带 gaps 标注
  ├─ UNAVAILABLE → onUnavailable='degrade' → 尝试策略 2
  └─ 错误 → 重试（最多 3 次），3 次均失败 → 尝试策略 2

策略 2: API 查询
  ├─ FULL → 直接返回 ✅
  ├─ PARTIAL → onPartial='proceed' → 直接返回
  ├─ UNAVAILABLE → onUnavailable='degrade' → 尝试策略 3
  └─ 错误 → 重试（最多 3 次）→ 尝试策略 3

策略 3: 缓存回退
  ...以此类推

策略 4: 用户手动提供
  ├─ 用户提供了 → 返回 PARTIAL（标记来源为用户）
  └─ 用户没提供 → 返回 UNAVAILABLE（完全放弃）
```

### 3.5 通用执行引擎

```typescript
interface AttemptResult<T> {
    completeness: DataCompleteness;
    data: Partial<T>;          // ⚠️ 始终是 Partial<T>，强制调用方处理缺失
    gaps: string[];            // 人类可读的缺口描述
    attemptNumber: number;
    strategy: string;          // 使用了哪个策略
    error?: string;
}

async function executeWithResilience<T>(
    config: ResilienceConfig
): Promise<AttemptResult<T>> {
    let lastError: string | undefined;

    for (const strategy of config.degradationChain) {
        for (let attempt = 1; attempt <= config.maxAttempts; attempt++) {
            try {
                const result = await strategy.extractor();
                result.attemptNumber = attempt;
                result.strategy = strategy.name;

                // 完整获取 → 立即返回
                if (result.completeness === DataCompleteness.FULL) {
                    return result;
                }

                // 部分获取 → 根据策略决定
                if (result.completeness === DataCompleteness.PARTIAL) {
                    if (config.onPartial === 'proceed') return result;
                    if (config.onPartial === 'degrade') break; // 跳出重试，试下一个策略
                    // onPartial === 'retry' → 继续重试
                }

                // 完全不可用 → 根据策略决定
                if (result.completeness === DataCompleteness.UNAVAILABLE) {
                    if (config.onUnavailable === 'skip') return result;
                    if (config.onUnavailable === 'degrade') break;
                    // onUnavailable === 'retry' → 继续重试
                }

                // 等待后重试
                await sleep(config.backoffMs * attempt);

            } catch (error) {
                lastError = error instanceof Error ? error.message : String(error);
                if (attempt < config.maxAttempts) {
                    await sleep(config.backoffMs * attempt);
                }
            }
        }
        // 当前策略所有重试耗尽，尝试下一个降级策略
    }

    // 所有策略都耗尽
    return {
        completeness: DataCompleteness.UNAVAILABLE,
        data: {} as Partial<T>,
        gaps: ['所有策略均已尝试，全部失败'],
        attemptNumber: config.maxAttempts,
        strategy: 'exhausted',
        error: lastError
    };
}
```

### 3.6 补充模式：Ticket-Troubleshoot-v3 的输出契约

`ticket-troubleshoot-v3` 将降级状态直接嵌入输出格式中，形成"可信度标注"：

```markdown
## 诊断结论

| 维度 | 值 |
|------|-----|
| 根因 | [found / partially identified / not found] |
| 证据强度 | [direct evidence / indirect evidence / insufficient data] |
| 置信度 | [high / medium / low] |
| 数据缺口 | [list of missing data points] |
```

这种输出格式让**降级状态直接可见**，无论是人还是下游系统，都知道哪些结论可信、哪些需要进一步验证。

### 3.7 模式总结

| 维度 | 要点 |
|------|------|
| **核心思想** | 数据不完整不是失败，是带注释的中间状态 |
| **关键枚举** | `DataCompleteness.FULL / PARTIAL / UNAVAILABLE` |
| **关键结构** | `AttemptResult<T>` — 始终 `Partial<T>`，携带 `gaps[]` |
| **降级策略** | 有序链：浏览器 → API → 缓存 → 用户 → 放弃 |
| **适用场景** | 任何依赖外部数据源（Web UI、API、数据库）的技能 |

---

## 四、模式 3：浏览器自动化应用 — 浏览器是 API 发现引擎，而非 DOM 提取器

### 4.1 设计哲学纠偏：浏览器自动化的真正价值

在编写本文档初版时，我们将"浏览器自动化"等同于"从 DOM 提取数据"。经过深入研究和跨技能对比后发现，**这是对该模式的根本性误读**。

> 浏览器自动化的最大价值不是"替代人眼读取页面"，而是**发现和调用那些前端已经调用的 API**。

为什么 DOM 提取不是主路径？有硬数据支持：

> ⚠️ **DOM 提取的不稳定性证据**（综合多项研究和案例）：
> - 实际准确率仅 **50-60%**（不是文档中假设的"又快又准"）
> - **10-15%** 的 scraper 每周需要修复（因 UI 改版导致选择器断裂）
> - hashed CSS class 中位寿命仅 **9 天**（Amazon 研究发现）
> - 选择器平均每 **11-16 天**失效一次
> - 维护成本约 **$48K/年**（一名全职维护工程师）
> - **最危险的失败模式**：HTTP 200 + `null` data（静默失败，比报错更隐蔽）
> - `newretail-attendance-gateway-tiangong-creator` 的实际教训：JS click 被 Vue/Element UI 拦截，hover 必须用 `locator.hover()`

**hera-slow-api-analyzer 的 3 次重试机制存在的根本原因**，不是 Hera 平台不稳定，而是 **DOM 提取本身就不可靠**。

正确的定位应该是：

```
浏览器 = API 发现引擎（主路径） + UI 交互驱动（支撑） + DOM 提取（兜底）

Layer 1: 网络拦截 —— 发现前端 API，记录请求/响应，直接调用
Layer 2: HAR 录制回放 —— 录制一次交互，之后无限重放
Layer 3: DOM 提取 —— 仅在无 API 可用时作为最后手段
```

```
❌ 初版误读：
   浏览器 = DOM 提取器
   page.evaluate() → 提取 JSON → 完成任务
   （脆弱、维护成本高、适用范围窄）

✅ 正确理解：
   浏览器 = API 发现引擎 + 网络级测试工具
   page.on('response') → 发现 API → page.route() → 拦截/修改请求
   （稳定、零维护、适用范围广）
```

### 4.2 三层架构：从网络层到 DOM 层

#### Layer 1（首选）：API 发现 — 网络拦截

**核心思想**：前端 SPA 本身就在调用后端 API 获取数据。不需要解析 DOM，直接"偷听"这些 API 调用即可。

```typescript
// ============================================
// Layer 1: 被动 API 发现（监听所有响应）
// ============================================

// 在页面导航前注册监听器
const capturedAPIs: CapturedAPI[] = [];

page.on('response', async (response) => {
    const url = response.url();
    const status = response.status();

    // 过滤：只关注 JSON API（排除静态资源）
    if (!url.includes('/api/') && !response.headers()['content-type']?.includes('json')) {
        return;
    }

    try {
        const body = await response.json();
        capturedAPIs.push({
            url,
            method: response.request().method(),
            status,
            headers: response.request().headers(),
            requestBody: response.request().postDataJSON(),
            responseBody: body
        });
    } catch {
        // 非 JSON 响应，忽略
    }
});

// 然后让用户正常操作 UI
await page.goto('https://target-app.com/dashboard');
await page.click('[data-action="load-trace-list"]');
await page.waitForTimeout(2000);  // 等待 API 调用完成

// 现在 capturedAPIs 里已经有了前端调用的所有 API 端点
console.log(`发现 ${capturedAPIs.length} 个 API 端点`);
capturedAPIs.forEach(api => {
    console.log(`${api.method} ${api.url} → ${api.status}`);
});
```

**进阶：主动 API 发现 + 签名提取**

```typescript
// ============================================
// Layer 1 进阶: 拦截所有请求以提取认证签名
// ============================================

const apiSignatures: APISignature[] = [];

await page.route('**/*', (route, request) => {
    const url = request.url();

    if (url.includes('/api/') && request.method() === 'POST') {
        // 记录完整的请求签名（headers + body template）
        apiSignatures.push({
            url: url,
            method: request.method(),
            headers: request.headers(),
            bodyTemplate: request.postDataJSON() || request.postData()
        });
    }

    route.continue();  // 不放行就会阻止请求
});

// 操作 UI 一次后，apiSignatures 包含所有可复用的 API 签名
// 后续可以直接用 fetch/axios 调用，完全绕过浏览器
```

**现有技能的差距**：在 vibe-hubs 仓库的 **39 个技能中**，**零个技能**使用 `page.on('response')` 或 `page.route()` 进行 API 发现。`API_REFERENCE.md` 第 257 行提到了 `browser-mcp_browser_network_requests`，但从未被用作**主要数据提取路径**。

#### Layer 2（降级）：HAR 录制 + 回放

**核心思想**：Layer 1 的 API 发现是一次性的。发现后，录制完整的 HTTP Archive (HAR)，后续执行直接回放。

```typescript
// ============================================
// Layer 2: HAR 录制 + 回放
// ============================================

// ① 录制模式：创建带 HAR 记录的 context
const context = await browser.newContext({
    storageState: authStatePath,  // 复用模式 1 的登录态
    recordHar: {
        path: './recordings/trace-query.har',
        mode: 'full',             // 记录完整请求/响应体
        content: 'embed'          // 将 body 嵌入 HAR 文件
    }
});

const page = await context.newPage();

// 执行一次交互（录制的数据来源于网络层，不依赖 DOM）
await page.goto('https://hera.company.com/trace');
await page.click('[data-testid="query-btn"]');
await page.waitForResponse(resp =>
    resp.url().includes('/api/trace/query') && resp.status() === 200
);

await context.close();
// 现在 trace-query.har 包含完整的 API 交互记录

// ② 回放模式：直接使用 HAR 文件，无需 UI 交互
const replayContext = await browser.newContext({
    storageState: authStatePath
});

// ⚠️ Playwright 原生 API: routeFromHAR
await replayContext.routeFromHAR('./recordings/trace-query.har', {
    url: '**/api/trace/**',    // 只匹配 trace 相关 API
    notFound: 'fallback'       // 未匹配的请求正常发送
});

const replayPage = await replayContext.newPage();
// 现在所有匹配的 API 调用都从 HAR 文件返回，无需实际网络请求
await replayPage.goto('https://hera.company.com/trace');
// ... UI 操作，但 API 数据来自 HAR
```

**HAR 回放的关键优势**：

| 对比维度 | DOM 提取 | HAR 回放 |
|---------|---------|---------|
| 稳定性 | 受 UI 改版影响，选择器易断裂 | 只依赖 API 契约，API 不变就不坏 |
| 维护成本 | 15-25 小时/周（2-3 名工程师） | 仅在 API 签约变化时需要更新 HAR |
| 执行速度 | 每次都要渲染完整 DOM | 网络层响应，0 渲染成本 |
| 离线可用 | ❌ 必须连接目标站点 | ✅ HAR 文件可离线使用 |
| 数据完整性 | 只提取页面显示的数据 | 获取完整 API 响应（含隐藏字段） |

#### Layer 3（兜底）：DOM 提取 — 仅在无 API 可用时使用

**核心思想**：DOM 提取仍然有价值，但必须正确定位——它是**最后手段**，不是默认路径。

```
什么时候用 DOM 提取？

✅ Canvas/WebGL 渲染的内容 —— 无 DOM 可解析，只能看到像素
✅ WebSocket 推送的实时数据 —— 无传统 HTTP API 可拦截
✅ 遗留系统无 API 层 —— 服务端渲染的纯 HTML 页面
✅ 跨域 iframe 内容 —— 浏览器安全策略阻止网络拦截
✅ 需要视觉验证时 —— 截图作为证据，而非数据源

❌ 什么时候不该用 DOM 提取？

❌ 有 JSON API 的现代 SPA —— 直接用 Layer 1
❌ 数据量超过一屏 —— evaluate() 只提取可见 DOM
❌ 需要持续监控 —— 选择器随时可能断裂
```

**DOM 提取的"稳一点"实践**：

当必须走 DOM 提取时，以下是减少断裂概率的最佳实践：

```typescript
// ============================================
// Layer 3: 防御性 DOM 提取
// ============================================

interface DefensiveExtractionConfig {
    // 声明式提取规则（而非硬编码选择器）
    rules: ExtractionRule[];
    // 验证提取结果的完整性
    validate: (data: any) => ValidationResult;
    // 提取失败时的自动截图
    screenshotOnFailure: boolean;
}

interface ExtractionRule {
    // 优先策略（按稳定性排序）
    strategies: SelectorStrategy[];
    // 如果所有策略都失败，返回什么默认值
    fallback: any;
    // 是否是必填字段
    required: boolean;
}

type SelectorStrategy =
    | { type: 'testid'; value: string }     // 最稳定：data-testid
    | { type: 'aria'; role: string; name?: string }  // 次稳定：无障碍属性
    | { type: 'text'; value: string }       // 中等：可见文本
    | { type: 'css'; selector: string };    // 最不稳定：CSS 类名

async function defensiveExtract<T>(
    page: Page,
    config: DefensiveExtractionConfig
): Promise<AttemptResult<T>> {
    const result: any = {};
    const gaps: string[] = [];

    for (const rule of config.rules) {
        let extracted: any = undefined;

        for (const strategy of rule.strategies) {
            try {
                switch (strategy.type) {
                    case 'testid':
                        extracted = await page.locator(`[data-testid="${strategy.value}"]`).textContent();
                        break;
                    case 'aria':
                        extracted = await page.getByRole(strategy.role as any, strategy.name ? { name: strategy.name } : {}).textContent();
                        break;
                    case 'text':
                        extracted = await page.getByText(strategy.value).textContent();
                        break;
                    case 'css':
                        extracted = await page.locator(strategy.selector).textContent();
                        break;
                }
                if (extracted) break;  // 成功提取，跳出策略循环
            } catch {
                continue;  // 当前策略失败，试下一个
            }
        }

        if (extracted === undefined) {
            if (rule.required) {
                gaps.push(`必填字段提取失败: ${JSON.stringify(rule.strategies[0])}`);
            }
            result[rule.strategies[0].value] = rule.fallback;
        } else {
            result[rule.strategies[0].value] = extracted;
        }
    }

    // 验证 + 失败截图
    const validation = config.validate(result);
    if (!validation.isValid && config.screenshotOnFailure) {
        await page.screenshot({ path: `extraction-failure-${Date.now()}.png` });
    }

    return {
        completeness: gaps.length === 0 ? DataCompleteness.FULL : DataCompleteness.PARTIAL,
        data: result as Partial<T>,
        gaps,
        attemptNumber: 1,
        strategy: 'dom-extraction',
        error: gaps.length > 0 ? gaps.join('; ') : undefined
    };
}
```

### 4.3 决策框架：什么情况下用哪一层

```
收到任务："从 Web 系统获取数据 X"

① 系统是现代 SPA（React/Vue/Angular）?
   ├─ 是 → 进入 ②
   └─ 否（服务端渲染 HTML）→ 跳至 Layer 3（DOM 提取）

② 打开 DevTools Network 面板，执行一次操作
   ├─ 看到 /api/ 请求返回 JSON → 恭喜！走 Layer 1（API 发现）
   │   操作：page.on('response') 监听 → 提取请求签名 → 直接 fetch 调用
   │   维护成本：近乎为零
   │
   ├─ 看到 GraphQL endpoint → 走 Layer 1（API 发现）
   │   操作：拦截 GraphQL query/mutation → 提取 query 文本和 variables
   │
   └─ 看到 WebSocket → 走 Layer 3（DOM 提取 or WebSocket 客户端）

③ 需要反复执行相同操作?
   ├─ 是 → 升级到 Layer 2（HAR 录制 + 回放）
   │   操作：录制一次 → routeFromHAR 回放
   │   优势：一次录制，永久可用
   │
   └─ 否 → 保持 Layer 1 即可

④ 必须用 DOM 提取?
   ├─ 确保有 data-testid 可用 → 用 testid 选择器
   ├─ 否则用 ARIA role + name → 用 getByRole
   ├─ 否则用可见文本 → 用 getByText
   ├─ 最后才用 CSS 类名 → 接受它会断裂
   └─ 防御性编程：每个字段至少配 2 个备选选择器
```

### 4.4 实际案例对比：同一个任务，三种实现

**场景**：从 Hera 监控平台获取"慢接口列表"

```typescript
// ============================================
// 方案 A（Layer 1 - 推荐）: API 发现 + 直接调用
// ============================================
async function getSlowAPIs_Layer1(): Promise<SlowAPI[]> {
    // 第一步：发现 API（只需执行一次，后续复用签名）
    // 打开 Hera → 点击"慢接口" → 观察到 POST /api/hera/slow-apis
    // 请求体: { "timeRange": "1h", "threshold": 1000 }

    // 第二步：直接调用（完全绕过浏览器）
    const response = await fetch('https://hera.company.com/api/hera/slow-apis', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`,  // 从模式 1 获取
        },
        body: JSON.stringify({ timeRange: '1h', threshold: 1000 })
    });
    return (await response.json()).data;
}

// ============================================
// 方案 B（Layer 2 - 推荐）: HAR 回放
// ============================================
async function getSlowAPIs_Layer2(): Promise<SlowAPI[]> {
    const context = await browser.newContext({
        storageState: authStatePath
    });
    await context.routeFromHAR('./recordings/hera-slow-apis.har', {
        url: '**/api/hera/slow-apis',
        notFound: 'fallback'
    });
    const page = await context.newPage();
    await page.goto('https://hera.company.com/trace');

    // 点击"查询"按钮，API 响应自动从 HAR 文件返回
    await page.click('[data-testid="query-slow-apis-btn"]');

    // 从 HAR 响应中提取数据（需要通过 response 事件获取）
    return new Promise((resolve) => {
        page.on('response', async (response) => {
            if (response.url().includes('/api/hera/slow-apis')) {
                const data = await response.json();
                resolve(data.data);
            }
        });
    });
}

// ============================================
// 方案 C（Layer 3 - 兜底）: DOM 提取
// ============================================
async function getSlowAPIs_Layer3(): Promise<AttemptResult<SlowAPI[]>> {
    // ⚠️ 仅在方案 A/B 不可用时使用
    return defensiveExtract<SlowAPI[]>(page, {
        rules: [
            {
                strategies: [
                    { type: 'testid', value: 'api-name' },
                    { type: 'css', selector: '.api-name' }
                ],
                fallback: '',
                required: true
            },
            {
                strategies: [
                    { type: 'testid', value: 'p99-latency' },
                    { type: 'css', selector: '.p99' }
                ],
                fallback: 0,
                required: true
            }
        ],
        validate: (data) => ({
            isValid: Array.isArray(data) && data.length > 0,
            completeness: Array.isArray(data) && data.length > 0
                ? DataCompleteness.FULL
                : DataCompleteness.PARTIAL
        }),
        screenshotOnFailure: true
    });
}
```

### 4.5 通用浏览器自动化 Skill 骨架（修正版）

```typescript
// ============================================
// 修正版: 浏览器自动化 Skill 骨架
// 核心改变: API 发现优先，DOM 提取兜底
// ============================================

interface BrowserSkillConfig<T> {
    // === Layer 1: API 发现配置 ===
    apiDiscovery: {
        enabled: boolean;
        // 触发 API 调用的 UI 操作序列
        triggerActions: Array<() => Promise<void>>;
        // API URL 匹配模式
        urlPattern: string | RegExp;
        // 提取请求签名（后续直接 fetch 调用）
        extractSignature: boolean;
    };

    // === Layer 2: HAR 回放配置 ===
    harReplay: {
        enabled: boolean;
        harFilePath: string;
    };

    // === Layer 3: DOM 提取配置（兜底） ===
    domExtraction: {
        enabled: boolean;
        rules: ExtractionRule[];
        screenshotOnFailure: boolean;
    };
}

async function executeBrowserSkill<T>(
    config: BrowserSkillConfig<T>
): Promise<AttemptResult<T>> {
    // Phase 0: 认证检查（委托模式 1）
    const authResult = await ensureAuth(targetUrl);
    if (authResult.loginStatus !== 'success' && authResult.loginStatus !== 'already_logged_in') {
        return createUnavailableResult('认证失败');
    }

    const page = await createPageWithAuth(authResult.storageStatePath);

    // Phase 1: 尝试 Layer 1 — API 发现 + 直接调用
    if (config.apiDiscovery.enabled) {
        try {
            // 注册响应监听器
            const apiPromise = new Promise<T>((resolve, reject) => {
                const timeout = setTimeout(() => reject(new Error('API discovery timeout')), 30000);
                page.on('response', async (response) => {
                    if (response.url().match(config.apiDiscovery.urlPattern) && response.status() === 200) {
                        try {
                            const data = await response.json();
                            clearTimeout(timeout);
                            resolve(data);
                        } catch { /* 非 JSON 响应 */ }
                    }
                });
            });

            // 执行触发操作（点击、填写等）
            for (const action of config.apiDiscovery.triggerActions) {
                await action();
            }

            const apiData = await apiPromise;
            return {
                completeness: DataCompleteness.FULL,
                data: apiData as Partial<T>,
                gaps: [],
                attemptNumber: 1,
                strategy: 'api-discovery'
            };
        } catch (e) {
            // API 发现失败 → 降级到 Layer 2 或 Layer 3
            console.warn('API 发现失败，尝试降级策略:', e);
        }
    }

    // Phase 2: 尝试 Layer 2 — HAR 回放
    if (config.harReplay.enabled) {
        try {
            await page.routeFromHAR(config.harReplay.harFilePath, {
                notFound: 'fallback'
            });
            // ... HAR 回放逻辑
        } catch (e) {
            console.warn('HAR 回放失败，尝试 DOM 提取:', e);
        }
    }

    // Phase 3: 兜底 — DOM 提取
    if (config.domExtraction.enabled) {
        return defensiveExtract<T>(page, {
            rules: config.domExtraction.rules,
            validate: () => ({ isValid: true, completeness: DataCompleteness.FULL }),
            screenshotOnFailure: config.domExtraction.screenshotOnFailure
        });
    }

    return createUnavailableResult('所有提取策略均失败');
}
```

### 4.6 模式总结

| 维度 | 要点 |
|------|------|
| **核心思想** | 浏览器是 API 发现引擎，不是 DOM 提取器；优先拦截网络层，DOM 仅兜底 |
| **Layer 1（首选）** | `page.on('response')` / `page.route()` — 发现前端 API，直接 fetch 调用 |
| **Layer 2（降级）** | HAR 录制 + `routeFromHAR()` — 一次录制，永久回放 |
| **Layer 3（兜底）** | 防御性 DOM 提取 — 多策略选择器 + 必填字段验证 + 失败截图 |
| **DOM 提取限制** | 仅在 Canvas/WebSocket/无 API 的遗留系统时使用 |
| **稳定性数据** | API 发现 ≈ 100%（API 契约不变则不断裂）；DOM 提取 ≈ 50-60%（选择器 11-16 天断裂一次） |
| **适用场景** | 任何需要从 Web 系统获取数据的技能（优先检查是否有 JSON API） |

---

## 五、三个模式的组合架构

### 5.1 组合关系图

```
┌──────────────────────────────────────────────────────────────┐
│                      SKILL: xxx-analyzer                      │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              模式 1: 登录即服务                       │   │
│  │                                                       │   │
│  │  ensureAuth(targetUrl) → AuthResult                   │   │
│  │  ┌──────────┬──────────┬──────────┐                  │   │
│  │  │ QR Code  │  OAuth   │ API Key  │  可插拔          │   │
│  │  └──────────┴──────────┴──────────┘                  │   │
│  │  输出: { status, storageStatePath, method, token }   │   │
│  │        ↑ 为 Layer 1/2/3 提供认证态                   │   │
│  └──────────────────────┬───────────────────────────────┘   │
│                         │                                    │
│  ┌──────────────────────▼───────────────────────────────┐   │
│  │           模式 3: 浏览器 = API 发现引擎               │   │
│  │                                                       │   │
│  │  ┌──────────────┬──────────────┬──────────────┐       │   │
│  │  │   Layer 1    │   Layer 2    │   Layer 3    │       │   │
│  │  │  API 发现    │  HAR 回放    │  DOM 兜底    │       │   │
│  │  │              │              │              │       │   │
│  │  │ on('resp')   │ routeFromHAR │ defensive-   │       │   │
│  │  │ route()      │ waitForResp  │ Extract()    │       │   │
│  │  │              │              │              │       │   │
│  │  │ 稳定性 100%  │ 稳定性 95%   │ 稳定性 50%   │       │   │
│  │  └──────────────┴──────────────┴──────────────┘       │   │
│  │  输出: { data, completeness, gaps, sourceLayer }      │   │
│  └──────────────────────┬───────────────────────────────┘   │
│                         │                                    │
│  ┌──────────────────────▼───────────────────────────────┐   │
│  │              模式 2: 重试 + 优雅降级                  │   │
│  │                                                       │   │
│  │  executeWithResilience(config)                        │   │
│  │  ┌──────────┬──────────┬──────────┬─────────┐        │   │
│  │  │ Layer 1  │ Layer 2  │ Layer 3  │ 用户    │        │   │
│  │  │ API 发现 │ HAR 回放 │ DOM 提取 │ 手动    │        │   │
│  │  └──────────┴──────────┴──────────┴─────────┘        │   │
│  │  输出: AttemptResult<T>（始终带 completeness）        │   │
│  └──────────────────────┬───────────────────────────────┘   │
│                         │                                    │
│                         ▼                                    │
│  ┌──────────────────────────────────────────────────────┐   │
│  │                  结构化输出                            │   │
│  │                                                       │   │
│  │  {                                                    │   │
│  │    data: {...},                                       │   │
│  │    completeness: 'full' | 'partial' | 'unavail',      │   │
│  │    gaps: ['缺少 X', '无法获取 Y'],                    │   │
│  │    sourceLayer: 'api-discovery' | 'har-replay' | 'dom',│   │
│  │    confidence: 'high' | 'medium' | 'low',             │   │
│  │    evidence: ['api-response.json', 'screenshot.png']  │   │
│  │  }                                                    │   │
│  └──────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────┘
```

### 5.2 新 Skill 开发清单

基于以上三个模式，构建一个新的浏览器自动化类 Skill 只需要：

```
1. 写一个 SKILL.md（描述触发条件、工具权限、输出契约）
2. 配置 IAuthProvider（选择一个认证实现 or 新建一个）
3. 分析目标系统类型：
   ├─ 现代 SPA（React/Vue/Angular）→ 优先 Layer 1: 打开 DevTools → 找到 JSON API
   ├─ 有 GraphQL endpoint → Layer 1: 提取 query template
   └─ 无 API（遗留系统、Canvas、WebSocket）→ 跳到步骤 5
4. 配置 apiDiscovery（urlPattern + triggerActions → 提取请求签名）
5. 配置 domExtraction（声明式 ExtractionRule[]，每个字段至少 2 个备选选择器）
6. 配置 ResilienceConfig（降级链：Layer 1 → Layer 2 → Layer 3 → 用户手动提供）
7. 组合调用：
   authResult = ensureAuth(url)                         # 模式 1：获取登录态
   dataResult = executeBrowserSkill(config)             # 模式 3：优先 API，DOM 兜底
   finalResult = executeWithResilience(resilienceConfig) # 模式 2：多策略降级
```

### 5.3 与现有学习文档的关系

| 本文档 | `learning.md` |
|--------|--------------|
| 专注于"怎么做"（设计模式实现） | 专注于"是什么"（功能、架构、流程） |
| 提取可复用的通用组件 | 分析 hera-slow-api-analyzer 的具体设计 |
| 给出可直接使用的代码蓝图 | 给出整体性的 Checklist 和测验 |
| 三个正交模式，独立可学 | 端到端流程，一次性理解 |

**建议阅读顺序**：先读 `learning.md` 理解技能全貌 → 再读本文档理解可复用模式 → 最后做 `quiz.md` 检验理解。

---

## 六、扩展阅读：值得进一步研究的模式

以下模式在分析中也有发现，但不属于本次三个重点，列在此处供后续深入研究：

| 模式 | 来源 | 一句话描述 |
|------|------|-----------|
| **检查点系统** | `ticket-troubleshoot-v3` | 复杂工作流的关键节点保存状态，失败时可从最近的检查点恢复 |
| **案例库** | `ticket-troubleshoot-v3` | 将过去的诊断结果结构化存储，新问题先做相似案例检索 |
| **输出契约** | `ticket-troubleshoot-v3` | 定义技能的固定输出格式（根因/证据/置信度），确保下游可消费 |
| **Fail-Closed** | `ticket-troubleshoot-v3` | 不确定性高时宁可"不知道"也不给错误结论 |
| **行为约束 Meta-Skill** | `continuous-execution-guard` | 不提供操作指令，而是约束 Agent 的执行行为 |
| **双层审查循环** | `writer-reviewer` | Writer 写 → Reviewer 审 → 不通过则 Writer 修改 → 再审查 |

---

## 附录 A：术语表

| 术语 | 英文 | 解释 |
|------|------|------|
| 登录即服务 | Login-as-a-Service | 登录功能作为独立可调用的技能，不嵌入业务逻辑 |
| 预检缓存 | Pre-flight Cache Validation | 在启动浏览器前静默检测 session 是否有效 |
| 语义定位 | Semantic Selector | 按元素的语义属性（角色、文本、标签）而非 DOM 路径定位 |
| 双信号检测 | Dual-Signal Completion | 同时监听两个完成信号，用 Promise.race 取先触发的那个 |
| 三态枚举 | DataCompleteness | FULL（完整）/ PARTIAL（部分）/ UNAVAILABLE（无数据） |
| 降级链 | Degradation Chain | 有序的备选策略列表，当前策略失败时自动尝试下一个 |
| 结构化返回契约 | Structured Return Contract | 技能间通信的固定数据格式，确保调用方能可靠解析 |
| 渐进式分析 | Progressive Analysis | 有多少数据分析多少，不因部分缺失而放弃全部 |
| 输出契约 | Output Contract | 技能产出的固定格式定义（含根因状态、证据级别、置信度） |
| 行为约束技能 | Behavior-Constraint Meta-Skill | 不提供操作指令，而是修改 Agent 执行行为的技能 |
| API 发现 | API Discovery | 通过监听浏览器网络请求发现前端调用的后端 API 端点 |
| 网络拦截 | Network Interception | 使用 `page.route()` 拦截/修改/记录浏览器中的所有网络请求 |
| HAR 录制回放 | HAR Record & Replay | 录制 HTTP Archive 文件，后续通过 `routeFromHAR` 在无网络环境下重放 |
| 防御性 DOM 提取 | Defensive DOM Extraction | 每个字段配置多个备选选择器 + 必填字段验证 + 失败自动截图 |
| 静默失败 | Silent Failure | HTTP 200 + `null` data — 不抛错但数据丢失，比报错更危险的失败模式 |
| 选择器断裂 | Selector Breakage | 前端 UI 改版导致 CSS 选择器/文本定位失效 |

---

## 附录 B：源技能关键指标对比

| 指标 | hera-slow-api-analyzer | dayu-cas-login |
|------|----------------------|----------------|
| SKILL.md 行数 | 510 | 48 |
| 附加文件 | API_REFERENCE.md, feishu-report-template.md, tables.md | scripts/cas_login_checker.js (136 行) |
| 文件架构 | 扁平（全部在根目录） | 分层（SKILL.md + scripts/） |
| 公司依赖数 | 4（Hera, CAS, 飞书, Intl-Retail） | 1（CAS） |
| 可独立测试 | ❌（需要 Hera 环境） | ⚠️（需要 CAS 环境） |
| 技能耦合 | 依赖 dayu-cas-login | 被 hera-slow-api-analyzer 依赖 |
| 设计焦点 | 端到端完整流程 | 单一职责（登录） |
