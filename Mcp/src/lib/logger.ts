import { redact } from "../security/redact.js";

type LogLevel = "debug" | "info" | "warn" | "error";

const levels: Record<LogLevel, number> = {
  debug: 10,
  info: 20,
  warn: 30,
  error: 40,
};

const configuredLevel = (process.env.LOG_LEVEL || "info").toLowerCase();
const currentLevel: LogLevel =
  configuredLevel === "debug" ||
  configuredLevel === "info" ||
  configuredLevel === "warn" ||
  configuredLevel === "error"
    ? configuredLevel
    : "info";

function write(level: LogLevel, data: Record<string, unknown>, message: string) {
  if (levels[level] < levels[currentLevel]) return;

  const payload = redact({
    time: new Date().toISOString(),
    level,
    message,
    ...data,
  });

  console.error(JSON.stringify(payload));
}

export const logger = {
  debug: (data: Record<string, unknown>, message: string) => write("debug", data, message),
  info: (data: Record<string, unknown>, message: string) => write("info", data, message),
  warn: (data: Record<string, unknown>, message: string) => write("warn", data, message),
  error: (data: Record<string, unknown>, message: string) => write("error", data, message),
};

