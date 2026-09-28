# GitLab Stdio MCP 实施计划

**目标：** 构建一个 stdio GitLab MCP 服务器，提供仓库和 CI/CD 工具，以及本地写操作防护措施。

**架构：** 使用一个小型 TypeScript MCP 服务器，按模块划分：工具定义、处理器、GitLab HTTP 访问、校验、脱敏、策略以及确认消息（confirm-message）强制执行。

**技术栈：** TypeScript、Node.js、`@modelcontextprotocol/sdk`、`axios`、Node 测试运行器。

---

### 任务 1：项目脚手架

**文件：**
- 创建：`package.json`
- 创建：`tsconfig.json`
- 创建：`.gitignore`
- 创建：`README.md`

- [x] 创建 TypeScript MCP 包元数据以及构建/测试脚本。
- [x] 创建严格的 NodeNext TypeScript 配置。
- [x] 编写 stdio 配置和高风险确认消息的文档。

### 任务 2：核心库

**文件：**
- 创建：`src/lib/errors.ts`
- 创建：`src/lib/logger.ts`
- 创建：`src/lib/response.ts`
- 创建：`src/lib/validation.ts`
- 创建：`src/lib/gitlab-client.ts`
- 创建：`src/security/redact.ts`
- 创建：`src/security/confirm.ts`
- 创建：`src/security/policy.ts`

- [x] 添加结构化 stderr 日志记录器。
- [x] 添加 MCP 安全的错误类型和 API 错误转换。
- [x] 添加运行时参数辅助函数。
- [x] 添加带项目路径归一化的 GitLab 客户端。
- [x] 添加脱敏和本地安全策略。

### 任务 3：工具

**文件：**
- 创建：`src/tools/definitions.ts`
- 创建：`src/tools/repository.ts`
- 创建：`src/tools/cicd.ts`
- 创建：`src/tools/registry.ts`
- 创建：`src/types.ts`
- 创建：`src/index.ts`

- [x] 添加仓库和 CI/CD 工具 schema。
- [x] 添加带校验和策略检查的处理器。
- [x] 通过 MCP stdio 服务器注册工具。

### 任务 4：验证

**文件：**
- 创建：`src/__tests__/redact.test.ts`
- 创建：`src/__tests__/confirm.test.ts`
- 创建：`src/__tests__/policy.test.ts`

- [x] 为脱敏、确认消息匹配和项目策略添加单元测试。
- [x] 运行构建和单元测试。
