# api-flow 设计规格书

> 版本: v0.2 | 日期: 2026-07-17 | 状态: 待审阅
> 语言: 简体中文
> 
> v0.2 变更: 文件分离（YAML 编排 + JSON 用例 + SQL 脚本）、纯 SKILL 工作流（去掉 CLI 暴露）、每用例单 checkpoint、单条失败 retry 机制

---

## 0. 概述

### 0.1 项目定位

`api-flow` 是一个独立工具，自动分析 Java/Spring Boot 代码 → 生成多分支测试用例和输入数据 → 逐条展示给用户确认 → 逐条自动化触发 API → 人工验证响应结果 → 自动清理数据。

**核心解决什么问题**：帮助测试/开发人员自动触发接口，难点是"提供跑通流程所需的输入数据（表单数据、依赖的配置数据等）"，然后回滚数据保证无污染。

### 0.2 与 api-test 的关系

- **不继承不复用**，独立新工具
- 底层共享 gitnexus（代码分析）和 MySQL MCP（数据准备/清理）
- 鉴权复用 api-test Phase 0 的 project-test-context.md 机制
- api-test 关注"单接口的快速 test case"，api-flow 关注"多分支的端到端流程触发"

### 0.3 核心理念

1. **不自动验证数据正确性**——跑通流程即算通过，验证交给人工
2. **数据合理级别 C 级**（规则推断级），用 gitnexus 分析校验逻辑，推断需要什么数据
3. **自动清理**，每条用例执行完立即回滚数据，不需要用户确认
4. **每组用例独立执行**（prepare → run → cleanup），不共享数据，不互相污染
5. **纯对话式工作流**——用户只需提供 API 入口，全程通过对话交互，无需记忆 CLI 命令

### 0.4 用户交互模型

```
用户: "帮我生成订单创建流程的测试用例"
  ↓
Phase 1: AI 分析代码，生成全部用例文件（YAML + JSON + SQL）
         → 摘要表格展示，用户审阅，修改/确认
  ↓
Phase 2: 逐用例 for 循环
         每条用例 1 次 checkpoint（确认执行）
         → 自动执行（prepare → request → cleanup）
         → 展示模板化结果（响应 JSON + 耗时）
         → 用户验证结果是否正确
         → 循环下一条
```

---

## §1 架构总览

### 1.1 纯 SKILL 架构

```
┌─────────────────────────────────────────────────────────┐
│                      SKILL.md                           │
│               用户唯一入口：对话即操作                     │
│                                                         │
│  Phase 1 — analyze（AI 负责）                           │
│  gitnexus 分析代码 → 生成 YAML + JSON + SQL 文件         │
│  依赖: gitnexus, MySQL MCP                              │
│                                                         │
│  Phase 2 — execute（Agent 调用 Python engine）           │
│  逐用例: checkpoint 确认 → prepare → request → cleanup   │
│  Python engine 作为内部库被 import，用户不直接接触         │
│                                                         │
│  Phase 3 — report（Agent 输出模板化报告）                │
│  每条用例 → tc-*.md    汇总 → summary.md                 │
└─────────────────────────────────────────────────────────┘
```

### 1.2 职责划分

| 层级 | 职责 | 技术 |
|------|------|------|
| AI（SKILL.md 编排） | 代码分析、分支识别、用例生成、用户交互、结果展示 | gitnexus + LLM |
| Python 执行引擎 | 文件解析、变量替换、SQL 执行、HTTP 请求、重试逻辑 | Python 3 + PyMySQL + requests |
| 契约层 | YAML 编排文件 + JSON 用例文件 + SQL 脚本 | 文件系统 |

### 1.3 Python engine 定位

Python engine **不是 CLI 工具**，是 Agent 内部调用的执行库。用户永远不直接执行 `api-flow run`。

Agent 在 Phase 2 中：
1. `import` engine 模块
2. 逐条调用 engine 的单个用例执行函数
3. 拿到返回结果后，按模板格式展示给用户
4. 等待用户人工验证后，继续下一条

