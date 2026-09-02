"""运行时变量管理 + {{@var}} 模板替换。"""

from __future__ import annotations

import re
from typing import Any

_VAR_PATTERN = re.compile(r"\{\{([@A-Z][A-Za-z0-9_]*)\}\}")


class RuntimeVariables:
    """存储 prepare SQL 产生的变量，供 request body 和 cleanup SQL 引用。"""

    def __init__(self) -> None:
        self._vars: dict[str, str] = {}

    def set(self, name: str, value: str) -> None:
        self._vars[name] = value

    def get(self, name: str) -> str | None:
        return self._vars.get(name)

    def set_auth_token(self, token: str) -> None:
        self._vars["AUTH_TOKEN"] = token

    def items(self):
        return self._vars.items()


def substitute(obj: Any, runtime: RuntimeVariables) -> Any:
    """递归替换对象中所有 {{var}} 占位符为 runtime 中的值。

    Args:
        obj: 字符串、字典、列表或基础类型
        runtime: 包含变量值的 RuntimeVariables 实例

    Returns:
        替换后的对象（类型与输入相同）

    Raises:
        KeyError: 存在 {{@var}} 但 runtime 中没有对应的变量
    """
    if isinstance(obj, str):
        result = obj
        for match in _VAR_PATTERN.finditer(obj):
            var_name = match.group(1)
            value = runtime.get(var_name)
            if value is None:
                raise KeyError(
                    f"变量 '{var_name}' 未在 runtime_vars 中找到。"
                    f" 可用变量: {list(runtime.items())}"
                )
            result = result.replace(match.group(0), value)
        return result
    elif isinstance(obj, dict):
        return {k: substitute(v, runtime) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [substitute(item, runtime) for item in obj]
    else:
        return obj


def parse_set_statement(sql: str) -> tuple[str, str] | None:
    """解析 SET @var = ... 语句，返回 (变量名, 值)。

    只处理简单形式: SET @varname = 'literal_value';
    不处理表达式——LAST_INSERT_ID() 等由 MySQL 端解析。
    """
    m = re.match(
        r"^\s*SET\s+(@[A-Za-z0-9_]+)\s*=\s*(.+?);?\s*$", sql, re.IGNORECASE
    )
    if m:
        var_name = m.group(1)
        expr = m.group(2).rstrip(";").strip()
        return var_name, expr
    return None
