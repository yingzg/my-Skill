# MCP 复杂开发代码规范

> 适用于从入门级 MCP Server 走向业务查询、业务更新、内部系统集成、远程部署、多工具维护的项目。

## 1. 核心原则

复杂 MCP 项目不要只把重点放在“工具能不能调用成功”，还要从一开始设计：

| 维度 | 要求 |
|---|---|
| 协议安全 | stdio 模式下 stdout 只能传 MCP JSON-RPC，日志必须走 stderr 或文件 |
| 可观测性 | 每次 tool 调用要有 `callId`，日志可串联完整链路 |
| 分层清晰 | tool 层、service 层、client 层、domain 层分离 |
| 错误可定位 | 用户可见错误带 `callId`，服务端日志记录完整 stack |
| 外部依赖可控 | 数据库、HTTP API、业务系统调用必须有超时、重试边界和错误包装 |
| 权限可控 | 查询、更新、删除等高风险 tool 必须有权限校验和参数确认 |
| 测试分层 | 单测 mock 外部依赖，真实集成测试显式开启 |
| 部署可切换 | 本地用 stdio，远程/共享服务用 Streamable HTTP |

## 2. Host / Client / Server 职责

MCP 是 client-server 架构，但实际有三类角色：

| 角色 | 说明 | 示例 |
|---|---|---|
| Host | 面向用户的 AI 应用，负责承载 LLM、展示 UI、管理多个 MCP 连接 | Claude Desktop、Cursor、VS Code 插件、内部 AI 助手 |
| MCP Client | Host 内部的连接组件，通常一个 server 对应一个 client 连接 | Claude Desktop 内部连接某个 MCP server 的实例 |
| MCP Server | 你开发的服务，暴露 tools、resources、prompts | 天气 MCP、订单查询 MCP、CRM 更新 MCP |

一次典型调用链：

```text
User
  -> Host AI 应用
  -> Host 内部 MCP Client
  -> MCP transport(stdio 或 HTTP)
  -> MCP Server
  -> Tool handler
  -> Service
  -> DB / HTTP API / 内部业务系统
  -> 返回结果
```

注意：

```text
Host 不是你通常要开发的部分
Client 通常由 Host 或 SDK 管理
你主要开发的是 MCP Server
```

除非你在做自己的 AI 应用平台，否则一般不用自己实现 MCP Host。

## 3. stdio 与 Streamable HTTP 的选择

| 传输 | 适用场景 | 优点 | 风险 / 限制 |
|---|---|---|---|
| stdio | 本地开发、本地工具、个人插件、桌面客户端启动子进程 | 配置简单，无需开放端口，适合单用户 | stdout 不能写日志；通常服务单个 client；不适合多人共享 |
| Streamable HTTP | 远程 MCP、团队共享、生产部署、统一鉴权 | 可多 client 连接，可接入网关、鉴权、日志平台 | 需要部署服务、鉴权、会话、安全控制 |

本地 stdio 配置通常是：

```json
{
  "mcpServers": {
    "business": {
      "command": "node",
      "args": ["D:/path/to/mcp-business/dist/index.js"],
      "env": {
        "BUSINESS_API_BASE_URL": "https://internal.example.com"
      }
    }
  }
}
```

远程 HTTP 集成通常是：

```text
Host / Client
  -> https://mcp-business.example.com/mcp
  -> Streamable HTTP transport
  -> MCP Server
```

远程模式需要重点设计：

```text
认证 Authorization
租户 tenantId
用户身份 userId
审计日志 audit log
权限控制 RBAC / ABAC
限流 rate limit
幂等 idempotency
```

## 4. 推荐项目结构

```text
src/
  index.ts                    # 入口，创建 server，注册 tools，启动 transport
  tools/                      # MCP tool handler，只做协议适配和参数转换
    query-order.ts
    update-order-status.ts
  services/                   # 业务用例编排
    order-service.ts
  clients/                    # 外部系统客户端，HTTP/DB/RPC
    order-api-client.ts
    crm-client.ts
  domain/                     # 业务模型、枚举、规则
    order.ts
  lib/
    logger.ts                 # 结构化日志
    errors.ts                 # 统一错误类型
    context.ts                # callId / request context
    mask.ts                   # 敏感信息脱敏
  __tests__/
    unit/
    integration/
scripts/
  check-network.cjs
  run-integration-tests.cjs
docs/
```

