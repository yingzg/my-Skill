const SENSITIVE_KEYS = [
  "authorization",
  "private-token",
  "private_token",
  "access_token",
  "refresh_token",
  "token",
  "password",
  "secret",
  "value",
  "webhook",
];

const SECRET_PATTERNS: Array<[RegExp, string]> = [
  [/glpat-[A-Za-z0-9_\-]{10,}/g, "glpat-[REDACTED]"],
  [/([?&](?:token|access_token|private_token)=)[^&\s]+/gi, "$1[REDACTED]"],
  [/(Authorization:\s*Bearer\s+)[^\s]+/gi, "$1[REDACTED]"],
  [/(PRIVATE-TOKEN:\s*)[^\s]+/gi, "$1[REDACTED]"],
];

function isSensitiveKey(key: string): boolean {
  const lower = key.toLowerCase();
  return SENSITIVE_KEYS.some((sensitive) => lower === sensitive || lower.includes(sensitive));
}

export function redact<T>(value: T): T {
  if (typeof value === "string") {
    let output: string = value;
    for (const [pattern, replacement] of SECRET_PATTERNS) {
      output = output.replace(pattern, replacement);
    }
    return output as T;
  }

  if (Array.isArray(value)) {
    return value.map((item) => redact(item)) as T;
  }

  if (value && typeof value === "object") {
    const output: Record<string, unknown> = {};
    for (const [key, item] of Object.entries(value)) {
      output[key] = isSensitiveKey(key) ? "[REDACTED]" : redact(item);
    }
    return output as T;
  }

  return value;
}
