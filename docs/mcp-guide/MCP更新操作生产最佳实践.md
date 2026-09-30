# MCP 更新操作生产最佳实践：stdio 与 HTTP 传输的安全设计

> 本文用于补充 MCP 入门教程和复杂开发代码规范，重点回答一个问题：当 MCP Tool 不只是查询，而是要执行更新、合并、删除、触发流水线、修改配置等写操作时，stdio 和 HTTP 两种传输模式下应该如何设计，才能更规范、可控、可上线。

## 1. 核心结论

MCP 的写操作安全不能只靠一个 `confirm=true` 参数，也不能只靠“相信 AI 不会乱调工具”。规范做法是根据传输方式和部署形态分层设计。

| 传输方式 | 典型场景 | 写操作确认方式 | 审计要求 | 认证授权要求 |
|---|---|---|---|---|
| stdio | 本地工具、个人插件、桌面客户端启动子进程 | 主要做防误操作，不等于强人工确认 | 默认可不做强审计，建议有结构化日志和可选操作记录 | 通常从环境变量读取凭据，依赖本机用户和本地配置 |
| HTTP / Streamable HTTP | 团队共享、远程 MCP、生产服务、多用户访问 | 应使用服务端 pending operation + 人工审批 UI 或 Host 原生确认能力 | 必须有审计日志 | 必须有认证、授权、scope、会话和资源级权限 |

一句话：

```text
stdio 的 confirm_message 是 guardrail，用来防误操作。
HTTP 的 approval flow 才是强确认，用来满足生产级审批和追责。
```

## 2. 为什么写操作 MCP 必须谨慎

查询类 MCP 的主要风险是信息泄露、返回过大、敏感字段未脱敏。写操作 MCP 的风险更高，因为它会改变外部系统状态。

典型高风险写操作包括：

```text
合并 Merge Request
关闭 Merge Request
rebase 分支
触发生产流水线
重试或取消 CI/CD job
创建、更新、删除 CI/CD 变量
创建、删除 trigger token
更新订单状态
退款、取消订单、修改客户资料
批量更新业务数据
```

写操作 MCP 必须至少具备：

```text
窄业务动作，而不是通用执行能力
运行时参数校验
权限校验
敏感信息脱敏
幂等控制
更新前状态检查
错误可追踪
必要的确认机制
必要的审计或结构化日志
```

不推荐暴露这类泛能力 Tool：

```text
execute_sql
call_any_api
update_any_field
run_shell_command
write_any_file
```

推荐暴露窄业务动作：

```text
create_merge_request_note
accept_merge_request
update_order_status
retry_failed_payment
trigger_release_pipeline
delete_cicd_variable
```

## 3. stdio 传输下的生产实践

### 3.1 stdio 的信任边界

stdio MCP 通常由 Host 在本地启动一个 MCP Server 子进程：

```text
Host / MCP Client
  -> 启动本地 MCP Server 子进程
  -> stdin/stdout 传 MCP JSON-RPC
  -> stderr 输出日志
  -> MCP Server 使用本地环境变量中的凭据调用外部系统
```

stdio 的典型特点：

```text
单用户
本机执行
不开放端口
凭据来自本地环境变量
没有天然的远程用户身份
没有天然的审批 UI
```

因此 stdio 下的重点不是做一套复杂的多用户审计系统，而是：

```text
不要污染 stdout
不要泄露 token
不要暴露过大的工具权限
不要让模型用模糊参数直接执行危险动作
```

### 3.2 stdio 下是否需要审计日志

stdio 第一优先级不是强审计，而是安全规范。

建议：

```text
默认不强制写 audit log
必须有 callId 和结构化错误
日志只能写 stderr 或文件，不能写 stdout
日志必须脱敏
高风险操作可以记录轻量 operation log，但默认关闭
```

原因：

```text
stdio 通常只有本机当前用户一个调用者
没有多租户身份需要区分
GitLab、订单系统、CI/CD 平台自身通常已有操作记录
本地保存过多日志反而可能泄露 secret
```

