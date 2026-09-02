import assert from "node:assert/strict";
import test from "node:test";
import {
  deleteTriggerTokenConfirm,
  deleteVariableConfirm,
  mergeConfirm,
  requireConfirmMessage,
} from "../security/confirm.js";

test("builds stable high-risk confirm messages", () => {
  assert.equal(mergeConfirm("group/project", 123), "MERGE group/project!123");
  assert.equal(deleteVariableConfirm("group/project", "SECRET"), "DELETE_VARIABLE group/project:SECRET");
  assert.equal(deleteTriggerTokenConfirm("group/project", 9), "DELETE_TRIGGER_TOKEN group/project:9");
});

test("rejects missing or mismatched confirm messages", () => {
  assert.throws(() => requireConfirmMessage(undefined, "MERGE group/project!123"), /requires confirm_message/);
  assert.throws(() => requireConfirmMessage("MERGE other/project!123", "MERGE group/project!123"), /requires confirm_message/);
  assert.doesNotThrow(() => requireConfirmMessage("MERGE group/project!123", "MERGE group/project!123"));
});

