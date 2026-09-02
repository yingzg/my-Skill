"""flow 文件解析器：flow.yaml + JSON 用例 + SQL 脚本（v0.2 拆分结构）。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


class ParseError(Exception):
    """YAML 解析或校验错误。"""
    pass


@dataclass
class AuthConfig:
    """鉴权配置。"""
    type: str  # oauth2 | bearer | apikey | none
    token_url: str = ""
    extra: dict[str, str] = field(default_factory=dict)


@dataclass
class RequestConfig:
    """HTTP 请求配置。"""
    method: str
    url: str
    headers: dict[str, str] = field(default_factory=dict)
    body: Any = None


@dataclass
class TestCase:
    """单条测试用例。"""
    id: str
    scenario: str
    branch: str = ""
    priority: str = "medium"            # high | medium | low
    expect_error: bool = False
    prepare: list[str] = field(default_factory=list)
    request: RequestConfig | None = None
    extract: dict[str, str] = field(default_factory=dict)
    cleanup: list[str] = field(default_factory=list)


@dataclass
class FlowConfig:
    """完整 flow 配置，由 flow.yaml + 引用的独立文件组装而成。"""
    name: str
    base_url: str
    service: str = ""
    auth: AuthConfig | None = None
    test_cases: list[TestCase] = field(default_factory=list)
    suspected_branches: list[str] = field(default_factory=list)


class CaseRef:
    """flow.yaml 中的单条用例引用。"""

    def __init__(
        self,
        id: str,
        file: str,
        prepare: str = "",
        cleanup: str = "",
    ) -> None:
        self.id = id
        self.file = file
        self.prepare = prepare
        self.cleanup = cleanup


def load_flow(flow_dir: Path | str) -> FlowConfig:
    """加载 flow 目录：解析 flow.yaml + 所有引用的用例文件。

    Args:
        flow_dir: 包含 flow.yaml 及 tc-*.json / tc-*.sql 的目录路径。

    Returns:
        组装后的 FlowConfig 对象。

    Raises:
        FileNotFoundError: flow.yaml 不存在。
        ValueError: YAML 解析失败。
    """
    flow_dir = Path(flow_dir)
    flow_yaml_path = flow_dir / "flow.yaml"

    if not flow_yaml_path.exists():
        raise FileNotFoundError(f"flow.yaml 不存在: {flow_yaml_path}")

    raw = flow_yaml_path.read_text(encoding="utf-8")
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as e:
        raise ValueError(f"YAML 解析失败: {e}") from e

    # 解析鉴权
    auth_raw = data.get("auth", {})
    auth = AuthConfig(
        type=auth_raw.get("type", "none"),
        token_url=auth_raw.get("token_url", ""),
        extra={k: v for k, v in auth_raw.items() if k not in ("type", "token_url")},
    )

    # 解析用例引用 + 加载独立文件
    test_cases: list[TestCase] = []
    for ref_raw in data.get("cases", []):
        ref = CaseRef(
            id=ref_raw.get("id", ""),
            file=ref_raw.get("file", ""),
            prepare=ref_raw.get("prepare", ""),
            cleanup=ref_raw.get("cleanup", ""),
        )
        tc = _load_case_from_ref(flow_dir, ref)
        test_cases.append(tc)

    return FlowConfig(
        name=data.get("name", ""),
        base_url=data.get("base_url", ""),
        service=data.get("service", ""),
        auth=auth,
        test_cases=test_cases,
        suspected_branches=data.get("suspected_branches", []),
    )


def _load_case_from_ref(flow_dir: Path, ref: CaseRef) -> TestCase:
    """根据 flow.yaml 中的引用，加载独立 JSON 文件和 SQL 文件。

    Args:
        flow_dir: flow 目录路径。
        ref: flow.yaml 中定义的用例引用。

    Returns:
        组装后的 TestCase 对象。
    """
    # 加载 JSON
    json_path = flow_dir / ref.file
    if not json_path.exists():
        raise FileNotFoundError(f"用例文件不存在: {json_path}")

    case_data = json.loads(json_path.read_text(encoding="utf-8"))
    req_raw = case_data.get("request", {})

    req = RequestConfig(
        method=req_raw.get("method", "GET"),
        url=req_raw.get("url", ""),
        headers=req_raw.get("headers", {}),
        body=json.loads(json.dumps(req_raw.get("body", {}), default=str)),
    )

    # 加载 prepare SQL 文件（可选）
    prepare_sql: list[str] = []
    if ref.prepare:
        prep_path = flow_dir / ref.prepare
        if prep_path.exists():
            raw_sql = prep_path.read_text(encoding="utf-8")
            prepare_sql = _parse_sql_statements(raw_sql)

    # 加载 cleanup SQL 文件（可选）
    cleanup_sql: list[str] = []
    if ref.cleanup:
        clean_path = flow_dir / ref.cleanup
        if clean_path.exists():
            raw_sql = clean_path.read_text(encoding="utf-8")
            cleanup_sql = _parse_sql_statements(raw_sql)

    return TestCase(
        id=case_data.get("id", ref.id),
        scenario=case_data.get("scenario", ""),
        branch=case_data.get("branch", ""),
        priority=case_data.get("priority", "medium"),
        expect_error=case_data.get("expect_error", False),
        prepare=prepare_sql,
        extract=case_data.get("extract", {}),
        cleanup=cleanup_sql,
        request=req,
    )


def _parse_sql_statements(raw: str) -> list[str]:
    """将原始 SQL 文本拆分为独立语句（按 ; 分隔，过滤空行和纯注释）。

    Args:
        raw: 从 .sql 文件读取的原始文本。

    Returns:
        每条语句以 ; 结尾的列表。
    """
    statements: list[str] = []
    for stmt in raw.split(";"):
        stmt = stmt.strip()
        if not stmt:
            continue
        if stmt.startswith("--"):
            continue
        statements.append(stmt + ";")
    return statements
