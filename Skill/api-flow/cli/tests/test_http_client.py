import pytest
from unittest.mock import patch, MagicMock
from api_flow.http_client import HttpClient, HttpResponse
from api_flow.variables import RuntimeVariables


class TestHttpClient:
    @patch("api_flow.http_client.requests.Session.request")
    def test_sends_request_with_substituted_vars(self, mock_request):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"Content-Type": "application/json"}
        mock_resp.json.return_value = {"code": 0, "data": {"orderId": "ORD-001"}}
        mock_resp.text = '{"code":0,"data":{"orderId":"ORD-001"}}'
        mock_request.return_value = mock_resp

        client = HttpClient(base_url="http://localhost:8080")
        rv = RuntimeVariables()
        rv.set("@uid", "abc")
        rv.set_auth_token("Bearer tok123")

        resp = client.request(
            method="POST",
            url="/api/orders",
            headers={"Authorization": "{{AUTH_TOKEN}}", "Content-Type": "application/json"},
            body={"userId": "{{@uid}}", "qty": 1},
            runtime=rv,
        )

        assert resp.status_code == 200
        mock_request.assert_called_once_with(
            method="POST",
            url="http://localhost:8080/api/orders",
            headers={"Authorization": "Bearer tok123", "Content-Type": "application/json"},
            json={"userId": "abc", "qty": 1},
            timeout=30,
        )

    @patch("api_flow.http_client.requests.Session.request")
    def test_extract_jsonpath_from_response(self, mock_request):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"code": 0, "data": {"orderId": "ORD-001", "amount": 6950}}
        mock_resp.text = "{}"
        mock_resp.headers = {}
        mock_request.return_value = mock_resp

        client = HttpClient(base_url="http://localhost:8080")
        rv = RuntimeVariables()

        resp = client.request(
            method="GET",
            url="/api/orders/ORD-001",
            runtime=rv,
        )

        client.extract_to_runtime(resp.body, {"orderId": "$.data.orderId", "amount": "$.data.amount"}, rv)
        assert rv.get("@orderId") == "ORD-001"
        assert rv.get("@amount") == "6950"
