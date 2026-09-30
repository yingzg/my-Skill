#!/usr/bin/env node

type ParsedMrUrl = {
  host: string;
  project_id: string;
  merge_request_iid: number;
  url: string;
};

function parseMrUrl(input: string): ParsedMrUrl {
  const url = new URL(input);
  const marker = "/-/merge_requests/";
  const markerIndex = url.pathname.indexOf(marker);
  if (markerIndex < 0) {
    throw new Error("Not a GitLab merge request URL: missing /-/merge_requests/<iid>");
  }

  const projectPath = decodeURIComponent(url.pathname.slice(1, markerIndex));
  const iidText = url.pathname.slice(markerIndex + marker.length).split("/")[0];
  const iid = Number(iidText);
  if (!projectPath || !Number.isInteger(iid) || iid <= 0) {
    throw new Error("Invalid GitLab merge request URL: project path or iid is invalid");
  }

  return {
    host: `${url.protocol}//${url.host}`,
    project_id: projectPath,
    merge_request_iid: iid,
    url: input,
  };
}

const input = process.argv[2];
if (!input) {
  console.error("Usage: node --experimental-strip-types scripts/parse_mr_url.ts <gitlab-mr-url>");
  process.exit(2);
}

try {
  console.log(JSON.stringify(parseMrUrl(input), null, 2));
} catch (error) {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
}

