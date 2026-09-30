import { PermissionError } from "../lib/errors.js";

export interface Policy {
  readonly: boolean;
  allowedProjects: string[];
  defaultTraceTailLines: number;
}

export function loadPolicy(env: NodeJS.ProcessEnv = process.env): Policy {
  return {
    readonly: (env.MCP_GITLAB_READONLY || "").toLowerCase() === "true",
    allowedProjects: (env.MCP_GITLAB_ALLOWED_PROJECTS || "")
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean),
    defaultTraceTailLines: parsePositiveInt(env.MCP_GITLAB_JOB_TRACE_TAIL_LINES, 300),
  };
}

function parsePositiveInt(value: string | undefined, fallback: number): number {
  if (!value) return fallback;
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? Math.trunc(parsed) : fallback;
}

export function assertWriteAllowed(policy: Policy, toolName: string) {
  if (policy.readonly) {
    throw new PermissionError(`Readonly mode is enabled; ${toolName} cannot perform write operations`);
  }
}

export function assertProjectAllowed(policy: Policy, projectId: string) {
  if (policy.allowedProjects.length === 0) return;
  if (!policy.allowedProjects.some((pattern) => matchesProject(pattern, projectId))) {
    throw new PermissionError(`Project is not allowed by MCP_GITLAB_ALLOWED_PROJECTS: ${projectId}`);
  }
}

export function matchesProject(pattern: string, projectId: string): boolean {
  if (pattern === projectId) return true;
  if (pattern.endsWith("/*")) {
    const prefix = pattern.slice(0, -1);
    return projectId.startsWith(prefix);
  }
  return false;
}

