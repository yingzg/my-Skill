#!/usr/bin/env python3
# AI 生成代码 - Prod 配置环境间差异检测
"""
检测 MR 中 prod 配置变更，对比同子模块内各环境的差异。
Diff 驱动：只检查 MR 变更涉及的属性，不做全量对比。

输出：/tmp/prod_config_diff_result.json
"""

import json
import os
import re
import subprocess
import sys
from collections import defaultdict


# ── 常量 ──────────────────────────────────────────────────────────────

RESULT_FILE = "/tmp/prod_config_diff_result.json"

# 匹配 prod 配置文件的模式
# 模式 A: application-prod*.yml / application-prod*.yaml
PATTERN_A = re.compile(r"application-prod[^/]*\.ya?ml$")
# 模式 B: 目录名含 prod 的配置文件
PATTERN_B = re.compile(r"/[^/]*prod[^/]*/[^/]+\.ya?ml$")

# 从 prod 文件名提取环境名
ENV_FROM_FILENAME = re.compile(r"application-(prod[^.]*)\.ya?ml$")
ENV_FROM_DIRNAME = re.compile(r"/([^/]*prod[^/]*)/")


# ── Git 工具函数 ─────────────────────────────────────────────────────

def git_cmd(args):
    """执行 git 命令，返回 stdout"""
    result = subprocess.run(
        ["git"] + args,
        capture_output=True, text=True, timeout=60
    )
    if result.returncode != 0:
        print("  git {0} 失败: {1}".format(" ".join(args[:3]), result.stderr.strip()),
              file=sys.stderr)
        return ""
    return result.stdout


def get_target_branch():
    """获取目标分支"""
    branch = os.environ.get("CI_MERGE_REQUEST_TARGET_BRANCH_NAME", "")
    if not branch:
        # 本地模式：尝试 main/master
        for b in ("main", "master"):
            ret = subprocess.run(
                ["git", "rev-parse", "--verify", "origin/" + b],
                capture_output=True, text=True
            )
            if ret.returncode == 0:
                branch = b
                break
    return branch


def get_changed_files(target_branch):
    """获取 MR 变更文件列表"""
    base_sha = os.environ.get("CI_MERGE_REQUEST_DIFF_BASE_SHA", "")
    if not base_sha:
        base_sha = git_cmd(["merge-base", "origin/" + target_branch, "HEAD"]).strip()
    if not base_sha:
        print("错误: 无法确定 diff base", file=sys.stderr)
        return []

    output = git_cmd(["diff", base_sha + "...HEAD", "--name-only"])
    return [f.strip() for f in output.splitlines() if f.strip()]


def get_file_diff(target_branch, file_path):
    """获取单个文件的 diff"""
    base_sha = os.environ.get("CI_MERGE_REQUEST_DIFF_BASE_SHA", "")
    if not base_sha:
        base_sha = git_cmd(["merge-base", "origin/" + target_branch, "HEAD"]).strip()
    if not base_sha:
        return ""
    return git_cmd(["diff", base_sha + "...HEAD", "--", file_path])


def read_file_content(file_path):
    """读取工作区文件内容"""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except (FileNotFoundError, UnicodeDecodeError):
        return ""


def discover_sibling_files_pattern_a(directory):
    """发现同目录下所有 application-prod*.yml 文件"""
    files = []
    try:
        for name in os.listdir(directory):
            if PATTERN_A.search(name):
                files.append(os.path.join(directory, name))
    except OSError:
        pass
    return sorted(files)


def discover_sibling_files_pattern_b(file_path):
    """发现其他 prod 目录下的同名文件"""
    dir_path = os.path.dirname(file_path)
    filename = os.path.basename(file_path)
    parent = os.path.dirname(dir_path)

    files = []
    try:
        for name in os.listdir(parent):
            full = os.path.join(parent, name)
            if os.path.isdir(full) and re.search(r"prod", name, re.IGNORECASE):
                candidate = os.path.join(full, filename)
                if os.path.isfile(candidate):
                    files.append(candidate)
    except OSError:
        pass
    return sorted(files)


# ── YAML 解析（简易缩进式，无需 pyyaml）──────────────────────────────

