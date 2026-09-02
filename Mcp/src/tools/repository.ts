import { jsonResponse } from "../lib/response.js";
import {
  asArgs,
  optionalBoolean,
  optionalEnum,
  optionalNumberArray,
  optionalPerPage,
  optionalString,
  requireNumber,
  requireString,
} from "../lib/validation.js";
import { ToolContext, ToolHandler } from "../types.js";
import { assertProjectAllowed, assertWriteAllowed } from "../security/policy.js";
import {
  closeConfirm,
  mergeConfirm,
  rebaseConfirm,
  requireConfirmMessage,
} from "../security/confirm.js";
import { ValidationError } from "../lib/errors.js";

function project(args: Record<string, unknown>, context: ToolContext): string {
  const projectId = requireString(args, "project_id");
  assertProjectAllowed(context.policy, projectId);
  return projectId;
}

export const listProjects: ToolHandler = async (rawArgs, context) => {
  const args = asArgs(rawArgs);
  const data = await context.gitlab.get("/projects", {
    params: {
      search: optionalString(args, "search"),
      owned: optionalBoolean(args, "owned"),
      membership: optionalBoolean(args, "membership"),
      per_page: optionalPerPage(args) ?? 50,
    },
  });
  return jsonResponse(data);
};

export const getProject: ToolHandler = async (rawArgs, context) => {
  const args = asArgs(rawArgs);
  const projectId = project(args, context);
  return jsonResponse(await context.gitlab.get(context.gitlab.projectPath(projectId)));
};

export const listBranches: ToolHandler = async (rawArgs, context) => {
  const args = asArgs(rawArgs);
  const projectId = project(args, context);
  return jsonResponse(
    await context.gitlab.get(`${context.gitlab.projectPath(projectId)}/repository/branches`, {
      params: {
        search: optionalString(args, "search"),
        per_page: optionalPerPage(args) ?? 50,
      },
    })
  );
};

export const listMergeRequests: ToolHandler = async (rawArgs, context) => {
  const args = asArgs(rawArgs);
  const projectId = project(args, context);
  return jsonResponse(
    await context.gitlab.get(`${context.gitlab.projectPath(projectId)}/merge_requests`, {
      params: {
        state: optionalEnum(args, "state", ["opened", "closed", "locked", "merged", "all"] as const),
        scope: optionalEnum(args, "scope", ["created_by_me", "assigned_to_me", "all"] as const),
        target_branch: optionalString(args, "target_branch"),
        source_branch: optionalString(args, "source_branch"),
        per_page: optionalPerPage(args) ?? 50,
      },
    })
  );
};

export const getMergeRequest: ToolHandler = async (rawArgs, context) => {
  const args = asArgs(rawArgs);
  const projectId = project(args, context);
  const iid = requireNumber(args, "merge_request_iid");
  return jsonResponse(await context.gitlab.get(`${context.gitlab.projectPath(projectId)}/merge_requests/${iid}`));
};

export const getMergeRequestChanges: ToolHandler = async (rawArgs, context) => {
  const args = asArgs(rawArgs);
  const projectId = project(args, context);
  const iid = requireNumber(args, "merge_request_iid");
  return jsonResponse(await context.gitlab.get(`${context.gitlab.projectPath(projectId)}/merge_requests/${iid}/changes`));
};

export const createMergeRequestDiffNote: ToolHandler = async (rawArgs, context) => {
  const args = asArgs(rawArgs);
  assertWriteAllowed(context.policy, "gitlab_create_merge_request_diff_note");
  const projectId = project(args, context);
  const iid = requireNumber(args, "merge_request_iid");
  const body = requireString(args, "body");
  const baseSha = requireString(args, "base_sha");
  const startSha = requireString(args, "start_sha");
  const headSha = requireString(args, "head_sha");
  const newPath = requireString(args, "new_path");
  const oldPath = optionalString(args, "old_path") ?? newPath;
  const oldLine = args.old_line === undefined ? undefined : requireNumber(args, "old_line");
  const newLine = args.new_line === undefined ? undefined : requireNumber(args, "new_line");

  if (oldLine === undefined && newLine === undefined) {
    throw new ValidationError("At least one of old_line or new_line is required");
  }

  const position: Record<string, unknown> = {
    position_type: "text",
    base_sha: baseSha,
    start_sha: startSha,
    head_sha: headSha,
    old_path: oldPath,
    new_path: newPath,
  };
  if (oldLine !== undefined) position.old_line = oldLine;
  if (newLine !== undefined) position.new_line = newLine;

  return jsonResponse(
    await context.gitlab.post(`${context.gitlab.projectPath(projectId)}/merge_requests/${iid}/discussions`, {
      body,
      position,
    })
  );
};

