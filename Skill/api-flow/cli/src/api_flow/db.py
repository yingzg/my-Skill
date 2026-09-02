"""数据库连接：prepare / cleanup SQL 执行（v0.2: 新增 retry）。"""

from __future__ import annotations

import time
from typing import Any

import pymysql

from api_flow.variables import RuntimeVariables, substitute

RETRYABLE_ERROR_CODES = {
    1205,   # ER_LOCK_WAIT_TIMEOUT
    1213,   # ER_LOCK_DEADLOCK
    2002,   # CR_CONNECTION_ERROR
    2003,   # CR_CONN_HOST_ERROR
    2006,   # CR_SERVER_GONE_ERROR
    2013,   # CR_SERVER_LOST
}
MAX_RETRIES = 3
RETRY_BACKOFF = [1, 2, 4]


def _is_retryable(error: Exception) -> bool:
    """判断 DB 错误是否可重试。"""
    if isinstance(error, pymysql.err.OperationalError):
        if error.args and error.args[0] in RETRYABLE_ERROR_CODES:
            return True
    msg = str(error).lower()
    retryable_messages = [
        "connection refused", "connection reset", "connection timed out",
        "lost connection", "server has gone away", "deadlock", "lock wait timeout",
    ]
    return any(m in msg for m in retryable_messages)


class Database:
    """MySQL 数据库连接（通过 PyMySQL）。带指数退避重试。"""

    def __init__(
        self,
        host: str = "localhost",
        user: str = "root",
        password: str = "",
        database: str = "test",
        port: int = 3306,
    ) -> None:
        self._host = host
        self._user = user
        self._password = password
        self._database = database
        self._port = port
        self._conn: Any = None
        self._consecutive_errors: int = 0

    def connect(self) -> None:
        """建立数据库连接（autocommit 模式）。"""
        try:
            self._conn = pymysql.connect(
                host=self._host,
                user=self._user,
                password=self._password,
                database=self._database,
                port=self._port,
                autocommit=True,
                charset="utf8mb4",
            )
        except Exception as e:
            raise Exception(f"数据库连接失败: {e}") from e

    def execute_prepare(self, sql_statements: list[str], runtime: RuntimeVariables) -> None:
        """执行 prepare SQL——顺序执行，每句做变量替换。可重试错误自动退避重试。"""
        if not sql_statements:
            return
        self._execute_with_retry(sql_statements, runtime)

    def execute_cleanup(self, sql_statements: list[str], runtime: RuntimeVariables | None = None) -> None:
        """执行 cleanup SQL——顺序执行。不重试（清理失败直接忽略）。"""
        if not sql_statements:
            return
        if self._conn is None:
            self.connect()
        cursor = self._conn.cursor()
        try:
            for raw_sql in sql_statements:
                resolved = substitute(raw_sql, runtime) if runtime else raw_sql
                if not resolved.strip():
                    continue
                cursor.execute(resolved)
        finally:
            cursor.close()

    def _execute_with_retry(self, sql_statements: list[str], runtime: RuntimeVariables) -> None:
        """带指数退避重试的 SQL 执行。不可重试错误直接抛。"""
        last_error: Exception | None = None

        for attempt in range(MAX_RETRIES):
            try:
                self._execute_batch(sql_statements, runtime)
                self._consecutive_errors = 0
                return
            except Exception as e:
                last_error = e
                if not _is_retryable(e):
                    raise
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_BACKOFF[attempt])
                    if self._conn:
                        try:
                            self._conn.close()
                        except Exception:
                            pass
                        self._conn = None
                    self.connect()

        self._consecutive_errors += 1
        raise Exception(f"SQL 执行失败（已重试 {MAX_RETRIES} 次）: {last_error}") from last_error

    def _execute_batch(self, sql_statements: list[str], runtime: RuntimeVariables) -> None:
        """批量执行 SQL（内部方法）。"""
        if self._conn is None:
            self.connect()
        cursor = self._conn.cursor()
        try:
            for raw_sql in sql_statements:
                resolved = substitute(raw_sql, runtime)
                if not resolved.strip():
                    continue
                cursor.execute(resolved)
        finally:
            cursor.close()

    @property
    def consecutive_errors(self) -> int:
        """连续失败计数（供 engine 判断是否全局中断）。"""
        return self._consecutive_errors

    def close(self) -> None:
        """关闭数据库连接。"""
        if self._conn:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> Database:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
