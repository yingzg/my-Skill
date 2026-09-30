#!/usr/bin/env python3
"""Database MCP client (Google Toolbox for Databases) shared by sql-review scripts.

Configured via environment variables:
  <DB_TYPE>_HOST / _PORT / _USER / _PASSWORD / _DATABASE  (e.g. MYSQL_HOST)
  TOOLBOX_BIN  (optional) — path to the toolbox binary
"""

import json
import os
import select
import shutil
import subprocess


def _resolve_toolbox_bin() -> str:
    """Resolve the Google Toolbox for Databases binary path.

    Resolution order: explicit TOOLBOX_BIN env var > PATH lookup
    (shutil.which) > user-level ~/.claude/bin/toolbox. Returns "" when
    not found so callers can surface a clear error instead of a bare
    FileNotFoundError.
    """
    explicit = os.environ.get("TOOLBOX_BIN", "")
    if explicit:
        return explicit
    found = shutil.which("toolbox")
    if found:
        return found
    user_bin = os.path.expanduser("~/.claude/bin/toolbox")
    if os.path.isfile(user_bin):
        return user_bin
    return ""


TOOLBOX_BIN = _resolve_toolbox_bin()


def db_env(db_type: str) -> dict | None:
    prefix = db_type.upper()
    env = {}
    for key in ("HOST", "PORT", "USER", "PASSWORD", "DATABASE"):
        value = os.environ.get(f"{prefix}_{key}", "")
        if not value:
            return None
        env[f"{prefix}_{key}"] = value
    return env


class ToolboxMcp:
    def __init__(self, db_type: str, db_env: dict, timeout: float = 30.0):
        if not TOOLBOX_BIN:
            raise RuntimeError(
                "toolbox binary not found: set TOOLBOX_BIN env var or install "
                "Google Toolbox for Databases "
                "(https://github.com/GoogleCloudPlatform/db-toolbox)"
            )
        self._proc = subprocess.Popen(
            [TOOLBOX_BIN, "--prebuilt", db_type, "--stdio"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env={**os.environ, **db_env},
            text=True,
            bufsize=1,
        )
        self._next_id = 1
        self._timeout = timeout

    def initialize(self) -> None:
        self._request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "sql-review", "version": "1.0.0"},
        })
        self._notify("notifications/initialized")

    def execute_sql(self, sql: str) -> str:
        resp = self._request("tools/call", {
            "name": "execute_sql",
            "arguments": {"sql": sql},
        })
        if "result" not in resp:
            raise RuntimeError(f"execute_sql failed: {json.dumps(resp, ensure_ascii=False)[:200]}")
        result = resp["result"]
        if result.get("isError"):
            raise RuntimeError(f"execute_sql error: {json.dumps(result, ensure_ascii=False)[:200]}")
        content = result.get("content", [])
        if not content:
            return ""
        return content[0].get("text", "")

    def close(self) -> None:
        try:
            self._proc.terminate()
        except Exception:
            pass

    def _request(self, method: str, params: dict) -> dict:
        msg_id = self._next_id
        self._next_id += 1
        self._write({"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params})
        while True:
            line = self._read_line()
            resp = json.loads(line)
            if resp.get("id") == msg_id:
                return resp

    def _read_line(self) -> str:
        ready, _, _ = select.select([self._proc.stdout], [], [], self._timeout)
        if not ready:
            raise RuntimeError(f"toolbox MCP timeout after {self._timeout}s")
        line = self._proc.stdout.readline()
        if not line:
            raise RuntimeError("toolbox MCP process exited unexpectedly")
        return line

    def _notify(self, method: str) -> None:
        self._write({"jsonrpc": "2.0", "method": method})

    def _write(self, msg: dict) -> None:
        self._proc.stdin.write(json.dumps(msg, ensure_ascii=False) + "\n")
        self._proc.stdin.flush()
