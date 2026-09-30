#!/usr/bin/env node

import { readFileSync } from "node:fs";

type GitLabMr = {
  iid?: number;
  title?: string;
  state?: string;
  author?: { username?: string; name?: string; email?: string };
  source_branch?: string;
  target_branch?: string;
  merge_status?: string;
  detailed_merge_status?: string;
  head_pipeline?: { id?: number; status?: string; web_url?: string };
  diff_refs?: { base_sha?: string; start_sha?: string; head_sha?: string };
  web_url?: string;
};

function readJson(path: string): GitLabMr {
  return JSON.parse(readFileSync(path, "utf8"));
}

function summarize(mr: GitLabMr) {
  return {
    iid: mr.iid ?? null,
    title: mr.title ?? null,
    state: mr.state ?? null,
    author: {
      username: mr.author?.username ?? null,
      name: mr.author?.name ?? null,
      email: mr.author?.email ?? null,
    },
    branches: {
      source: mr.source_branch ?? null,
      target: mr.target_branch ?? null,
    },
    merge: {
      merge_status: mr.merge_status ?? null,
      detailed_merge_status: mr.detailed_merge_status ?? null,
      has_conflict: ["cannot_be_merged", "conflicts"].includes(String(mr.merge_status ?? "")) ||
        String(mr.detailed_merge_status ?? "").includes("conflict"),
    },
    pipeline: {
      id: mr.head_pipeline?.id ?? null,
      status: mr.head_pipeline?.status ?? null,
      web_url: mr.head_pipeline?.web_url ?? null,
      passed: mr.head_pipeline?.status === "success",
      failed: mr.head_pipeline?.status === "failed",
    },
    diff_refs: {
      base_sha: mr.diff_refs?.base_sha ?? null,
      start_sha: mr.diff_refs?.start_sha ?? null,
      head_sha: mr.diff_refs?.head_sha ?? null,
      complete: Boolean(mr.diff_refs?.base_sha && mr.diff_refs?.start_sha && mr.diff_refs?.head_sha),
    },
    web_url: mr.web_url ?? null,
  };
}

const path = process.argv[2];
if (!path) {
  console.error("Usage: node --experimental-strip-types scripts/summarize_gitlab_mr.ts <gitlab_get_merge_request.json>");
  process.exit(2);
}

try {
  console.log(JSON.stringify(summarize(readJson(path)), null, 2));
} catch (error) {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
}
