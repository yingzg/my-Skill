---
name: api-flow
description: API 流程测试工具。自动分析 Java/Spring Boot 代码，生成多分支测试用例和输入数据，逐条确认后批量触发 API 流程，人工验证响应结果，自动清理数据。当用户需要测试 API 接口流程、生成多分支测试用例、批量执行接口调用、或需要自动准备测试数据并清理时使用此 skill。
---

# api-flow

自动化 API 流程测试工具：分析代码 → 生成用例 → 逐条确认执行 → 数据清理。

## 核心概念

- **analyze**（Phase 1，AI 负责）：gitnexus 分析代码 → 识别分支 → 生成 flow.yaml + tc-*.json + tc-*-{prepare,cleanup}.sql
- **execute**（Phase 2，Agent 调用 Python engine）：逐用例 checkpoint 确认 → prepare → request → cleanup → 展示结果
- 每条用例独立执行，不共享数据，不互相污染
- **纯对话式**——用户不需要记忆任何命令

## 前置依赖

api-flow 依赖以下组件，skill 启动时会自动检测；任何缺失都会明确报错并给出修复指令。

### Python 包（cli/pyproject.toml 声明）

| 包 | 版本 | 用途 |
|---|---|---|
| `pyyaml` | ≥6.0 | 解析 flow.yaml 编排文件 |
| `pymysql` | ≥1.1.0 | 直连 MySQL 执行 prepare/cleanup SQL |
| `requests` | ≥2.31.0 | HTTP 客户端发起 API 调用 |
| `jsonpath-rw` | ≥1.4 | 响应体 JSONPath 提取（extract 指令） |
| `pytest`（dev） | ≥7.0 | 测试框架 |

### 外部工具

| 工具 | 说明 |
|---|---|
| `gitnexus` | 代码分析工具，用于 Phase 1 自动生成用例文件 |
| MySQL | 5.7+ 或 8.0+，用于 prepare/cleanup SQL 执行 |

### 环境变量

| 变量 | 说明 |
|---|---|
| `API_FLOW_DB_HOST` | MySQL 主机（默认 localhost） |
| `API_FLOW_DB_PORT` | MySQL 端口（默认 3306） |
| `API_FLOW_DB_USER` | MySQL 用户（默认 root） |
| `API_FLOW_DB_PASSWORD` | MySQL 密码（默认空） |
| `API_FLOW_DB_NAME` | MySQL 数据库名（默认 test） |
| `API_FLOW_AUTH_TOKEN` | Bearer token，注入到请求头 `Authorization: Bearer <value>` |

### 运行时自检（skill 启动时执行）

```bash
# 1. Python 包检查（缺包则自动 pip install）
python -c "import pymysql, yaml, requests, jsonpath_rw" 2>&1

# 2. MySQL 连通性检查（不通则报环境变量修正提示）
python -c "
import pymysql, os
try:
    c = pymysql.connect(
        host=os.getenv('API_FLOW_DB_HOST', 'localhost'),
        user=os.getenv('API_FLOW_DB_USER', 'root'),
        password=os.getenv('API_FLOW_DB_PASSWORD', ''),
        database=os.getenv('API_FLOW_DB_NAME', 'test'),
        port=int(os.getenv('API_FLOW_DB_PORT', '3306')),
    )
    c.close()
    print('MySQL OK')
except Exception as e:
    print(f'MySQL FAIL: {e}')
"

# 3. gitnexus 可用性检查（不可用则跳过 Phase 1，手动提供文件即可）
which gitnexus || echo "gitnexus not found — Phase 1 需手动编写用例文件"
```

---

## 工作流

### Phase 1: 分析代码，生成用例文件

用户只需提供 API 入口：
```
"帮我生成订单创建流程的测试用例"  →  Controller: com.example.controller.OrderController.createOrder()
"分析 POST /api/orders 的所有分支"  →  同上
```

**AI 执行 analyze 流程：**

1. **发现入口** — gitnexus 搜索 Controller 类和方法
2. **追踪调用链** — Controller → Service → Repository，最多 3 层
3. **识别分支** — 扫描 @Valid、if/else/switch、throw、自定义校验
4. **生成用例** — 每个分支一个用例，含中文场景描述
5. **生成 prepare SQL** — 保存为 `tc-*-prepare.sql`，带注释说明依赖表和 FK 顺序
6. **生成 cleanup SQL** — 保存为 `tc-*-cleanup.sql`，FK 逆序
7. **生成 request body** — 保存为 `tc-*.json`，变量引用用 `{{@var}}`
8. **生成 flow.yaml** — 编排引用，不含用例内容

