import pytest
from api_flow.templates import render_case_result, render_summary


class TestRenderCaseResult:
    def test_pass_case(self):
        md = render_case_result(
            tc_id="tc-001",
            scenario="正常创建",
            branch="库存充足",
            priority="high",
            status="pass",
            status_code=200,
            duration_ms=100.0,
            method="POST",
            url="/api/orders",
            request_body={"productId": "P001"},
            response_body={"code": 0},
            prepare_sql=["INSERT INTO product VALUES ('P001');"],
            cleanup_sql=["DELETE FROM product WHERE id = 'P001';"],
        )
        assert "tc-001" in md
        assert "正常创建" in md
        assert "```json" in md
        assert "```sql" in md
        assert "200" in md

    def test_fail_case_shows_error(self):
        md = render_case_result(
            tc_id="tc-002",
            scenario="参数缺失",
            branch="no items",
            priority="medium",
            status="fail",
            status_code=400,
            duration_ms=50.0,
            method="POST",
            url="/api/orders",
            request_body={},
            response_body={"error": "Bad Request"},
            prepare_sql=None,
            cleanup_sql=None,
            error="400 Bad Request",
        )
        assert "tc-002" in md
        assert "参数缺失" in md
        assert "400" in md
        assert "Bad Request" in md

    def test_error_case_with_no_body(self):
        md = render_case_result(
            tc_id="tc-003",
            scenario="网络错误",
            branch="",
            priority="low",
            status="error",
            status_code=None,
            duration_ms=0,
            method="GET",
            url="/api/ping",
            request_body=None,
            response_body=None,
            prepare_sql=None,
            cleanup_sql=None,
            error="Connection refused",
        )
        assert "tc-003" in md
        assert "网络错误" in md
        assert "Connection refused" in md

    def test_prepare_sql_is_optional(self):
        md = render_case_result(
            tc_id="tc-004",
            scenario="无 prepare",
            branch="",
            priority="medium",
            status="pass",
            status_code=200,
            duration_ms=10.0,
            method="GET",
            url="/api/health",
            request_body=None,
            response_body={"ok": True},
            prepare_sql=None,
            cleanup_sql=None,
        )
        assert "tc-004" in md


class TestRenderSummary:
    def test_basic_summary(self):
        results = [
            {"tc_id": "tc-001", "scenario": "正常", "status": "pass", "status_code": 200, "duration_ms": 100, "error": None},
            {"tc_id": "tc-002", "scenario": "异常", "status": "fail", "status_code": 500, "duration_ms": 200, "error": "bug"},
        ]
        md = render_summary("测试流程", results)
        assert "测试流程" in md
        assert "tc-001" in md
        assert "tc-002" in md
        assert "500" in md

    def test_empty_results(self):
        md = render_summary("空流程", [])
        assert "空流程" in md
