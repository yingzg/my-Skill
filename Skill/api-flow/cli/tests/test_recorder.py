import pytest
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
from api_flow.recorder import Recorder, TResult


class TestTResult:
    def test_creates_result_with_defaults(self):
        tr = TResult(tc_id="tc-001", scenario="测试", status="pass")
        assert tr.tc_id == "tc-001"
        assert tr.scenario == "测试"
        assert tr.status == "pass"
        assert tr.status_code is None
        assert tr.duration_ms == 0
        assert tr.error == ""

    def test_full_result(self):
        tr = TResult(
            tc_id="tc-002",
            scenario="异常场景",
            status="fail",
            status_code=500,
            duration_ms=120.5,
            error="Internal Server Error",
        )
        assert tr.tc_id == "tc-002"
        assert tr.status_code == 500
        assert tr.duration_ms == 120.5
        assert tr.error == "Internal Server Error"


class TestRecorder:
    def test_initializes_output_dir(self, tmp_path):
        output_dir = tmp_path / "results"
        Recorder("test-flow", str(output_dir))
        assert output_dir.exists()

    def test_record_saves_meta_file(self, tmp_path):
        output_dir = tmp_path / "results"
        recorder = Recorder("test-flow", str(output_dir))

        tr = TResult(tc_id="tc-001", scenario="normal", status="pass", status_code=200, duration_ms=50.0)
        recorder.record(tr)

        meta_file = recorder.run_dir / "tc-001.meta.json"
        assert meta_file.exists()
        content = meta_file.read_text(encoding="utf-8")
        assert "tc-001" in content
        assert "normal" in content
        assert "pass" in content

    def test_save_summary_creates_json(self, tmp_path):
        output_dir = tmp_path / "results"
        recorder = Recorder("test-flow", str(output_dir))

        results = [
            TResult(tc_id="tc-001", scenario="a", status="pass", status_code=200, duration_ms=100),
            TResult(tc_id="tc-002", scenario="b", status="fail", status_code=500, duration_ms=200, error="bug"),
        ]
        path = recorder.save_summary(results)

        assert path.exists()
        content = path.read_text(encoding="utf-8")
        assert "500" in content
