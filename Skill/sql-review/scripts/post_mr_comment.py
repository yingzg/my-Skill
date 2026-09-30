#!/usr/bin/env python3
"""Post the SQL review comment to a GitLab merge request.

Reads a markdown comment file and posts it as a note on a GitLab MR via the
REST API. Credentials are read from environment variables:

  auth:      GITLAB_TOKEN (PRIVATE-TOKEN, 优先——PAT 有写权限，需 api scope)
             → CI_JOB_TOKEN (JOB-TOKEN, 兜底——默认只读，评论会 401)
  api_url:   CI_API_V4_URL  →  GITLAB_API_URL  (default https://gitlab.com/api/v4)
  project:   CI_PROJECT_ID  →  GITLAB_PROJECT_ID
  mr iid:    CI_MERGE_REQUEST_IID  →  GITLAB_MR_IID

Usage:
    python3 post_mr_comment.py --comment-file mr-comment.md
    python3 post_mr_comment.py --comment-file mr-comment.md --dry-run
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_API_URL = "https://gitlab.com/api/v4"


def _env(*keys: str) -> str:
    for key in keys:
        value = os.environ.get(key, "")
        if value:
            return value
    return ""


def _resolve_auth() -> tuple[str, str]:
    pat = os.environ.get("GITLAB_TOKEN", "")
    if pat:
        return "PRIVATE-TOKEN", pat
    job_token = os.environ.get("CI_JOB_TOKEN", "")
    if job_token:
        return "JOB-TOKEN", job_token
    return "", ""


def main() -> None:
    parser = argparse.ArgumentParser(description="Post a note to a GitLab MR")
    parser.add_argument("--comment-file", required=True,
                        help="Path to markdown comment file (e.g. mr-comment.md)")
    parser.add_argument("--project-id", default="", help="GitLab project ID or path")
    parser.add_argument("--mr-iid", default="", help="Merge request IID")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be posted without calling the API")
    args = parser.parse_args()

    auth_header, token = _resolve_auth()
    api_url = _env("CI_API_V4_URL", "GITLAB_API_URL") or DEFAULT_API_URL
    project_id = args.project_id or _env("CI_PROJECT_ID", "GITLAB_PROJECT_ID")
    mr_iid = args.mr_iid or _env("CI_MERGE_REQUEST_IID", "GITLAB_MR_IID")

    with open(args.comment_file, encoding="utf-8") as f:
        body = f.read()

    missing = []
    if not token:
        missing.append("CI_JOB_TOKEN/GITLAB_TOKEN")
    if not project_id:
        missing.append("CI_PROJECT_ID/GITLAB_PROJECT_ID")
    if not mr_iid:
        missing.append("CI_MERGE_REQUEST_IID/GITLAB_MR_IID")
    if missing:
        print(f"ERROR: missing required config: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

    url = (f"{api_url.rstrip('/')}/projects/"
           f"{urllib.parse.quote(project_id, safe='')}/merge_requests/{mr_iid}/notes")

    if args.dry_run:
        print(f"DRY-RUN: would POST {url}")
        print(body)
        return

    print(f"INFO: 回贴认证方式 {auth_header}（project {project_id}, MR !{mr_iid}）", file=sys.stderr)

    request = urllib.request.Request(
        url,
        data=json.dumps({"body": body}).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            auth_header: token,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="replace")
        print(f"ERROR: GitLab API HTTP {exc.code}: {err_body[:500]}", file=sys.stderr)
        if exc.code == 401:
            if auth_header == "PRIVATE-TOKEN":
                print(
                    "提示: GITLAB_TOKEN(PAT) 认证失败。请确认：① PAT 具有 api scope；"
                    "② PAT 未过期/未撤销；③ 配置在正确的项目/组 Variables（变量名 GITLAB_TOKEN）。",
                    file=sys.stderr,
                )
            else:
                print(
                    "提示: 当前用 CI_JOB_TOKEN（默认仅读）无法评论 MR。"
                    "请在项目 Settings→CI/CD→Variables 配置 GITLAB_TOKEN（PAT，需 api scope）。",
                    file=sys.stderr,
                )
        sys.exit(1)
    except urllib.error.URLError as exc:
        print(f"ERROR: GitLab API network error: {exc.reason}", file=sys.stderr)
        sys.exit(1)

    print(f"OK: note posted (id={data.get('id', '?')})")


if __name__ == "__main__":
    main()
