"""Gate 3B transactional outbox and recovery contracts."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import json
import os
from pathlib import Path
from threading import Barrier

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import delete, func, select

from app.db.base import utc_now
from app.db.models import ApprovalDecision, ApprovalNotification, ApprovalTask, Expense, OutboxDeliveryAttempt, OutboxEvent, WorkflowEvent, WorkflowFailure, WorkflowRun
from app.main import create_app

PROJECT_DIR = Path(__file__).resolve().parents[1]


def payload(expense_id: str) -> dict:
    value = json.loads((PROJECT_DIR / "demo_payloads" / "suspicious_expense.json").read_text(encoding="utf-8"))
    value["expense_id"] = expense_id
    return value


@pytest.fixture
def client(tmp_path: Path, monkeypatch) -> TestClient:
    monkeypatch.setenv("NORTHSTAR_OUTBOX_RETRY_SECONDS", "0,0,0,0")
    return TestClient(create_app(tmp_path / "gate3b.db"))


def make_resume_event(client: TestClient, expense_id: str = "G3B-RESUME") -> dict:
    client.post("/api/expenses/process", json=payload(expense_id)).raise_for_status()
    task = client.get(f"/api/internal/approval-tasks/by-expense/{expense_id}").json()
    client.post(f"/api/expenses/{expense_id}/decision", json={"decision": "approve", "approver": "Director", "comment": "Gate 3B"}).raise_for_status()
    return client.get(f"/api/internal/outbox/by-delivery-key/approval-resume:{task['task_id']}").json()


def test_resume_and_notification_intents_commit_transactionally(client: TestClient) -> None:
    event = make_resume_event(client)
    assert event["event_type"] == "APPROVAL_RESUME_REQUIRED"
    assert set(event["payload"]) == {"approval_task_id", "expense_id"}
    assert "resume_url" not in event["payload"]
    assert "webhook-waiting" not in json.dumps(event["payload"]).lower()

    task_id = event["payload"]["approval_task_id"]
    notification = client.post(f"/api/internal/approval-tasks/{task_id}/notifications/reserve", json={"notification_type": "REMINDER", "escalation_level": 0}).json()
    notification_event = client.get(f"/api/internal/outbox/by-delivery-key/notification:{notification['notification_id']}").json()
    assert notification_event["payload"] == {"notification_id": notification["notification_id"]}
    assert notification_event["event_type"] == "NOTIFICATION_DELIVERY_REQUIRED"


def test_delivery_keys_remain_unique_on_idempotent_replays(client: TestClient) -> None:
    event = make_resume_event(client, "G3B-UNIQUE")
    task_id = event["payload"]["approval_task_id"]

    client.post(
        "/api/expenses/G3B-UNIQUE/decision",
        json={"decision": "approve", "approver": "Director", "comment": "Gate 3B"},
    ).raise_for_status()
    first_notification = client.post(
        f"/api/internal/approval-tasks/{task_id}/notifications/reserve",
        json={"notification_type": "REMINDER", "escalation_level": 0},
    ).json()
    repeated_notification = client.post(
        f"/api/internal/approval-tasks/{task_id}/notifications/reserve",
        json={"notification_type": "REMINDER", "escalation_level": 0},
    ).json()
    assert first_notification["notification_id"] == repeated_notification["notification_id"]

    with client.app.state.store.database.session() as session:
        keys = (
            f"approval-resume:{task_id}",
            f"notification:{first_notification['notification_id']}",
        )
        counts = {
            key: session.scalar(
                select(func.count()).select_from(OutboxEvent).where(OutboxEvent.delivery_key == key)
            )
            for key in keys
        }
    assert counts == {key: 1 for key in keys}


def test_claim_retry_dead_letter_and_replay_preserve_attempts(client: TestClient) -> None:
    event = make_resume_event(client, "G3B-DLQ")
    event_id = event["outbox_event_id"]
    for attempt in range(1, 5):
        claimed = client.post(f"/api/internal/outbox/{event_id}/claim", json={"worker_id": "worker-a", "lease_seconds": 1})
        assert claimed.status_code == 200
        failed = client.post(f"/api/internal/outbox/{event_id}/failure", json={"worker_id": "worker-a", "status_code": 503, "error_message": "temporary provider failure"}).json()
        assert failed["attempt_count"] == attempt
    assert failed["status"] == "DEAD_LETTER"
    assert failed["dead_lettered_at"] is not None
    assert client.post("/api/internal/outbox/claim", json={"worker_id": "worker-b"}).json()["events"] == []
    detail = client.get(f"/api/internal/outbox/{event_id}").json()
    assert [item["attempt_number"] for item in detail["attempts"]] == [1, 2, 3, 4]
    assert all(item["outcome"] == "RETRYABLE_FAILURE" for item in detail["attempts"])

    replay = client.post(f"/api/internal/outbox/{event_id}/replay").json()
    assert replay["status"] == "PENDING" and replay["replay_count"] == 1
    client.post(f"/api/internal/outbox/{event_id}/claim", json={"worker_id": "worker-b"}).raise_for_status()
    delivered = client.post(f"/api/internal/outbox/{event_id}/success", json={"worker_id": "worker-b", "status_code": 200}).json()
    assert delivered["status"] == "DELIVERED"
    detail = client.get(f"/api/internal/outbox/{event_id}").json()
    assert len(detail["attempts"]) == 5
    assert detail["attempts"][-1]["outcome"] == "SUCCESS"


def test_permanent_failure_dead_letters_immediately(client: TestClient) -> None:
    event = make_resume_event(client, "G3B-PERMANENT")
    event_id = event["outbox_event_id"]
    client.post(f"/api/internal/outbox/{event_id}/claim", json={"worker_id": "worker"}).raise_for_status()
    failed = client.post(f"/api/internal/outbox/{event_id}/failure", json={"worker_id": "worker", "status_code": 404, "error_message": "missing target"}).json()
    assert failed["status"] == "DEAD_LETTER"
    assert failed["attempt_count"] == 1
    assert client.get(f"/api/internal/outbox/{event_id}").json()["attempts"][0]["outcome"] == "PERMANENT_FAILURE"


def test_lease_expiry_recovers_abandoned_claim(client: TestClient) -> None:
    event = make_resume_event(client, "G3B-LEASE")
    repository = client.app.state.store.outbox
    now = utc_now()
    first = repository.claim_one(event["outbox_event_id"], "worker-a", 10, now=now)
    assert first["lease_owner"] == "worker-a"
    assert repository.claim_due("worker-b", 10, now=now + timedelta(seconds=9)) == []
    recovered = repository.claim_due("worker-b", 10, now=now + timedelta(seconds=11))
    assert [item["outbox_event_id"] for item in recovered] == [event["outbox_event_id"]]
    assert repository.success(event["outbox_event_id"], "worker-b", now=now + timedelta(seconds=12))["status"] == "DELIVERED"


def test_reconciliation_repairs_missing_intents_once(client: TestClient) -> None:
    event = make_resume_event(client, "G3B-RECONCILE")
    store = client.app.state.store
    task_id = event["payload"]["approval_task_id"]
    notification = client.post(f"/api/internal/approval-tasks/{task_id}/notifications/reserve", json={"notification_type": "OVERDUE", "escalation_level": 0}).json()
    with store.database.transaction() as session:
        session.execute(delete(OutboxEvent).where(OutboxEvent.delivery_key.in_((f"approval-resume:{task_id}", f"notification:{notification['notification_id']}"))))
    first = client.post("/api/internal/reliability/reconcile").json()
    second = client.post("/api/internal/reliability/reconcile").json()
    assert first == {"resume_events_created": 1, "notification_events_created": 1}
    assert second == {"resume_events_created": 0, "notification_events_created": 0}


def test_workflow_failure_is_idempotent_and_sanitized(client: TestClient) -> None:
    body = {"workflow_id": "workflow-1", "workflow_name": "Broken Workflow", "execution_id": "123", "failed_node": "HTTP", "error_class": "NodeApiError", "safe_message": "token=secret-value\npostgresql://user:pass@host/db https://host/webhook-waiting/123?signature=secret", "correlation_id": "corr-1", "expense_id": "EXP-1"}
    first = client.post("/api/internal/workflow-failures", json=body).json()
    second = client.post("/api/internal/workflow-failures", json=body).json()
    assert first["failure_id"] == second["failure_id"]
    assert second["occurrence_count"] == 2
    assert "secret-value" not in second["safe_message"]
    assert "user:pass" not in second["safe_message"]
    assert "signature=" not in second["safe_message"]


POSTGRES_URL = os.getenv("NORTHSTAR_TEST_POSTGRES_URL")


@pytest.mark.skipif(not POSTGRES_URL, reason="requires PostgreSQL")
def test_postgres_skip_locked_divides_events_between_workers(monkeypatch) -> None:
    monkeypatch.setenv("NORTHSTAR_OUTBOX_RETRY_SECONDS", "0,0,0,0")
    app = create_app(POSTGRES_URL)
    store = app.state.store
    with store.database.transaction() as session:
        session.execute(delete(WorkflowFailure))
        session.execute(delete(OutboxDeliveryAttempt))
        session.execute(delete(OutboxEvent))
        session.execute(delete(ApprovalDecision))
        session.execute(delete(ApprovalNotification))
        session.execute(delete(ApprovalTask))
        session.execute(delete(WorkflowEvent))
        session.execute(delete(WorkflowRun))
        session.execute(delete(Expense))
    with TestClient(app) as client_pg:
        for index in range(6):
            client_pg.post("/api/expenses/process", json=payload(f"G3B-PG-CLAIM-{index}")).raise_for_status()
            client_pg.post(f"/api/expenses/G3B-PG-CLAIM-{index}/decision", json={"decision": "approve", "approver": "Director", "comment": "claim"}).raise_for_status()
    barrier = Barrier(2)
    def claim(worker: str) -> list[str]:
        barrier.wait(timeout=10)
        return [event["outbox_event_id"] for event in store.outbox.claim_due(worker, 3)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        claimed = list(pool.map(claim, ("worker-a", "worker-b")))
    assert len(claimed[0]) == len(claimed[1]) == 3
    assert set(claimed[0]).isdisjoint(claimed[1])
