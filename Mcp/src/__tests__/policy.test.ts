import assert from "node:assert/strict";
import test from "node:test";
import { assertProjectAllowed, assertWriteAllowed, loadPolicy, matchesProject } from "../security/policy.js";

test("matches exact projects and wildcard group prefixes", () => {
  assert.equal(matchesProject("group/project", "group/project"), true);
  assert.equal(matchesProject("group/*", "group/project"), true);
  assert.equal(matchesProject("group/*", "group/sub/project"), true);
  assert.equal(matchesProject("group/*", "other/project"), false);
});

test("loads readonly and allowed project policy from env", () => {
  const policy = loadPolicy({
    MCP_GITLAB_READONLY: "true",
    MCP_GITLAB_ALLOWED_PROJECTS: "group/project, other/*",
    MCP_GITLAB_JOB_TRACE_TAIL_LINES: "25",
  });

  assert.equal(policy.readonly, true);
  assert.deepEqual(policy.allowedProjects, ["group/project", "other/*"]);
  assert.equal(policy.defaultTraceTailLines, 25);
});

test("enforces readonly and project allowlist", () => {
  assert.throws(() => assertWriteAllowed({ readonly: true, allowedProjects: [], defaultTraceTailLines: 100 }, "tool"), /Readonly mode/);
  assert.doesNotThrow(() => assertProjectAllowed({ readonly: false, allowedProjects: ["group/*"], defaultTraceTailLines: 100 }, "group/project"));
  assert.throws(() => assertProjectAllowed({ readonly: false, allowedProjects: ["group/*"], defaultTraceTailLines: 100 }, "other/project"), /not allowed/);
});

