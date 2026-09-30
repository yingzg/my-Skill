import { ValidationError } from "../lib/errors.js";

export function requireConfirmMessage(actual: string | undefined, expected: string) {
  if (actual !== expected) {
    throw new ValidationError(`High-risk operation requires confirm_message exactly: ${expected}`);
  }
}

export function mergeConfirm(projectId: string, mergeRequestIid: number): string {
  return `MERGE ${projectId}!${mergeRequestIid}`;
}

export function rebaseConfirm(projectId: string, mergeRequestIid: number): string {
  return `REBASE ${projectId}!${mergeRequestIid}`;
}

export function closeConfirm(projectId: string, mergeRequestIid: number): string {
  return `CLOSE ${projectId}!${mergeRequestIid}`;
}

export function deleteVariableConfirm(projectId: string, key: string): string {
  return `DELETE_VARIABLE ${projectId}:${key}`;
}

export function deleteTriggerTokenConfirm(projectId: string, triggerId: number): string {
  return `DELETE_TRIGGER_TOKEN ${projectId}:${triggerId}`;
}

