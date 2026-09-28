#!/usr/bin/env node

import { readFileSync } from "node:fs";

type Note = {
  id?: number | string;
  body?: string;
  system?: boolean;
  author?: { username?: string; name?: string };
};

type Discussion = {
  id?: string;
  notes?: Note[];
};

const DEFAULT_BOTS = new Set(["MockGateBot", "GateBot", "QualityBot"]);

function parseRatio(body: string, patterns: RegExp[]) {
  for (const pattern of patterns) {
    const match = body.match(pattern);
    if (match) {
      const current = Number(match[1]);
      const required = Number(match[2]);
      return {
        current,
        required,
        passed: Number.isFinite(current) && Number.isFinite(required) ? current >= required : null,
      };
    }
  }
  return null;
}

function parseStatus(body: string, patterns: RegExp[]) {
  for (const pattern of patterns) {
    const match = body.match(pattern);
    if (match) {
      const raw = match[1].trim();
      const normalized = raw.toLowerCase();
      const passed = ["通过", "passed", "pass", "success", "succeeded", "ok", "approved"].includes(normalized);
      const failed = ["未通过", "failed", "fail", "failure", "missing", "blocked", "error"].includes(normalized);
      return {
        status: raw,
        passed: passed ? true : failed ? false : null,
      };
    }
  }
  return null;
}

function parseGateBody(body: string) {
  return {
    effective_comments: parseRatio(body, [
      /有效评论数\s*[:：]\s*(\d+(?:\.\d+)?)\s*\/\s*(\d+(?:\.\d+)?)/i,
      /effective\s+comments\s*[:：]\s*(\d+(?:\.\d+)?)\s*\/\s*(\d+(?:\.\d+)?)/i,
    ]),
    coverage: parseRatio(body, [
      /(?:变更代码)?单元测试覆盖率\s*[:：]\s*(\d+(?:\.\d+)?)%?\s*\/\s*(\d+(?:\.\d+)?)%?/i,
      /(?:new\s+line\s+)?coverage\s*[:：]\s*(\d+(?:\.\d+)?)%?\s*\/\s*(\d+(?:\.\d+)?)%?/i,
    ]),
    test_pass_rate: parseRatio(body, [
      /单测用例执行通过率\s*[:：]\s*(\d+(?:\.\d+)?)%?\s*\/\s*(\d+(?:\.\d+)?)%?/i,
      /test\s+pass\s+rate\s*[:：]\s*(\d+(?:\.\d+)?)%?\s*\/\s*(\d+(?:\.\d+)?)%?/i,
    ]),
    sonar_gate: parseStatus(body, [
      /Sonar质量门禁\s*[:：]\s*([^\n\r]+)/i,
      /Sonar\s+quality\s+gate\s*[:：]\s*([^\n\r]+)/i,
    ]),
    pipeline: parseStatus(body, [
      /Pipeline\s*[:：]\s*([^\n\r]+)/i,
      /流水线\s*[:：]\s*([^\n\r]+)/i,
    ]),
    approval: parseStatus(body, [
      /Approve\s*[:：]\s*([^\n\r]+)/i,
      /Approval\s*[:：]\s*([^\n\r]+)/i,
      /审批\s*[:：]\s*([^\n\r]+)/i,
    ]),
  };
}

function compact<T extends Record<string, unknown>>(obj: T): Partial<T> {
  return Object.fromEntries(Object.entries(obj).filter(([, value]) => value !== null)) as Partial<T>;
}

function parseDiscussions(discussions: Discussion[]) {
  const gateNotes: Array<{ discussion_id: string | null; note_id: number | string | null; bot_username: string; parsed: unknown }> = [];

  for (const discussion of discussions) {
    for (const note of discussion.notes ?? []) {
      const username = note.author?.username ?? "";
      const body = note.body ?? "";
      if (!DEFAULT_BOTS.has(username)) continue;
      const parsed = compact(parseGateBody(body));
      if (Object.keys(parsed).length === 0) continue;
      gateNotes.push({
        discussion_id: discussion.id ?? null,
        note_id: note.id ?? null,
        bot_username: username,
        parsed,
      });
    }
  }

  const merged: Record<string, unknown> = {};
  for (const note of gateNotes) {
    Object.assign(merged, note.parsed);
  }

  const blockers = Object.entries(merged)
    .filter(([, value]) => typeof value === "object" && value !== null && "passed" in value && (value as { passed?: boolean | null }).passed === false)
    .map(([name]) => name);

  return {
    found_gate_notes: gateNotes.length,
    gate_notes: gateNotes,
    latest: merged,
    blockers,
    passed: blockers.length === 0 && Object.keys(merged).length > 0,
  };
}

const path = process.argv[2];
if (!path) {
  console.error("Usage: node --experimental-strip-types scripts/parse_gate_discussions.ts <gitlab_list_merge_request_discussions.json>");
  process.exit(2);
}

try {
  const input = JSON.parse(readFileSync(path, "utf8"));
  const discussions = Array.isArray(input) ? input : input.discussions ?? [];
  console.log(JSON.stringify(parseDiscussions(discussions), null, 2));
} catch (error) {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
}

