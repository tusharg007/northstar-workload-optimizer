"""Lightweight acceptance tests for the North Star runtime service."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.runtime_store import RuntimeStore

PROJECT_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture
def normal_expense() -> dict:
    return json.loads(
        (PROJECT_DIR / "demo_payloads" / "normal_expense.json").read_text(
            encoding="utf-8"
        )
    )


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(tmp_path / "runtime.db"))


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "northstar",
        "database": "connected",
    }


def test_event_stream_headers_payload_and_cleanup(client: TestClient) -> None:
    async def scenario() -> None:
        route = next(
            route
            for route in client.app.routes
            if getattr(route, "path", None) == "/api/events/stream"
        )
        response = await route.endpoint()
        queue = client.app.state.event_subscribers[-1]
        try:
            assert response.media_type == "text/event-stream"
            assert response.headers["cache-control"] == "no-cache"
            assert response.headers["x-accel-buffering"] == "no"

            client.app.state.broadcast_event("probe", {"expense_id": "SSE-1"})
            chunk = await anext(response.body_iterator)
            assert chunk == 'data: {"type": "probe", "expense_id": "SSE-1"}\n\n'
        finally:
            await response.body_iterator.aclose()
        assert queue not in client.app.state.event_subscribers

    asyncio.run(scenario())


def test_process_and_decision_broadcast_state_events(
    client: TestClient, normal_expense: dict
) -> None:
    queue: asyncio.Queue[dict[str, object]] = asyncio.Queue()
    client.app.state.event_subscribers.append(queue)
    try:
        created = client.post("/api/expenses/process", json=normal_expense)
        created.raise_for_status()
        assert queue.get_nowait() == {
            "type": "expense_created",
            "expense_id": normal_expense["expense_id"],
            "status": "PENDING_APPROVAL",
        }

        updated = client.post(
            f"/api/expenses/{normal_expense['expense_id']}/decision",
            json={
                "decision": "approve",
                "approver": "Finance Director",
                "comment": "SSE verification",
            },
        )
        updated.raise_for_status()
        assert queue.get_nowait() == {
            "type": "expense_updated",
            "expense_id": normal_expense["expense_id"],
            "status": "APPROVED",
        }
    finally:
        client.app.state.event_subscribers.remove(queue)


def test_successful_expense_processing(
    client: TestClient, normal_expense: dict
) -> None:
    response = client.post("/api/expenses/process", json=normal_expense)
    assert response.status_code == 200
    body = response.json()
    assert body["expense_id"] == normal_expense["expense_id"]
    assert body["status"] == "PENDING_APPROVAL"
    assert body["risk_level"] == "LOW"
    assert body["approver_role"] == "Department Head"


def test_suspicious_expense_contract(client: TestClient) -> None:
    payload = json.loads(
        (PROJECT_DIR / "demo_payloads" / "suspicious_expense.json").read_text(
            encoding="utf-8"
        )
    )
    response = client.post("/api/expenses/process", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["expense_id"] == "DEMO-SUSPICIOUS-001"
    assert body["status"] == "ESCALATED"
    assert body["risk_level"] == "CRITICAL"
    assert body["approver_role"] == "Finance Director + Compliance"
    assert body["anomaly_flags"]


def test_persisted_expense_lookup(
    client: TestClient, normal_expense: dict
) -> None:
    client.post("/api/expenses/process", json=normal_expense).raise_for_status()
    response = client.get(f"/api/expenses/{normal_expense['expense_id']}")
    assert response.status_code == 200
    assert response.json()["input_payload"]["merchant"] == "Regional Air"
    assert response.json()["result"]["validation"]["is_valid"] is True


def test_persistence_survives_app_recreation(
    tmp_path: Path, normal_expense: dict
) -> None:
    database = tmp_path / "restart.db"
    first_client = TestClient(create_app(database))
    first_client.post(
        "/api/expenses/process", json=normal_expense
    ).raise_for_status()

    restarted_client = TestClient(create_app(database))
    response = restarted_client.get(
        f"/api/expenses/{normal_expense['expense_id']}"
    )
    assert response.status_code == 200
    assert response.json()["status"] == "PENDING_APPROVAL"


def test_invalid_expense_returns_validation_error(
    client: TestClient, normal_expense: dict
) -> None:
    invalid = {**normal_expense, "expense_id": "TEST-INVALID", "amount": -1}
    response = client.post("/api/expenses/process", json=invalid)
    assert response.status_code == 422
    assert response.json()["detail"]


def test_approval_state_transition(
    client: TestClient, normal_expense: dict
) -> None:
    client.post("/api/expenses/process", json=normal_expense).raise_for_status()
    response = client.post(
        f"/api/expenses/{normal_expense['expense_id']}/decision",
        json={
            "decision": "approve",
            "approver": "Finance Director",
            "comment": "Reviewed and approved",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "APPROVED"
    assert body["decision"] == "approve"
    assert body["decided_by"] == "Finance Director"
    assert body["decision_comment"] == "Reviewed and approved"


def test_explanation_endpoint(client: TestClient, normal_expense: dict) -> None:
    client.post("/api/expenses/process", json=normal_expense).raise_for_status()
    response = client.get(
        f"/api/expenses/{normal_expense['expense_id']}/explanation"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["risk_level"] == "LOW"
    assert body["anomaly_flags"] == []
    assert body["routing_decision"]["approver_role"] == "Department Head"
    assert "Department Head" in body["reason"]


def test_runtime_store_round_trip_and_filter(tmp_path: Path) -> None:
    store = RuntimeStore(tmp_path / "standalone.db")
    stored = store.upsert(
        expense_id="STORE-001",
        input_payload={"expense_id": "STORE-001", "amount": 10},
        result={"status": "PENDING_APPROVAL", "anomaly": {"flags": []}},
        status="PENDING_APPROVAL",
        risk_level="LOW",
        approver_role="Direct Manager",
    )
    assert stored["input_payload"]["amount"] == 10
    assert store.list(status="PENDING_APPROVAL")[0]["expense_id"] == "STORE-001"
    updated = store.update_decision("STORE-001", "reject", "Manager", "No receipt")
    assert updated is not None
    assert updated["status"] == "REJECTED"
    assert store.get("missing") is None
