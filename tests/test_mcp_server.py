"""Release checks for the thin MCP HTTP adapter."""

from __future__ import annotations

import asyncio
from unittest.mock import Mock, patch

import httpx

from mcp_server import server


def test_expected_mcp_tools_are_registered() -> None:
    tools = asyncio.run(server.mcp.list_tools())
    assert {tool.name for tool in tools} == {
        "submit_expense",
        "get_expense_status",
        "list_pending_approvals",
        "explain_risk",
        "approve_expense",
    }


def test_request_uses_timeout_and_returns_json() -> None:
    response = Mock()
    response.json.return_value = {"status": "ok"}
    with patch("mcp_server.server.httpx.request", return_value=response) as request:
        result = server._request("GET", "http://127.0.0.1:8000/health")
    assert result == {"status": "ok"}
    assert request.call_args.kwargs["timeout"] == server.REQUEST_TIMEOUT_SECONDS
    response.raise_for_status.assert_called_once_with()


def test_request_reports_timeout_and_connection_errors() -> None:
    timeout = httpx.ReadTimeout("slow")
    with patch("mcp_server.server.httpx.request", side_effect=timeout):
        assert "Timed out" in server._request("GET", "http://example.test")["error"]

    request = httpx.Request("GET", "http://example.test")
    connect = httpx.ConnectError("offline", request=request)
    with patch("mcp_server.server.httpx.request", side_effect=connect):
        result = server._request("GET", "http://example.test")
    assert result["ok"] is False
    assert "Could not connect" in result["error"]


def test_local_environment_defaults_are_safe() -> None:
    assert server.API_BASE_URL == "http://127.0.0.1:8000"
    assert server.EXPENSE_WEBHOOK_URL == (
        "http://127.0.0.1:5678/webhook/northstar-expense"
    )
    assert server.APPROVAL_WEBHOOK_URL == (
        "http://127.0.0.1:5678/webhook/northstar-approval"
    )
    assert server.REQUEST_TIMEOUT_SECONDS == 10.0
