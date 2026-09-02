"""HTTP 请求发送 + JSONPath 响应提取。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import requests
from jsonpath_rw import parse as jsonpath_parse

from api_flow.variables import RuntimeVariables, substitute


@dataclass
class HttpResponse:
    status_code: int
    headers: dict[str, str]
    body: Any
    text: str


class HttpClient:
    """发送 HTTP 请求，自动替换 {{@var}} 变量，支持 JSONPath 提取。"""

    def __init__(self, base_url: str, timeout: int = 30) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._session = requests.Session()

    def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        body: Any = None,
        runtime: RuntimeVariables | None = None,
    ) -> HttpResponse:
        """发送一个 HTTP 请求。变量替换在发送前完成。"""
        full_url = f"{self._base_url}{url}"

        if runtime:
            headers = substitute(headers or {}, runtime)
            body = substitute(body, runtime)

        resp = self._session.request(
            method=method.upper(),
            url=full_url,
            headers=headers or {},
            json=body,
            timeout=self._timeout,
        )

        try:
            resp_body = resp.json()
        except (json.JSONDecodeError, ValueError):
            resp_body = resp.text

        return HttpResponse(
            status_code=resp.status_code,
            headers=dict(resp.headers),
            body=resp_body,
            text=resp.text,
        )

    def extract_to_runtime(
        self,
        response_body: Any,
        extract_rules: dict[str, str],
        runtime: RuntimeVariables,
    ) -> None:
        """从响应 body 中按 JSONPath 提取值，写入 runtime。

        extract_rules 格式: {"varname": "$.path.to.field"}
        提取后存入 runtime: @varname = "extracted_value"
        """
        for var_name, jsonpath_expr in extract_rules.items():
            try:
                expr = jsonpath_parse(jsonpath_expr)
                matches = expr.find(response_body)
                if matches:
                    value = str(matches[0].value)
                    runtime.set(f"@{var_name}", value)
            except Exception:
                pass

    def close(self) -> None:
        self._session.close()
