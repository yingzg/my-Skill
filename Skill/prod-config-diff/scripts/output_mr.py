#!/usr/bin/env python3
# AI 生成代码 - 将 prod 配置差异结果发布为 MR 评论
"""
读取 prod_config_diff_result.json，格式化为 Markdown，
通过 GitLab Notes API 发布到 MR。

每次运行会查找已有的 bot 评论并更新，而非重复创建。
仅在 CI 环境中使用，依赖 GitLab CI 环境变量。
"""

import json
import os
import re
import sys
import urllib.request
import urllib.error
from collections import defaultdict

# bot 评论标记，用于识别和更新已有评论
BOT_MARKER = "<!-- prod-config-diff-bot -->"


# ── GitLab API ────────────────────────────────────────────────────────

def gitlab_api_get(url, token):
    """GET 请求 GitLab API"""
    req = urllib.request.Request(url, method="GET")
    req.add_header("PRIVATE-TOKEN", token)
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def gitlab_api_put(url, payload, token):
    """PUT 请求 GitLab API"""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="PUT")
    req.add_header("Content-Type", "application/json")
    req.add_header("PRIVATE-TOKEN", token)
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def gitlab_api_post(url, payload, token):
    """POST 请求 GitLab API"""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("PRIVATE-TOKEN", token)
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ── 评论格式化 ────────────────────────────────────────────────────────

_PLACEHOLDER_RE = re.compile(r"^\$\{.*\}$")
_URL_RE = re.compile(r"^https?://")
_ENCRYPT_RE = re.compile(r"^(ENC\(|KS\(|[A-Za-z0-9+/]{32,}={0,2}$)")


