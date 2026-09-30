import { ToolHandler } from "../types.js";
import * as repository from "./repository.js";
import * as cicd from "./cicd.js";

export const toolRegistry: Record<string, ToolHandler> = {
  gitlab_list_projects: repository.listProjects,
  gitlab_get_project: repository.getProject,
  gitlab_list_branches: repository.listBranches,
  gitlab_list_merge_requests: repository.listMergeRequests,
  gitlab_get_merge_request: repository.getMergeRequest,
  gitlab_get_merge_request_changes: repository.getMergeRequestChanges,
  gitlab_create_merge_request_diff_note: repository.createMergeRequestDiffNote,
  gitlab_create_merge_request_note: repository.createMergeRequestNote,
  gitlab_create_merge_request_note_internal: repository.createMergeRequestNoteInternal,
  gitlab_update_merge_request: repository.updateMergeRequest,
  gitlab_close_merge_request: repository.closeMergeRequest,
  gitlab_create_merge_request: repository.createMergeRequest,
  gitlab_list_merge_request_discussions: repository.listMergeRequestDiscussions,
  gitlab_resolve_merge_request_discussion: repository.resolveMergeRequestDiscussion,
  gitlab_rebase_merge_request: repository.rebaseMergeRequest,
  gitlab_accept_merge_request: repository.acceptMergeRequest,
  gitlab_get_merge_request_approvals: repository.getMergeRequestApprovals,
  gitlab_list_issues: repository.listIssues,
  gitlab_get_repository_file: repository.getRepositoryFile,
  gitlab_compare_branches: repository.compareBranches,

  gitlab_list_trigger_tokens: cicd.listTriggerTokens,
  gitlab_get_trigger_token: cicd.getTriggerToken,
  gitlab_create_trigger_token: cicd.createTriggerToken,
  gitlab_update_trigger_token: cicd.updateTriggerToken,
  gitlab_delete_trigger_token: cicd.deleteTriggerToken,
  gitlab_trigger_pipeline: cicd.triggerPipeline,
  gitlab_list_cicd_variables: cicd.listCiCdVariables,
  gitlab_get_cicd_variable: cicd.getCiCdVariable,
  gitlab_create_cicd_variable: cicd.createCiCdVariable,
  gitlab_update_cicd_variable: cicd.updateCiCdVariable,
  gitlab_delete_cicd_variable: cicd.deleteCiCdVariable,
  gitlab_get_job: cicd.getJob,
  gitlab_get_job_trace: cicd.getJobTrace,
  gitlab_retry_job: cicd.retryJob,
  gitlab_cancel_job: cicd.cancelJob,
  gitlab_list_pipeline_jobs: cicd.listPipelineJobs,
};