---

## §2 文件结构与数据格式

### 2.1 文件目录结构

```
docs/api-flow/
└── 订单创建流程/                          # 每个 flow 一个子目录
    ├── flow.yaml                          # 编排层：元数据 + 鉴权 + 用例引用
    ├── tc-001.json                        # 单条用例：scenario, branch, request, extract
    ├── tc-001-prepare.sql                 # 数据准备 SQL（用户可直接查看/修改）
    ├── tc-001-cleanup.sql                 # 回滚 SQL（用户可直接查看/补充）
    ├── tc-002.json
    ├── tc-002-prepare.sql
    ├── tc-002-cleanup.sql
    ├── tc-003.json                        # expect_error 用例，无需 SQL 文件
    └── results/
        ├── run-20260717-143000/
        │   ├── tc-001.md                  # 单条结果（模板化输出）
        │   ├── tc-002.md
        │   ├── tc-003.md
        │   └── summary.md                 # 汇总报告（模板化输出）
        └── run-20260717-153000/
            └── ...
```

### 2.2 flow.yaml — 编排层（精简）

仅包含元数据、鉴权配置、用例引用列表。不含测试用例内容。

```yaml
name: "订单创建流程"
description: "覆盖 POST /api/orders 的所有业务分支"
base_url: "http://localhost:8080"

auth:
  type: oauth2
  token_url: "http://localhost:8080/oauth/token"
  client_id: "test-client"
  client_secret: "${OAUTH_SECRET}"
  username: "test_admin"
  password: "test123"

# ── 用例引用（不含内容，内容在独立文件中）──
cases:
  - id: tc-001
    file: tc-001.json
    prepare: tc-001-prepare.sql       # 相对路径，可空
    cleanup: tc-001-cleanup.sql
  - id: tc-002
    file: tc-002.json
    prepare: tc-002-prepare.sql
    cleanup: tc-002-cleanup.sql
  - id: tc-003
    file: tc-003.json
    # 无 prepare/cleanup = expect_error 用例

# ── 依赖分析（AI 得出，供审阅）──
dependencies:
  - table: users
    reason: "需要 VIP 和 NORMAL 两种等级的用户"
    fields: [id, name, level]
  - table: products
    reason: "需要电子和图书两种类别的商品"
    fields: [id, name, category, price, stock]
  - table: coupons
    reason: "需要满减券用于折扣分支"
    fields: [id, code, type, amount, min_order]

# ── 忽略字段 ──
ignore_response_fields:
  - "*.createTime"
  - "*.updateTime"
  - "*.timestamp"
  - "*.requestId"

# ── 疑似隐藏分支 ──
suspected_branches:
  - source: "com.example.aop.OrderLogAspect"
    type: "AOP 拦截器"
    hint: "@Around 织入了 orderService.create()，可能产生额外副作用"
  - source: "com.example.listener.OrderEventListener"
    type: "事件监听器"
    hint: "订单创建后异步发送通知，可能影响消息队列状态"

# ── 全局兜底清理（可选）──
global_cleanup:
  - "DELETE FROM order_items WHERE order_id LIKE 'ORD-%'"
  - "DELETE FROM orders WHERE id LIKE 'ORD-%'"
  - "DELETE FROM coupons WHERE code LIKE 'TEST-%'"
  - "DELETE FROM products WHERE name LIKE '测试%'"
  - "DELETE FROM users WHERE name LIKE '测试%'"
```