export const createMergeRequestNote: ToolHandler = async (rawArgs, context) => {
  const args = asArgs(rawArgs);
  assertWriteAllowed(context.policy, "gitlab_create_merge_request_note");
  const projectId = project(args, context);
  const iid = requireNumber(args, "merge_request_iid");
  return jsonResponse(
    await context.gitlab.post(`${context.gitlab.projectPath(projectId)}/merge_requests/${iid}/notes`, {
      body: requireString(args, "body"),
    })
  );
};

export const createMergeRequestNoteInternal: ToolHandler = async (rawArgs, context) => {
  const args = asArgs(rawArgs);
  assertWriteAllowed(context.policy, "gitlab_create_merge_request_note_internal");
  const projectId = project(args, context);
  const iid = requireNumber(args, "merge_request_iid");
  return jsonResponse(
    await context.gitlab.post(`${context.gitlab.projectPath(projectId)}/merge_requests/${iid}/notes`, {
      body: requireString(args, "body"),
      internal: optionalBoolean(args, "internal") === true,
    })
  );
};

export const updateMergeRequest: ToolHandler = async (rawArgs, context) => {
  const args = asArgs(rawArgs);
  assertWriteAllowed(context.policy, "gitlab_update_merge_request");
  const projectId = project(args, context);
  const iid = requireNumber(args, "merge_request_iid");
  const body: Record<string, unknown> = {};
  for (const key of ["title", "description", "target_branch", "labels"] as const) {
    const value = optionalString(args, key);
    if (value !== undefined) body[key] = value;
  }
  const draft = optionalBoolean(args, "draft");
  if (draft !== undefined) body.draft = draft;
  if (Object.keys(body).length === 0) {
    throw new ValidationError("At least one update field is required");
  }
  return jsonResponse(await context.gitlab.put(`${context.gitlab.projectPath(projectId)}/merge_requests/${iid}`, body));
};

export const closeMergeRequest: ToolHandler = async (rawArgs, context) => {
  const args = asArgs(rawArgs);
  assertWriteAllowed(context.policy, "gitlab_close_merge_request");
  const projectId = project(args, context);
  const iid = requireNumber(args, "merge_request_iid");
  requireConfirmMessage(optionalString(args, "confirm_message"), closeConfirm(projectId, iid));
  return jsonResponse(
    await context.gitlab.put(`${context.gitlab.projectPath(projectId)}/merge_requests/${iid}`, {
      state_event: "close",
    })
  );
};

export const createMergeRequest: ToolHandler = async (rawArgs, context) => {
  const args = asArgs(rawArgs);
  assertWriteAllowed(context.policy, "gitlab_create_merge_request");
  const projectId = project(args, context);
  const body: Record<string, unknown> = {
    source_branch: requireString(args, "source_branch"),
    target_branch: requireString(args, "target_branch"),
    title: requireString(args, "title"),
  };
  for (const key of ["description", "labels"] as const) {
    const value = optionalString(args, key);
    if (value !== undefined) body[key] = value;
  }
  for (const key of ["assignee_id"] as const) {
    const value = args[key] === undefined ? undefined : requireNumber(args, key);
    if (value !== undefined) body[key] = value;
  }
  const reviewerIds = optionalNumberArray(args, "reviewer_ids");
  if (reviewerIds !== undefined) body.reviewer_ids = reviewerIds;
  for (const key of ["remove_source_branch", "squash", "draft"] as const) {
    const value = optionalBoolean(args, key);
    if (value !== undefined) body[key] = value;
  }
  return jsonResponse(await context.gitlab.post(`${context.gitlab.projectPath(projectId)}/merge_requests`, body));
};

export const listMergeRequestDiscussions: ToolHandler = async (rawArgs, context) => {
  const args = asArgs(rawArgs);
  const projectId = project(args, context);
  const iid = requireNumber(args, "merge_request_iid");
  return jsonResponse(await context.gitlab.get(`${context.gitlab.projectPath(projectId)}/merge_requests/${iid}/discussions`));
};

