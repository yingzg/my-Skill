"""模板化输出：生成 tc-*.md 和 summary.md 内容（v0.2 新增）。"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

STATUS_ICONS = {
    "pass": "✅",
    "fail": "❌",
    "error": "❌",
    "skipped": "⚠️",
}

STATUS_TEXT = {
    "pass": "通过",
    "fail": "失败",
    "error": "执行异常",
    "skipped": "跳过",
}


def _error_section(error: str | None) -> str:
    if not error:
        return ""
    nl = "\n"
    return f"### 错误信息{nl}{nl}```{nl}{error}{nl}```"


def render_case_result(
    tc_id: str,
    scenario: str,
    branch: str,
    priority: str,
    status: str,
    status_code: int | None,
    duration_ms: float,
    method: str,
    url: str,
    request_body: dict[str, Any] | None,
    response_body: Any,
    prepare_sql: list[str] | None,
    cleanup_sql: list[str] | None,
    error: str = "",
) -> str:
    """生成单条用例结果 Markdown（按设计规格书 §4.5 模板）。

    Args:
        tc_id: 用例 ID
        scenario: 场景描述
        branch: 分支说明
        priority: 优先级 (high/medium/low)
        status: 执行状态 (pass/fail/error/skipped)
        status_code: HTTP 状态码
        duration_ms: 耗时（毫秒）
        method: HTTP 方法
        url: 请求路径
        request_body: 请求体（字典）
        response_body: 响应体
        prepare_sql: prepare SQL 语句列表
        cleanup_sql: cleanup SQL 语句列表
        error: 错误信息（可选）

    Returns:
        完整的 Markdown 格式用例报告
    """
    icon = STATUS_ICONS.get(status, "❓")
    status_text = STATUS_TEXT.get(status, status)

    req_body_str = json.dumps(request_body, ensure_ascii=False, indent=2) if request_body else ""
    resp_body_str = ""
    if response_body is not None:
        if isinstance(response_body, (dict, list)):
            resp_body_str = json.dumps(response_body, ensure_ascii=False, indent=2)
        else:
            resp_body_str = str(response_body)

    prepare_str = "\n".join(prepare_sql) if prepare_sql else "(无)"
    cleanup_str = "\n".join(cleanup_sql) if cleanup_sql else "(无)"

    return f"""## {tc_id} {icon} — {scenario}

| 项目 | 内容 |
|------|------|
| 分支 | {branch} |
| 优先级 | {priority} |
| 状态 | {icon} {status_text} |
| HTTP 状态码 | {status_code or "—"} |
| 耗时 | {duration_ms:.0f}ms |

### 请求

**{method or "GET"}** `{url or ""}`

```json
{req_body_str}
```

### 响应

```json
{resp_body_str}
```

### 数据操作

**Prepare SQL**（{len(prepare_sql) if prepare_sql else 0} 条）:
```sql
{prepare_str}
```

**Cleanup SQL**（{len(cleanup_sql) if cleanup_sql else 0} 条）:
```sql
{cleanup_str}
```
{_error_section(error)}
"""


def render_summary(
    flow_name: str,
    results: list[dict[str, Any]],
    total_duration_ms: float = 0,
) -> str:
    """生成汇总报告 Markdown（按设计规格书 §4.5 模板）。

    Args:
        flow_name: 流程名称
        results: 每条用例的结果字典列表，每项应包含:
            - tc_id, scenario, status, status_code, duration_ms (可选: error)
        total_duration_ms: 总耗时（毫秒）

    Returns:
        完整的 Markdown 格式汇总报告
    """
    total = len(results)
    passed = sum(1 for r in results if r.get("status") == "pass")
    failed = sum(1 for r in results if r.get("status") in ("fail", "error"))
    skipped = total - passed - failed

    lines: list[str] = [
        f"# {flow_name} — 测试汇总",
        "",
        "| 项目 | 内容 |",
        "|------|------|",
        f"| 执行时间 | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} |",
        f"| 总用例数 | {total} |",
        f"| 通过 | {passed} |",
        f"| 失败 | {failed} |",
        f"| 跳过 | {skipped} |",
        f"| 总耗时 | {total_duration_ms:.0f}ms |",
        "",
        "## 用例明细",
        "",
        "| ID | 场景 | 状态 | HTTP | 耗时 |",
        "|----|------|------|------|------|",
    ]

    for r in results:
        icon = STATUS_ICONS.get(r.get("status", ""), "❓")
        sc = str(r.get("status_code", "—"))
        dur = f"{r.get('duration_ms', 0):.0f}ms"
        lines.append(
            f"| {r.get('tc_id', '')} "
            f"| {r.get('scenario', '')} "
            f"| {icon} "
            f"| {sc} "
            f"| {dur} |"
        )

    failures = [r for r in results if r.get("status") not in ("pass",)]
    if failures:
        lines.append("")
        lines.append("## 失败/异常")
        lines.append("")
        for r in failures:
            lines.append(f"### {r.get('tc_id', '')} — {r.get('scenario', '')}")
            lines.append(f"- 错误: {r.get('error', '未知错误')}")
            lines.append("")

    return "\n".join(lines)