def _derive_env_errors(issues):
    """根据同一 key 的多条 issue，推导每个环境的错误信息。
    返回 {env: [error_str, ...]}"""
    env_errors = defaultdict(list)

    for issue in issues:
        rule = issue.get("rule", "")
        envs = issue.get("envs", {})

        if rule == "MISSING_KEY":
            for env, val in envs.items():
                if val is None:
                    env_errors[env].append("缺失")

        elif rule == "PLACEHOLDER_VS_VALUE":
            for env, val in envs.items():
                if val and _PLACEHOLDER_RE.match(val):
                    env_errors[env].append("占位符未替换")

        elif rule == "URL_FORMAT_MISMATCH":
            for env, val in envs.items():
                if val and not _URL_RE.match(val) and not _PLACEHOLDER_RE.match(val):
                    env_errors[env].append("格式不一致")

        elif rule == "ENCRYPT_MISMATCH":
            for env, val in envs.items():
                if val and not _ENCRYPT_RE.match(val) and not _PLACEHOLDER_RE.match(val):
                    env_errors[env].append("未加密")

        elif rule == "MAGNITUDE_DIFF":
            nums = {}
            for env, val in envs.items():
                if val:
                    try:
                        nums[env] = float(val)
                    except ValueError:
                        pass
            if len(nums) >= 2:
                sorted_vals = sorted(nums.values())
                median_val = sorted_vals[len(sorted_vals) // 2]
                for env, num in nums.items():
                    if median_val != 0 and num != 0:
                        ratio = max(abs(num), abs(median_val)) / min(abs(num), abs(median_val))
                        if ratio > 10:
                            env_errors[env].append("量级差异")

        elif rule == "BOOL_MISMATCH":
            bool_vals = {}
            for env, val in envs.items():
                if val and val.lower() in ("true", "false"):
                    bool_vals[env] = val.lower()
            if len(set(bool_vals.values())) > 1:
                counts = defaultdict(list)
                for env, bv in bool_vals.items():
                    counts[bv].append(env)
                minority_val = min(counts, key=lambda k: len(counts[k]))
                for env in counts[minority_val]:
                    env_errors[env].append("布尔值不一致")

        elif rule == "TYPE_MISMATCH":
            def _classify(v):
                if v.lower() in ("true", "false"):
                    return "bool"
                try:
                    float(v)
                    return "number"
                except ValueError:
                    pass
                if _PLACEHOLDER_RE.match(v):
                    return "placeholder"
                return "string"

            type_map = {}
            for env, val in envs.items():
                if val:
                    t = _classify(val)
                    if t != "placeholder":
                        type_map[env] = t
            if len(set(type_map.values())) > 1:
                counts = defaultdict(list)
                for env, t in type_map.items():
                    counts[t].append(env)
                majority_type = max(counts, key=lambda k: len(counts[k]))
                for env, t in type_map.items():
                    if t != majority_type:
                        env_errors[env].append("类型不一致")

    return env_errors


def format_key_markdown(config_file, key, issues):
    """将同一 (config_file, key) 的所有 issue 合并为一条带错误列的表格"""
    envs = {}
    for issue in issues:
        for env, val in issue.get("envs", {}).items():
            if env not in envs or envs[env] is None:
                envs[env] = val

    env_errors = _derive_env_errors(issues)

    lines = []
    if config_file:
        lines.append("\u26a0\ufe0f **`{0}`** \uff08{1}\uff09".format(key, config_file))
    else:
        lines.append("\u26a0\ufe0f **`{0}`**".format(key))
    lines.append("")
    lines.append("| 环境 | 值 | 错误信息 |")
    lines.append("|------|-----|---------|")

    for env in sorted(envs.keys()):
        val = envs[env]
        errors = env_errors.get(env, [])

        if val is None:
            val_display = ""
            error_str = "\u274c " + "\u3001".join(errors) if errors else "\u274c 缺失"
        else:
            display = val if len(val) <= 80 else val[:77] + "..."
            val_display = "`{0}`".format(display)
            error_str = "\u26a0\ufe0f " + "\u3001".join(errors) if errors else ""

        lines.append("| {0} | {1} | {2} |".format(env, val_display, error_str))

    return "\n".join(lines)


# ── 查找 / 更新 / 创建评论 ───────────────────────────────────────────

def find_bot_note(api_url, project_id, mr_iid, token):
    """查找已有的 bot 评论，返回 note_id 或 None"""
    page = 1
    while True:
        url = "{0}/projects/{1}/merge_requests/{2}/notes?per_page=100&page={3}".format(
            api_url, project_id, mr_iid, page)
        try:
            notes = gitlab_api_get(url, token)
        except Exception:
            break
        if not notes:
            break
        for note in notes:
            body = note.get("body", "")
            if BOT_MARKER in body:
                return note.get("id")
        if len(notes) < 100:
            break
        page += 1
    return None


def upsert_mr_note(markdown, api_url, project_id, mr_iid, token):
    """创建或更新 bot 评论"""
    body = "{0}\n{1}".format(BOT_MARKER, markdown)

    existing_note_id = find_bot_note(api_url, project_id, mr_iid, token)

    if existing_note_id:
        # 更新已有评论
        url = "{0}/projects/{1}/merge_requests/{2}/notes/{3}".format(
            api_url, project_id, mr_iid, existing_note_id)
        try:
            gitlab_api_put(url, {"body": body}, token)
            print("  已更新评论 (note_id: {0})".format(existing_note_id))
            return True
        except Exception as e:
            print("  更新评论失败: {0}，尝试新建".format(e))

    # 新建评论
    url = "{0}/projects/{1}/merge_requests/{2}/notes".format(
        api_url, project_id, mr_iid)
    try:
        gitlab_api_post(url, {"body": body}, token)
        print("  评论发布成功")
        return True
    except Exception as e:
        print("  评论发布失败: {0}".format(e))

    return False


# ── 主流程 ────────────────────────────────────────────────────────────

def main():
    result_file = sys.argv[1] if len(sys.argv) > 1 else "/tmp/prod_config_diff_result.json"

    try:
        with open(result_file, "r", encoding="utf-8") as f:
            results = json.load(f)
    except FileNotFoundError:
        print("结果文件 {0} 不存在".format(result_file), file=sys.stderr)
        return 0

    # 收集所有 issue
    all_issues = []
    for module_result in results:
        for issue in module_result.get("issues", []):
            all_issues.append(issue)

    if not all_issues:
        print("  无问题需要评论")
        return 0

    api_url = os.environ.get("CI_API_V4_URL")
    project_id = os.environ.get("CI_PROJECT_ID")
    mr_iid = os.environ.get("CI_MERGE_REQUEST_IID")
    token = os.environ.get("GITLAB_TOKEN", os.environ.get("CI_JOB_TOKEN"))

    # 按 (config_file, key) 分组，避免不同配置文件的同名 key 混淆
    key_groups = defaultdict(list)
    for issue in all_issues:
        group_key = (issue.get("config_file", ""), issue.get("key", ""))
        key_groups[group_key].append(issue)

    parts = [format_key_markdown(cf, key, issues) for (cf, key), issues in key_groups.items()]
    markdown = "\n\n---\n\n".join(parts)

    print("  {0} 个属性合并为 1 条评论".format(len(key_groups)))

    if not all([api_url, project_id, mr_iid, token]):
        print("  缺少 GitLab CI 环境变量，输出到 stdout")
        print(markdown)
        return 0

    upsert_mr_note(markdown, api_url, project_id, mr_iid, token)

    return 0


if __name__ == "__main__":
    sys.exit(main())
