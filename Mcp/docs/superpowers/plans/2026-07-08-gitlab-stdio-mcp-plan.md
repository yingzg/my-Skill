# GitLab Stdio MCP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a stdio GitLab MCP server with repository and CI/CD tools plus local write-operation guardrails.

**Architecture:** Use a small TypeScript MCP server with focused modules for tool definitions, handlers, GitLab HTTP access, validation, redaction, policy, and confirm-message enforcement.

**Tech Stack:** TypeScript, Node.js, `@modelcontextprotocol/sdk`, `axios`, Node test runner.

---

### Task 1: Project Scaffold

**Files:**
- Create: `package.json`
- Create: `tsconfig.json`
- Create: `.gitignore`
- Create: `README.md`

- [x] Create TypeScript MCP package metadata and build/test scripts.
- [x] Create strict NodeNext TypeScript config.
- [x] Document stdio configuration and high-risk confirm messages.

### Task 2: Core Libraries

**Files:**
- Create: `src/lib/errors.ts`
- Create: `src/lib/logger.ts`
- Create: `src/lib/response.ts`
- Create: `src/lib/validation.ts`
- Create: `src/lib/gitlab-client.ts`
- Create: `src/security/redact.ts`
- Create: `src/security/confirm.ts`
- Create: `src/security/policy.ts`

- [x] Add structured stderr logger.
- [x] Add MCP-safe errors and API error conversion.
- [x] Add runtime argument helpers.
- [x] Add GitLab client with project path normalization.
- [x] Add redaction and local safety policy.

### Task 3: Tools

**Files:**
- Create: `src/tools/definitions.ts`
- Create: `src/tools/repository.ts`
- Create: `src/tools/cicd.ts`
- Create: `src/tools/registry.ts`
- Create: `src/types.ts`
- Create: `src/index.ts`

- [x] Add repository and CI/CD tool schemas.
- [x] Add handlers with validation and policy checks.
- [x] Register tools through MCP stdio server.

### Task 4: Verification

**Files:**
- Create: `src/__tests__/redact.test.ts`
- Create: `src/__tests__/confirm.test.ts`
- Create: `src/__tests__/policy.test.ts`

- [x] Add unit tests for redaction, confirm-message matching, and project policy.
- [x] Run build and unit tests.
