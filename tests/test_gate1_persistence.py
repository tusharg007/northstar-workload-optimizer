"""Gate 1 operational persistence, idempotency, and audit contracts."""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from uuid import UUID
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, inspect, select
from sqlalchemy.exc import IntegrityError

from app.db.models import (
    ApprovalDecision,
    ApprovalTask,
    Expense,
    WorkflowEvent,
    WorkflowRun,
)
from app.main import create_app

PROJECT_DIR = Path(__file__).resolve().parents[1]


def _payload(name: str) -> dict:
    return json.loads(
        (PROJECT_DIR / "demo_payloads" / name).read_text(encoding="utf-8")
    )


@pytest.fixture
def gate1_client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(tmp_path / "gate1.db"))


def _count(client: TestClient, model) -> int:
    store = client.app.state.store
    with store.database.session() as session:
        return session.scalar(select(func.count()).select_from(model))


def test_schema_creation_and_repository_json_round_trip(
    gate1_client: TestClient,
) -> None:
    response = gate1_client.post(
        "/api/expenses/process", json=_payload("normal_expense.json")
    )
    assert response.status_code == 200
    store = gate1_client.app.state.store
    assert set(inspect(store.database.engine).get_table_names()) == {
        "approval_decisions",
        "approval_tasks",
        "expenses",
        "workflow_events",
        "workflow_runs",
    }
    with store.database.session() as session:
        expense = session.scalar(select(Expense))
        assert expense is not None
        assert expense.input_payload["merchant"] == "Regional Air"
        assert expense.processing_result["validation"]["is_valid"] is True
        assert str(expense.amount) == "640.00"
        assert expense.created_at.tzinfo is not None
        assert expense.updated_at.tzinfo is not None
    assert datetime.fromisoformat(response.json()["created_at"]).tzinfo is not None


def test_processing_transaction_rolls_back_completely(
    gate1_client: TestClient, monkeypatch
) -> None:
    repository = gate1_client.app.state.store.repository

    def fail_events(*args, **kwargs):
        raise RuntimeError("event persistence failed")

    monkeypatch.setattr(repository, "_add_processing_events", fail_events)
    with pytest.raises(RuntimeError, match="event persistence failed"):
        repository.process_expense(
            _payload("normal_expense.json"),
            lambda payload: {
                "expense_id": payload["expense_id"],
                "status": "PENDING_APPROVAL",
                "validation": {"is_valid": True},
                "anomaly": {"risk_level": "LOW", "flags": []},
                "decision": {
                    "approver_role": "Department Head",
                    "approver_level": 2,
                },
                "notification": None,
            },
        )
    assert _count(gate1_client, Expense) == 0
    assert _count(gate1_client, WorkflowRun) == 0
    assert _count(gate1_client, WorkflowEvent) == 0
    assert _count(gate1_client, ApprovalTask) == 0


def test_idempotent_replay_preserves_decision_and_creates_no_duplicates(
    gate1_client: TestClient,
) -> None:
    payload = _payload("suspicious_expense.json")
    headers = {
        "Idempotency-Key": "interview-expense-001",
        "X-Correlation-ID": "interview-correlation-001",
    }
    first = gate1_client.post(
        "/api/expenses/process", json=payload, headers=headers
    )
    assert first.status_code == 200
    assert first.headers["X-Correlation-ID"] == "interview-correlation-001"

    decision = gate1_client.post(
        f"/api/expenses/{payload['expense_id']}/decision",
        json={
            "decision": "approve",
            "approver": "Finance Director",
            "comment": "Approved once",
        },
    )
    assert decision.status_code == 200

    replay = gate1_client.post(
        "/api/expenses/process",
        json=payload,
        headers={
            "Idempotency-Key": "interview-expense-001",
            "X-Correlation-ID": "retry-correlation-is-not-persisted",
        },
    )
    assert replay.status_code == 200
    assert replay.headers["X-Correlation-ID"] == "interview-correlation-001"
    body = replay.json()
    assert body["status"] == "APPROVED"
    assert body["decision"] == "approve"
    assert body["decided_by"] == "Finance Director"
    assert body["decision_comment"] == "Approved once"
    assert _count(gate1_client, Expense) == 1
    assert _count(gate1_client, WorkflowRun) == 1
    assert _count(gate1_client, ApprovalTask) == 1
    assert _count(gate1_client, ApprovalDecision) == 1


def test_idempotency_and_expense_payload_conflicts(
    gate1_client: TestClient,
) -> None:
    payload = _payload("normal_expense.json")
    headers = {"Idempotency-Key": "fixed-key"}
    gate1_client.post("/api/expenses/process", json=payload, headers=headers)

    changed = {**payload, "amount": payload["amount"] + 1}
    reused_key = gate1_client.post(
        "/api/expenses/process", json=changed, headers=headers
    )
    assert reused_key.status_code == 409
    assert "Idempotency-Key" in reused_key.json()["detail"]

    changed_expense = gate1_client.post("/api/expenses/process", json=changed)
    assert changed_expense.status_code == 409
    assert "expense_id" in changed_expense.json()["detail"]


