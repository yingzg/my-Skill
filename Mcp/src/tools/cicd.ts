import { deleteTriggerTokenConfirm, deleteVariableConfirm, requireConfirmMessage } from "../security/confirm.js";
import { assertProjectAllowed, assertWriteAllowed } from "../security/policy.js";
import { textResponse, jsonResponse } from "../lib/response.js";
import {
  asArgs,
  optionalBoolean,
  optionalEnum,
  optionalPerPage,
  optionalPositiveInteger,
  optionalString,
  optionalStringRecord,
  requireNumber,
  requireString,
} from "../lib/validation.js";
import { ToolContext, ToolHandler } from "../types.js";

function project(args: Record<string, unknown>, context: ToolContext): string {
  const projectId = requireString(args, "project_id");
  assertProjectAllowed(context.policy, projectId);
  return projectId;
}

export const listTriggerTokens: ToolHandler = async (rawArgs, context) => {
  const args = asArgs(rawArgs);
  const projectId = project(args, context);
  return jsonResponse(await context.gitlab.get(`${context.gitlab.projectPath(projectId)}/triggers`));
};

export const getTriggerToken: ToolHandler = async (rawArgs, context) => {
  const args = asArgs(rawArgs);
  const projectId = project(args, context);
  const triggerId = requireNumber(args, "trigger_id");
  return jsonResponse(await context.gitlab.get(`${context.gitlab.projectPath(projectId)}/triggers/${triggerId}`));
};

export const createTriggerToken: ToolHandler = async (rawArgs, context) => {
  const args = asArgs(rawArgs);
  assertWriteAllowed(context.policy, "gitlab_create_trigger_token");
  const projectId = project(args, context);
  return jsonResponse(
    await context.gitlab.post(`${context.gitlab.projectPath(projectId)}/triggers`, {
      description: requireString(args, "description"),
    })
  );
};

export const updateTriggerToken: ToolHandler = async (rawArgs, context) => {
  const args = asArgs(rawArgs);
  assertWriteAllowed(context.policy, "gitlab_update_trigger_token");
  const projectId = project(args, context);
  const triggerId = requireNumber(args, "trigger_id");
  return jsonResponse(
    await context.gitlab.put(`${context.gitlab.projectPath(projectId)}/triggers/${triggerId}`, {
      description: requireString(args, "description"),
    })
  );
};

export const deleteTriggerToken: ToolHandler = async (rawArgs, context) => {
  const args = asArgs(rawArgs);
  assertWriteAllowed(context.policy, "gitlab_delete_trigger_token");
  const projectId = project(args, context);
  const triggerId = requireNumber(args, "trigger_id");
  requireConfirmMessage(optionalString(args, "confirm_message"), deleteTriggerTokenConfirm(projectId, triggerId));
  return jsonResponse(await context.gitlab.delete(`${context.gitlab.projectPath(projectId)}/triggers/${triggerId}`));
};

export const triggerPipeline: ToolHandler = async (rawArgs, context) => {
  const args = asArgs(rawArgs);
  assertWriteAllowed(context.policy, "gitlab_trigger_pipeline");
  const projectId = project(args, context);
  return jsonResponse(
    await context.gitlab.post(
      `${context.gitlab.projectPath(projectId)}/trigger/pipeline`,
      { variables: optionalStringRecord(args, "variables") },
      { params: { token: requireString(args, "token"), ref: requireString(args, "ref") } }
    )
  );
};

export const listCiCdVariables: ToolHandler = async (rawArgs, context) => {
  const args = asArgs(rawArgs);
  const projectId = project(args, context);
  return jsonResponse(await context.gitlab.get(`${context.gitlab.projectPath(projectId)}/variables`));
};

export const getCiCdVariable: ToolHandler = async (rawArgs, context) => {
  const args = asArgs(rawArgs);
  const projectId = project(args, context);
  return jsonResponse(
    await context.gitlab.get(`${context.gitlab.projectPath(projectId)}/variables/${encodeURIComponent(requireString(args, "key"))}`, {
      params: { filter: optionalString(args, "environment_scope") ? { environment_scope: optionalString(args, "environment_scope") } : undefined },
    })
  );
};

export const createCiCdVariable: ToolHandler = async (rawArgs, context) => {
  const args = asArgs(rawArgs);
  assertWriteAllowed(context.policy, "gitlab_create_cicd_variable");
  const projectId = project(args, context);
  const body = variableBody(args, true);
  return jsonResponse(await context.gitlab.post(`${context.gitlab.projectPath(projectId)}/variables`, body));
};

