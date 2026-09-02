import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from api_flow.engine import Engine, RunResult, MAX_CASE_RETRIES, MAX_CONSECUTIVE_FAILURES
from api_flow.recorder import TResult

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "order-flow"


class TestEngine:
    def test_engine_loads_flow(self):
        engine = Engine(
            flow_path=FIXTURE_DIR,
            db_config={"host": "localhost", "user": "root", "password": "", "database": "test"},
        )
        assert engine.flow.name == "订单创建流程"
        assert len(engine.flow.test_cases) == 3

    @patch("api_flow.engine.Database")
    def test_run_all_returns_run_result(self, mock_db_cls):
        mock_db = MagicMock()
        mock_db.consecutive_errors = 0
        mock_db_cls.return_value = mock_db

        with patch("api_flow.engine.HttpClient") as mock_http_cls, \
             patch("api_flow.engine.Recorder") as mock_rec_cls, \
             patch("api_flow.engine.AuthInjector") as mock_auth_cls:
            mock_http = MagicMock()
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.body = {"code": 0}
            mock_http.request.return_value = mock_resp
            mock_http_cls.return_value = mock_http

            mock_rec = MagicMock()
            mock_rec_cls.return_value = mock_rec

            mock_auth = MagicMock()
            mock_auth.get_token.return_value = ""
            mock_auth_cls.return_value = mock_auth

            engine = Engine(
                flow_path=FIXTURE_DIR,
                db_config={"host": "localhost", "user": "root", "password": "", "database": "test"},
            )
            result = engine.run_all()

            assert isinstance(result, RunResult)
            assert result.total == 3

    @patch("api_flow.engine.Database")
    def test_consecutive_failures_halt(self, mock_db_cls):
        mock_db = MagicMock()
        mock_db.consecutive_errors = 0
        mock_db_cls.return_value = mock_db

        with patch("api_flow.engine.HttpClient") as mock_http_cls, \
             patch("api_flow.engine.Recorder") as mock_rec_cls, \
             patch("api_flow.engine.AuthInjector") as mock_auth_cls:
            mock_http = MagicMock()
            mock_resp = MagicMock()
            mock_resp.status_code = 500
            mock_resp.body = {"error": "fail"}
            mock_http.request.return_value = mock_resp
            mock_http_cls.return_value = mock_http

            mock_rec = MagicMock()
            mock_rec_cls.return_value = mock_rec

            mock_auth = MagicMock()
            mock_auth.get_token.return_value = ""
            mock_auth_cls.return_value = mock_auth

            engine = Engine(
                flow_path=FIXTURE_DIR,
                db_config={"host": "localhost", "user": "root", "password": "", "database": "test"},
            )
            result = engine.run_all()

            assert len(result.results) <= MAX_CONSECUTIVE_FAILURES


class TestRunResult:
    def test_default_counts_are_zero(self):
        rr = RunResult()
        assert rr.total == 0
        assert rr.passed == 0
        assert rr.failed == 0
        assert rr.skipped == 0
        assert rr.results == []

    def test_counts_accumulate(self):
        rr = RunResult(total=3, passed=2, failed=1)
        assert rr.total == 3
        assert rr.passed == 2
        assert rr.failed == 1
