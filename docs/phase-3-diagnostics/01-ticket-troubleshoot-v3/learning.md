# ticket-troubleshoot-v3 — 深度学习文档

> 对应 SKILL.md: `/root/.opencode/skills/ticket-troubleshoot-v3/SKILL.md` (409行)
>
> 原实现仓库: `/mnt/d/测试项目/vibe-hubs/skill/ticket-troubleshoot-v3/`

---

## 一、功能全景

### 一句话定位
**线上工单排障引擎** — 7 步流水线 + 经验库复用 + 输出契约 + 中断恢复，按固定结构产出诊断结论。

### 核心流程

```
用户描述问题
    ↓
[§4 入口] 系统选择菜单（唯一中断点1）
    ↓
[§5 排查主线]
  Step 1: 历史案例预检（经验库匹配）
    ├─ 高置信 → 快速复用路径 → 直达 Step 6
    ├─ 中置信 → 作为假设参考 → 继续 Step 2
    └─ 未命中 → 继续 Step 2
  Step 2: 补齐问题上下文（结构化摘要 + 排查计划）
  Step 3: 代码定位（接口路径、调用链、候选表名）
    ├─ 满足跳过条件 → 跳过 Step 4/5
    └─ 需要数据验证 → 继续 Step 4
  Step 4: 整理 SQL（需三项验证：表名/数据源/不确定时自查）
  Step 5: 数据库查询（MCP，retry ≤3）
  Step 6: 根因分析与结论输出（简版/详版两层）
  Step 7: 结案回写（唯一等待用户输入的步骤）
```

---

## 二、架构设计分析

### 2.1 文件分层架构

```
ticket-troubleshoot-v3/
├── SKILL.md              # 主控文件：原则、流程、契约、护栏
├── config/
│   ├── service.md        # 系统配置增删改流程
│   ├── cli-adapter.md    # init.py CLI 调用规范
│   └── init.py           # 配置管理可执行脚本
├── templates/
│   └── output.md         # 3 类输出模板（简版/详版/回写）
├── references/
│   ├── sql-rules.md      # 判库判表优先级规则
│   └── troubleshoot-examples.md  # 3 个完整排查示例
└── golden-cases/         # 回归测试用例
    ├── GC-001-full-troubleshoot.md
    ├── GC-002-case-reuse.md
    ├── GC-003-partial-success.md
    └── README.md
```

**设计思想**: SKILL.md 是"宪法"（原则+流程），子文件是"法律细则"（具体规则+模板）。这种分层让 SKILL.md 保持 409 行的可读性，同时规则可以无限细化而不影响主线。

### 2.2 Pipeline 设计

```text
Step 1 ──→ Step 2 ──→ Step 3 ──→ Step 4 ──→ Step 5 ──→ Step 6 ──→ Step 7
  │                                               │
  └── 高置信复用：跳到 Step 6                      └── 满足跳过条件：跳到 Step 6
```

**关键设计决策**:
1. **允许跳跃但不允许回退** — 快速路径是设计亮点，避免了"所有工单都走完整流程"的低效
2. **Step 6 是唯一交付点** — 无论哪条路径，最终都必须经过 Step 6 的契约校验
3. **Step 7 是唯一的异步等待点** — 回写需要人工确认，其他步骤零中断

### 2.3 Checkpoint 机制

```
每步完成 → 写 RUNS_DIR/<run_id>.json
                ↓
          包含：current_step, step_results, evidence, next_action
                ↓
中断后恢复 → 读 checkpoint → 校验 current_step → 续跑
```

**核心数据结构**:
```json
{
  "run_id": "2026-04-23-001",
  "current_step": 3,
  "step_results": {
    "step_1": { "status": "success", "case_hits": [], "confidence": "miss" },
    "step_2": { "status": "success", "context": {} },
    "step_3": { "status": "in_progress", "code_paths": [] }
  },
  "evidence": [
    { "type": "code", "path": "OrderMapper.xml:42" }
  ],
  "next_action": "执行步骤 4"
}
```

---

## 三、设计模式深度分析

### 3.1 Output Contract（输出契约）— 最重要的设计

这不是简单的"输出格式要求"，而是一个**可机器校验的形式化契约**：

```yaml
status: success | partial_success | failed   # 三态强制选择
summary: 一句话结论（≤30 字）
problem: 业务语言描述（≤50 字）
root_cause: 因果链（业务语言，≤80 字）
data_verified: 查库结果业务语言转述 | null
evidence:
  code_paths: [文件路径:行号]
  sql_results: [{ db, table, matched_rows }]
confidence: high | medium | low
restricted_info: []
meta:
  contract_version: "3.0.0"  # 契约版本号
```

**为什么这是革命性的设计**：

1. **契约冻结** — 进入 Step 2 后 `contract_version` 不得漂移。这解决了 LLM 在长对话中"输出格式逐渐退化"的经典问题
2. **Fail-Closed** — 关键字段缺失时强制 `partial_success` 或 `failed`，禁止伪装 `success`。这是安全工程的"默认拒绝"原则
3. **受限信息显式化** — `restricted_info` 数组让"我不知道"变成了结构化信息，而不是被隐藏
4. **版本化管理** — `contract_version` 意味着如果契约需要升级，旧版本的运行应该被拒绝

