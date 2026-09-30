import { ValidationError } from "./errors.js";

export type Args = Record<string, unknown>;

export function asArgs(value: unknown): Args {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return {};
  }
  return value as Args;
}

export function requireString(args: Args, key: string): string {
  const value = args[key];
  if (typeof value !== "string" || value.trim() === "") {
    throw new ValidationError(`${key} is required and must be a non-empty string`);
  }
  return value;
}

export function optionalString(args: Args, key: string): string | undefined {
  const value = args[key];
  if (value === undefined || value === null || value === "") return undefined;
  if (typeof value !== "string") {
    throw new ValidationError(`${key} must be a string`);
  }
  return value;
}

export function requireNumber(args: Args, key: string): number {
  const value = args[key];
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new ValidationError(`${key} is required and must be a number`);
  }
  return value;
}

export function optionalNumber(args: Args, key: string): number | undefined {
  const value = args[key];
  if (value === undefined || value === null || value === "") return undefined;
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new ValidationError(`${key} must be a number`);
  }
  return value;
}

export function optionalBoolean(args: Args, key: string): boolean | undefined {
  const value = args[key];
  if (value === undefined || value === null) return undefined;
  if (typeof value !== "boolean") {
    throw new ValidationError(`${key} must be a boolean`);
  }
  return value;
}

export function optionalStringRecord(args: Args, key: string): Record<string, string> | undefined {
  const value = args[key];
  if (value === undefined || value === null) return undefined;
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new ValidationError(`${key} must be an object`);
  }

  const result: Record<string, string> = {};
  for (const [recordKey, recordValue] of Object.entries(value)) {
    if (typeof recordValue !== "string") {
      throw new ValidationError(`${key}.${recordKey} must be a string`);
    }
    result[recordKey] = recordValue;
  }
  return result;
}

export function optionalNumberArray(args: Args, key: string): number[] | undefined {
  const value = args[key];
  if (value === undefined || value === null) return undefined;
  if (!Array.isArray(value) || value.some((item) => typeof item !== "number" || !Number.isFinite(item))) {
    throw new ValidationError(`${key} must be an array of numbers`);
  }
  return value;
}

export function optionalEnum<T extends string>(args: Args, key: string, values: readonly T[]): T | undefined {
  const value = optionalString(args, key);
  if (value === undefined) return undefined;
  if (!values.includes(value as T)) {
    throw new ValidationError(`${key} must be one of: ${values.join(", ")}`);
  }
  return value as T;
}

export function optionalPerPage(args: Args): number | undefined {
  const value = optionalNumber(args, "per_page");
  if (value === undefined) return undefined;
  if (value < 1 || value > 100) {
    throw new ValidationError("per_page must be between 1 and 100");
  }
  return Math.trunc(value);
}

export function optionalPositiveInteger(args: Args, key: string): number | undefined {
  const value = optionalNumber(args, key);
  if (value === undefined) return undefined;
  if (value < 1) {
    throw new ValidationError(`${key} must be greater than 0`);
  }
  return Math.trunc(value);
}