分层要求：

| 层 | 允许做什么 | 不建议做什么 |
|---|---|---|
| tools | zod 参数校验、生成 callId、调用 service、包装 MCP 返回 | 写复杂业务逻辑、直接拼 SQL |
| services | 编排业务流程、权限判断、幂等判断、领域规则 | 直接处理 MCP 协议细节 |
| clients | 调外部 HTTP、数据库、内部 RPC，处理超时和状态码 | 做复杂业务决策 |
| lib | 日志、错误、上下文、脱敏、通用工具 | 依赖具体业务流程 |

## 5. 日志规范

### 5.1 stdio 日志规则

stdio 模式下：

```text
stdin/stdout = MCP JSON-RPC 协议
stderr = 日志
```

禁止：

```ts
console.log("debug message");
```

允许：

```ts
console.error("debug message");
```

复杂项目建议使用结构化 logger，输出到 stderr 或文件。

### 5.2 推荐日志字段

每条关键日志建议包含：

| 字段 | 说明 |
|---|---|
| `time` | ISO 时间 |
| `level` | debug / info / warn / error |
| `callId` | 单次 tool 调用 ID |
| `tool` | tool 名称 |
| `userId` | 当前用户，若可获取 |
| `tenantId` | 当前租户，若可获取 |
| `operation` | 业务操作 |
| `elapsedMs` | 耗时 |
| `status` | success / failed |
| `errorName` | 错误类型 |
| `message` | 简短描述 |

不要记录：

```text
API Key 明文
Authorization header
密码
token
身份证号/手机号等敏感数据
完整 SQL 参数中的敏感字段
```

### 5.3 简单 logger 示例

不引入依赖时可以先用：

```ts
type LogLevel = "debug" | "info" | "warn" | "error";

const levels: Record<LogLevel, number> = {
  debug: 10,
  info: 20,
  warn: 30,
  error: 40,
};

const currentLevel = (process.env.LOG_LEVEL || "info") as LogLevel;

function write(level: LogLevel, data: Record<string, unknown>, message: string) {
  if (levels[level] < levels[currentLevel]) return;

  console.error(
    JSON.stringify({
      time: new Date().toISOString(),
      level,
      message,
      ...data,
    })
  );
}

export const logger = {
  debug: (data: Record<string, unknown>, message: string) => write("debug", data, message),
  info: (data: Record<string, unknown>, message: string) => write("info", data, message),
  warn: (data: Record<string, unknown>, message: string) => write("warn", data, message),
  error: (data: Record<string, unknown>, message: string) => write("error", data, message),
};
```

复杂项目建议使用：

```text
pino
winston
OpenTelemetry
```

## 6. callId / traceId 规范

每次 tool 调用都生成一个 `callId`：

```ts
import crypto from "node:crypto";

const callId = crypto.randomUUID();
```

所有链路日志都带上它：

```ts
logger.info({ callId, tool: "query-order", orderId }, "tool started");
logger.info({ callId, elapsedMs }, "business api succeeded");
logger.error({ callId, err }, "tool failed");
```

返回给用户的错误也带 `callId`：

```ts
return {
  isError: true,
  content: [
    {
      type: "text",
      text: `查询失败，请联系管理员并提供 callId=${callId}`,
    },
  ],
};
```

这样用户反馈问题时，可以直接用 `callId` 搜日志。

## 7. 错误处理规范

### 7.1 不要让未知异常裸奔

tool handler 应统一 try/catch：

```ts
server.tool("query-order", schema, async (args) => {
  const callId = crypto.randomUUID();

  try {
    logger.info({ callId, tool: "query-order", args: maskArgs(args) }, "tool started");

    const result = await orderService.queryOrder(args, { callId });

    logger.info({ callId, tool: "query-order" }, "tool succeeded");

    return {
      content: [{ type: "text", text: JSON.stringify(result, null, 2) }],
    };
  } catch (error) {
    logger.error(normalizeErrorLog(error, { callId, tool: "query-order" }), "tool failed");

    return {
      isError: true,
      content: [{ type: "text", text: `查询订单失败，callId=${callId}` }],
    };
  }
});
```