### 2.3 flow.yaml 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | string | 流程名称，用于报告标题 |
| `description` | string | 流程描述（可选） |
| `base_url` | string | 目标服务 base URL |
| `auth` | object | 鉴权配置 |
| `cases` | array | **用例引用列表**（不含内容） |
| `cases[].id` | string | 用例唯一标识 |
| `cases[].file` | string | 用例 JSON 文件相对路径 |
| `cases[].prepare` | string | prepare SQL 文件相对路径（可空） |
| `cases[].cleanup` | string | cleanup SQL 文件相对路径（可空） |
| `dependencies` | array | 依赖表分析，供人工审查 |
| `ignore_response_fields` | array | JSONPath 通配符，响应中忽略这些字段 |
| `suspected_branches` | array | 疑似隐藏分支警告 |
| `global_cleanup` | array | 全局兜底清理 SQL（手动执行用） |

### 2.4 tc-*.json — 单条用例内容

```json
{
  "id": "tc-001",
  "scenario": "VIP用户购买电子产品（单价7000），使用满减券300-50，验证折后金额=6950",
  "branch": "user.level == VIP && product.category == ELECTRONICS && amount >= coupon.min",
  "priority": "high",
  "expect_error": false,
  "request": {
    "method": "POST",
    "url": "/api/orders",
    "headers": {
      "Authorization": "{{AUTH_TOKEN}}",
      "Content-Type": "application/json"
    },
    "body": {
      "userId": "{{@uid_001}}",
      "items": [
        {
          "productId": "{{@pid_001}}",
          "quantity": 1
        }
      ],
      "couponCode": "{{@cid_001}}"
    }
  },
  "extract": {
    "orderId": "$.data.orderId"
  }
}
```

### 2.5 tc-*-prepare.sql — 数据准备脚本

```sql
-- tc-001: VIP用户购买电子产品（单价7000），使用满减券
-- 依赖表: users, products, coupons
-- 外键顺序: users → products → coupons → orders（prepare）
--            order_items → orders → coupons → products → users（cleanup）

INSERT INTO users (id, name, level) VALUES (UUID(), '测试VIP-A', 'VIP');
SET @uid_001 = LAST_INSERT_ID();

INSERT INTO products (id, name, category, price, stock) VALUES (UUID(), '测试笔记本', 'ELECTRONICS', 7000, 100);
SET @pid_001 = LAST_INSERT_ID();

INSERT INTO coupons (id, code, type, amount, min_order) VALUES (UUID(), 'TEST-F50', 'FULL_REDUCTION', 50, 300);
SET @cid_001 = LAST_INSERT_ID();
```

### 2.6 tc-*-cleanup.sql — 回滚脚本

```sql
-- tc-001 回滚: 按 FK 逆序删除（先子表后父表）
DELETE FROM order_items WHERE order_id = '{{@orderId}}';
DELETE FROM orders WHERE id = '{{@orderId}}';
DELETE FROM coupons WHERE id = '{{@cid_001}}';
DELETE FROM products WHERE id = '{{@pid_001}}';
DELETE FROM users WHERE id = '{{@uid_001}}';
```

### 2.7 变量传递机制

```
prepare SQL → SET @uid = LAST_INSERT_ID()  → runtime_vars["uid"] = "abc123"
request body → "userId": "{{@uid}}"        → 替换为 "abc123"
response extract → $.data.orderId          → runtime_vars["orderId"] = "ORD-001"
cleanup SQL → "WHERE id = '{{@orderId}}'"  → 替换为 "ORD-001"
```

**保留变量**（engine 自动注入）：
- `{{AUTH_TOKEN}}`：鉴权 token

---

## §3 代码分析 & 测试用例生成（Phase 1: analyze）

### 3.1 分析流程