def parse_yaml_to_flat(content):
    """将 YAML 内容解析为扁平的 dotted key → value 映射。
    简易实现：基于缩进层级，不处理锚点/别名/多文档等高级特性。"""
    result = {}
    key_stack = []  # (indent_level, key_name)

    for line in content.splitlines():
        stripped = line.strip()
        # 跳过空行、注释、文档标记
        if not stripped or stripped.startswith("#") or stripped in ("---", "..."):
            continue

        # 计算缩进
        indent = len(line) - len(line.lstrip())

        # 弹出缩进栈中不再有效的层级
        while key_stack and key_stack[-1][0] >= indent:
            key_stack.pop()

        # 解析 key: value
        match = re.match(r"^([^:#]+?)\s*:\s*(.*)", stripped)
        if not match:
            # 列表项（- value）等暂不处理
            continue

        key = match.group(1).strip()
        value = match.group(2).strip()

        # 去除行内注释
        if value and not value.startswith("'") and not value.startswith('"'):
            comment_pos = value.find(" #")
            if comment_pos >= 0:
                value = value[:comment_pos].strip()

        # 去除引号
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]

        key_stack.append((indent, key))
        dotted_key = ".".join(k for _, k in key_stack)

        if value:
            result[dotted_key] = value
        # 如果 value 为空，说明是父 key，继续解析子级

    return result


# ── Diff 解析：提取变更的 key ────────────────────────────────────────

def extract_changed_keys_from_diff(diff_text):
    """从 git diff 输出中提取变更行，解析对应的 YAML key。
    返回 {dotted_key: line_number} 映射。"""
    changed_keys = {}
    context_stack = []  # (indent, key_name)
    current_new_line = 0

    for line in diff_text.splitlines():
        # hunk header
        if line.startswith("@@"):
            try:
                plus_part = line.split("+")[1].split(" ")[0]
                current_new_line = int(plus_part.split(",")[0])
            except (IndexError, ValueError):
                pass
            context_stack = []
            continue

        if line.startswith("---") or line.startswith("+++"):
            continue

        if line.startswith("-"):
            # 删除行不计入 new_line 计数
            continue

        is_added = line.startswith("+")
        content = line[1:] if (is_added or line.startswith(" ")) else line

        # 跳过空行和注释
        stripped = content.strip()
        if not stripped or stripped.startswith("#") or stripped in ("---", "..."):
            if not line.startswith("-"):
                current_new_line += 1
            continue

        indent = len(content) - len(content.lstrip())

        # 更新上下文栈
        while context_stack and context_stack[-1][0] >= indent:
            context_stack.pop()

        match = re.match(r"^([^:#]+?)\s*:\s*(.*)", stripped)
        if match:
            key = match.group(1).strip()
            value = match.group(2).strip()

            context_stack.append((indent, key))
            dotted_key = ".".join(k for _, k in context_stack)

            if is_added and value:
                changed_keys[dotted_key] = current_new_line

            # 如果是父 key（value 为空），不弹出栈
            if value:
                pass  # leaf key，保留栈供同级使用
        elif is_added:
            # 非 key: value 行（如列表项），关联到当前父 key
            if context_stack:
                parent_key = ".".join(k for _, k in context_stack)
                if parent_key not in changed_keys:
                    changed_keys[parent_key] = current_new_line

        current_new_line += 1

    return changed_keys


# ── 对比规则 ─────────────────────────────────────────────────────────

