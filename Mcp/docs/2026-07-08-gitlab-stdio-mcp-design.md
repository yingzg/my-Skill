# GitLab Stdio MCP 设计

## 目标

构建一个简洁的 TypeScript stdio MCP 服务器，用于 GitLab 仓库和 CI/CD 操作，不包含用户/组管理以及集成/webhook 能力。

## 传输

版本 1 仅支持 stdio。它面向本地单用户 MCP 客户端，凭据通过环境变量提供。HTTP、OAuth、审批 UI、会话处理以及集中式审计日志推迟到后续针对具体传输方式的设计中。

## 安全模型

服务器使用本地防护措施而非强审批：

- 对每个工具进行运行时参数校验。
- 对工具响应、错误和日志进行密钥脱敏。
- 通过 `MCP_GITLAB_READONLY=true` 启用可选的只读模式。
- 通过 `MCP_GITLAB_ALLOWED_PROJECTS` 启用可选的项目白名单。
- 高风险写操作要求精确的 `confirm_message` 值。
- 合并操作要求 `sha`，并在调用 GitLab 合并前重新读取合并请求。
- 作业日志默认按尾部截取并脱敏。

## 工具范围

仓库工具包括项目、分支、MR、issue、文件、比较、讨论、备注、变基、关闭和合并操作。

CI/CD 工具包括触发器令牌、流水线触发、CI/CD 变量、作业、作业日志、重试/取消作业以及流水线作业。

## 架构

`src/index.ts` 负责 MCP 启动。`src/tools` 包含定义和处理器。`src/lib` 包含 GitLab HTTP 访问、校验、响应格式化、错误和日志。`src/security` 包含脱敏、策略和确认消息规则。

## 验证

单元测试覆盖项目策略匹配、确认消息强制执行和脱敏。构建必须通过 TypeScript 严格模式。
