import json
import pytest
from pathlib import Path
from api_flow.generate import init_flow, write_tc_json, write_sql


class TestInitFlow:
    def test_creates_directory_structure(self, tmp_path: Path):
        target = init_flow("测试流程", "http://localhost:8080", output_dir=str(tmp_path))
        assert target.is_dir()
        assert target.name == "测试流程"
        assert (target / "flow.yaml").exists()
        assert (target / "results").is_dir()

    def test_flow_yaml_has_required_fields(self, tmp_path: Path):
        target = init_flow("测试流程", "http://localhost:8080", output_dir=str(tmp_path))
        content = (target / "flow.yaml").read_text()
        assert "测试流程" in content
        assert "http://localhost:8080" in content
        assert "bearer" in content

    def test_overwrite_false_skips_existing(self, tmp_path: Path):
        target = init_flow("已存在", "http://a", output_dir=str(tmp_path))
        yaml = target / "flow.yaml"
        yaml.write_text("自定义内容")

        target2 = init_flow("已存在", "http://b", output_dir=str(tmp_path), overwrite=False)
        assert (target2 / "flow.yaml").read_text() == "自定义内容"

    def test_overwrite_true_replaces(self, tmp_path: Path):
        target = init_flow("覆盖测试", "http://a", output_dir=str(tmp_path))
        yaml = target / "flow.yaml"
        yaml.write_text("旧内容")

        init_flow("覆盖测试", "http://b", output_dir=str(tmp_path), overwrite=True)
        assert "http://b" in (target / "flow.yaml").read_text()


class TestWriteTcJson:
    def test_writes_valid_json(self, tmp_path: Path):
        p = write_tc_json(tmp_path, "tc-001", "测试场景", method="POST", url="/api/x")
        assert p.exists()
        data = json.loads(p.read_text())
        assert data["id"] == "tc-001"
        assert data["scenario"] == "测试场景"
        assert data["request"]["method"] == "POST"
        assert data["request"]["url"] == "/api/x"

    def test_all_fields_written(self, tmp_path: Path):
        p = write_tc_json(
            tmp_path, "tc-002",
            scenario="完整字段",
            branch="if x > 0",
            priority="high",
            expect_error=True,
            method="GET",
            url="/api/y",
            body={"k": "v"},
            extract={"var": "$.data"},
        )
        data = json.loads(p.read_text())
        assert data["branch"] == "if x > 0"
        assert data["priority"] == "high"
        assert data["expect_error"] is True
        assert data["request"]["method"] == "GET"
        assert data["request"]["body"] == {"k": "v"}
        assert data["extract"] == {"var": "$.data"}


class TestWriteSql:
    def test_writes_sql_file(self, tmp_path: Path):
        p = write_sql(tmp_path, "test.sql", ["SELECT 1;", "SELECT 2;"])
        assert p.exists()
        content = p.read_text()
        assert "SELECT 1;" in content
        assert "SELECT 2;" in content

    def test_single_statement(self, tmp_path: Path):
        p = write_sql(tmp_path, "single.sql", ["INSERT INTO t VALUES (1)"])
        content = p.read_text().strip()
        assert content == "INSERT INTO t VALUES (1)"
