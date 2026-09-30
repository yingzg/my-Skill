#!/usr/bin/env node

import { readFileSync } from "node:fs";

type FailedTest = {
  class: string | null;
  method: string | null;
  raw: string;
  message?: string;
};

type CompilationError = {
  file: string;
  line: number | null;
  column: number | null;
  message: string;
  symbol?: string;
  location?: string;
};

function parseNumber(pattern: RegExp, text: string): number | null {
  const match = text.match(pattern);
  return match ? Number(match[1]) : null;
}

function parseFailedTests(text: string): FailedTest[] {
  const failed: FailedTest[] = [];
  const lines = text.split(/\r?\n/);

  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i];
    const explicit = line.match(/(?:FAILED|FAILURE|ERROR)\s*:?\s+([A-Za-z0-9_.$]+)(?:[.#]([A-Za-z0-9_$-]+))?/);
    const maven = line.match(/\[ERROR\]\s+([A-Za-z0-9_.$]+)\.([A-Za-z0-9_$-]+)/);
    const pytest = line.match(/FAILED\s+(.+?)::([A-Za-z0-9_$-]+)/);

    const match = explicit ?? maven ?? pytest;
    if (!match) continue;

    const className = match[1] ?? null;
    const method = match[2] ?? null;
    const next = lines.slice(i + 1, i + 5).find((candidate) => {
      const trimmed = candidate.trim();
      return trimmed &&
        !trimmed.includes("[INFO]") &&
        !trimmed.startsWith("Total ") &&
        !trimmed.startsWith("[ERROR] Failures:") &&
        !trimmed.startsWith("[ERROR] Tests run:");
    });
    failed.push({
      class: className,
      method,
      raw: line.trim(),
      message: next?.trim(),
    });
  }

  const seen = new Set<string>();
  return failed.filter((item) => {
    const classTail = item.class?.split(".").slice(-1)[0] ?? "";
    const key = item.method ? `${classTail}#${item.method}` : `${item.class ?? ""}#${item.raw}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function parseCompilationErrors(text: string): CompilationError[] {
  const errors: CompilationError[] = [];
  const lines = text.split(/\r?\n/);

  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i];
    const match = line.match(/\[ERROR\]\s+(.+?\.java):\[(\d+),(\d+)\]\s+(.+)/);
    if (!match) continue;

    const symbolLine = lines.slice(i + 1, i + 4).find((candidate) => candidate.trim().startsWith("symbol:"));
    const locationLine = lines.slice(i + 1, i + 5).find((candidate) => candidate.trim().startsWith("location:"));

    errors.push({
      file: match[1],
      line: Number(match[2]),
      column: Number(match[3]),
      message: match[4].trim(),
      symbol: symbolLine?.replace(/^\s*symbol:\s*/, "").trim(),
      location: locationLine?.replace(/^\s*location:\s*/, "").trim(),
    });
  }

  const seen = new Set<string>();
  return errors.filter((error) => {
    const key = `${error.file}:${error.line}:${error.column}:${error.message}:${error.symbol ?? ""}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function parseTrace(text: string) {
  const totalPassed = parseNumber(/Total Passed\s*:\s*(\d+)/i, text);
  const totalFailed = parseNumber(/Total Failed\s*:\s*(\d+)/i, text);
  const totalCases = parseNumber(/Total Test Cases\s*:\s*(\d+)/i, text);

  const mavenSummary = text.match(/Tests run:\s*(\d+),\s*Failures:\s*(\d+),\s*Errors:\s*(\d+),\s*Skipped:\s*(\d+)/i);
  const mavenCases = mavenSummary ? Number(mavenSummary[1]) : null;
  const mavenFailures = mavenSummary ? Number(mavenSummary[2]) + Number(mavenSummary[3]) : null;

  const cases = totalCases ?? mavenCases;
  const failures = totalFailed ?? mavenFailures;
  const passed = totalPassed ?? (cases !== null && failures !== null ? cases - failures : null);
  const passRate = cases && passed !== null ? Number(((passed / cases) * 100).toFixed(2)) : null;

  return {
    total_passed: passed,
    total_failed: failures,
    total_cases: cases,
    pass_rate: passRate,
    compilation_errors: parseCompilationErrors(text),
    failed_tests: parseFailedTests(text),
  };
}

const path = process.argv[2];
if (!path) {
  console.error("Usage: node --experimental-strip-types scripts/parse_job_trace.ts <gitlab_get_job_trace.txt>");
  process.exit(2);
}

try {
  console.log(JSON.stringify(parseTrace(readFileSync(path, "utf8")), null, 2));
} catch (error) {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
}
