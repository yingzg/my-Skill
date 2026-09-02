#!/usr/bin/env node

import { readFileSync } from "node:fs";

type Job = {
  id?: number;
  name?: string;
  status?: string;
  stage?: string;
  web_url?: string;
};

const TEST_JOB_PATTERNS = [/sonar-scan\+test/i, /unit[-_ ]?test/i, /\btest\b/i, /maven.*test/i, /npm.*test/i];

function isTestJob(job: Job): boolean {
  const text = `${job.name ?? ""} ${job.stage ?? ""}`;
  return TEST_JOB_PATTERNS.some((pattern) => pattern.test(text));
}

function summarize(jobs: Job[]) {
  const testJobs = jobs.filter(isTestJob);
  return {
    total_jobs: jobs.length,
    failed_jobs: jobs.filter((job) => job.status === "failed"),
    test_jobs: testJobs,
    failed_test_jobs: testJobs.filter((job) => job.status === "failed"),
    preferred_trace_job: testJobs.find((job) => job.status === "failed") ?? testJobs[0] ?? null,
  };
}

const path = process.argv[2];
if (!path) {
  console.error("Usage: node --experimental-strip-types scripts/parse_pipeline_jobs.ts <gitlab_list_pipeline_jobs.json>");
  process.exit(2);
}

try {
  const input = JSON.parse(readFileSync(path, "utf8"));
  const jobs = Array.isArray(input) ? input : input.jobs ?? [];
  console.log(JSON.stringify(summarize(jobs), null, 2));
} catch (error) {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
}

