# GitLab Stdio MCP

A local stdio MCP server for GitLab repository and CI/CD operations.

## Scope

Included:

- Repository and merge request tools
- CI/CD variables, trigger tokens, pipelines, and job tools
- Runtime parameter validation
- Secret redaction
- Project allowlist support
- Readonly mode
- `confirm_message` guardrails for high-risk local write operations

Excluded from v1:

- HTTP / Streamable HTTP transport
- Approval UI
- User and group administration
- GitLab integrations and webhooks

## Configuration

Required:

```bash
GITLAB_API_TOKEN=your-token
```

Optional:

```bash
GITLAB_API_URL=https://gitlab.com/api/v4
MCP_GITLAB_READONLY=false
MCP_GITLAB_ALLOWED_PROJECTS=group/project,group2/*
MCP_GITLAB_JOB_TRACE_TAIL_LINES=300
LOG_LEVEL=info
```

## Build

```bash
npm install
npm run build
```

## MCP Client Configuration

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

## High-Risk Confirm Messages

These are local stdio guardrails, not strong human approval.

| Operation | Required `confirm_message` |
|---|---|
| Merge MR | `MERGE <project_id>!<iid>` |
| Rebase MR | `REBASE <project_id>!<iid>` |
| Close MR | `CLOSE <project_id>!<iid>` |
| Delete CI/CD variable | `DELETE_VARIABLE <project_id>:<key>` |
| Delete trigger token | `DELETE_TRIGGER_TOKEN <project_id>:<trigger_id>` |
