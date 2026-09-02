import { Tool } from "@modelcontextprotocol/sdk/types.js";
import { GitLabClient } from "./lib/gitlab-client.js";
import { Policy } from "./security/policy.js";

export type ToolDefinition = Tool;

export interface ToolContext {
  gitlab: GitLabClient;
  policy: Policy;
}

export type ToolResult = {
  content: Array<{ type: "text"; text: string }>;
  isError?: boolean;
};

export type ToolHandler = (args: Record<string, unknown>, context: ToolContext) => Promise<ToolResult>;