```
用户输入：POST /api/orders  或  com.example.controller.OrderController.createOrder()

① 发现入口
   gitnexus → OrderController.createOrder()

② 追踪调用链（≤ 3 层）
   Layer 1: Controller → Service
   Layer 2: Service → UserService, ProductService, OrderRepository
   Layer 3: Repository → SQL 语句
   超出 3 层 → 截断 + 标记 max_depth_exceeded

③ 扫描分支
   对每层代码逐行扫描：
   - @Valid          → 参数校验分支
   - if/else/switch  → 业务逻辑分支
   - throw            → 异常分支
   - @Transactional   → 事务边界（不展开，写入 suspected_branches）

④ 生成测试用例
   - 同一路径上的分支 → 合并到一个用例
   - 不同路径上的分支 → 各自一个用例
   - 同层兄弟分支     → 各自一个用例
   - 去重             → 相同分支模式只保留一个代表

⑤ 生成 prepare SQL → 保存为 tc-*-prepare.sql
   - 分析分支条件的字段来源 → 确定依赖表
   - NOT NULL 字段填默认值
   - 唯一约束用 UUID() 或 CONCAT
   - 外键用上层变量引用
   - 业务字段从分支条件反推
   - 文件头注释：依赖表、FK 顺序

⑥ 生成 request body → 保存为 tc-*.json
   - 复刻 Controller DTO 结构
   - 变量替换为 {{@var}}
   - 条件分支中缺失的字段不生成

⑦ 生成 cleanup SQL → 保存为 tc-*-cleanup.sql
   - FK 逆序生成
   - 文件头注释：涉及的表、级联提示

⑧ 生成 flow.yaml → 编排引用
   - 展示摘要表格给用户审阅
```

### 3.2 AI 生成 prepare/cleanup SQL 后的自检

生成完成后，AI 自动检查：

| 检查项 | 说明 |
|--------|------|
| 外键顺序 | INSERT 先父表后子表，DELETE 先子表后父表 |
| 危险操作 | 禁止 DROP TABLE / TRUNCATE / DELETE 无 WHERE |
| 变量引用 | `{{@var}}` 是否都有对应的 SET 语句 |
| 级联遗漏 | 扫描 DB 外键约束，提示可能遗漏的级联删除 |

### 3.3 分支识别规则

| 代码模式 | 识别为 | 处理方式 |
|----------|--------|----------|
| `@Valid` / `@NotNull` / `@NotEmpty` | 参数校验分支 | 生成 expect_error=true 的用例 |
| `if (condition)` | 业务分支 | 生成 true/false 两个用例 |
| `switch (expr)` | 多路分支 | 每个 case 一个用例 |
| `throw new ...` | 异常分支 | 生成 expect_error=true 的用例 |
| `@Aspect` / `@Around` | AOP 拦截器 | 不展开，写入 suspected_branches |
| `@EventListener` | 事件监听器 | 不展开，写入 suspected_branches |
| `@Transactional` | 事务边界 | 不展开，写入 suspected_branches |
| `@Value` / `DictService` | 配置/字典读取 | 标记在 prepare SQL 注释中提醒用户 |

### 3.4 Phase 1 输出格式（摘要表格）

生成全部文件后，展示给用户：

```
生成目录: docs/api-flow/订单创建流程/

用例清单:
  ✅ tc-001  VIP用户购买电子产品，使用满减券           [high]   2 表 / 2 条清理
  ✅ tc-002  普通用户购买图书，无优惠券                 [high]   2 表 / 2 条清理
  ✅ tc-003  缺少 items 字段，参数校验                  [medium] 无数据
  ✅ tc-004  产品不存在                                [high]   无数据
  ✅ tc-005  库存不足                                  [medium]  2 表 / 2 条清理
  ✅ tc-006  用户不存在                                [high]   无数据

⚠️  suspected: @EventListener 可能触发通知、@Transactional 可能回滚

各用例的 prepare SQL 和 cleanup SQL 已保存为独立文件，可直接检查修改。
确认无误输入"开始执行"，或输入用例编号修改。
```

### 3.5 局限性处理

| 情况 | 处理方式 |
|------|---------|
| 调用链 > 3 层 | 截断，标记 `max_depth_exceeded` |
| 嵌套 > 5 层 | 截断，标记 "嵌套深度超出，未覆盖分支可能遗漏" |
| AOP / 事件监听器 / 事务 | 不展开，写入 `suspected_branches` |
| 配置/字典值 | 硬编码默认值 + SQL 注释提醒 |
| 搜索结果过多 | 只取当前模块、当前包路径，过滤无关结果 |

