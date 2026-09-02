"""执行协调器：prepare → HTTP request → cleanup 主循环（v0.2: 新增 retry + 对话式 checkpoint）。"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from api_flow.parser import FlowConfig, load_flow, TestCase
from api_flow.variables import RuntimeVariables, substitute
from api_flow.auth import AuthInjector, auth_config_from_yaml
from api_flow.db import Database
from api_flow.http_client import HttpClient, HttpResponse
from api_flow.recorder import Recorder, TResult
from api_flow.templates import render_case_result, render_summary

MAX_CASE_RETRIES = 3
MAX_CONSECUTIVE_FAILURES = 3

CheckpointCallback = Callable[[TestCase, dict[str, Any]], bool]
"""checkpoint 回调：接收（用例对象, checkpoint 信息字典），返回 True 表示确认执行。"""


@dataclass
class RunResult:
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    results: list[TResult] = field(default_factory=list)


class Engine:
    """api-flow 执行引擎。支持两种模式：
    - 自动模式：`engine.run_all()` 一次性跑完
    - 对话式模式：Agent 逐条显示 checkpoint → 用户确认 → 调用 `engine.run_one()`
    """

    def __init__(
        self,
        flow_path: Path | str,
        output_root: str = "api-flow-output",
        fail_fast: bool = False,
        db_config: dict[str, Any] | None = None,
    ) -> None:
        self._flow: FlowConfig = load_flow(flow_path)
        self._output_root = output_root
        self._fail_fast = fail_fast
        self._db_config = db_config or {}
        self._auth_injector: AuthInjector | None = None
        self._db: Database | None = None
        self._http_client: HttpClient | None = None
        self._recorder: Recorder | None = None
        self._consecutive_failures: int = 0

    @property
    def flow(self) -> FlowConfig:
        return self._flow

    @property
    def db(self) -> Database:
        assert self._db is not None
        return self._db

    def init_resources(self) -> None:
        """初始化 DB / HTTP / Recorder 等资源。调用 `run_one()` / `run_all()` 前必须调用。"""
        self._auth_injector = AuthInjector(auth_config_from_yaml({
            "type": self._flow.auth.type,
            "token_url": self._flow.auth.token_url,
            **self._flow.auth.extra,
        }))
        self._db = Database(
            host=self._db_config.get("host", "localhost"),
            user=self._db_config.get("user", "root"),
            password=self._db_config.get("password", ""),
            database=self._db_config.get("database", "test"),
            port=self._db_config.get("port", 3306),
        )
        self._http_client = HttpClient(base_url=self._flow.base_url)
        self._recorder = Recorder(self._flow.name, self._output_root)

    def close_resources(self) -> None:
        """释放 DB / HTTP 等资源。"""
        if self._recorder:
            self._recorder = None
        if self._http_client:
            self._http_client.close()
            self._http_client = None
        if self._db:
            self._db.close()
            self._db = None

    def checkpoint_info(self, tc: TestCase) -> dict[str, Any]:
        """生成单条用例的 checkpoint 预览信息，供 Agent 展示确认。

        返回字典包含:
            - tc_id, scenario, branch, priority
            - method, url, request_body
            - prepare_tables: prepare SQL 影响的表名列表
            - prepare_count: prepare SQL 语句数量
            - cleanup_count: cleanup SQL 语句数量
            - expect_error
        """
        info: dict[str, Any] = {
            "tc_id": tc.id,
            "scenario": tc.scenario,
            "branch": tc.branch or "(未指定)",
            "priority": tc.priority,
            "method": tc.request.method if tc.request else "GET",
            "url": tc.request.url if tc.request else "",
            "request_body": tc.request.body if tc.request else None,
            "prepare_count": len(tc.prepare),
            "prepare_tables": _extract_tables(tc.prepare),
            "cleanup_count": len(tc.cleanup),
            "expect_error": tc.expect_error,
        }
        return info

    def run_all(self, checkpoint_callback: CheckpointCallback | None = None) -> RunResult:
        """执行全部测试用例（自动模式）。

        Args:
            checkpoint_callback: 可选，每条用例执行前调用。返回 False 则跳过该用例。
        """
        self.init_resources()
        assert self._db is not None
        assert self._http_client is not None
        assert self._recorder is not None
        assert self._auth_injector is not None

        result = RunResult()
        result.total = len(self._flow.test_cases)

        try:
            for tc in self._flow.test_cases:
                if checkpoint_callback:
                    info = self.checkpoint_info(tc)
                    if not checkpoint_callback(tc, info):
                        result.skipped += 1
                        continue

                tc_result = self._run_one_with_retry(
                    tc, MAX_CASE_RETRIES
                )
                result.results.append(tc_result)

                if tc_result.status == "pass":
                    result.passed += 1
                    self._consecutive_failures = 0
                elif tc_result.status == "fail":
                    result.failed += 1
                    self._consecutive_failures += 1
                elif tc_result.status == "error":
                    result.failed += 1
                    self._consecutive_failures += 1
                else:
                    result.skipped += 1

                if self._db.consecutive_errors >= MAX_CONSECUTIVE_FAILURES:
                    break
                if self._consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    break
                if self._fail_fast and tc_result.status in ("fail", "error"):
                    break
        finally:
            self._recorder.save_summary(result.results)
            self.close_resources()

        return result

    def run_one(self, tc: TestCase) -> TResult:
        """执行单条用例（对话式模式）。Agent 在用户确认后调用。

        必须先调用 `init_resources()`。
        """
        assert self._db is not None and self._recorder is not None
        assert self._http_client is not None and self._auth_injector is not None
        return self._run_one_with_retry(tc, MAX_CASE_RETRIES)

    def _run_one_with_retry(self, tc: TestCase, max_retries: int) -> TResult:
        last_result: TResult | None = None

        for attempt in range(max_retries):
            if attempt > 0:
                if last_result and last_result.cleanup_sql:
                    try:
                        self.db.execute_cleanup(last_result.cleanup_sql, RuntimeVariables())
                    except Exception:
                        pass

            tr = self._run_one(tc)

            if tr.status == "pass":
                return tr
            if tc.expect_error:
                return tr

            last_result = tr
            if tr.error and "不可重试" in str(tr.error):
                return tr

        if last_result:
            return last_result
        return TResult(tc_id=tc.id, scenario=tc.scenario, status="error", error="重试耗尽")

    def _run_one(self, tc: TestCase) -> TResult:
        assert self._db is not None and self._recorder is not None
        assert self._http_client is not None and self._auth_injector is not None

        tr = TResult(tc_id=tc.id, scenario=tc.scenario, status="skipped")
        runtime = RuntimeVariables()

        token = self._auth_injector.get_token()
        runtime.set_auth_token(token)

        start = time.time()

        try:
            self._db.execute_prepare(tc.prepare, runtime)
            tr.prepare_sql = tc.prepare
        except Exception as e:
            tr.status = "error"
            tr.error = f"prepare 失败: {e}"
            tr.duration_ms = (time.time() - start) * 1000
            self._recorder.record(tr)
            return tr

        try:
            response = self._http_client.request(
                method=tc.request.method,
                url=tc.request.url,
                headers=tc.request.headers,
                body=tc.request.body,
                runtime=runtime,
            )
            tr.status_code = response.status_code
            tr.request_body = tc.request.body
            tr.response_body = response.body
            tr.duration_ms = (time.time() - start) * 1000

            if tc.expect_error:
                tr.status = "pass" if response.status_code >= 400 else "fail"
            else:
                tr.status = "pass" if 200 <= response.status_code < 300 else "fail"

            self._http_client.extract_to_runtime(response.body, tc.extract, runtime)
        except Exception as e:
            tr.status = "error"
            tr.error = f"请求失败: {e}"
            tr.duration_ms = (time.time() - start) * 1000
            self._recorder.record(tr)
            return tr

        try:
            substituted_cleanup = [substitute(stmt, runtime) for stmt in tc.cleanup]
            tr.cleanup_sql = substituted_cleanup
            self._db.execute_cleanup(substituted_cleanup)
        except Exception:
            pass

        self._recorder.record(tr)
        return tr


def _extract_tables(sql_statements: list[str]) -> list[str]:
    """从 SQL 语句中提取涉及的表名（简单正则匹配 INSERT/UPDATE/DELETE/SELECT）。"""
    import re
    tables: list[str] = []
    for stmt in sql_statements:
        matches = re.findall(r'(?:FROM|INTO|UPDATE|JOIN)\s+(\w+)', stmt, re.IGNORECASE)
        tables.extend(matches)
    return sorted(set(tables))