export const resolveMergeRequestDiscussion: ToolHandler = async (rawArgs, context) => {
  const args = asArgs(rawArgs);
  assertWriteAllowed(context.policy, "gitlab_resolve_merge_request_discussion");
  const projectId = project(args, context);
  const iid = requireNumber(args, "merge_request_iid");
  const discussionId = requireString(args, "discussion_id");
  return jsonResponse(
    await context.gitlab.put(`${context.gitlab.projectPath(projectId)}/merge_requests/${iid}/discussions/${discussionId}`, {
      resolved: optionalBoolean(args, "resolved") !== false,
    })
  );
};

export const rebaseMergeRequest: ToolHandler = async (rawArgs, context) => {
  const args = asArgs(rawArgs);
  assertWriteAllowed(context.policy, "gitlab_rebase_merge_request");
  const projectId = project(args, context);
  const iid = requireNumber(args, "merge_request_iid");
  requireConfirmMessage(optionalString(args, "confirm_message"), rebaseConfirm(projectId, iid));
  return jsonResponse(
    await context.gitlab.put(`${context.gitlab.projectPath(projectId)}/merge_requests/${iid}/rebase`, {
      skip_ci: optionalBoolean(args, "skip_ci") === true,
    })
  );
};

export const acceptMergeRequest: ToolHandler = async (rawArgs, context) => {
  const args = asArgs(rawArgs);
  assertWriteAllowed(context.policy, "gitlab_accept_merge_request");
  const projectId = project(args, context);
  const iid = requireNumber(args, "merge_request_iid");
  const sha = requireString(args, "sha");
  requireConfirmMessage(optionalString(args, "confirm_message"), mergeConfirm(projectId, iid));

  const current = await context.gitlab.get<Record<string, unknown>>(`${context.gitlab.projectPath(projectId)}/merge_requests/${iid}`);
  if (current.sha !== sha) {
    throw new ValidationError("Merge request sha no longer matches; re-read the MR before merging");
  }

  const body: Record<string, unknown> = { sha };
  for (const key of ["merge_commit_message", "squash_commit_message"] as const) {
    const value = optionalString(args, key);
    if (value !== undefined) body[key] = value;
  }
  for (const key of ["squash", "should_remove_source_branch", "merge_when_pipeline_succeeds"] as const) {
    const value = optionalBoolean(args, key);
    if (value !== undefined) body[key] = value;
  }
  return jsonResponse(await context.gitlab.put(`${context.gitlab.projectPath(projectId)}/merge_requests/${iid}/merge`, body));
};

export const getMergeRequestApprovals: ToolHandler = async (rawArgs, context) => {
  const args = asArgs(rawArgs);
  const projectId = project(args, context);
  const iid = requireNumber(args, "merge_request_iid");
  return jsonResponse(await context.gitlab.get(`${context.gitlab.projectPath(projectId)}/merge_requests/${iid}/approvals`));
};

export const listIssues: ToolHandler = async (rawArgs, context) => {
  const args = asArgs(rawArgs);
  const projectId = project(args, context);
  return jsonResponse(
    await context.gitlab.get(`${context.gitlab.projectPath(projectId)}/issues`, {
      params: {
        state: optionalEnum(args, "state", ["opened", "closed", "all"] as const),
        labels: optionalString(args, "labels"),
        per_page: optionalPerPage(args) ?? 50,
      },
    })
  );
};

export const getRepositoryFile: ToolHandler = async (rawArgs, context) => {
  const args = asArgs(rawArgs);
  const projectId = project(args, context);
  const filePath = encodeURIComponent(requireString(args, "file_path"));
  return jsonResponse(
    await context.gitlab.get(`${context.gitlab.projectPath(projectId)}/repository/files/${filePath}`, {
      params: { ref: optionalString(args, "ref") ?? "main" },
    })
  );
};

export const compareBranches: ToolHandler = async (rawArgs, context) => {
  const args = asArgs(rawArgs);
  const projectId = project(args, context);
  return jsonResponse(
    await context.gitlab.get(`${context.gitlab.projectPath(projectId)}/repository/compare`, {
      params: {
        from: requireString(args, "from"),
        to: requireString(args, "to"),
      },
    })
  );
};

