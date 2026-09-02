"""录制输出：将每次执行的结果保存为结构化文件（v0.2: MD 输出）。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class TResult:
    """单条测试用例的执行结果数据类。"""

    tc_id: str
    scenario: str
    status: str  # pass | fail | skipped | error
    status_code: int | None = None
    duration_ms: float = 0.0
    error: str = ""
    request_body: Any = None
    response_body: Any = None
    prepare_sql: list[str] | None = None
    cleanup_sql: list[str] | None = None


class Recorder:
    """管理 results/run-<timestamp>/ 目录结构并写入结果文件。

    v0.2 变更:
    - 输出目录改为 flow_dir/results/run-<timestamp>/
    - 输出文件名统一为 .md 格式
    """

    def __init__(self, flow_name: str, output_root: str = "results") -> None:
        """初始化录制器，创建 run 时间戳目录。

        Args:
            flow_name: 流程名称（用于子目录名）
            output_root: 输出根目录（通常为 flow_dir/results/）
        """
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self._run_dir = Path(output_root) / f"run-{timestamp}"
        self._run_dir.mkdir(parents=True, exist_ok=True)

    def record(self, result: TResult) -> None:
        """保存单个测试用例的执行结果到结构化文件。

        Args:
            result: 单条用例执行结果
        """
        if result.prepare_sql:
            (self._run_dir / f"{result.tc_id}-prepare.sql").write_text(
                "\n".join(result.prepare_sql), encoding="utf-8"
            )

        if result.request_body is not None:
            (self._run_dir / f"{result.tc_id}-request.json").write_text(
                json.dumps(result.request_body, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        if result.response_body is not None:
            (self._run_dir / f"{result.tc_id}-response.json").write_text(
                json.dumps(result.response_body, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        if result.cleanup_sql:
            (self._run_dir / f"{result.tc_id}-cleanup.sql").write_text(
                "\n".join(result.cleanup_sql), encoding="utf-8"
            )

        meta = {
            "tc_id": result.tc_id,
            "scenario": result.scenario,
            "status": result.status,
            "status_code": result.status_code,
            "duration_ms": result.duration_ms,
            "error": result.error,
        }
        (self._run_dir / f"{result.tc_id}.meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def save_summary(self, results: list[TResult]) -> Path:
        """保存汇总 JSON。

        Args:
            results: 全部用例执行结果列表

        Returns:
            汇总文件路径
        """
        passed = sum(1 for r in results if r.status == "pass")
        failed = sum(1 for r in results if r.status in ("fail", "error"))
        skipped = len(results) - passed - failed

        summary = {
            "run_id": self._run_dir.name,
            "total": len(results),
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "results": [
                {
                    "tc_id": r.tc_id,
                    "scenario": r.scenario,
                    "status": r.status,
                    "status_code": r.status_code,
                    "duration_ms": r.duration_ms,
                    "error": r.error,
                }
                for r in results
            ],
        }
        summary_path = self._run_dir / "summary.json"
        summary_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return summary_path

    @property
    def run_dir(self) -> Path:
        """当前运行的输出目录。"""
        return self._run_dir
