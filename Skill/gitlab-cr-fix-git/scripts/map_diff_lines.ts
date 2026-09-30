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

type CommentableLine = {
  type: "added" | "removed" | "context";
  old_line: number | null;
  new_line: number | null;
  content: string;
};

type Hunk = {
  old_start: number;
  old_count: number;
  new_start: number;
  new_count: number;
  header: string;
};

function parseHunkHeader(line: string): Hunk | null {
  const match = line.match(/^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@/);
  if (!match) return null;
  return {
    old_start: Number(match[1]),
    old_count: Number(match[2] ?? "1"),
    new_start: Number(match[3]),
    new_count: Number(match[4] ?? "1"),
    header: line,
  };
}

function mapChange(change: Change) {
  const oldPath = change.old_path ?? change.new_path ?? "";
  const newPath = change.new_path ?? change.old_path ?? "";
  const lines = (change.diff ?? "").split(/\r?\n/);
  const hunks: Hunk[] = [];
  const commentableLines: CommentableLine[] = [];

  let oldLine = 0;
  let newLine = 0;
  let inHunk = false;

  for (const line of lines) {
    const hunk = parseHunkHeader(line);
    if (hunk) {
      hunks.push(hunk);
      oldLine = hunk.old_start;
      newLine = hunk.new_start;
      inHunk = true;
      continue;
    }

    if (!inHunk || line === "" || line === "\\ No newline at end of file") {
      continue;
    }

    if (line.startsWith("+") && !line.startsWith("+++")) {
      commentableLines.push({
        type: "added",
        old_line: null,
        new_line: newLine,
        content: line.slice(1),
      });
      newLine += 1;
      continue;
    }

    if (line.startsWith("-") && !line.startsWith("---")) {
      commentableLines.push({
        type: "removed",
        old_line: oldLine,
        new_line: null,
        content: line.slice(1),
      });
      oldLine += 1;
      continue;
    }

    commentableLines.push({
      type: "context",
      old_line: oldLine,
      new_line: newLine,
      content: line.startsWith(" ") ? line.slice(1) : line,
    });
    oldLine += 1;
    newLine += 1;
  }

  return {
    old_path: oldPath,
    new_path: newPath,
    change_type: change.deleted_file ? "deleted" : change.new_file ? "new" : change.renamed_file ? "renamed" : "modified",
    hunks,
    commentable_lines: commentableLines,
    added_lines: commentableLines.filter((item) => item.type === "added"),
    removed_lines: commentableLines.filter((item) => item.type === "removed"),
  };
}

function mapDiffLines(input: ChangesResponse) {
  const changes = input.changes ?? [];
  return {
    changed_file_count: changes.length,
    files: changes.map(mapChange),
  };
}

const path = process.argv[2];
if (!path) {
  console.error("Usage: node --experimental-strip-types scripts/map_diff_lines.ts <gitlab_get_merge_request_changes.json>");
  process.exit(2);
}

try {
  const input = JSON.parse(readFileSync(path, "utf8"));
  console.log(JSON.stringify(mapDiffLines(input), null, 2));
} catch (error) {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
}
