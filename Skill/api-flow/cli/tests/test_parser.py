import pytest
from pathlib import Path
from api_flow.parser import FlowConfig, TestCase, ParseError, load_flow

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "order-flow"


class TestLoadFlow:
    def test_loads_valid_flow(self):
        flow = load_flow(FIXTURE_DIR)

        assert flow.name == "订单创建流程"
        assert flow.base_url == "http://localhost:8080"
        assert flow.auth is not None
        assert flow.auth.type == "oauth2"
        assert len(flow.test_cases) == 3

    def test_flow_yaml_not_found_raises(self):
        with pytest.raises(FileNotFoundError, match="flow.yaml"):
            load_flow(FIXTURE_DIR / "nonexistent")

    def test_tc_ids_are_loaded(self):
        flow = load_flow(FIXTURE_DIR)
        ids = [tc.id for tc in flow.test_cases]
        assert "tc-001" in ids
        assert "tc-002" in ids
        assert "tc-003" in ids

    def test_request_method_is_uppercased(self):
        flow = load_flow(FIXTURE_DIR)
        for tc in flow.test_cases:
            if tc.request:
                assert tc.request.method == tc.request.method.upper()

    def test_prepare_sql_loaded(self):
        flow = load_flow(FIXTURE_DIR)
        tc = flow.test_cases[0]
        assert len(tc.prepare) > 0
        for stmt in tc.prepare:
            assert stmt.strip().endswith(";")

    def test_cleanup_sql_loaded(self):
        flow = load_flow(FIXTURE_DIR)
        tc = flow.test_cases[0]
        assert len(tc.cleanup) > 0
        for stmt in tc.cleanup:
            assert stmt.strip().endswith(";")

    def test_expect_error_loaded(self):
        flow = load_flow(FIXTURE_DIR)
        tc_002 = next(tc for tc in flow.test_cases if tc.id == "tc-002")
        assert tc_002.expect_error is True


def test_parse_sql_statements():
    from api_flow.parser import _parse_sql_statements
    raw = """
    INSERT INTO users VALUES (1);
    UPDATE users SET name = 'x';
    """
    stmts = _parse_sql_statements(raw)
    assert len(stmts) == 2
    assert "INSERT" in stmts[0]
    assert "UPDATE" in stmts[1]


def test_parse_sql_statements_filters_comments():
    from api_flow.parser import _parse_sql_statements
    raw = """
    INSERT INTO users VALUES (1);
    -- this is a comment line
    """
    stmts = _parse_sql_statements(raw)
    assert len(stmts) == 1
    assert "INSERT" in stmts[0]