但即使不做强审计，也应保留基础可观测能力：

```json
{
  "time": "2026-07-08T10:00:00.000Z",
  "level": "info",
  "callId": "uuid",
  "tool": "accept_merge_request",
  "operation": "merge_mr",
  "projectId": "group/project",
  "mergeRequestIid": 123,
  "status": "success",
  "elapsedMs": 812
}
```

不要记录：

```text
GitLab token
pipeline trigger token
CI/CD variable value
Authorization header
job trace 全文
包含 secret 的错误详情
```

### 3.3 stdio 下的 confirm_message 到底是什么

`confirm_message` 不是强人工确认。它不能证明用户真的看过并确认了操作。

它的本质是：

```text
让高风险 Tool 无法被一个模糊、低成本、缺少目标摘要的调用直接触发。
```

也就是说，它是防误操作 guardrail，不是审批系统。

#### 错误理解

不要把流程理解成：

```text
第一次不传 confirm_message
服务端提示缺少 confirm_message
第二次 AI 自动补上 confirm_message
这样就完成了用户确认
```

如果只是这样，安全收益很有限。因为 AI 确实可以自己构造 `confirm_message`。

#### 正确理解

stdio 下更合理的流程是：

```text
1. 用户明确提出高风险意图
2. AI 先调用只读工具获取当前状态
3. AI 把即将执行的操作摘要展示给用户
4. 用户在对话中明确要求执行
5. AI 再调用写操作，并带上精确的 confirm_message
6. MCP Server 校验 confirm_message、目标状态、sha、权限、幂等
7. 校验通过才执行
```

以合并 MR 为例：

```text
用户：帮我看看 group/project 的 MR 123 能不能合并

AI：
  -> get_merge_request
  -> get_merge_request_approvals
  -> list_pipeline_jobs

AI 返回：
  MR: group/project!123
  source: feature/a
  target: main
  head sha: abc123
  pipeline: passed
  approvals: satisfied
  这是高风险操作。若要继续，请明确说：合并 group/project!123

用户：确认，合并 group/project!123

AI：
  -> accept_merge_request({
       project_id: "group/project",
       merge_request_iid: 123,
       sha: "abc123",
       confirm_message: "MERGE group/project!123"
     })

MCP Server：
  -> 校验 confirm_message 是否完全等于 MERGE group/project!123
  -> 重新读取 MR，校验当前 head sha 是否仍然是 abc123
  -> 校验目标分支、状态、pipeline、approval
  -> 执行 merge
```

这个流程的安全收益来自多层叠加：

```text
高风险工具不能被缺少 confirm_message 的调用执行
confirm_message 必须和服务端计算出来的目标摘要完全一致
merge 必须带 sha，避免 MR 内容变化后仍继续合并
执行前重新读取当前状态，避免使用过期上下文
用户对话中能看到操作摘要，减少误解
```

### 3.4 AI 会不会自己造 confirm_message

会。所以必须承认：

```text
stdio 的 confirm_message 不能防恶意 AI，也不能防 prompt injection 后的强行调用。
```

它能防的是这些问题：

```text
用户说“处理一下这个 MR”，AI 不应该直接 merge
工具参数缺失或目标不清时不能直接执行
模型误把查询意图理解成写操作
模型在没有重新读取状态时直接执行
模型拿旧 sha 或旧上下文执行危险动作
```

它不能防：

```text
模型已经决定绕过用户意图，自行构造 confirm_message
用户把恶意 prompt 粘贴给 AI，让 AI 强行调用工具
Host 没有任何工具调用可见性
本地 MCP token 权限过大
```

因此 stdio 下真正有效的安全策略不是只靠 `confirm_message`，而是组合拳：