export const updateCiCdVariable: ToolHandler = async (rawArgs, context) => {
  const args = asArgs(rawArgs);
  assertWriteAllowed(context.policy, "gitlab_update_cicd_variable");
  const projectId = project(args, context);
  const key = requireString(args, "key");
  const body = variableBody(args, false);
  return jsonResponse(
    await context.gitlab.put(`${context.gitlab.projectPath(projectId)}/variables/${encodeURIComponent(key)}`, body, {
      params: { filter: optionalString(args, "environment_scope") ? { environment_scope: optionalString(args, "environment_scope") } : undefined },
    })
  );
};

export const deleteCiCdVariable: ToolHandler = async (rawArgs, context) => {
  const args = asArgs(rawArgs);
  assertWriteAllowed(context.policy, "gitlab_delete_cicd_variable");
  const projectId = project(args, context);
  const key = requireString(args, "key");
  requireConfirmMessage(optionalString(args, "confirm_message"), deleteVariableConfirm(projectId, key));
  return jsonResponse(
    await context.gitlab.delete(`${context.gitlab.projectPath(projectId)}/variables/${encodeURIComponent(key)}`, {
      params: { filter: optionalString(args, "environment_scope") ? { environment_scope: optionalString(args, "environment_scope") } : undefined },
    })
  );
};

function variableBody(args: Record<string, unknown>, requireValue: boolean): Record<string, unknown> {
  const body: Record<string, unknown> = {};
  body.key = requireString(args, "key");
  const value = requireValue ? requireString(args, "value") : optionalString(args, "value");
  if (value !== undefined) body.value = value;
  const variableType = optionalEnum(args, "variable_type", ["env_var", "file"] as const);
  if (variableType !== undefined) body.variable_type = variableType;
  const environmentScope = optionalString(args, "environment_scope");
  if (environmentScope !== undefined) body.environment_scope = environmentScope;
  for (const key of ["protected", "masked"] as const) {
    const booleanValue = optionalBoolean(args, key);
    if (booleanValue !== undefined) body[key] = booleanValue;
  }
  return body;
}

export const getJob: ToolHandler = async (rawArgs, context) => {
  const args = asArgs(rawArgs);
  const projectId = project(args, context);
  const jobId = requireNumber(args, "job_id");
  return jsonResponse(await context.gitlab.get(`${context.gitlab.projectPath(projectId)}/jobs/${jobId}`));
};

export const getJobTrace: ToolHandler = async (rawArgs, context) => {
  const args = asArgs(rawArgs);
  const projectId = project(args, context);
  const jobId = requireNumber(args, "job_id");
  const tailLines = optionalPositiveInteger(args, "tail_lines") ?? context.policy.defaultTraceTailLines;
  const trace = await context.gitlab.get<string>(`${context.gitlab.projectPath(projectId)}/jobs/${jobId}/trace`, {
    responseType: "text",
    transformResponse: [(data: string) => data],
  });
  return textResponse(trace.split("\n").slice(-tailLines).join("\n"));
};

export const retryJob: ToolHandler = async (rawArgs, context) => {
  const args = asArgs(rawArgs);
  assertWriteAllowed(context.policy, "gitlab_retry_job");
  const projectId = project(args, context);
  const jobId = requireNumber(args, "job_id");
  return jsonResponse(await context.gitlab.post(`${context.gitlab.projectPath(projectId)}/jobs/${jobId}/retry`));
};

export const cancelJob: ToolHandler = async (rawArgs, context) => {
  const args = asArgs(rawArgs);
  assertWriteAllowed(context.policy, "gitlab_cancel_job");
  const projectId = project(args, context);
  const jobId = requireNumber(args, "job_id");
  return jsonResponse(await context.gitlab.post(`${context.gitlab.projectPath(projectId)}/jobs/${jobId}/cancel`));
};

export const listPipelineJobs: ToolHandler = async (rawArgs, context) => {
  const args = asArgs(rawArgs);
  const projectId = project(args, context);
  const pipelineId = requireNumber(args, "pipeline_id");
  return jsonResponse(
    await context.gitlab.get(`${context.gitlab.projectPath(projectId)}/pipelines/${pipelineId}/jobs`, {
      params: { per_page: optionalPerPage(args) ?? 50 },
    })
  );
};