def check_issues(key, env_values):
    """对比同一 key 在各环境中的值，返回 issue 列表。
    env_values: {env_name: value_or_None}"""
    issues = []
    envs_with_value = {e: v for e, v in env_values.items() if v is not None}
    envs_without_value = {e for e, v in env_values.items() if v is None}

    # MISSING_KEY: 某些环境有值，某些没有
    if envs_without_value and envs_with_value:
        present = ", ".join(sorted(envs_with_value.keys()))
        missing = ", ".join(sorted(envs_without_value))
        issues.append({
            "rule": "MISSING_KEY",
            "message": "key '{0}' 在 {1} 中存在但 {2} 中缺失".format(key, present, missing),
        })

    if len(envs_with_value) < 2:
        return issues

    values = list(envs_with_value.values())

    # PLACEHOLDER_VS_VALUE: 占位符 vs 实际值
    placeholder_re = re.compile(r"^\$\{.*\}$")
    placeholders = {e for e, v in envs_with_value.items() if placeholder_re.match(v)}
    non_placeholders = {e for e, v in envs_with_value.items() if not placeholder_re.match(v)}
    if placeholders and non_placeholders:
        issues.append({
            "rule": "PLACEHOLDER_VS_VALUE",
            "message": "key '{0}': {1} 使用占位符，{2} 使用实际值".format(
                key, ", ".join(sorted(placeholders)), ", ".join(sorted(non_placeholders))),
        })

    # URL_FORMAT_MISMATCH
    url_re = re.compile(r"^https?://")
    urls = {e for e, v in envs_with_value.items() if url_re.match(v)}
    non_urls = {e for e, v in envs_with_value.items() if not url_re.match(v) and not placeholder_re.match(v)}
    if urls and non_urls:
        issues.append({
            "rule": "URL_FORMAT_MISMATCH",
            "message": "key '{0}': {1} 是 URL 格式，{2} 不是".format(
                key, ", ".join(sorted(urls)), ", ".join(sorted(non_urls))),
        })

    # ENCRYPT_MISMATCH: 加密 vs 明文
    encrypt_re = re.compile(r"^(ENC\(|KS\(|[A-Za-z0-9+/]{32,}={0,2}$)")
    encrypted = {e for e, v in envs_with_value.items() if encrypt_re.match(v)}
    plaintext = {e for e, v in envs_with_value.items()
                 if not encrypt_re.match(v) and not placeholder_re.match(v)}
    if encrypted and plaintext:
        issues.append({
            "rule": "ENCRYPT_MISMATCH",
            "message": "key '{0}': {1} 使用加密值，{2} 可能是明文".format(
                key, ", ".join(sorted(encrypted)), ", ".join(sorted(plaintext))),
        })

    # BOOL_MISMATCH
    bool_map = {}
    for e, v in envs_with_value.items():
        if v.lower() in ("true", "false"):
            bool_map[e] = v.lower()
    if len(set(bool_map.values())) > 1:
        issues.append({
            "rule": "BOOL_MISMATCH",
            "message": "key '{0}' 布尔值不一致: {1}".format(
                key, ", ".join("{0}={1}".format(e, v) for e, v in sorted(bool_map.items()))),
        })

    # MAGNITUDE_DIFF: 数值量级差异
    num_map = {}
    for e, v in envs_with_value.items():
        try:
            num_map[e] = float(v)
        except ValueError:
            pass
    if len(num_map) >= 2:
        nums = list(num_map.values())
        min_val = min(abs(n) for n in nums if n != 0) if any(n != 0 for n in nums) else 0
        max_val = max(abs(n) for n in nums)
        if min_val > 0 and max_val / min_val > 10:
            issues.append({
                "rule": "MAGNITUDE_DIFF",
                "message": "key '{0}' 数值量级差异 >10x: {1}".format(
                    key, ", ".join("{0}={1}".format(e, v) for e, v in sorted(num_map.items()))),
            })

    # TYPE_MISMATCH: 值类型不一致
    def classify_type(v):
        if v.lower() in ("true", "false"):
            return "bool"
        try:
            float(v)
            return "number"
        except ValueError:
            pass
        if v.startswith("[") or v.startswith("{"):
            return "collection"
        if placeholder_re.match(v):
            return "placeholder"
        return "string"

    type_map = {e: classify_type(v) for e, v in envs_with_value.items()}
    real_types = {e: t for e, t in type_map.items() if t != "placeholder"}
    unique_types = set(real_types.values())
    if len(unique_types) > 1:
        issues.append({
            "rule": "TYPE_MISMATCH",
            "message": "key '{0}' 值类型不一致: {1}".format(
                key, ", ".join("{0}={1}".format(e, t) for e, t in sorted(real_types.items()))),
        })

    return issues


# ── 环境名提取 ────────────────────────────────────────────────────────

def extract_env_name(file_path):
    """从文件路径提取环境名"""
    # 模式 A: application-prod1.yml → prod1
    m = ENV_FROM_FILENAME.search(file_path)
    if m:
        return m.group(1)
    # 模式 B: .../prod1/application.yml → prod1
    m = ENV_FROM_DIRNAME.search(file_path)
    if m:
        return m.group(1)
    return os.path.basename(file_path)


def extract_module_path(file_path):
    """提取子模块路径（src/main/resources 的上级）"""
    idx = file_path.find("src/main/resources")
    if idx > 0:
        return file_path[:idx].rstrip("/")
    # fallback: 目录路径
    return os.path.dirname(file_path)


# ── 主流程 ────────────────────────────────────────────────────────────

def is_prod_config(file_path):
    """判断是否为 prod 配置文件"""
    return bool(PATTERN_A.search(file_path) or PATTERN_B.search(file_path))


