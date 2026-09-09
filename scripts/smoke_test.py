"""End-to-end smoke test for a running FastAPI + n8n demo."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

PROJECT_DIR = Path(__file__).resolve().parents[1]
API_BASE_URL = os.getenv("NORTHSTAR_API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
EXPENSE_WEBHOOK_URL = os.getenv(
    "N8N_EXPENSE_WEBHOOK_URL",
    "http://127.0.0.1:5678/webhook/northstar-expense",
)
APPROVAL_WEBHOOK_URL = os.getenv(
    "N8N_APPROVAL_WEBHOOK_URL",
    "http://127.0.0.1:5678/webhook/northstar-approval",
)


def request(client: httpx.Client, method: str, url: str, **kwargs) -> httpx.Response:
    try:
        response = client.request(method, url, **kwargs)
        response.raise_for_status()
        return response
    except httpx.ConnectError as exc:
        raise RuntimeError(f"Cannot connect to {url}. Is the service running?") from exc
    except httpx.TimeoutException as exc:
        raise RuntimeError(f"Request to {url} timed out.") from exc
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(
            f"{url} returned HTTP {exc.response.status_code}: {exc.response.text[:500]}"
        ) from exc


def main() -> int:
    expense_id = "SMOKE-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    payload = {
        "expense_id": expense_id,
        "employee_id": "EMP-042",
        "employee_name": "Jordan Lee",
        "department": "IT",
        "transaction_date": "2025-01-18",
        "merchant": "Cloud Vendor",
        "category": "Software & Subscriptions",
        "description": "DUPLICATE annual platform renewal",
        "amount": 3000.0,
        "currency": "USD",
        "payment_method": "Corporate Card",
        "receipt_attached": False,
    }

    try:
        with httpx.Client(timeout=10.0) as client:
            health = request(client, "GET", f"{API_BASE_URL}/health").json()
            if not (
                health.get("status") == "ok"
                and health.get("service") == "northstar"
                and health.get("database") == "connected"
            ):
                raise RuntimeError(f"Unexpected health response: {health}")

            submitted = request(client, "POST", EXPENSE_WEBHOOK_URL, json=payload).json()
            if submitted.get("expense_id") != expense_id:
                raise RuntimeError(f"n8n intake returned an unexpected result: {submitted}")
            print(
                "Submitted:",
                submitted.get("status"),
                "risk=",
                submitted.get("risk_level"),
                "route=",
                submitted.get("approver_role"),
            )

            stored = request(client, "GET", f"{API_BASE_URL}/api/expenses/{expense_id}").json()
            if stored.get("expense_id") != expense_id:
                raise RuntimeError("Processed expense was not persisted by FastAPI.")

            approved = request(
                client,
                "POST",
                APPROVAL_WEBHOOK_URL,
                json={
                    "expense_id": expense_id,
                    "decision": "approve",
                    "approver": "Finance Director",
                    "comment": "Smoke test approval",
                },
            ).json()
            if approved.get("status") != "APPROVED":
                raise RuntimeError(f"Approval workflow did not approve expense: {approved}")

            final = request(client, "GET", f"{API_BASE_URL}/api/expenses/{expense_id}").json()
            if final.get("status") != "APPROVED":
                raise RuntimeError(f"Final durable state is not APPROVED: {final}")

        print("NORTH STAR END-TO-END DEMO: PASS")
        return 0
    except (RuntimeError, ValueError) as exc:
        print(f"NORTH STAR END-TO-END DEMO: FAIL - {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