```text
1. 高风险工具尽量少暴露
2. 工具动作要窄，不做泛能力
3. 写操作前强制读取当前状态
4. 高风险操作要求 confirm_message
5. merge 类操作要求 sha
6. 删除类操作要求精确目标
7. 服务端做 allowlist / readonly 开关
8. token 最小权限
9. 响应和日志脱敏
10. Host 侧尽量打开工具调用确认或可见性
```

### 3.5 stdio 推荐的高风险参数规则

| 操作 | 必须参数 | confirm_message 格式 |
|---|---|---|
| 合并 MR | `project_id`, `merge_request_iid`, `sha`, `confirm_message` | `MERGE <project_id>!<iid>` |
| rebase MR | `project_id`, `merge_request_iid`, `confirm_message` | `REBASE <project_id>!<iid>` |
| 关闭 MR | `project_id`, `merge_request_iid`, `confirm_message` | `CLOSE <project_id>!<iid>` |
| 删除 CI/CD 变量 | `project_id`, `key`, `confirm_message` | `DELETE_VARIABLE <project_id>:<key>` |
| 删除 trigger token | `project_id`, `trigger_id`, `confirm_message` | `DELETE_TRIGGER_TOKEN <project_id>:<trigger_id>` |
| 触发生产流水线 | `project_id`, `ref`, `variables`, `confirm_message` | `TRIGGER_PIPELINE <project_id>@<ref>` |

服务端不要只判断 `confirm_message` 存在，而要判断它是否等于服务端根据参数计算出的固定字符串。

示例：

```ts
function requireConfirm(actual: string | undefined, expected: string) {
  if (actual !== expected) {
    throw new Error(`High risk operation requires confirm_message exactly: ${expected}`);
  }
}
```

### 3.6 stdio 下的推荐开发清单

stdio 写操作 MCP 至少做到：

```text
Tool schema 使用 zod 等运行时校验
高风险 Tool description 明确写出使用前提
stdout 只输出 MCP JSON-RPC
stderr 写结构化日志
所有 token 和 secret 脱敏
默认限制分页和返回大小
job trace 默认 tail，且脱敏
写操作返回 before / after 或关键状态摘要
merge / rebase / delete 要求 confirm_message
merge 要求 sha
支持 readonly 环境变量
可选 allowed projects
```

## 4. HTTP / Streamable HTTP 传输下的生产实践

### 4.1 HTTP 的信任边界

HTTP MCP 通常是远程服务：

```text
多个 Host / Client
  -> HTTPS
  -> API Gateway / MCP Server
  -> 认证授权
  -> Tool handler
  -> 业务系统 / GitLab / CI/CD
```

HTTP 与 stdio 的关键区别：

```text
可能多用户访问
可能多客户端访问
服务长期运行
暴露网络入口
需要处理会话、认证、授权、限流、审计
```

因此 HTTP MCP 的写操作不能只靠 `confirm_message`，必须有生产级控制面。

### 4.2 HTTP MCP 必须具备的基础安全能力

上线前至少具备：

```text
HTTPS
认证 Authentication
授权 Authorization
Origin / Host 校验
CORS 策略
会话管理
限流
请求体大小限制
结构化日志
审计日志
敏感信息脱敏
工具级权限
项目/租户/资源级权限
高风险操作审批
```

认证解决：

```text
你是谁
```

授权解决：

```text
你能调用哪些工具
你能操作哪些项目/租户/业务对象
你能不能执行高风险写操作
```

审计解决：

```text
谁在什么时候对什么对象执行了什么操作，结果是什么
```

### 4.3 HTTP 写操作的强确认流程

HTTP 生产环境推荐使用 pending operation + approval UI。

核心原则：

```text
确认信号不能由 AI 自己伪造。
```

推荐流程：

```text
1. AI 调用高风险 Tool
2. MCP Server 不立即执行，而是创建 pending operation
3. Server 返回 operation_id、操作摘要、approval_url
4. 用户打开 approval_url，在可信 UI 中登录并确认
5. Server 保存 approval 结果
6. AI 或 Host 调用 commit_approved_operation
7. Server 校验身份、approval、digest、TTL、当前状态
8. 校验通过后执行真正写操作
9. 写入审计日志
```

