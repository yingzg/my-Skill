import pytest
from unittest.mock import patch, MagicMock
from api_flow.auth import AuthInjector, AuthConfig, AuthError


class TestAuthInjector:
    def test_none_auth_returns_empty_token(self):
        config = AuthConfig(type="none")
        injector = AuthInjector(config)
        token = injector.get_token()
        assert token == ""

    def test_bearer_auth_uses_literal_token(self):
        config = AuthConfig(type="bearer", token="my-fixed-token")
        injector = AuthInjector(config)
        token = injector.get_token()
        assert token == "Bearer my-fixed-token"

    def test_apikey_auth(self):
        config = AuthConfig(type="apikey", api_key="sk-abc", header_name="X-API-Key")
        injector = AuthInjector(config)
        token = injector.get_token()
        assert token == "sk-abc"

    @patch("api_flow.auth.requests.post")
    def test_oauth2_fetches_token(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"access_token": "tok-oauth"}
        mock_resp.raise_for_status.return_value = None
        mock_post.return_value = mock_resp

        config = AuthConfig(
            type="oauth2",
            token_url="http://localhost/oauth/token",
            client_id="cid",
            client_secret="csec",
        )
        injector = AuthInjector(config)
        token = injector.get_token()
        assert token == "Bearer tok-oauth"

    @patch("api_flow.auth.requests.post")
    def test_oauth2_http_error_raises(self, mock_post):
        import requests as req
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = req.HTTPError("401")
        mock_post.return_value = mock_resp

        config = AuthConfig(
            type="oauth2",
            token_url="http://localhost/oauth/token",
        )
        injector = AuthInjector(config)
        with pytest.raises(AuthError, match="获取 OAuth2 token 失败"):
            injector.get_token()
