"""MCP tools for the North Star expense workflow.

Submission and approval tools intentionally call n8n. Read-only tools call the
FastAPI domain service so MCP remains an interface rather than an orchestrator.
"""

from __future__ import annotations

import os
from typing import Any

import httpx
from mcp.server import MCPServer

REQUEST_TIMEOUT_SECONDS = 10.0
API_BASE_URL = os.getenv("NORTHSTAR_API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
EXPENSE_WEBHOOK_URL = os.getenv(
    "N8N_EXPENSE_WEBHOOK_URL",
    "http://127.0.0.1:5678/webhook/northstar-expense",
)
APPROVAL_WEBHOOK_URL = os.getenv(
    "N8N_APPROVAL_WEBHOOK_URL",
    "http://127.0.0.1:5678/webhook/northstar-approval",
)

mcp = MCPServer("North Star Workload Optimizer")


def _request(method: str, url: str, **kwargs: Any) -> dict[str, Any] | list[Any]:
    try:
        response = httpx.request(
            method,
            url,
            timeout=REQUEST_TIMEOUT_SECONDS,
            **kwargs,
        )
        response.raise_for_status()
        return response.json()
    except httpx.TimeoutException:
        return {"ok": False, "error": f"Timed out contacting {url}"}
    except httpx.ConnectError:
        return {
            "ok": False,
            "error": f"Could not connect to {url}. Confirm FastAPI and n8n are running.",
        }
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:500]
        return {
            "ok": False,
            "error": f"North Star request failed with HTTP {exc.response.status_code}: {detail}",
        }
    except (httpx.HTTPError, ValueError) as exc:
        return {"ok": False, "error": f"North Star request failed: {exc}"}


@mcp.tool()
def submit_expense(
    expense_id: str,
    employee_id: str,
    employee_name: str,
    department: str,
    transaction_date: str,
    merchant: str,
    category: str,
    amount: float,
    description: str = "",
    currency: str = "USD",
    payment_method: str = "Corporate Card",
    receipt_attached: bool = False,
) -> dict[str, Any] | list[Any]:
    """Submit an expense through the n8n intake workflow."""
    payload = {
        "expense_id": expense_id,
        "employee_id": employee_id,
        "employee_name": employee_name,
        "department": department,
        "transaction_date": transaction_date,
        "merchant": merchant,
        "category": category,
        "description": description,
        "amount": amount,
        "currency": currency,
        "payment_method": payment_method,
        "receipt_attached": receipt_attached,
    }
    return _request("POST", EXPENSE_WEBHOOK_URL, json=payload)


@mcp.tool()
def get_expense_status(expense_id: str) -> dict[str, Any] | list[Any]:
    """Get the durable status and pipeline result for one expense."""
    return _request("GET", f"{API_BASE_URL}/api/expenses/{expense_id}")


@mcp.tool()
def list_pending_approvals() -> dict[str, Any] | list[Any]:
    """List expenses currently pending approval or escalated review."""
    response = _request("GET", f"{API_BASE_URL}/api/expenses")
    if isinstance(response, list):
        return [
            item
            for item in response
            if item.get("status") in {"PENDING_APPROVAL", "ESCALATED"}
        ]
    return response


@mcp.tool()
def explain_risk(expense_id: str) -> dict[str, Any] | list[Any]:
    """Return the deterministic risk and routing explanation for an expense."""
    return _request("GET", f"{API_BASE_URL}/api/expenses/{expense_id}/explanation")


@mcp.tool()
def approve_expense(
    expense_id: str,
    approver: str,
    comment: str = "",
) -> dict[str, Any] | list[Any]:
    """Approve an expense through the n8n approval-decision workflow."""
    return _request(
        "POST",
        APPROVAL_WEBHOOK_URL,
        json={
            "expense_id": expense_id,
            "decision": "approve",
            "approver": approver,
            "comment": comment,
        },
    )


def main() -> None:
    """Run the local MCP server over the standard stdio transport."""
    mcp.run()


if __name__ == "__main__":
    main()