### 7.2 错误分类

建议至少区分：

| 错误类型 | 示例 | 用户可见信息 |
|---|---|---|
| ValidationError | 参数缺失、格式错误 | 参数不合法 |
| AuthError | 未登录、token 失效 | 无权限或认证失败 |
| PermissionError | 用户不能更新该业务对象 | 无权执行该操作 |
| NotFoundError | 订单不存在 | 未找到对应数据 |
| ExternalApiError | 下游业务系统失败 | 外部系统暂不可用 |
| TimeoutError | DB/API 超时 | 请求超时 |
| UnknownError | 未预期异常 | 系统异常，提供 callId |

### 7.3 错误日志必须包含 stack

```ts
function normalizeErrorLog(error: unknown, extra: Record<string, unknown>) {
  if (error instanceof Error) {
    return {
      ...extra,
      errorName: error.name,
      errorMessage: error.message,
      stack: error.stack,
    };
  }

  return {
    ...extra,
    errorName: "UnknownError",
    errorMessage: String(error),
  };
}
```

## 8. 参数校验规范

使用 `zod` 描述 tool 参数：

```ts
const QueryOrderSchema = {
  orderId: z.string().min(1),
};
```

高风险更新类 tool 要更严格：

```ts
const UpdateOrderStatusSchema = {
  orderId: z.string().min(1),
  status: z.enum(["PAID", "CANCELLED", "SHIPPED"]),
  reason: z.string().min(5),
  confirm: z.literal(true),
};
```

更新类工具建议要求显式确认字段：

```json
{
  "orderId": "SO123",
  "status": "CANCELLED",
  "reason": "用户申请取消",
  "confirm": true
}
```

## 9. 查询类与更新类 Tool 设计

### 9.1 查询类 Tool

查询类工具可以相对宽松，但必须控制返回大小：

```text
分页 limit / offset
默认时间范围
最大返回条数
字段白名单
敏感字段脱敏
```

示例：

```text
query-order
search-customer
list-payment-records
```

### 9.2 更新类 Tool

更新类工具必须更谨慎：

```text
权限校验
幂等 key
显式 confirm
更新前后日志
审计日志
必要时二次确认
禁止大批量无条件更新
```

示例：

```text
update-order-status
retry-payment
sync-customer-to-crm
```

更新类返回结果应包含：

```text
是否成功
业务对象 ID
更新前状态
更新后状态
callId
审计 ID
```

## 10. 外部系统调用规范

所有外部调用必须有：

```text
超时
错误包装
耗时日志
状态码日志
必要的重试策略
敏感信息脱敏
```

HTTP 调用日志示例：

```ts
logger.info(
  {
    callId,
    target: "order-api",
    method: "GET",
    path: "/orders/{orderId}",
  },
  "external api request"
);
```

不要记录完整 URL 中的 token：

```ts
function maskUrl(url: string) {
  return url
    .replace(/appid=[^&]+/g, "appid=***")
    .replace(/token=[^&]+/g, "token=***");
}
```

## 11. 数据库访问规范

如果 MCP 直接访问数据库：

```text
只使用参数化查询
禁止拼接 SQL
查询必须有 limit
更新必须有 where
更新必须记录审计日志
连接池配置必须可控
慢 SQL 记录 elapsedMs
```

高风险 SQL 应避免直接暴露给 LLM 参数决定。

不推荐：

```text
execute-sql
```

更推荐：

```text
query-order-by-id
search-customer-by-phone
update-order-status
```

即 tool 是业务动作，不是裸数据库能力。

## 12. 安全规范

### 12.1 最小权限

MCP Server 使用的业务系统账号应只具备必要权限。

例如：

```text
查询 MCP：只读账号
更新 MCP：只允许指定业务操作
财务 MCP：单独权限域
```

### 12.2 明确风险级别

给 tool 标注风险：

| 风险 | 示例 | 要求 |
|---|---|---|
| low | 查询天气、查询公开信息 | 常规日志 |
| medium | 查询客户、查询订单 | 权限校验、脱敏 |
| high | 更新订单、触发财务动作 | confirm、审计、幂等 |
| critical | 删除、退款、批量变更 | 尽量不直接暴露，必须强审批 |

