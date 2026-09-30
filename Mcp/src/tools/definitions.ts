import { ToolDefinition } from "../types.js";

const projectId = {
  type: "string",
  description: "GitLab project ID or path. Prefer raw path such as group/project; the server handles URL encoding.",
};

const confirmMessage = {
  type: "string",
  description: "Exact high-risk confirmation string required by this local stdio guardrail.",
};

export const toolDefinitions: ToolDefinition[] = [
  {
    name: "gitlab_list_projects",
    description: "List GitLab projects accessible to the token.",
    inputSchema: {
      type: "object",
      properties: {
        search: { type: "string" },
        owned: { type: "boolean" },
        membership: { type: "boolean" },
        per_page: { type: "number", minimum: 1, maximum: 100 },
      },
    },
  },
  {
    name: "gitlab_get_project",
    description: "Get details for a GitLab project.",
    inputSchema: { type: "object", properties: { project_id: projectId }, required: ["project_id"] },
  },
  {
    name: "gitlab_list_branches",
    description: "List branches for a project.",
    inputSchema: {
      type: "object",
      properties: { project_id: projectId, search: { type: "string" }, per_page: { type: "number", minimum: 1, maximum: 100 } },
      required: ["project_id"],
    },
  },
  {
    name: "gitlab_list_merge_requests",
    description: "List merge requests for a project.",
    inputSchema: {
      type: "object",
      properties: {
        project_id: projectId,
        state: { type: "string", enum: ["opened", "closed", "locked", "merged", "all"] },
        scope: { type: "string", enum: ["created_by_me", "assigned_to_me", "all"] },
        target_branch: { type: "string" },
        source_branch: { type: "string" },
        per_page: { type: "number", minimum: 1, maximum: 100 },
      },
      required: ["project_id"],
    },
  },
  {
    name: "gitlab_get_merge_request",
    description: "Get details for a merge request.",
    inputSchema: {
      type: "object",
      properties: { project_id: projectId, merge_request_iid: { type: "number" } },
      required: ["project_id", "merge_request_iid"],
    },
  },
  {
    name: "gitlab_get_merge_request_changes",
    description: "Get changes for a merge request.",
    inputSchema: {
      type: "object",
      properties: { project_id: projectId, merge_request_iid: { type: "number" } },
      required: ["project_id", "merge_request_iid"],
    },
  },
  {
    name: "gitlab_create_merge_request_diff_note",
    description: "Add an inline diff discussion note to a merge request.",
    inputSchema: {
      type: "object",
      properties: {
        project_id: projectId,
        merge_request_iid: { type: "number" },
        body: { type: "string" },
        base_sha: { type: "string" },
        start_sha: { type: "string" },
        head_sha: { type: "string" },
        old_path: { type: "string" },
        new_path: { type: "string" },
        old_line: { type: "number" },
        new_line: { type: "number" },
      },
      required: ["project_id", "merge_request_iid", "body", "base_sha", "start_sha", "head_sha", "new_path"],
    },
  },
  {
    name: "gitlab_create_merge_request_note",
    description: "Add a public note to a merge request.",
    inputSchema: {
      type: "object",
      properties: { project_id: projectId, merge_request_iid: { type: "number" }, body: { type: "string" } },
      required: ["project_id", "merge_request_iid", "body"],
    },
  },
  {
    name: "gitlab_create_merge_request_note_internal",
    description: "Add a merge request note, optionally marked internal where supported by GitLab.",
    inputSchema: {
      type: "object",
      properties: { project_id: projectId, merge_request_iid: { type: "number" }, body: { type: "string" }, internal: { type: "boolean" } },
      required: ["project_id", "merge_request_iid", "body"],
    },
  },
  {
    name: "gitlab_update_merge_request",
    description: "Update selected merge request attributes.",
    inputSchema: {
      type: "object",
      properties: {
        project_id: projectId,
        merge_request_iid: { type: "number" },
        title: { type: "string" },
        description: { type: "string" },
        target_branch: { type: "string" },
        labels: { type: "string" },
        draft: { type: "boolean" },
      },
      required: ["project_id", "merge_request_iid"],
    },
  },
  {
    name: "gitlab_close_merge_request",
    description: "Close a merge request. Requires confirm_message: CLOSE <project_id>!<iid>.",
    inputSchema: {
      type: "object",
      properties: { project_id: projectId, merge_request_iid: { type: "number" }, confirm_message: confirmMessage },
      required: ["project_id", "merge_request_iid", "confirm_message"],
    },
  },
  {
    name: "gitlab_create_merge_request",
    description: "Create a merge request.",
    inputSchema: {
      type: "object",
      properties: {
        project_id: projectId,
        source_branch: { type: "string" },
        target_branch: { type: "string" },
        title: { type: "string" },
        description: { type: "string" },
        assignee_id: { type: "number" },
        reviewer_ids: { type: "array", items: { type: "number" } },
        labels: { type: "string" },
        remove_source_branch: { type: "boolean" },
        squash: { type: "boolean" },
        draft: { type: "boolean" },
      },
      required: ["project_id", "source_branch", "target_branch", "title"],
    },
  },
  {
    name: "gitlab_list_merge_request_discussions",
    description: "List discussions on a merge request.",
    inputSchema: {
      type: "object",
      properties: { project_id: projectId, merge_request_iid: { type: "number" } },
      required: ["project_id", "merge_request_iid"],
    },
  },
  {
    name: "gitlab_resolve_merge_request_discussion",
    description: "Resolve or unresolve a merge request discussion.",
    inputSchema: {
      type: "object",
      properties: { project_id: projectId, merge_request_iid: { type: "number" }, discussion_id: { type: "string" }, resolved: { type: "boolean" } },
      required: ["project_id", "merge_request_iid", "discussion_id"],
    },
  },
  {
    name: "gitlab_rebase_merge_request",
    description: "Rebase a merge request. Requires confirm_message: REBASE <project_id>!<iid>.",
    inputSchema: {
      type: "object",
      properties: { project_id: projectId, merge_request_iid: { type: "number" }, skip_ci: { type: "boolean" }, confirm_message: confirmMessage },
      required: ["project_id", "merge_request_iid", "confirm_message"],
    },
  },
  {
    name: "gitlab_accept_merge_request",
    description: "Merge a merge request. Requires sha and confirm_message: MERGE <project_id>!<iid>.",
    inputSchema: {
      type: "object",
      properties: {
        project_id: projectId,
        merge_request_iid: { type: "number" },
        sha: { type: "string" },
        squash: { type: "boolean" },
        should_remove_source_branch: { type: "boolean" },
        merge_when_pipeline_succeeds: { type: "boolean" },
        merge_commit_message: { type: "string" },
        squash_commit_message: { type: "string" },
        confirm_message: confirmMessage,
      },
      required: ["project_id", "merge_request_iid", "sha", "confirm_message"],
    },
  },
  {
    name: "gitlab_get_merge_request_approvals",
    description: "Get approval state for a merge request.",
    inputSchema: {
      type: "object",
      properties: { project_id: projectId, merge_request_iid: { type: "number" } },
      required: ["project_id", "merge_request_iid"],
    },
  },
  {
    name: "gitlab_list_issues",
    description: "List project issues.",
    inputSchema: {
      type: "object",
      properties: { project_id: projectId, state: { type: "string", enum: ["opened", "closed", "all"] }, labels: { type: "string" }, per_page: { type: "number", minimum: 1, maximum: 100 } },
      required: ["project_id"],
    },
  },
  {
    name: "gitlab_get_repository_file",
    description: "Get repository file metadata and base64 content from GitLab.",
    inputSchema: {
      type: "object",
      properties: { project_id: projectId, file_path: { type: "string" }, ref: { type: "string" } },
      required: ["project_id", "file_path"],
    },
  },
  {
    name: "gitlab_compare_branches",
    description: "Compare branches, tags, or commits.",
    inputSchema: {
      type: "object",
      properties: { project_id: projectId, from: { type: "string" }, to: { type: "string" } },
      required: ["project_id", "from", "to"],
    },
  },
  {
    name: "gitlab_list_trigger_tokens",
    description: "List pipeline trigger tokens for a project. Token values are redacted.",
    inputSchema: { type: "object", properties: { project_id: projectId }, required: ["project_id"] },
  },
  {
    name: "gitlab_get_trigger_token",
    description: "Get a pipeline trigger token. Token values are redacted.",
    inputSchema: { type: "object", properties: { project_id: projectId, trigger_id: { type: "number" } }, required: ["project_id", "trigger_id"] },
  },
  {
    name: "gitlab_create_trigger_token",
    description: "Create a pipeline trigger token. Returned token value is redacted.",
    inputSchema: { type: "object", properties: { project_id: projectId, description: { type: "string" } }, required: ["project_id", "description"] },
  },
  {
    name: "gitlab_update_trigger_token",
    description: "Update a pipeline trigger token description.",
    inputSchema: { type: "object", properties: { project_id: projectId, trigger_id: { type: "number" }, description: { type: "string" } }, required: ["project_id", "trigger_id", "description"] },
  },
  {
    name: "gitlab_delete_trigger_token",
    description: "Delete a pipeline trigger token. Requires confirm_message: DELETE_TRIGGER_TOKEN <project_id>:<trigger_id>.",
    inputSchema: { type: "object", properties: { project_id: projectId, trigger_id: { type: "number" }, confirm_message: confirmMessage }, required: ["project_id", "trigger_id", "confirm_message"] },
  },
  {
    name: "gitlab_trigger_pipeline",
    description: "Trigger a pipeline with a trigger token or CI job token. Token is never logged or returned.",
    inputSchema: {
      type: "object",
      properties: { project_id: projectId, ref: { type: "string" }, token: { type: "string" }, variables: { type: "object", additionalProperties: { type: "string" } } },
      required: ["project_id", "ref", "token"],
    },
  },
  {
    name: "gitlab_list_cicd_variables",
    description: "List CI/CD variables. Values are redacted.",
    inputSchema: { type: "object", properties: { project_id: projectId }, required: ["project_id"] },
  },
  {
    name: "gitlab_get_cicd_variable",
    description: "Get a CI/CD variable. Value is redacted.",
    inputSchema: { type: "object", properties: { project_id: projectId, key: { type: "string" }, environment_scope: { type: "string" } }, required: ["project_id", "key"] },
  },
  {
    name: "gitlab_create_cicd_variable",
    description: "Create a CI/CD variable. Value is not returned in clear text.",
    inputSchema: {
      type: "object",
      properties: {
        project_id: projectId,
        key: { type: "string" },
        value: { type: "string" },
        protected: { type: "boolean" },
        masked: { type: "boolean" },
        variable_type: { type: "string", enum: ["env_var", "file"] },
        environment_scope: { type: "string" },
      },
      required: ["project_id", "key", "value"],
    },
  },
  {
    name: "gitlab_update_cicd_variable",
    description: "Update a CI/CD variable. Value is not returned in clear text.",
    inputSchema: {
      type: "object",
      properties: {
        project_id: projectId,
        key: { type: "string" },
        value: { type: "string" },
        protected: { type: "boolean" },
        masked: { type: "boolean" },
        variable_type: { type: "string", enum: ["env_var", "file"] },
        environment_scope: { type: "string" },
      },
      required: ["project_id", "key"],
    },
  },
  {
    name: "gitlab_delete_cicd_variable",
    description: "Delete a CI/CD variable. Requires confirm_message: DELETE_VARIABLE <project_id>:<key>.",
    inputSchema: {
      type: "object",
      properties: { project_id: projectId, key: { type: "string" }, environment_scope: { type: "string" }, confirm_message: confirmMessage },
      required: ["project_id", "key", "confirm_message"],
    },
  },
  {
    name: "gitlab_get_job",
    description: "Get CI/CD job details.",
    inputSchema: { type: "object", properties: { project_id: projectId, job_id: { type: "number" } }, required: ["project_id", "job_id"] },
  },
  {
    name: "gitlab_get_job_trace",
    description: "Get redacted CI/CD job trace text. Defaults to the last configured number of lines.",
    inputSchema: { type: "object", properties: { project_id: projectId, job_id: { type: "number" }, tail_lines: { type: "number" } }, required: ["project_id", "job_id"] },
  },
  {
    name: "gitlab_retry_job",
    description: "Retry a CI/CD job.",
    inputSchema: { type: "object", properties: { project_id: projectId, job_id: { type: "number" } }, required: ["project_id", "job_id"] },
  },
  {
    name: "gitlab_cancel_job",
    description: "Cancel a CI/CD job.",
    inputSchema: { type: "object", properties: { project_id: projectId, job_id: { type: "number" } }, required: ["project_id", "job_id"] },
  },
  {
    name: "gitlab_list_pipeline_jobs",
    description: "List jobs for a pipeline.",
    inputSchema: { type: "object", properties: { project_id: projectId, pipeline_id: { type: "number" }, per_page: { type: "number", minimum: 1, maximum: 100 } }, required: ["project_id", "pipeline_id"] },
  },
];

