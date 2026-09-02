# GitLab Stdio MCP Design

## Goal

Build a clean TypeScript stdio MCP server for GitLab repository and CI/CD operations, excluding user/group and integration/webhook capabilities.

## Transport

Version 1 supports only stdio. It is intended for local single-user MCP clients where credentials are provided through environment variables. HTTP, OAuth, approval UI, session handling, and centralized audit logging are deferred to a later transport-specific design.

## Safety Model

The server uses local guardrails rather than strong approval:

- Runtime argument validation for every tool.
- Secret redaction for tool responses, errors, and logs.
- Optional readonly mode through `MCP_GITLAB_READONLY=true`.
- Optional project allowlist through `MCP_GITLAB_ALLOWED_PROJECTS`.
- High-risk write operations require exact `confirm_message` values.
- Merge operations require `sha` and re-read the merge request before calling GitLab merge.
- Job traces are tailed and redacted by default.

## Tool Scope

Repository tools include project, branch, MR, issue, file, compare, discussion, note, rebase, close, and merge operations.

CI/CD tools include trigger tokens, pipeline triggering, CI/CD variables, jobs, job traces, retry/cancel job, and pipeline jobs.

## Architecture

`src/index.ts` owns MCP startup. `src/tools` contains definitions and handlers. `src/lib` contains GitLab HTTP access, validation, response formatting, errors, and logging. `src/security` contains redaction, policy, and confirm-message rules.

## Validation

Unit tests cover project policy matching, confirm-message enforcement, and redaction. The build must pass TypeScript strict mode.