**输出目录**: `docs/api-flow/<flow-name>/`

生成完成后展示摘要表格（设计规格书 §3.4），用户审阅修改后确认。

### Phase 2: 逐用例执行

用户确认后，Agent 开始逐条执行：

每条用例执行前展示 checkpoint（设计规格书 §4.2 格式）：
- 用例 ID + 场景 + 分支
- prepare SQL 影响哪些表
- request method + URL + body
- cleanup 概况

用户确认 → Agent 调用 `execute_flow()` → 展示结果 → 人工验证 → 下一条。

### Phase 2 Python API

Agent 通过调用 `api_flow.execute.execute_flow()` 执行流程，无需记忆命令行参数。

**导入方式**：

```python
from api_flow.execute import execute_flow
```

**函数签名**：

```python
def execute_flow(
    flow_path: Path | str,
    output_root: str = "results",
    db_config: dict[str, Any] | None = None,
    confirm_fn: Callable[[TestCase, dict], bool] | None = None,
    show_fn: Callable[[str], None] | None = None,
) -> RunResult
```

| 参数 | 说明 |
|------|------|
| `flow_path` | flow.yaml 所在目录路径 |
| `output_root` | 输出根目录（默认 `results/`） |
| `db_config` | 数据库连接配置，默认 localhost/test；支持 `API_FLOW_DB_*` 环境变量 |
| `confirm_fn` | 确认回调：接收 `(tc, info)`，返回 `True` 执行 / `False` 跳过；`None` = 自动全部执行 |
| `show_fn` | 展示回调：接收一行格式化文本；`None` = 用 `print()` |

**返回值**：`RunResult` 包含 `total` / `passed` / `failed` / `skipped` / `results: list[TResult]`。

**对话式执行示例**（Agent 调用）：

```python
from api_flow.execute import execute_flow

def agent_confirm(tc, info):
    # 展示 checkpoint 给用户
    display_checkpoint(info)
    return user_confirms()

def agent_show(text):
    display_to_user(text)

result = execute_flow(
    "docs/api-flow/订单创建流程",
    confirm_fn=agent_confirm,
    show_fn=agent_show,
)
# result.passed, result.failed, result.results ...
```

**自动模式**（无人值守）：

```python
result = execute_flow("docs/api-flow/订单创建流程")
# confirm_fn=None → 自动执行全部用例，不等待确认
```

### Phase 1 文件生成工具

```python
from api_flow.generate import init_flow, write_tc_json, write_sql

flow_dir = init_flow("订单创建流程", "http://localhost:8080")
write_tc_json(flow_dir, "tc-001", "正常创建订单", method="POST", url="/api/orders", body={"userId": "{{@uid}}"})
write_sql(flow_dir, "tc-001-prepare.sql", ["INSERT INTO users VALUES (1, 'test');"])
write_sql(flow_dir, "tc-001-cleanup.sql", ["DELETE FROM orders WHERE user_id = 1;"])
```

### 失败处理

- DB 可重试错误（死锁/断连）：自动退避重试 3 次 → 仍失败则全新 prepare 重试该用例（最多 3 次）
- DB 不可重试错误（语法/权限）：标记 FAILED，继续下一条
- HTTP 业务错误：标记 FAILED，继续下一条
- 连续 3 条用例失败：全局中断（基本确定 DB 挂了）

### Phase 3: 汇总报告

全部用例执行完毕后，输出 summary.md。

---

## 文件结构

```
docs/api-flow/<flow-name>/
├── flow.yaml                 # 编排层：元数据 + 鉴权 + 用例引用
├── tc-001.json               # 用例内容：scenario, branch, request, extract
├── tc-001-prepare.sql        # 数据准备（用户可直接查看/修改）
├── tc-001-cleanup.sql        # 回滚脚本（用户可直接查看/补充）
├── tc-002.json
├── ...
└── results/
    └── run-<timestamp>/
        ├── tc-001.md         # 模板化单条结果
        ├── tc-002.md
        └── summary.md        # 汇总报告
```

## 模板

所有输出均使用固定模板，保证稳定性：
- `tc-*.md` → 设计规格书 §4.5
- `summary.md` → 设计规格书 §4.5
- `flow.yaml` → `references/flow-yaml.template.yaml`
- `tc-*.json` → `references/test-case.template.json`
- checkpoint 展示 → 设计规格书 §4.2

## 相关文件

- 设计规格书：`docs/specs/2026-07-16-api-flow-design.zh-CN.md` (v0.2)
- 实施计划：`docs/plans/2026-07-16-api-flow.zh-CN.md` (v0.2)