### 3.2 经验库复用（Case Reuse）

```
CASES_DIR/
├── INDEX.md           # 案例索引
├── CASE-001.md        # 案例 1
├── CASE-002.md        # 案例 2
└── SOP-{类型名}.md     # 标准操作流程
```

**两轮检索策略**:
1. 第一轮：精确匹配 frontmatter (`ticket_type + trigger_route + system`)
2. 第二轮：模糊匹配现象关键词 (`related_tables` / `key_business_ids`)

**复用判断逻辑**:
| 置信度 | 条件 | 处理 |
|--------|------|------|
| 高 | 现象+接口+表完全匹配且已验证 | 最小验证 → 直达 Step 6 |
| 中 | 相似但不完全一致 | 摘要作为假设 → 进 Step 2 |
| 未命中 | — | 直接进 Step 2 |

### 3.3 Golden Cases（回归测试）

```
golden-cases/
├── GC-001  →  完整排查（success）
├── GC-002  →  快速复用（success，跳过步骤）
└── GC-003  →  配置缺失（partial_success）
```

每个 Golden Case 包含：
- 预置条件（CONFIG_FILE 状态、经验库状态）
- 用户对话序列
- 预期 AI 输出（status、关键字段、中断行为）

**这是 Skill 的单元测试** — 修改 SKILL.md 后运行 GC，验证行为是否退化。

### 3.4 四层验证体系

```
L1 工具返回验证  ←  贯穿 Step 3/5（exit code, HTTP 状态）
L2 步骤契约验证  ←  每步结束（输入/输出 schema）
L3 业务逻辑验证  ←  Step 3/5 后（代码行号可达、SQL 能查到行）
L4 最终输出验证  ←  Step 6 前（符合 Output Contract）
```

**每一层失败的处理**:
- L1/L2 失败 → 回当前步补齐
- L3 失败 → 换证据或换库
- L4 失败 → 回退到最近可修复步骤，超过 2 轮 → failed

### 3.5 熔断机制（Stop-the-line）

5 个强制停止条件：
1. 用户未选系统即开始排查
2. Output Contract 冻结后字段含义改变
3. 检测到 No Invention 违规（脑补数据）
4. Checkpoint 损坏
5. 数据查询连续 3 次 500 错误

---

## 四、优秀设计亮点

### ⭐ 亮点 1：零中断设计 + 精确的中断白名单

绝大部分排查过程"一口气完成"，只有两个允许中断的点：
- 系统选择菜单（必须等用户选）
- 回写确认（必须等用户确认）

其他所有情况（信息不足、表名不确定、代码搜不到）都**不中断**，而是标注 `restricted_info` 继续。这解决了"AI 排查到一半停下来问用户"的经典痛点。

### ⭐ 亮点 2：No Invention 原则的落地

不只是口号，而是有一整套机制：
- §7.4 列出 4 条禁止项
- §9 Stop-the-line 将违规作为熔断条件
- L3 业务逻辑验证检查"代码行号是否可达"
- SQL 输出前必须通过三项验证（表名来源、数据源来源、不确定时自查）

### ⭐ 亮点 3：Checkpoint 让长流程可恢复

对于 7 步的排查流程，中断是不可避免的。Checkpoint 机制让中断变成"暂停"而不是"失败"：
- 独立文件存储（不依赖 LLM 记忆）
- 24h TTL（防止过期数据污染）
- 恢复协议（校验 current_step、询问续跑、已完成步骤只读复用）

### ⭐ 亮点 4：回写机制的"先草稿后确认"模式

Step 7 不自动写入经验库，而是：
1. 生成草稿（按模板填充 YAML frontmatter + 正文）
2. 用户确认
3. 采集验证人（`verified_by` 不得留空）
4. 优先更新已有案例，避免重复

这体现了"AI 建议 + 人做决策"的协作模式。

### ⭐ 亮点 5：工具调用预算（§8.2）

```
Step 3: ≤5 次工具调用（关键词搜索 + 文件读取）
Step 4: ≤3 次（list_tables / table_struct）
Step 5: ≤N 次（N = 候选 SQL 条数）
```

这不是 LLM 能自动遵守的，但作为设计意图表达了"应该限制搜索深度"的思想。

---

## 五、公司依赖分析 + 通用化方案

### 5.1 依赖清单

| 依赖 | 类型 | 用途 | 通用化难度 |
|------|------|------|-----------|
| `zeus-devx-database` MCP | MCP 工具 | 线上数据库查询 | ⭐⭐ (可替换) |
| `~/.config/ticket-troubleshoot/config.json` | 配置文件 | 系统-数据库映射 | ⭐ (纯配置) |
| `~/.config/ticket-troubleshoot/cases/` | 文件目录 | 经验库存储 | ⭐ (纯文件) |
| `~/.config/ticket-troubleshoot/runs/` | 文件目录 | Checkpoint 存储 | ⭐ (纯文件) |
| `config/init.py` | Python 脚本 | 配置管理 CLI | ⭐ (独立脚本) |
| Zeus 平台 URL | URL 模板 | 数据库配置来源 | ⭐⭐ (需替换) |

