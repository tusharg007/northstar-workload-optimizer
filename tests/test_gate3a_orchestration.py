"""Gate 3A durable approval orchestration and SLA contracts."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import func, select

from app.approval_sla import ApprovalSLAService
from app.db.models import ApprovalDecision, ApprovalNotification, ApprovalTask
from app.main import create_app

PROJECT_DIR = Path(__file__).resolve().parents[1]


def _payload(expense_id: str) -> dict:
    payload = json.loads(
        (PROJECT_DIR / "demo_payloads" / "suspicious_expense.json").read_text(
            encoding="utf-8"
        )
    )
    payload["expense_id"] = expense_id
    return payload


@pytest.fixture
def client(tmp_path: Path, monkeypatch) -> TestClient:
    monkeypatch.setenv("NORTHSTAR_APPROVAL_SLA_CRITICAL_SECONDS", "20")
    return TestClient(create_app(tmp_path / "gate3a.db"))


def _create_task(client: TestClient, expense_id: str = "G3A-001") -> dict:
    response = client.post("/api/expenses/process", json=_payload(expense_id))
    assert response.status_code == 200
    return client.get(
        f"/api/internal/approval-tasks/by-expense/{expense_id}"
    ).json()


def test_sla_due_at_is_created_from_configured_risk_duration(
    client: TestClient,
) -> None:
    task = _create_task(client)
    created_at = datetime.fromisoformat(task["created_at"])
    due_at = datetime.fromisoformat(task["due_at"])
    assert due_at - created_at == timedelta(seconds=20)
    assert task["risk_level"] == "CRITICAL"
    assert task["orchestration_status"] == "NOT_STARTED"


def test_claim_registration_conflict_and_completion_are_deterministic(
    client: TestClient,
) -> None:
    task = _create_task(client)
    expense_id = task["expense_id"]
    task_id = task["task_id"]

    first_claim = client.post(
        f"/api/internal/approval-tasks/by-expense/{expense_id}/orchestration/claim"
    )
    assert first_claim.status_code == 200
    assert first_claim.json()["launch_required"] is True
    second_claim = client.post(
        f"/api/internal/approval-tasks/by-expense/{expense_id}/orchestration/claim"
    )
    assert second_claim.json()["launch_required"] is False

    registration = {
        "n8n_execution_id": "n8n-execution-1",
        "resume_url": "http://127.0.0.1:5678/webhook-waiting/1?token=secret",
    }
    first = client.post(
        f"/api/internal/approval-tasks/{task_id}/orchestration/register",
        json=registration,
    )
    assert first.status_code == 200
    assert first.json()["should_wait"] is True
    assert first.json()["orchestration_status"] == "WAITING"
    replay = client.post(
        f"/api/internal/approval-tasks/{task_id}/orchestration/register",
        json=registration,
    )
    assert replay.status_code == 200
    assert replay.json()["replayed"] is True

    conflict = client.post(
        f"/api/internal/approval-tasks/{task_id}/orchestration/register",
        json={**registration, "n8n_execution_id": "n8n-execution-2"},
    )
    assert conflict.status_code == 409

    client.post(
        f"/api/expenses/{expense_id}/decision",
        json={"decision": "approve", "approver": "Director", "comment": "OK"},
    ).raise_for_status()
    completed = client.post(
        f"/api/internal/approval-tasks/{task_id}/orchestration/complete",
        json={"n8n_execution_id": "n8n-execution-1"},
    )
    assert completed.status_code == 200
    assert completed.json()["orchestration_status"] == "COMPLETED"
    assert completed.json()["resume_url"] is None


def test_decision_before_registration_skips_wait_without_losing_truth(
    client: TestClient,
) -> None:
    task = _create_task(client, "G3A-RACE")
    client.post(
        "/api/internal/approval-tasks/by-expense/G3A-RACE/orchestration/claim"
    ).raise_for_status()
    decision = client.post(
        "/api/expenses/G3A-RACE/decision",
        json={
            "decision": "reject",
            "approver": "Finance Director",
            "comment": "Race winner",
        },
    )
    assert decision.status_code == 200
    registration = client.post(
        f"/api/internal/approval-tasks/{task['task_id']}/orchestration/register",
        json={
            "n8n_execution_id": "late-orchestrator",
            "resume_url": "http://127.0.0.1:5678/webhook-waiting/late?token=secret",
        },
    )
    assert registration.status_code == 200
    assert registration.json()["should_wait"] is False
    assert registration.json()["orchestration_status"] == "COMPLETED"
    assert client.get("/api/expenses/G3A-RACE").json()["status"] == "REJECTED"
    store = client.app.state.store
    with store.database.session() as session:
        assert session.scalar(select(func.count()).select_from(ApprovalDecision)) == 1


def test_notification_reservation_and_sent_marking_are_idempotent(
    client: TestClient,
) -> None:
    task = _create_task(client, "G3A-NOTIFY")
    url = f"/api/internal/approval-tasks/{task['task_id']}/notifications/reserve"
    body = {"notification_type": "APPROVAL_REQUEST", "escalation_level": 0}
    first = client.post(url, json=body)
    replay = client.post(url, json=body)
    assert first.status_code == replay.status_code == 200
    assert first.json()["notification_id"] == replay.json()["notification_id"]
    assert "resume_url" not in json.dumps(first.json())
    notification_id = first.json()["notification_id"]
    sent = client.post(
        f"/api/internal/approval-notifications/{notification_id}/sent",
        json={"provider_message_id": "sink-1"},
    )
    assert sent.status_code == 200
    assert sent.json()["status"] == "SENT"
    duplicate_sent = client.post(
        f"/api/internal/approval-notifications/{notification_id}/sent", json={}
    )
    assert duplicate_sent.json()["status"] == "SENT"
    store = client.app.state.store
    with store.database.session() as session:
        assert session.scalar(
            select(func.count()).select_from(ApprovalNotification)
        ) == 1


def test_sla_stage_boundaries_and_scheduler_dedupe(client: TestClient) -> None:
    service = ApprovalSLAService({risk: 20 for risk in ApprovalSLAService.DEFAULT_SECONDS})
    created = datetime(2026, 1, 1, tzinfo=timezone.utc)
    due = created + timedelta(seconds=20)
    assert service.stage(created, due, created + timedelta(seconds=9)) == (None, 0)
    assert service.stage(created, due, created + timedelta(seconds=10)) == (
        "REMINDER",
        0,
    )
    assert service.stage(created, due, created + timedelta(seconds=20)) == (
        "OVERDUE",
        0,
    )
    assert service.stage(created, due, created + timedelta(seconds=30)) == (
        "ESCALATION",
        1,
    )

    task = _create_task(client, "G3A-SLA")
    task_created = datetime.fromisoformat(task["created_at"])
    reminder_time = task_created + timedelta(seconds=11)
    first = client.post(
        "/api/internal/approval-tasks/sla/notifications/reserve",
        json={"as_of": reminder_time.isoformat()},
    ).json()["notifications"]
    assert [item["type"] for item in first] == ["REMINDER"]
    notification_id = first[0]["notification_id"]
    client.post(
        f"/api/internal/approval-notifications/{notification_id}/sent", json={}
    ).raise_for_status()
    repeated = client.post(
        "/api/internal/approval-tasks/sla/notifications/reserve",
        json={"as_of": reminder_time.isoformat()},
    ).json()["notifications"]
    assert repeated == []

    client.post(
        "/api/expenses/G3A-SLA/decision",
        json={"decision": "approve", "approver": "Director", "comment": "Done"},
    ).raise_for_status()
    after_approval = client.post(
        "/api/internal/approval-tasks/sla/notifications/reserve",
        json={"as_of": (task_created + timedelta(seconds=40)).isoformat()},
    ).json()["notifications"]
    assert after_approval == []


def test_public_expense_and_decision_responses_never_leak_resume_url(
    client: TestClient,
) -> None:
    task = _create_task(client, "G3A-NO-LEAK")
    client.post(
        "/api/internal/approval-tasks/by-expense/G3A-NO-LEAK/orchestration/claim"
    ).raise_for_status()
    client.post(
        f"/api/internal/approval-tasks/{task['task_id']}/orchestration/register",
        json={
            "n8n_execution_id": "sensitive-execution",
            "resume_url": "http://127.0.0.1:5678/webhook-waiting/sensitive?token=secret",
        },
    ).raise_for_status()
    public = client.get("/api/expenses/G3A-NO-LEAK")
    assert "resume" not in public.text.lower()
    decision = client.post(
        "/api/expenses/G3A-NO-LEAK/decision",
        json={"decision": "approve", "approver": "Director", "comment": "OK"},
    )
    assert decision.status_code == 200
    assert "resume" not in decision.text.lower()
