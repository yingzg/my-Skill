"""Agent 对话式入口：execute_flow() 提供逐用例 checkpoint 确认流程。

此模块是 SKILL.md Phase 2 的执行入口。Agent 调用 execute_flow() 后：
1. 加载 flow 用例
2. 逐条展示 checkpoint 摘要（按 §4.2 格式）
3. 等待用户确认
4. 执行确认的用例
5. 展示单条结果 + 继续下一条
6. 全部完成后输出 summary
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from api_flow.engine import Engine, RunResult
from api_flow.parser import TestCase
from api_flow.templates import render_case_result, render_summary


def execute_flow(
    flow_path: Path | str,
    output_root: str = "results",
    db_config: dict[str, Any] | None = None,
    confirm_fn: Any = None,
    show_fn: Any = None,
) -> RunResult:
    """逐用例执行 flow（对话式 checkpoint 模式）。

    Args:
        flow_path: flow.yaml 所在目录路径
        output_root: 输出根目录（默认为 flow_dir/results/）
        db_config: 数据库连接配置（可选，默认 localhost/test）
        confirm_fn: 确认回调，签名为 fn(tc: TestCase, info: dict) -> bool
                    返回 True 表示确认执行，False 表示跳过。
                    为 None 时自动执行全部（自动模式）。
        show_fn: 展示回调，签名为 fn(text: str) -> None
                 用于输出 checkpoint 和结果。为 None 时用 print()。

    Returns:
        RunResult 对象，包含 total/passed/failed/skipped/results。
    """
    engine = Engine(
        flow_path=flow_path,
        output_root=output_root,
        db_config=db_config,
    )

    engine.init_resources()
    result = RunResult()
    result.total = len(engine.flow.test_cases)

    try:
        for tc in engine.flow.test_cases:
            info = engine.checkpoint_info(tc)

            confirmed = True
            if confirm_fn:
                confirmed = confirm_fn(tc, info)

            if not confirmed:
                result.skipped += 1
                continue

            tr = engine.run_one(tc)
            result.results.append(tr)

            if tr.status == "pass":
                result.passed += 1
            elif tr.status in ("fail", "error"):
                result.failed += 1
            else:
                result.skipped += 1

            if show_fn:
                show_fn(_format_single_result(tr, tc, info))

    finally:
        engine.close_resources()

    return result


def _format_single_result(tr: Any, tc: TestCase, info: dict[str, Any]) -> str:
    """格式化单条用例执行结果。"""
    status_icons = {"pass": "✅", "fail": "❌", "error": "❌", "skipped": "⚠️"}
    icon = status_icons.get(tr.status, "❓")

    lines = [
        f"{icon} {tc.id} — {tc.scenario}",
        f"  分支: {tc.branch or '(未指定)'}",
        f"  {info['method']} {info['url']} → {tr.status_code or '—'} ({tr.duration_ms:.0f}ms)",
    ]
    if tr.error:
        lines.append(f"  错误: {tr.error}")
    return "\n".join(lines)


__all__ = ["execute_flow"]