### 5.2 抽象接口设计

```typescript
// 核心抽象：数据库查询
interface IDatabaseQuery {
  listTables(databaseId: string): Promise<string[]>;
  tableStruct(databaseId: string, tableName: string): Promise<ColumnDef[]>;
  queryData(databaseId: string, sql: string): Promise<QueryResult>;
}

// 适配器：MySQL 直连
class MySQLAdapter implements IDatabaseQuery { ... }

// 适配器：PostgreSQL 直连
class PostgresAdapter implements IDatabaseQuery { ... }

// 适配器：通过 HTTP API（兼容原 zeus 模式）
class HTTPDatabaseAdapter implements IDatabaseQuery { ... }
```

### 5.3 配置结构通用化

原始配置：
```json
{
  "projects": {
    "intl-retail": {
      "backend_repos": [{
        "databases": [{
          "dashboard_id": "62014",  // ← Zeus 特有字段
          "proxy": "gaea"           // ← Zeus 特有字段
        }]
      }]
    }
  }
}
```

通用化后：
```yaml
# config.yaml
projects:
  my-project:
    backend_repos:
      - name: order-service
        path: /path/to/repo
        databases:
          - label: 主库
            adapter: mysql           # 适配器类型
            connection:              # 通用连接信息
              host: localhost
              port: 3306
              database: order_db
```

---

## 六、可改进点

### 6.1 ⚠️ 工具调用预算不可执行

§8.2 定义了每步的工具调用预算（如 Step 3 最多 5 次），但 LLM 无法自我计数。改进方案：
- 在 Checkpoint 中记录 `tool_call_count`
- 每次工具调用后自增计数器
- 达到预算后自动熔断

### 6.2 ⚠️ 经验库检索效率

当前是文件级别的 `rg` 搜索，案例多时性能堪忧。改进方案：
- 使用向量嵌入（embedding）做语义匹配
- 支持跨案例的相似度排序
- 案例自动去重

### 6.3 ⚠️ Golden Cases 数量不足

只有 3 个 GC，覆盖不够全面。应增加：
- GC-004: 多候选未收敛 → partial_success
- GC-005: 经验库命中但验证失败 → 退回到 Step 2
- GC-006: Checkpoint 恢复场景

### 6.4 ⚠️ 缺少跨 Skill 协作机制

当前通过 NOT-for 边界声明职责分离，但没有"一个 Skill 调用另一个 Skill"的机制。例如：
- `ticket-troubleshoot` 识别到 SQL 慢查询 → 自动委托 `sql-review`
- `ticket-troubleshoot` 识别到性能问题 → 自动委托 `hera-slow-api-analyzer`

### 6.5 ⚠️ 多语言支持缺失

当前硬编码了 Java/MyBatis-Plus 的判表规则。通用化时应该：
- 判表规则按语言/框架可插拔
- Python/Django ORM、Go/GORM、Rust/Diesel 各一套规则

---

## 七、量化质量指标

| 维度 | 指标 | 测量方法 | v3 基准 | 目标 |
|------|------|---------|---------|------|
| **完整性** | Golden Case 通过率 | 修改后运行全部 GC | 3/3 | 100% |
| **可靠性** | Checkpoint 恢复成功率 | 模拟中断后恢复 | - | 100% |
| **安全性** | Fail-Closed 触发准确率 | 不应 success 但标记了 success 的比例 | - | 0% |
| **效率** | 平均步骤数（完整排查） | 统计 Step 轨迹 | ~7 | ≤7 |
| **效率** | 快速路径命中率 | 有经验库时的复用率 | - | ≥50% |
| **可迁移性** | 平台硬编码数量 | 搜索 URL/平台名 | ~3 | 0 |
| **可测试性** | GC 覆盖的场景数 | GC 数量 × 场景类型 | 3 | ≥10 |
| **可观测性** | Checkpoint 覆盖步骤数 | 有 checkpoint 的步骤数 | 7/7 | 7/7 |

---

## 八、复刻要点 Checklist

- [ ] 理解 7 步 Pipeline 的每一步输入/输出
- [ ] 理解 Output Contract 的三种终态（success/partial_success/failed）
- [ ] 理解 Fail-Closed：什么时候必须降级
- [ ] 理解 No Invention：4 条禁止项
- [ ] 理解 Checkpoint 的数据结构和恢复协议
- [ ] 理解经验库的两轮检索策略
- [ ] 理解 Golden Cases 的作用和编写方法
- [ ] 能设计 `IDatabaseQuery` 抽象接口
- [ ] 能设计配置文件的通用化结构
- [ ] 能编写至少 3 个 Golden Case
