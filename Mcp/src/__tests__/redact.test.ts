import assert from "node:assert/strict";
import test from "node:test";
import { redact } from "../security/redact.js";

test("redacts sensitive object keys recursively", () => {
  const result = redact({
    token: "abc",
    nested: {
      password: "secret",
      keep: "visible",
    },
  });

  assert.deepEqual(result, {
    token: "[REDACTED]",
    nested: {
      password: "[REDACTED]",
      keep: "visible",
    },
  });
});

test("redacts token-like strings", () => {
  assert.equal(redact("PRIVATE-TOKEN: glpat-abcdefghijklmnop"), "PRIVATE-TOKEN: [REDACTED]");
  assert.equal(redact("https://x.test?a=1&token=abc123"), "https://x.test?a=1&token=[REDACTED]");
});

