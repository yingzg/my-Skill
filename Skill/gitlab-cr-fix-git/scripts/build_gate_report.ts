#!/usr/bin/env node

import { readFileSync, existsSync } from "node:fs";
import { join } from "node:path";
import { config, readInput } from "./config.ts";
import { parseSonarMeasures, type SonarResponse } from "./sonar_measures.ts";

type Note = {
  id?: number | string;
  body?: string;
  system?: boolean;
  author?: { username?: string; name?: string };
};
type Discussion = { id?: string; notes?: Note[] };
type Job = { id?: number; name?: string; status?: string; stage?: string };

type GateReportInput = {
  discussions: unknown;
  jobs: unknown;
  trace: string | null;
  junit: string | null;
  jacoco: string | null;
  sonar: SonarResponse | null;
};

function readIfExists(dir: string, name: string): string | null {
  const path = join(dir, name);
  return existsSync(path) ? readFileSync(path, "utf8") : null;
}

function readJson(dir: string, name: string): unknown | null {
  const text = readIfExists(dir, name);
  if (text === null) return null;
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

function toDiscussionList(input: unknown): Discussion[] {
  if (Array.isArray(input)) return input as Discussion[];
  return ((input as { discussions?: Discussion[] })?.discussions ?? []);
}

function toJobList(input: unknown): Job[] {
  if (Array.isArray(input)) return input as Job[];
  return ((input as { jobs?: Job[] })?.jobs ?? []);
}

function countEffectiveComments(discussions: Discussion[]) {
  const bots = new Set(config.gate.bot_usernames);
  const authors: string[] = [];
  let count = 0;
  for (const discussion of discussions) {
    for (const note of discussion.notes ?? []) {
      if (note.system === true) continue;
      const username = note.author?.username ?? "";
      if (bots.has(username)) continue;
      count += 1;
      authors.push(username || note.author?.name || "anonymous");
    }
  }
  return { current: count, authors };
}

function lineCoverageFromJacoco(xml: string): number | null {
  const lastPackageClose = xml.lastIndexOf("</package>");
  const tail = lastPackageClose >= 0 ? xml.slice(lastPackageClose + "</package>".length) : xml;
  for (const tag of tail.match(/<counter\b[^>]*?\/>/g) ?? []) {
    if ((tag.match(/\btype="([^"]*)"/)?.[1] ?? "") !== "LINE") continue;
    const missed = Number(tag.match(/\bmissed="([^"]*)"/)?.[1] ?? "0");
    const covered = Number(tag.match(/\bcovered="([^"]*)"/)?.[1] ?? "0");
    const total = missed + covered;
    if (total > 0) return Number(((covered / total) * 100).toFixed(2));
  }
  return null;
}

function passRateFromJunit(xml: string): number | null {
  let tests = 0;
  let failures = 0;
  let errors = 0;
  for (const tag of xml.match(/<testsuite\b[^>]*>/g) ?? []) {
    const attr = (name: string) => tag.match(new RegExp(`\\b${name}="([^"]*)"`))?.[1];
    tests += Number(attr("tests") ?? "0");
    failures += Number(attr("failures") ?? "0");
    errors += Number(attr("errors") ?? "0");
  }
  if (tests <= 0) return null;
  return Number((((tests - failures - errors) / tests) * 100).toFixed(2));
}

function passRateFromTrace(text: string): number | null {
  const totalPassed = Number(text.match(/Total Passed\s*:\s*(\d+)/i)?.[1]);
  const totalFailed = Number(text.match(/Total Failed\s*:\s*(\d+)/i)?.[1]);
  const totalCases = Number(text.match(/Total Test Cases\s*:\s*(\d+)/i)?.[1]);
  const cases = Number.isFinite(totalCases)
    ? totalCases
    : Number.isFinite(totalPassed) && Number.isFinite(totalFailed)
      ? totalPassed + totalFailed
      : NaN;
  const passed = Number.isFinite(totalPassed)
    ? totalPassed
    : Number.isFinite(cases) && Number.isFinite(totalFailed)
      ? cases - totalFailed
      : NaN;
  if (Number.isFinite(cases) && cases > 0 && Number.isFinite(passed)) {
    return Number(((passed / cases) * 100).toFixed(2));
  }
  const maven = text.match(/Tests run:\s*(\d+),\s*Failures:\s*(\d+),\s*Errors:\s*(\d+),\s*Skipped:\s*(\d+)/i);
  if (maven) {
    const mavenCases = Number(maven[1]);
    const mavenFailed = Number(maven[2]) + Number(maven[3]);
    if (mavenCases > 0) return Number((((mavenCases - mavenFailed) / mavenCases) * 100).toFixed(2));
  }
  return null;
}

function computeReport(input: GateReportInput) {
  const discussions = toDiscussionList(input.discussions);
  const jobs = toJobList(input.jobs);
  const trace = input.trace;
  const junit = input.junit;
  const jacoco = input.jacoco;
  const sonar = input.sonar;

  const comments = countEffectiveComments(discussions);
  const minComments = config.gate.min_effective_comments;

  const sonarParsed = sonar ? parseSonarMeasures(sonar) : null;
  const coverageFromSonar = sonarParsed?.coverage ?? null;
  const coverageFromJacoco = jacoco ? lineCoverageFromJacoco(jacoco) : null;
  const coverage = coverageFromSonar ?? coverageFromJacoco;
  const coverageThreshold = config.sonar.coverage_threshold;
  const coverageSource =
    coverageFromSonar !== null
      ? sonarParsed?.coverage_metric === "new_line_coverage"
        ? "sonar:new_line_coverage"
        : "sonar:coverage（全量）"
      : coverageFromJacoco !== null
        ? "jacoco.xml（全量行覆盖，非新增）"
        : null;

  const passRateFromTraceVal = trace ? passRateFromTrace(trace) : null;
  const passRateFromJunitVal = junit ? passRateFromJunit(junit) : null;
  const passRate = passRateFromTraceVal ?? passRateFromJunitVal;
  const passRateThreshold = config.gate.test_pass_rate_threshold;
  const passRateSource =
    passRateFromTraceVal !== null
      ? "gitlab_get_job_trace.txt（全局汇总）"
      : passRateFromJunitVal !== null
        ? "junit_report.xml"
        : null;

  const failedJobs = jobs.filter((job) => job.status === "failed");
  const pipelineStatus = jobs.length === 0 ? null : failedJobs.length > 0 ? "failed" : "passed";

  const gate = {
    effective_comments: {
      current: comments.current,
      required: minComments,
      passed: comments.current >= minComments,
      authors: comments.authors,
    },
    coverage: {
      current: coverage,
      required: coverageThreshold,
      passed: coverage !== null ? coverage >= coverageThreshold : null,
      source: coverageSource,
    },
    test_pass_rate: {
      current: passRate,
      required: passRateThreshold,
      passed: passRate !== null ? passRate >= passRateThreshold : null,
      source: passRateSource,
    },
    code_quality: {
      status: "missing",
      passed: null,
      note: "代码规范门禁（bugs/code smells）需外部 Sonar/静态分析结果提供",
    },
    pipeline: {
      status: pipelineStatus,
      passed: pipelineStatus === "passed",
      failed_jobs: failedJobs.map((job) => job.name ?? job.id ?? null),
    },
    approval: {
      status: "unknown",
      passed: null,
      note: "需 gitlab_get_merge_request_approvals 数据",
    },
  };

  const blockers = Object.entries({
    effective_comments: gate.effective_comments.passed,
    coverage: gate.coverage.passed,
    test_pass_rate: gate.test_pass_rate.passed,
    pipeline: gate.pipeline.passed,
  })
    .filter(([, passed]) => passed === false)
    .map(([name]) => name);

  const lines = ["### Gate Report", ""];
  lines.push(`- 有效评论数：${comments.current} / ${minComments}`);
  lines.push(
    coverage !== null
      ? `- 变更代码单元测试覆盖率：${coverage}% / ${coverageThreshold}%`
      : `- 变更代码单元测试覆盖率：缺失 / ${coverageThreshold}%`,
  );
  lines.push(
    passRate !== null
      ? `- 单测用例执行通过率：${passRate}% / ${passRateThreshold}%`
      : `- 单测用例执行通过率：缺失 / ${passRateThreshold}%`,
  );
  lines.push(`- Sonar质量门禁：缺失（需外部 Sonar/静态分析结果）`);
  if (pipelineStatus !== null) lines.push(`- Pipeline：${pipelineStatus}`);
  lines.push(`- Approve：未知（需 approval API）`);

  return {
    markdown: lines.join("\n"),
    gate,
    blockers,
    missing_data: {
      code_quality: true,
      approval: true,
      coverage: coverage === null,
      test_pass_rate: passRate === null,
    },
  };
}

function readDirInput(dir: string): GateReportInput {
  return {
    discussions: readJson(dir, "gitlab_list_merge_request_discussions.json"),
    jobs: readJson(dir, "gitlab_list_pipeline_jobs.json"),
    trace: readIfExists(dir, "gitlab_get_job_trace.txt"),
    junit: readIfExists(dir, "junit_report.xml"),
    jacoco: readIfExists(dir, "jacoco.xml"),
    sonar: readJson(dir, "sonar_measures_component.json") as SonarResponse | null,
  };
}

function readStdinInput(): GateReportInput {
  const data = JSON.parse(readInput("-")) as {
    discussions?: unknown;
    pipeline_jobs?: unknown;
    job_trace?: string;
    junit_xml?: string;
    jacoco_xml?: string;
    sonar_measures?: SonarResponse;
  };
  return {
    discussions: data.discussions ?? null,
    jobs: data.pipeline_jobs ?? null,
    trace: data.job_trace ?? null,
    junit: data.junit_xml ?? null,
    jacoco: data.jacoco_xml ?? null,
    sonar: data.sonar_measures ?? null,
  };
}

const arg = process.argv[2];
if (!arg) {
  console.error("Usage: node --experimental-strip-types scripts/build_gate_report.ts <data_dir> | -（stdin 聚合 JSON）");
  process.exit(2);
}

try {
  const input = arg === "-" ? readStdinInput() : readDirInput(arg);
  console.log(JSON.stringify(computeReport(input), null, 2));
} catch (error) {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
}