---

## §4 执行流程（Phase 2: execute）

### 4.1 执行模型：逐用例 for 循环

```
Phase 1 审阅完成，用户确认"开始执行"
  ↓
┌─ for 每条用例 ─────────────────────────────────┐
│                                                │
│ ① checkpoint（1 次确认，展示即将执行的内容）    │
│    - 用例 ID + 场景描述                         │
│    - 影响哪些表（来自 prepare SQL）             │
│    - request method + URL + body                │
│    - cleanup 概况（回滚哪些表）                 │
│    用户确认 → 继续 / 用户拒绝 → skip            │
│                                                │
│ ② 执行（全自动，中间不中断）                    │
│    2a. prepare → 执行 SQL，捕获变量             │
│    2b. request → 变量替换 → HTTP 请求           │
│    2c. cleanup → 变量替换 → 执行回滚 SQL        │
│                                                │
│    ┌ 失败处理 ──────────────────────────┐      │
│    │ DB 可重试错误（连接超时/死锁）       │      │
│    │  → 间隔 1s/2s/4s 重试，最多 3 次   │      │
│    │  → 仍失败 → cleanup → 全新 prepare  │      │
│    │  → 重试该用例，最多 3 次            │      │
│    │                                     │      │
│    │ DB 不可重试错误（语法/权限）         │      │
│    │  → 立即标记 FAILED，继续下一条       │      │
│    │                                     │      │
│    │ HTTP 错误（网络/5xx）               │      │
│    │  → 记录失败，继续下一条              │      │
│    │                                     │      │
│    │ 连续 3 条用例 FAILED → 中断全部      │      │
│    │ （基本确定 DB 挂了）                  │      │
│    └─────────────────────────────────────┘      │
│                                                │
│ ③ 展示结果（模板化 tc-*.md 格式）               │
│    - 响应 JSON + HTTP 状态码 + 耗时             │
│    - 用户验证："结果正确 / 结果异常"             │
│                                                │
│ ④ 人工验证后继续下一条                          │
│                                                │
└────────────────────────────────────────────────┘
  ↓
Phase 3: 输出 summary.md 汇总报告
```

### 4.2 Checkpoint 展示格式

每条用例执行前，展示以下信息供用户确认：

```
┌──────────────────────────────────────────────────┐
│ 🔜 [3/6] tc-003 — 库存不足                        │
│ 分支: product.stock < quantity                    │
│ 预期: expect_error = true（应返回 4xx）            │
│                                                   │
│ 📝 Prepare SQL (影响 products, users):            │
│   INSERT INTO product (id, name, stock, price)    │
│     VALUES (UUID(), '限量产品', 1, 999.00)         │
│   INSERT INTO user (id, name, credit)             │
│     VALUES (UUID(), '测试用户', 10000.00)          │
│                                                   │
│ 📤 Request:                                       │
│   POST /api/orders                                │
│   {"productId":"{{@pid}}","userId":"{{@uid}}",    │
│    "quantity":999}                                │
│                                                   │
│ 🧹 Cleanup: 自动回滚 2 张表                       │
│                                                   │
│ 确认执行？"y" 执行 / "s" 跳过 / "q" 中断全部      │
└──────────────────────────────────────────────────┘
```

### 4.3 执行模式

| 模式 | 行为 | 说明 |
|------|------|------|
| 遇错即停 | HTTP 业务失败立即停止后续用例 | 调试用 |
| 全部跑完（默认） | 失败标记错误，继续下一条 | 批量回归用 |

DB 层面的"遇错即停"由连续失败判定自动触发（见 4.1），不需要用户选择。

### 4.4 输出文件结构

```
docs/api-flow/订单创建流程/results/
└── run-20260717-143000/
    ├── tc-001.md       # 模板化单条结果
    ├── tc-002.md
    ├── tc-003.md
    └── summary.md      # 模板化汇总报告
```