以合并 MR 为例：

```text
AI -> prepare_accept_merge_request({
  project_id: "group/project",
  merge_request_iid: 123
})

Server -> 返回：
{
  "requires_approval": true,
  "operation_id": "op_abc",
  "summary": "Merge group/project!123 feature/a -> main, head sha abc123",
  "approval_url": "https://mcp.example.com/approvals/op_abc"
}

用户 -> 打开 approval_url -> 登录 -> 点击确认

AI/Host -> commit_approved_operation({
  "operation_id": "op_abc"
})

Server -> 校验：
  approval 已存在
  approval 用户有权限
  operation 未过期
  MR head sha 没变
  pipeline/approval 仍满足

Server -> 执行 merge
```

这和 stdio 的 `confirm_message` 有本质区别：

| 机制 | 谁能生成确认信号 | 能否证明人工确认 | 适用场景 |
|---|---|---|---|
| `confirm_message` | AI 可以生成 | 不能 | stdio 本地防误操作 |
| approval UI | 用户在可信页面确认 | 可以 | HTTP 生产强确认 |

### 4.4 HTTP 审计日志应该记录什么

HTTP 生产写操作必须有审计日志。

推荐字段：

```json
{
  "auditId": "audit_uuid",
  "time": "2026-07-08T10:00:00.000Z",
  "actor": {
    "userId": "u123",
    "clientId": "cursor",
    "tenantId": "t1"
  },
  "tool": "accept_merge_request",
  "riskLevel": "critical",
  "target": {
    "projectId": "group/project",
    "mergeRequestIid": 123,
    "targetBranch": "main"
  },
  "approval": {
    "required": true,
    "approved": true,
    "approvedBy": "u123",
    "operationId": "op_abc"
  },
  "requestSummary": {
    "sha": "abc123",
    "confirmDigest": "sha256..."
  },
  "result": {
    "status": "success",
    "externalRequestId": "gitlab-request-id"
  },
  "elapsedMs": 812
}
```

审计日志禁止记录：

```text
access token 明文
refresh token 明文
CI/CD variable value
pipeline trigger token
Authorization header
密码
完整敏感请求体
未脱敏 job trace
```

### 4.5 HTTP 写操作权限模型

HTTP MCP 不应该只有一个全局 token。推荐按用户、工具、资源、风险等级做授权。

示例 scope：

```text
gitlab:read
gitlab:mr-comment
gitlab:mr-write
gitlab:mr-merge
gitlab:pipeline-run
gitlab:cicd-variable-write
gitlab:admin
```

示例策略：

```text
普通研发：
  gitlab:read
  gitlab:mr-comment
  gitlab:pipeline-run

项目维护者：
  gitlab:read
  gitlab:mr-comment
  gitlab:mr-write
  gitlab:mr-merge

平台管理员：
  gitlab:cicd-variable-write
```

服务端还要做资源级判断：

```text
用户是否属于该项目
用户是否能操作该目标分支
用户是否能修改该 CI/CD variable
当前操作是否命中生产环境规则
```

不能只相信模型说“用户有权限”。

### 4.6 HTTP 写操作的状态校验和幂等

生产写操作要防止重复执行和状态漂移。

推荐规则：

```text
每个写操作有 idempotencyKey
pending operation 有 TTL
approval 绑定 operation digest
commit 时重新读取当前状态
merge 必须校验 head sha
删除必须校验目标仍然存在且未变化
批量操作必须限制数量
失败重试不能造成重复副作用
```

## 5. stdio 与 HTTP 的设计对照表

