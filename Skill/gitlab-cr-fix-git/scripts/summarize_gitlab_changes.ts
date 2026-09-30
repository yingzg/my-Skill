#!/usr/bin/env node

import { readFileSync } from "node:fs";

type Change = {
  old_path?: string;
  new_path?: string;
  new_file?: boolean;
  renamed_file?: boolean;
  deleted_file?: boolean;
  diff?: string;
};

type ChangesResponse = {
  changes?: Change[];
};

function riskForPath(path: string): "high" | "medium" | "low" | "ignore" {
  const lower = path.toLowerCase();
  if (/\.(png|jpg|jpeg|gif|webp|ico|pdf|zip|jar)$/.test(lower)) return "ignore";
  if (lower.includes(".claude/") || lower.includes("settings.local")) return "ignore";
  if (/(test|spec|readme|\.md$)/i.test(path)) return "low";
  if (/(service|serviceimpl|domainservice|controller|repository|mapper\.xml|dao|gateway|sql)/i.test(path)) return "high";
  if (/(helper|util|strategy|entity|model|config|client|adapter)/i.test(path)) return "medium";
  if (/(dto|request|response|converter|constant|enum)/i.test(path)) return "low";
  if (/\.(java|kt|ts|tsx|js|jsx|go|rs|py|xml|yml|yaml|json)$/.test(lower)) return "medium";
  return "low";
}

function languageForPath(path: string): string {
  const ext = path.split(".").pop()?.toLowerCase() ?? "";
  const map: Record<string, string> = {
    java: "java",
    kt: "kotlin",
    ts: "typescript",
    tsx: "typescript",
    js: "javascript",
    jsx: "javascript",
    py: "python",
    go: "go",
    rs: "rust",
    xml: "xml",
    sql: "sql",
    yml: "yaml",
    yaml: "yaml",
    json: "json",
    md: "markdown",
  };
  return map[ext] ?? "unknown";
}

function summarize(input: ChangesResponse) {
  const changes = input.changes ?? [];
  const files = changes.map((change) => {
    const path = change.new_path || change.old_path || "";
    const risk = riskForPath(path);
    return {
      path,
      old_path: change.old_path ?? null,
      change_type: change.deleted_file ? "deleted" : change.new_file ? "new" : change.renamed_file ? "renamed" : "modified",
      language: languageForPath(path),
      risk,
      additions_hint: (change.diff?.match(/^\+(?!\+\+)/gm) ?? []).length,
      deletions_hint: (change.diff?.match(/^-(?!--)/gm) ?? []).length,
      diff_bytes: Buffer.byteLength(change.diff ?? "", "utf8"),
    };
  });

  const byRisk = files.reduce<Record<string, number>>((acc, file) => {
    acc[file.risk] = (acc[file.risk] ?? 0) + 1;
    return acc;
  }, {});

  return {
    changed_file_count: files.length,
    by_risk: byRisk,
    high_priority_files: files.filter((file) => file.risk === "high").map((file) => file.path),
    files,
  };
}

const path = process.argv[2];
if (!path) {
  console.error("Usage: node --experimental-strip-types scripts/summarize_gitlab_changes.ts <gitlab_get_merge_request_changes.json>");
  process.exit(2);
}

try {
  const input = JSON.parse(readFileSync(path, "utf8"));
  console.log(JSON.stringify(summarize(input), null, 2));
} catch (error) {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
}
