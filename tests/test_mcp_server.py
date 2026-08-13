"""Backward-compatible and hardened MCP HTTP-adapter release checks."""

from __future__ import annotations

import asyncio
from unittest.mock import Mock, patch

import httpx
import pytest

from mcp_server import server
from mcp_server.adapters import adapter
from mcp_server.errors import NorthStarMCPError

ORIGINAL_TOOLS = {
    "submit_expense", "get_expense_status", "list_pending_approvals",
    "explain_risk", "approve_expense",
}


def test_original_mcp_tools_remain_registered() -> None:
    tools = asyncio.run(server.mcp.list_tools())
    names = {tool.name for tool in tools}
    assert ORIGINAL_TOOLS <= names
    assert len(names) == 12
    assert all(tool.description and tool.output_schema for tool in tools)


def test_request_uses_timeout_and_returns_json() -> None:
    response = Mock(is_success=True, headers={})
    response.json.return_value = {"status": "ok"}
    with patch("mcp_server.adapters.httpx.request", return_value=response) as request:
        result = server._request("GET", "http://127.0.0.1:8000/health")
    assert result == {"status": "ok"}
    assert request.call_args.kwargs["timeout"] == adapter.timeout


def test_request_reports_safe_timeout_and_connection_errors() -> None:
    with patch("mcp_server.adapters.httpx.request", side_effect=httpx.ReadTimeout("slow")):
        with pytest.raises(NorthStarMCPError, match="UPSTREAM_UNAVAILABLE"):
            server._request("GET", "http://example.test")
    request = httpx.Request("GET", "http://example.test")
    with patch("mcp_server.adapters.httpx.request", side_effect=httpx.ConnectError("offline", request=request)):
        with pytest.raises(NorthStarMCPError, match="UPSTREAM_UNAVAILABLE") as failure:
            server._request("GET", "http://example.test")
    assert "example.test" not in str(failure.value)


def test_local_environment_defaults_are_safe() -> None:
    assert server.API_BASE_URL == "http://127.0.0.1:8000"
    assert server.EXPENSE_WEBHOOK_URL == "http://127.0.0.1:5678/webhook/northstar-expense"
    assert server.APPROVAL_WEBHOOK_URL == "http://127.0.0.1:5678/webhook/northstar-approval"
    assert server.REQUEST_TIMEOUT_SECONDS == 10.0
