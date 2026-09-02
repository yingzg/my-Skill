import { redact } from "../security/redact.js";

export function jsonResponse(data: unknown) {
  return {
    content: [
      {
        type: "text" as const,
        text: JSON.stringify(redact(data), null, 2),
      },
    ],
  };
}

export function textResponse(text: string) {
  return {
    content: [
      {
        type: "text" as const,
        text: redact(text),
      },
    ],
  };
}