### 4.5 模板化输出

#### tc-*.md 模板 — 单条用例结果

```markdown
## {{tc_id}} {{icon}} — {{scenario}}

| 项目 | 内容 |
|------|------|
| 分支 | {{branch}} |
| 优先级 | {{priority}} |
| 状态 | {{status_icon}} {{status_text}} |
| HTTP 状态码 | {{status_code}} |
| 耗时 | {{duration_ms}}ms |

### 请求

**{{method}}** `{{url}}`

```json
{{request_body_json}}
```

### 响应

```json
{{response_body_json}}
```

### 数据操作

**Prepare SQL**（{{prepare_count}} 条）:
```sql
{{prepare_sql}}
```

**Cleanup SQL**（{{cleanup_count}} 条）:
```sql
{{cleanup_sql}}
```
```

#### summary.md 模板 — 汇总报告

```markdown
# {{flow_name}} — 测试汇总

| 项目 | 内容 |
|------|------|
| 执行时间 | {{timestamp}} |
| 总用例数 | {{total}} |
| 通过 | {{passed}} |
| 失败 | {{failed}} |
| 跳过 | {{skipped}} |
| 总耗时 | {{total_duration_ms}}ms |

## 用例明细

| ID | 场景 | 状态 | HTTP | 耗时 |
|----|------|------|------|------|
{{#each results}}
| {{tc_id}} | {{scenario}} | {{status_icon}} | {{status_code}} | {{duration_ms}}ms |
{{/each}}

## 失败/异常

{{#each failures}}
### {{tc_id}} — {{scenario}}
- 错误: {{error}}
{{/each}}
```

---

## 附录 A：已决策的问题

| # | 问题 | 决策 |
|---|------|------|
| 1 | 输入数据来源 | 代码分析 + MySQL 造数据 |
| 2 | 数据合理级别 | C 级——规则推断级 |
| 3 | 测试用例隔离方式 | 每组独立 prepare → run → cleanup |
| 4 | 级联数据清理 | 显示 SQL + 提示 + 用户手动补充 |
| 5 | 鉴权注入 | 复用 api-test Phase 0 的 project-test-context.md |
| 6 | FK 依赖排序 | AI 按 FK 关系生成 SQL，engine 不做智能排序 |
| 7 | 重复执行 | AI 生成幂等 SQL（UUID() / WHERE NOT EXISTS） |
| 8 | 变量传递 | SET @var = ... → {{@var}}，engine 维护 runtime_vars |
| 9 | AOP/事件监听器 | 不自动分析，写入 suspected_branches |
| 10 | 配置/字典值 | 硬编码默认值 + 注释提醒 |
| 11 | 搜索深度限制 | Controller → Service 最大 3 层，超出截断 |
| 12 | 文件结构 | flow.yaml 仅编排引用，用例内容在 JSON + SQL 独立文件 |
| 13 | 工作流入口 | 纯 SKILL + Agent 对话，无 CLI 暴露 |
| 14 | 用例执行 checkpoint | 每条用例 1 次确认（展示即将执行的内容） |
| 15 | 单条失败处理 | cleanup → 全新 prepare → 重试该用例，最多 3 次 |
| 16 | DB 异常策略 | 可重试（3 次 backoff）→ 不可重试立即失败 → 连续 3 条失败全局中断 |
| 17 | 输出模板化 | tc-*.md 和 summary.md 全部模板化，保证输出稳定 |

## 附录 B：已知局限

1. AOP 织入、事件监听器、事务边界产生的隐藏副作用无法自动覆盖
2. 调用链超出 3 层、嵌套分支超出 5 层会截断
3. 配置表枚举值需人工确认
4. 级联数据清理依赖用户手动补充
5. 不自动验证响应数据正确性（由人工判断）
6. v0.1 不做 incremental resume（从头跑，cleanup 保证幂等）
7. 长流程接口单条重试仍有成本，v0.2 考虑更细粒度的 resume
