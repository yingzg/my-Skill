#!/usr/bin/env node

type ParsedRemote = {
  host: string | null;
  project_id: string;
  protocol: "ssh" | "https" | "http" | "file" | "unknown";
  original: string;
};

function stripGitSuffix(path: string): string {
  return path.replace(/\.git$/i, "").replace(/^\/+/, "").replace(/\/+$/, "");
}

function parseRemote(input: string): ParsedRemote {
  const trimmed = input.trim();
  if (!trimmed) {
    throw new Error("Remote URL is empty");
  }

  const scpLike = trimmed.match(/^git@([^:]+):(.+)$/);
  if (scpLike) {
    return {
      host: `https://${scpLike[1]}`,
      project_id: stripGitSuffix(decodeURIComponent(scpLike[2])),
      protocol: "ssh",
      original: input,
    };
  }

  const sshUrl = trimmed.match(/^ssh:\/\/(?:git@)?([^/]+)\/(.+)$/i);
  if (sshUrl) {
    return {
      host: `https://${sshUrl[1]}`,
      project_id: stripGitSuffix(decodeURIComponent(sshUrl[2])),
      protocol: "ssh",
      original: input,
    };
  }

  if (/^https?:\/\//i.test(trimmed)) {
    const url = new URL(trimmed);
    const protocol = url.protocol === "http:" ? "http" : "https";
    return {
      host: `${url.protocol}//${url.host}`,
      project_id: stripGitSuffix(decodeURIComponent(url.pathname)),
      protocol,
      original: input,
    };
  }

  if (trimmed.startsWith("/") || trimmed.startsWith("file://")) {
    const path = trimmed.startsWith("file://") ? new URL(trimmed).pathname : trimmed;
    return {
      host: null,
      project_id: stripGitSuffix(path),
      protocol: "file",
      original: input,
    };
  }

  throw new Error("Unsupported Git remote URL format");
}

const input = process.argv[2];
if (!input) {
  console.error("Usage: node --experimental-strip-types scripts/parse_git_remote.ts <git-remote-url>");
  process.exit(2);
}

try {
  console.log(JSON.stringify(parseRemote(input), null, 2));
} catch (error) {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
}
