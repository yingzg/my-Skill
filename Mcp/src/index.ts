#!/usr/bin/env node

import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ErrorCode,
  ListToolsRequestSchema,
  McpError,
} from "@modelcontextprotocol/sdk/types.js";
import crypto from "node:crypto";
import { GitLabClient } from "./lib/gitlab-client.js";
import { logger } from "./lib/logger.js";
import { toMcpError } from "./lib/errors.js";
import { loadPolicy } from "./security/policy.js";
import { toolDefinitions } from "./tools/definitions.js";
import { toolRegistry } from "./tools/registry.js";
import { ToolContext } from "./types.js";

const token = process.env.GITLAB_API_TOKEN;
const apiUrl = process.env.GITLAB_API_URL || "https://gitlab.com/api/v4";

if (!token) {
  console.error("GITLAB_API_TOKEN environment variable is required");
  process.exit(1);
}

const server = new Server(
  {
    name: "mcp-gitlab-stdio",
    version: "0.1.0",
  },
  {
    capabilities: {
      tools: { listChanged: false },
    },
  }
);

const context: ToolContext = {
  gitlab: new GitLabClient(apiUrl, token),
  policy: loadPolicy(),
};

server.setRequestHandler(ListToolsRequestSchema, async () => {
  return { tools: toolDefinitions };
});

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const callId = crypto.randomUUID();
  const toolName = request.params.name;
  const handler = toolRegistry[toolName];

  if (!handler) {
    throw new McpError(ErrorCode.InvalidRequest, `Unknown tool: ${toolName}`);
  }

  logger.info({ callId, tool: toolName }, "tool started");
  const started = Date.now();

  try {
    const result = await handler((request.params.arguments ?? {}) as Record<string, unknown>, context);
    logger.info({ callId, tool: toolName, elapsedMs: Date.now() - started }, "tool succeeded");
    return result;
  } catch (error) {
    logger.error(
      {
        callId,
        tool: toolName,
        elapsedMs: Date.now() - started,
        errorName: error instanceof Error ? error.name : "UnknownError",
        errorMessage: error instanceof Error ? error.message : String(error),
      },
      "tool failed"
    );
    throw toMcpError(error, `Error executing ${toolName}`);
  }
});

const transport = new StdioServerTransport();
server.connect(transport).catch((error) => {
  logger.error(
    {
      errorName: error instanceof Error ? error.name : "UnknownError",
      errorMessage: error instanceof Error ? error.message : String(error),
    },
    "server failed"
  );
  process.exit(1);
});

