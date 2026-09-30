#!/usr/bin/env node

import { readInput } from "./config.ts";

type FailedTest = {
  classname: string | null;
  name: string | null;
  type: string | null;
  message: string | null;
};

function attr(attrs: string, name: string): string | null {
  const match = attrs.match(new RegExp(`\\b${name}="([^"]*)"`));
  return match ? match[1] : null;
}

function toNumber(value: string | null): number {
  if (value === null) return 0;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function parseJunit(xml: string) {
  let tests = 0;
  let failures = 0;
  let errors = 0;
  let skipped = 0;
  let suites = 0;

  const suitePattern = /<testsuite\b[^>]*>/g;
  for (const suiteTag of xml.match(suitePattern) ?? []) {
    suites += 1;
    tests += toNumber(attr(suiteTag, "tests"));
    failures += toNumber(attr(suiteTag, "failures"));
    errors += toNumber(attr(suiteTag, "errors"));
    skipped += toNumber(attr(suiteTag, "skipped"));
  }

  const failedTests: FailedTest[] = [];
  const testcasePattern = /<testcase\b([^>]*)>([\s\S]*?)<\/testcase>|<testcase\b([^>]*)\/>/g;
  for (const match of xml.matchAll(testcasePattern)) {
    const attrs = match[1] ?? match[3] ?? "";
    const body = match[2] ?? "";
    const failureTag = body.match(/<failure\b([^>]*)/) ?? body.match(/<error\b([^>]*)/);
    if (!failureTag) continue;
    failedTests.push({
      classname: attr(attrs, "classname"),
      name: attr(attrs, "name"),
      type: attr(failureTag[1], "type"),
      message: attr(failureTag[1], "message"),
    });
  }

  const passRate = tests > 0 ? Number((((tests - failures - errors) / tests) * 100).toFixed(2)) : null;

  return {
    suites,
    tests,
    failures,
    errors,
    skipped,
    pass_rate: passRate,
    failed_tests: failedTests,
  };
}

const path = process.argv[2];
if (!path) {
  console.error("Usage: node --experimental-strip-types scripts/parse_junit_xml.ts <junit_report.xml>");
  process.exit(2);
}

try {
  const xml = readInput(path);
  console.log(JSON.stringify(parseJunit(xml), null, 2));
} catch (error) {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
}