def find_sibling_prod_files(file_path):
    """找到同子模块下的所有同类 prod 文件"""
    basename = os.path.basename(file_path)

    if PATTERN_A.search(basename):
        # 模式 A: 同目录下的 application-prod*.yml
        directory = os.path.dirname(file_path)
        return discover_sibling_files_pattern_a(directory)
    elif PATTERN_B.search(file_path):
        # 模式 B: 其他 prod 目录下的同名文件
        return discover_sibling_files_pattern_b(file_path)

    return [file_path]


def main():
    target_branch = get_target_branch()
    if not target_branch:
        print("错误: 无法确定目标分支", file=sys.stderr)
        sys.exit(1)

    print("  目标分支: {0}".format(target_branch))

    # Step 1: 获取变更文件
    changed_files = get_changed_files(target_branch)
    if not changed_files:
        print("  无变更文件")
        json.dump([], open(RESULT_FILE, "w"))
        return

    print("  变更文件数: {0}".format(len(changed_files)))

    # Step 2: 筛选 prod 配置文件
    prod_changed = [f for f in changed_files if is_prod_config(f)]
    if not prod_changed:
        print("  无 prod 配置变更")
        json.dump([], open(RESULT_FILE, "w"))
        return

    print("  变更的 prod 配置: {0}".format(", ".join(prod_changed)))

    # Step 3: 按 (子模块, 配置文件名) 分组 + 发现同类文件
    # key = (module, basename)，避免同模块下不同配置文件互相覆盖
    module_groups = defaultdict(dict)  # (module, basename) -> {env_name: file_path}

    for f in prod_changed:
        module = extract_module_path(f)
        basename = os.path.basename(f)
        siblings = find_sibling_prod_files(f)
        for sib in siblings:
            env = extract_env_name(sib)
            module_groups[(module, basename)][env] = sib

    # Step 4: 从 diff 提取变更 key
    all_results = []

    for (module, basename), env_files in module_groups.items():
        if len(env_files) < 2:
            print("  模块 {0}/{1}: 仅 {2} 个环境，跳过".format(module, basename, len(env_files)))
            continue

        print("  模块 {0}/{1}: 环境 {2}".format(module, basename, ", ".join(sorted(env_files.keys()))))

        # 收集所有变更 key
        all_changed_keys = {}  # dotted_key -> {file_path, line_number}
        for env, file_path in env_files.items():
            if file_path in prod_changed:
                diff_text = get_file_diff(target_branch, file_path)
                if diff_text:
                    keys = extract_changed_keys_from_diff(diff_text)
                    for k, line in keys.items():
                        if k not in all_changed_keys:
                            all_changed_keys[k] = {"file": file_path, "line": line}

        if not all_changed_keys:
            print("    未提取到变更 key")
            continue

        print("    变更 key: {0} 个".format(len(all_changed_keys)))

        # Step 5: 读取所有环境文件，只对比变更 key
        env_flat = {}
        for env, file_path in env_files.items():
            content = read_file_content(file_path)
            if content:
                env_flat[env] = parse_yaml_to_flat(content)
            else:
                env_flat[env] = {}

        module_issues = []
        for key, source_info in all_changed_keys.items():
            env_values = {}
            for env in env_files:
                env_values[env] = env_flat.get(env, {}).get(key)

            issues = check_issues(key, env_values)
            for issue in issues:
                # 确定评论目标文件和行号
                # 优先评论在变更的源文件上
                issue_file = source_info["file"]
                issue_line = source_info["line"]

                # 对于 MISSING_KEY，评论在有值的文件上（即变更的文件）
                module_issues.append({
                    "rule": issue["rule"],
                    "key": key,
                    "config_file": basename,
                    "envs": {env: env_values[env] for env in sorted(env_values)},
                    "file": issue_file,
                    "line": issue_line,
                    "message": issue["message"],
                })

        if module_issues:
            all_results.append({
                "module": module,
                "issues": module_issues,
            })
            print("    发现 {0} 个问题".format(len(module_issues)))
        else:
            print("    未发现不一致")

    # 写入结果
    with open(RESULT_FILE, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)

    total = sum(len(m["issues"]) for m in all_results)
    print("\n  总计: {0} 个模块，{1} 个问题".format(len(all_results), total))
    print("  结果已写入 {0}".format(RESULT_FILE))


if __name__ == "__main__":
    main()
