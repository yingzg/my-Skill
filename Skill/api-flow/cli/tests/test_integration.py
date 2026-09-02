import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from api_flow.execute import execute_flow

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "order-flow"


class TestExecuteFlow:
    @patch("api_flow.execute.Engine")
    def test_execute_flow_returns_run_result(self, mock_engine_cls):
        from api_flow.engine import RunResult
        from api_flow.recorder import TResult

        mock_engine = MagicMock()
        mock_engine.flow.name = "测试流程"
        mock_engine.flow.test_cases = []

        tr = TResult(
            tc_id="tc-001", scenario="正常创建订单",
            status="pass", status_code=200, duration_ms=50.0,
        )

        mock_tc = MagicMock()
        mock_tc.id = "tc-001"
        mock_tc.scenario = "正常创建订单"
        mock_tc.branch = None
        mock_tc.priority = "P0"
        mock_tc.request.method = "POST"
        mock_tc.request.url = "/api/orders"
        mock_tc.request.body = {"item": "test"}
        mock_tc.prepare = []
        mock_tc.cleanup = []
        mock_tc.expect_error = False
        mock_engine.flow.test_cases = [mock_tc]

        mock_engine.checkpoint_info.return_value = {
            "tc_id": "tc-001",
            "scenario": "正常创建订单",
            "branch": "(未指定)",
            "priority": "P0",
            "method": "POST",
            "url": "/api/orders",
            "request_body": {"item": "test"},
            "prepare_count": 0,
            "prepare_tables": [],
            "cleanup_count": 0,
            "expect_error": False,
        }
        mock_engine.run_one.return_value = tr
        mock_engine_cls.return_value = mock_engine

        result = execute_flow(str(FIXTURE_DIR))

        assert isinstance(result, RunResult)
        assert result.total == 1
        assert result.passed == 1
        assert result.failed == 0
        assert len(result.results) == 1
        assert result.results[0].status == "pass"

    @patch("api_flow.execute.Engine")
    def test_execute_flow_empty_cases(self, mock_engine_cls):
        from api_flow.engine import RunResult

        mock_engine = MagicMock()
        mock_engine.flow.name = "空流程"
        mock_engine.flow.test_cases = []
        mock_engine_cls.return_value = mock_engine

        result = execute_flow(str(FIXTURE_DIR))

        assert isinstance(result, RunResult)
        assert result.total == 0
        assert result.passed == 0
        assert result.failed == 0
        assert len(result.results) == 0

    @patch("api_flow.execute.Engine")
    def test_execute_flow_with_confirm_skip(self, mock_engine_cls):
        """确认回调返回 False 时跳过用例。"""
        from api_flow.engine import RunResult

        mock_engine = MagicMock()
        mock_engine.flow.name = "测试流程"
        mock_tc = MagicMock()
        mock_engine.flow.test_cases = [mock_tc]
        mock_engine.checkpoint_info.return_value = {}
        mock_engine_cls.return_value = mock_engine

        result = execute_flow(
            str(FIXTURE_DIR),
            confirm_fn=lambda tc, info: False,
        )

        assert result.total == 1
        assert result.skipped == 1
        assert result.passed == 0
        mock_engine.run_one.assert_not_called()