| 维度 | stdio | HTTP / Streamable HTTP |
|---|---|---|
| 运行位置 | 本机子进程 | 远程或独立服务 |
| 用户身份 | 通常是本机用户，不一定有远程 userId | 必须有明确 userId / clientId |
| 凭据来源 | 环境变量 | OAuth / JWT / API Key / token vault |
| 日志 | stderr 或本地文件 | 集中日志平台 |
| 审计 | 可选，轻量 | 必须 |
| 确认机制 | confirm_message 防误操作 | approval UI / Host 确认 / 审批流 |
| 强确认能力 | 弱 | 强 |
| 适合写操作 | 个人或小范围受控写操作 | 团队/生产写操作 |
| 权限模型 | token 最小权限 + 工具白名单 | 认证 + scope + RBAC/ABAC + 资源策略 |
| 高风险工具 | 尽量少暴露 | 可暴露，但必须审批和审计 |

## 6. 推荐分级策略

| 风险等级 | 示例 | stdio 策略 | HTTP 策略 |
|---|---|---|---|
| low | 查询项目、查询 MR、查询 job | 直接执行，脱敏和限流 | 认证后执行，记录访问日志 |
| medium | 创建 MR 评论、创建 MR、retry job | 直接执行，结构化日志 | 权限校验，审计可选或简化 |
| high | rebase、close MR、触发生产 pipeline、删除变量 | `confirm_message` + 状态校验 | pending operation + approval |
| critical | merge 到生产分支、退款、批量更新、权限变更 | 不建议 stdio 暴露；如暴露必须 confirm + sha + allowlist | 强审批 + 审计 + 幂等 + 双人复核 |

## 7. 对 GitLab MCP 的落地建议

针对 GitLab 操作类 MCP，第一版 stdio 可以采用：

```text
不做 user/group
不做 integration/webhook
只做 repository + CI/CD
默认不强制 audit log
实现 callId 和 stderr 日志
实现统一 redact
实现 zod 参数校验
实现 readonly 开关
实现 allowed projects 可选限制
实现 confirm_message 防误操作
merge 要求 sha
job trace 默认 tail + 脱敏
CI/CD variable value 永不回显
```

高风险 GitLab 操作规则：

```text
accept_merge_request:
  需要 sha
  需要 confirm_message = MERGE <project_id>!<iid>
  执行前重新读取 MR 状态

rebase_merge_request:
  需要 confirm_message = REBASE <project_id>!<iid>

close_merge_request:
  需要 confirm_message = CLOSE <project_id>!<iid>

delete_cicd_variable:
  需要 confirm_message = DELETE_VARIABLE <project_id>:<key>

delete_trigger_token:
  需要 confirm_message = DELETE_TRIGGER_TOKEN <project_id>:<trigger_id>
```

如果未来升级为 HTTP 生产服务，再补：

```text
OAuth / JWT 认证
用户和项目权限映射
scope 模型
approval UI
pending operation 存储
审计日志
集中日志
限流
多租户隔离
安全网关
```

## 8. 最终判断标准

判断一个 MCP 写操作设计是否合格，可以问这些问题：

```text
这个 Tool 是窄业务动作吗？
参数是否有运行时 schema 校验？
是否能从 tool description 看出风险和使用前提？
是否做了权限校验？
是否做了敏感信息脱敏？
是否限制了返回大小？
是否有 callId？
失败时能否定位？
重复调用是否安全？
状态变化后是否会拒绝执行？
高风险操作是否需要确认？
stdio 下是否承认 confirm_message 只是防误操作？
HTTP 下是否有 AI 不能伪造的人工确认？
生产环境是否有审计日志？
```

如果这些问题回答不清楚，就不应该直接上线写操作 MCP。

## 9. 参考资料

- MCP Transports: https://modelcontextprotocol.io/specification/2025-06-18/basic/transports
- MCP Authorization: https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization
- MCP Security Best Practices: https://modelcontextprotocol.io/docs/tutorials/security/security_best_practices
- 本目录：`MCP入门开发教程.md`
- 本目录：`MCP复杂开发代码规范.md`
- 本目录：`MCP开发面试自测题.md`