### 12.3 禁止把敏感密钥交给模型

API Key、数据库密码、内部 token 应只在 server 环境变量中使用，不通过 tool 返回。

## 13. 测试规范

### 13.1 单元测试

单元测试不访问真实外网、真实数据库。

```powershell
npm.cmd run test:unit
```

适合覆盖：

```text
参数校验
错误转换
响应格式化
业务规则
异常分支
外部 API mock 返回
```

### 13.2 网络诊断

用于确认本机 Node.js 是否能访问外部服务：

```powershell
npm.cmd run test:network
```

### 13.3 真实集成测试

真实集成测试必须显式开启：

```powershell
npm.cmd run test:integration
```

不要让真实集成测试成为默认 `npm test` 的一部分。

### 13.4 回归测试

每次线上 bug 修复后，都要补一个单测，避免只靠手动 Inspector 验证。

## 14. Debug 规范

本地调试推荐：

```powershell
npm.cmd run inspector:debug
```

然后 VS Code：

```text
Attach to MCP Server (9229)
```

不要用 VS Code Debugger 直接包住 Inspector 的 stdio transport，避免调试器输出污染 MCP stdout。

常见断点位置：

```text
tool handler 入口
service 业务判断
外部 API 调用前后
错误 catch 分支
返回 MCP response 前
```

## 15. 部署规范

### 15.1 本地 stdio 部署

适合：

```text
个人开发
桌面客户端
本机文件/命令工具
小型内部工具
```

特点：

```text
Host 启动 MCP server 子进程
server 通过 stdin/stdout 与 client 通信
环境变量由 Host 配置传入
日志写 stderr 或文件
```

### 15.2 远程 HTTP 部署

适合：

```text
团队共享
生产系统
统一业务 MCP
需要鉴权和审计
需要多 client 连接
```

特点：

```text
MCP Server 独立部署
Host/Client 通过 HTTPS 访问
服务端负责鉴权、会话、限流、审计
日志接入集中平台
```

## 16. 业务 MCP 集成模式

### 16.1 查询类业务 MCP

推荐流程：

```text
Host
  -> MCP Client
  -> query-order tool
  -> orderService.queryOrder
  -> orderApiClient / DB
  -> 返回结构化摘要
```

注意：

```text
默认限制返回条数
敏感字段脱敏
返回字段尽量结构化
不要把整张表直接暴露给 LLM
```

### 16.2 更新类业务 MCP

推荐流程：

```text
Host
  -> MCP Client
  -> update-order-status tool
  -> 参数校验 + confirm
  -> 权限校验
  -> 幂等校验
  -> orderService.updateStatus
  -> 审计日志
  -> 返回更新结果
```

必须关注：

```text
谁操作
操作了什么
为什么操作
更新前是什么
更新后是什么
失败如何回滚或补偿
```

## 17. 配置规范

使用 `.env` 或部署平台环境变量：

```env
LOG_LEVEL=info
BUSINESS_API_BASE_URL=https://internal.example.com
BUSINESS_API_TOKEN=***
HTTPS_PROXY=http://127.0.0.1:7890
HTTP_PROXY=http://127.0.0.1:7890
```

要求：

```text
.env 不提交
.env.example 提交
敏感配置不要写入 README
日志中所有密钥必须脱敏
```

## 18. 上线前检查清单

| 检查项 | 状态 |
|---|---|
| stdout 没有业务日志 | ☐ |
| 所有 tool 有参数校验 | ☐ |
| 所有 tool 有 try/catch | ☐ |
| 错误返回包含 callId | ☐ |
| 服务端日志包含 stack | ☐ |
| 外部调用有 timeout | ☐ |
| 更新类 tool 有权限校验 | ☐ |
| 更新类 tool 有审计日志 | ☐ |
| 敏感信息已脱敏 | ☐ |
| 单元测试覆盖主要分支 | ☐ |
| 真实集成测试显式开启 | ☐ |
| Inspector 可手动验证 | ☐ |
| 生产环境日志级别合理 | ☐ |

## 19. 参考资料

- MCP Architecture: https://modelcontextprotocol.io/docs/concepts/architecture
- MCP Transports: https://modelcontextprotocol.io/specification/2025-06-18/basic/transports
