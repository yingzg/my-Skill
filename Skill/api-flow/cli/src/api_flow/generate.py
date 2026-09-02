"""Phase 1 文件生成工具。Agent 调用 init_flow() 创建目录结构和基础文件。"""

from __future__ import annotations

import json
from pathlib import Path
from textwrap import dedent

FLOW_YAML_TEMPLATE = """\
# =============================================================
# api-flow flow.yaml
# {{flow_name}}
# =============================================================

name: "{{flow_name}}"
base_url: "{{base_url}}"

auth:
  type: bearer

cases:
{% for tc in test_cases %}
  - id: {{tc.id}}
    file: {{tc.id}}.json
{% if tc.prepare_has_sql %}
    prepare: {{tc.id}}-prepare.sql
{% endif %}
{% if tc.cleanup_has_sql %}
    cleanup: {{tc.id}}-cleanup.sql
{% endif %}
{% endfor %}
"""

TEST_CASE_TEMPLATE = {
    "id": "",
    "scenario": "",
    "branch": "",
    "priority": "medium",
    "expect_error": False,
    "request": {
        "method": "POST",
        "url": "",
        "headers": {
            "Authorization": "{{AUTH_TOKEN}}",
            "Content-Type": "application/json",
        },
        "body": {},
    },
    "extract": {},
}


def init_flow(
    flow_name: str,
    base_url: str,
    output_dir: str = "docs/api-flow",
    overwrite: bool = False,
) -> Path:
    """创建 flow 目录并生成初始 flow.yaml。
    """
    target = Path(output_dir) / flow_name
    target.mkdir(parents=True, exist_ok=True)
    target.joinpath("results").mkdir(exist_ok=True)

    yaml_path = target / "flow.yaml"
    if not yaml_path.exists() or overwrite:
        yaml_path.write_text(
            f'name: "{flow_name}"\nbase_url: "{base_url}"\n\nauth:\n  type: bearer\n\ncases: []\n',
            encoding="utf-8",
        )

    return target


def write_tc_json(
    flow_dir: Path,
    tc_id: str,
    scenario: str,
    branch: str = "",
    priority: str = "medium",
    expect_error: bool = False,
    method: str = "POST",
    url: str = "",
    headers: dict[str, str] | None = None,
    body: dict | None = None,
    extract: dict[str, str] | None = None,
) -> Path:
    """写入单条测试用例 JSON 文件。"""
    default_headers = {
        "Authorization": "{{AUTH_TOKEN}}",
        "Content-Type": "application/json",
    }

    tc = {
        "id": tc_id,
        "scenario": scenario,
        "branch": branch,
        "priority": priority,
        "expect_error": expect_error,
        "request": {
            "method": method.upper(),
            "url": url,
            "headers": headers or default_headers,
            "body": body or {},
        },
        "extract": extract or {},
    }

    filepath = flow_dir / f"{tc_id}.json"
    filepath.write_text(
        json.dumps(tc, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return filepath


def write_sql(flow_dir: Path, filename: str, statements: list[str]) -> Path:
    """写入 SQL 文件。"""
    filepath = flow_dir / filename
    content = (
        "\n".join(statements) + "\n"
    )
    filepath.write_text(content, encoding="utf-8")
    return filepath


__all__ = ["init_flow", "write_tc_json", "write_sql"]
