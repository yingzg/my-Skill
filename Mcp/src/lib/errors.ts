import { ErrorCode, McpError } from "@modelcontextprotocol/sdk/types.js";
import axios from "axios";
import { redact } from "../security/redact.js";

export class ValidationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ValidationError";
  }
}

export class PermissionError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "PermissionError";
  }
}

export function toMcpError(error: unknown, fallbackMessage: string): McpError {
  if (error instanceof McpError) return error;

  if (error instanceof ValidationError) {
    return new McpError(ErrorCode.InvalidParams, error.message);
  }

  if (error instanceof PermissionError) {
    return new McpError(ErrorCode.InvalidRequest, error.message);
  }

  if (axios.isAxiosError(error)) {
    const message = error.response?.data?.message ?? error.message;
    return new McpError(
      ErrorCode.InternalError,
      `GitLab API error: ${redact(String(message))}`
    );
  }

  if (error instanceof Error) {
    return new McpError(
      ErrorCode.InternalError,
      `${fallbackMessage}: ${redact(error.message)}`
    );
  }

  return new McpError(ErrorCode.InternalError, fallbackMessage);
}

