# GitLab Stdio MCP

用于 GitLab 仓库和 CI/CD 操作的本地 stdio MCP 服务器。

## 范围

包含：

- 仓库和合并请求（merge request）工具
- CI/CD 变量、触发器令牌（trigger token）、流水线和作业工具
- 运行时参数校验
- 密钥脱敏
- 项目白名单支持
- 只读模式
- 用于高风险本地写操作的 `confirm_message` 防护措施

v1 不包含：

- HTTP / Streamable HTTP 传输
- 审批 UI
- 用户和组管理
- GitLab 集成和 webhook

## 配置

必需：

```bash
GITLAB_API_TOKEN=your-token
```

可选：

```bash
GITLAB_API_URL=https://gitlab.com/api/v4
MCP_GITLAB_READONLY=false
MCP_GITLAB_ALLOWED_PROJECTS=group/project,group2/*
MCP_GITLAB_JOB_TRACE_TAIL_LINES=300
LOG_LEVEL=info
```

## 构建

```bash
npm install
npm run build
```

## MCP 客户端配置

```json
{
  "mcpServers": {
    "gitlab": {
      "command": "node",
      "args": ["/absolute/path/to/mcp-gitlab-stdio/build/index.js"],
      "env": {
        "GITLAB_API_TOKEN": "YOUR_GITLAB_TOKEN",
        "GITLAB_API_URL": "https://gitlab.example.com/api/v4"
      }
    }
  }
}
```

## 高风险确认消息

这些是本地 stdio 防护措施，而非强人工审批。

| 操作 | 所需的 `confirm_message` |
|---|---|
| 合并 MR | `MERGE <project_id>!<iid>` |
| 变基 MR | `REBASE <project_id>!<iid>` |
| 关闭 MR | `CLOSE <project_id>!<iid>` |
| 删除 CI/CD 变量 | `DELETE_VARIABLE <project_id>:<key>` |
| 删除触发器令牌 | `DELETE_TRIGGER_TOKEN <project_id>:<trigger_id>` |
