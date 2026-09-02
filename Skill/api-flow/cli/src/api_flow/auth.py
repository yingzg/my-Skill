"""鉴权注入：读取配置获取 token 并注入 {{AUTH_TOKEN}}。"""

from __future__ import annotations

import os
from dataclasses import dataclass

import requests


class AuthError(Exception):
    """鉴权失败。"""
    pass


@dataclass
class AuthConfig:
    type: str  # oauth2 | bearer | apikey | none
    token_url: str = ""
    token: str = ""
    api_key: str = ""
    header_name: str = "Authorization"
    client_id: str = ""
    client_secret: str = ""
    username: str = ""
    password: str = ""


class AuthInjector:
    """处理鉴权获取和 token 注入。"""

    def __init__(self, config: AuthConfig) -> None:
        self._config = config
        self._cached_token: str | None = None

    def get_token(self) -> str:
        """获取 token（带缓存）。"""
        if self._cached_token is not None:
            return self._cached_token

        token = self._fetch_token()
        self._cached_token = token
        return token

    def _fetch_token(self) -> str:
        t = self._config.type
        if t == "none":
            return ""
        elif t == "bearer":
            token = self._config.token
            if not token:
                raise AuthError("bearer 类型需要提供 token")
            return f"Bearer {token}"
        elif t == "apikey":
            return self._config.api_key
        elif t == "oauth2":
            return self._fetch_oauth2()
        else:
            raise AuthError(f"不支持的鉴权类型: {t}")

    def _fetch_oauth2(self) -> str:
        cfg = self._config
        try:
            resp = requests.post(
                cfg.token_url,
                data={
                    "grant_type": "password",
                    "client_id": cfg.client_id,
                    "client_secret": cfg.client_secret,
                    "username": cfg.username,
                    "password": cfg.password,
                },
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            access_token = data.get("access_token", "")
            if not access_token:
                raise AuthError("响应中未找到 access_token")
            return f"Bearer {access_token}"
        except requests.RequestException as e:
            raise AuthError(f"获取 OAuth2 token 失败: {e}") from e


def auth_config_from_yaml(raw: dict) -> AuthConfig:
    """从 flow.yaml 的 auth 段构造 AuthConfig。

    同时从环境变量和 project-test-context.md 读取敏感凭据。
    """
    return AuthConfig(
        type=raw.get("type", "none"),
        token_url=raw.get("token_url", ""),
        token=os.environ.get("API_FLOW_AUTH_TOKEN", raw.get("token", "")),
        api_key=os.environ.get("API_FLOW_API_KEY", raw.get("api_key", "")),
        header_name=raw.get("header_name", "Authorization"),
        client_id=os.environ.get("API_FLOW_CLIENT_ID", raw.get("client_id", "")),
        client_secret=os.environ.get("API_FLOW_CLIENT_SECRET", raw.get("client_secret", "")),
        username=os.environ.get("API_FLOW_USERNAME", raw.get("username", "")),
        password=os.environ.get("API_FLOW_PASSWORD", raw.get("password", "")),
    )