def test_generated_and_supplied_correlation_ids_are_persisted(
    gate1_client: TestClient,
) -> None:
    normal = _payload("normal_expense.json")
    response = gate1_client.post("/api/expenses/process", json=normal)
    generated = response.headers["X-Correlation-ID"]
    UUID(generated)

    suspicious = _payload("suspicious_expense.json")
    suspicious["expense_id"] = "DEMO-SUSPICIOUS-CORRELATION"
    supplied = gate1_client.post(
        "/api/expenses/process",
        json=suspicious,
        headers={"X-Correlation-ID": "caller-supplied-123"},
    )
    assert supplied.headers["X-Correlation-ID"] == "caller-supplied-123"

    store = gate1_client.app.state.store
    with store.database.session() as session:
        runs = {
            run.expense_id: run.correlation_id
            for run in session.scalars(select(WorkflowRun))
        }
    assert runs[normal["expense_id"]] == generated
    assert runs[suspicious["expense_id"]] == "caller-supplied-123"


def test_correlation_id_validation(gate1_client: TestClient) -> None:
    response = gate1_client.post(
        "/api/expenses/process",
        json=_payload("normal_expense.json"),
        headers={"X-Correlation-ID": "contains spaces"},
    )
    assert response.status_code == 422


def test_approval_rejection_history_and_duplicate_callback_safety(
    gate1_client: TestClient,
) -> None:
    payload = _payload("normal_expense.json")
    gate1_client.post("/api/expenses/process", json=payload).raise_for_status()
    body = {"decision": "reject", "approver": "Department Head", "comment": "No"}
    first = gate1_client.post(
        f"/api/expenses/{payload['expense_id']}/decision", json=body
    )
    assert first.status_code == 200
    assert first.json()["status"] == "REJECTED"

    duplicate = gate1_client.post(
        f"/api/expenses/{payload['expense_id']}/decision", json=body
    )
    assert duplicate.status_code == 200
    assert _count(gate1_client, ApprovalDecision) == 1
    with gate1_client.app.state.store.database.session() as session:
        task = session.scalar(select(ApprovalTask))
        history = session.scalar(select(ApprovalDecision))
        assert task.status == "REJECTED"
        assert history.decision == "reject"
        assert history.decided_at.tzinfo is not None

    conflicting = gate1_client.post(
        f"/api/expenses/{payload['expense_id']}/decision",
        json={"decision": "approve", "approver": "Department Head", "comment": "No"},
    )
    assert conflicting.status_code == 409
    assert _count(gate1_client, ApprovalDecision) == 1


def test_approval_transaction_rolls_back_on_decision_insert_failure(
    gate1_client: TestClient,
) -> None:
    first_payload = _payload("normal_expense.json")
    second_payload = _payload("suspicious_expense.json")
    gate1_client.post(
        "/api/expenses/process", json=first_payload
    ).raise_for_status()
    gate1_client.post(
        f"/api/expenses/{first_payload['expense_id']}/decision",
        json={"decision": "approve", "approver": "Head", "comment": "Seed"},
    ).raise_for_status()
    with gate1_client.app.state.store.database.session() as session:
        existing_id = session.scalar(select(ApprovalDecision.decision_id))

    gate1_client.post(
        "/api/expenses/process", json=second_payload
    ).raise_for_status()
    with patch("app.db.repositories.workflows.uuid4", return_value=existing_id):
        with pytest.raises(IntegrityError):
            gate1_client.app.state.store.repository.decide(
                second_payload["expense_id"],
                "approve",
                "Finance Director",
                "Must roll back",
            )

    state = gate1_client.get(
        f"/api/expenses/{second_payload['expense_id']}"
    ).json()
    assert state["status"] == "ESCALATED"
    assert state["decision"] is None
    with gate1_client.app.state.store.database.session() as session:
        task = session.scalar(
            select(ApprovalTask).where(
                ApprovalTask.expense_id == second_payload["expense_id"]
            )
        )
        assert task.status == "PENDING"
    assert _count(gate1_client, ApprovalDecision) == 1


def test_workflow_event_sequence_and_uniqueness(gate1_client: TestClient) -> None:
    payload = _payload("suspicious_expense.json")
    gate1_client.post("/api/expenses/process", json=payload).raise_for_status()
    database = gate1_client.app.state.store.database
    with database.session() as session:
        run = session.scalar(select(WorkflowRun))
        events = list(
            session.scalars(
                select(WorkflowEvent)
                .where(WorkflowEvent.workflow_run_id == run.id)
                .order_by(WorkflowEvent.sequence_number)
            )
        )
        assert [event.event_type for event in events] == [
            "EXPENSE_RECEIVED",
            "VALIDATION_COMPLETED",
            "RISK_EVALUATED",
            "APPROVAL_ROUTED",
            "APPROVAL_REQUIRED",
        ]
        assert [event.sequence_number for event in events] == [1, 2, 3, 4, 5]
        run_id = run.id

    with pytest.raises(IntegrityError):
        with database.transaction() as session:
            session.add(
                WorkflowEvent(
                    workflow_run_id=run_id,
                    expense_id=payload["expense_id"],
                    event_type="DUPLICATE_SEQUENCE",
                    sequence_number=1,
                    payload={},
                )
            )
