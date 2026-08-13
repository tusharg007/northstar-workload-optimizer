"""PostgreSQL-only Gate 1.5 runtime and concurrency contracts."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
from threading import Barrier
from unittest.mock import patch
from uuid import UUID

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
import psycopg
import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.db.models import (
    ApprovalDecision,
    ApprovalTask,
    Expense,
    WorkflowEvent,
    WorkflowRun,
    DecisionProvenance,
    DecisionRiskEvidence,
)
from app.context.seed import apply_seed, load_seed
from app.db.session import Database
from app.main import create_app

PROJECT_DIR = Path(__file__).resolve().parents[1]
POSTGRES_URL = os.getenv("NORTHSTAR_TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(
    not POSTGRES_URL,
    reason="NORTHSTAR_TEST_POSTGRES_URL is not configured",
)


def _payload(name: str, expense_id: str | None = None) -> dict:
    payload = json.loads(
        (PROJECT_DIR / "demo_payloads" / name).read_text(encoding="utf-8")
    )
    if expense_id:
        payload["expense_id"] = expense_id
    return payload


def _psycopg_url() -> str:
    assert POSTGRES_URL is not None
    return POSTGRES_URL.replace("postgresql+psycopg://", "postgresql://", 1)


@pytest.fixture(scope="module", autouse=True)
def postgres_schema() -> None:
    if not POSTGRES_URL:
        yield
        return
    config = Config(str(PROJECT_DIR / "alembic.ini"))
    os.environ["NORTHSTAR_DATABASE_URL"] = POSTGRES_URL
    command.upgrade(config, "head")
    apply_seed(Database(POSTGRES_URL), load_seed(PROJECT_DIR / "context" / "registry.seed.json"), write=True)
    yield


@pytest.fixture(autouse=True)
def clean_postgres(postgres_schema) -> None:
    if not POSTGRES_URL:
        yield
        return
    with psycopg.connect(_psycopg_url()) as connection:
        connection.execute(
            "TRUNCATE approval_decisions, approval_tasks, workflow_events, "
            "workflow_runs, expenses RESTART IDENTITY CASCADE"
        )
    yield


def _counts() -> dict[str, int]:
    with psycopg.connect(_psycopg_url()) as connection:
        return dict(
            connection.execute(
                """
                SELECT 'expenses', count(*) FROM expenses
                UNION ALL SELECT 'workflow_runs', count(*) FROM workflow_runs
                UNION ALL SELECT 'workflow_events', count(*) FROM workflow_events
                UNION ALL SELECT 'approval_tasks', count(*) FROM approval_tasks
                UNION ALL SELECT 'approval_decisions', count(*) FROM approval_decisions
                UNION ALL SELECT 'decision_provenance', count(*) FROM decision_provenance
                UNION ALL SELECT 'decision_risk_evidence', count(*) FROM decision_risk_evidence
                """
            ).fetchall()
        )


def test_postgres_normal_suspicious_read_explain_restart_and_correlation() -> None:
    normal = _payload("normal_expense.json", "PG-NORMAL-001")
    suspicious = _payload("suspicious_expense.json", "PG-SUSPICIOUS-001")
    with TestClient(create_app(POSTGRES_URL)) as client:
        normal_response = client.post("/api/expenses/process", json=normal)
        assert normal_response.status_code == 200
        assert normal_response.json()["status"] == "PENDING_APPROVAL"
        assert normal_response.json()["risk_level"] == "LOW"
        UUID(normal_response.headers["X-Correlation-ID"])

        suspicious_response = client.post(
            "/api/expenses/process",
            json=suspicious,
            headers={
                "Idempotency-Key": "pg-explicit-001",
                "X-Correlation-ID": "pg-correlation-001",
            },
        )
        assert suspicious_response.status_code == 200
        assert suspicious_response.json()["status"] == "ESCALATED"
        assert suspicious_response.json()["risk_level"] == "CRITICAL"
        assert suspicious_response.json()["approver_role"] == (
            "Finance Director + Compliance"
        )
        assert suspicious_response.headers["X-Correlation-ID"] == (
            "pg-correlation-001"
        )
        lookup = client.get(f"/api/expenses/{suspicious['expense_id']}")
        explanation = client.get(
            f"/api/expenses/{suspicious['expense_id']}/explanation"
        )
        assert lookup.status_code == 200
        assert explanation.status_code == 200
        assert explanation.json()["risk_level"] == "CRITICAL"
        assert explanation.json()["routing_decision"]["approver_role"] == (
            "Finance Director + Compliance"
        )

    with TestClient(create_app(POSTGRES_URL)) as restarted:
        persisted = restarted.get(f"/api/expenses/{suspicious['expense_id']}")
        assert persisted.status_code == 200
        assert persisted.json()["status"] == "ESCALATED"

    with psycopg.connect(_psycopg_url()) as connection:
        run = connection.execute(
            "SELECT correlation_id, idempotency_key FROM workflow_runs "
            "WHERE expense_id=%s",
            (suspicious["expense_id"],),
        ).fetchone()
        assert run == ("pg-correlation-001", "pg-explicit-001")
        assert connection.execute(
            "SELECT count(*) FROM workflow_events WHERE expense_id=%s",
            (suspicious["expense_id"],),
        ).fetchone()[0] == 5
        assert connection.execute(
            "SELECT status FROM approval_tasks WHERE expense_id=%s",
            (suspicious["expense_id"],),
        ).fetchone()[0] == "PENDING"


def test_postgres_derived_idempotency_and_decision_metadata_survive_replay() -> None:
    payload = _payload("suspicious_expense.json", "PG-DERIVED-001")
    with TestClient(create_app(POSTGRES_URL)) as client:
        first = client.post("/api/expenses/process", json=payload)
        original_correlation = first.headers["X-Correlation-ID"]
        approved = client.post(
            f"/api/expenses/{payload['expense_id']}/decision",
            json={
                "decision": "approve",
                "approver": "Finance Director",
                "comment": "Derived key approval",
            },
        )
        assert approved.status_code == 200
        replay = client.post("/api/expenses/process", json=payload)
        assert replay.status_code == 200
        assert replay.headers["X-Correlation-ID"] == original_correlation
        assert replay.json()["status"] == "APPROVED"
        assert replay.json()["decision"] == "approve"
        assert replay.json()["decision_comment"] == "Derived key approval"
    counts = _counts()
    assert counts["expenses"] == 1
    assert counts["workflow_runs"] == 1
    assert counts["approval_tasks"] == 1
    assert counts["decision_provenance"] == 1
    assert counts["decision_risk_evidence"] == 6
    assert counts["approval_decisions"] == 1


def test_postgres_rejection_and_immutable_duplicate_callback() -> None:
    payload = _payload("normal_expense.json", "PG-REJECT-001")
    body = {
        "decision": "reject",
        "approver": "Department Head",
        "comment": "Rejected in PostgreSQL",
    }
    with TestClient(create_app(POSTGRES_URL)) as client:
        client.post("/api/expenses/process", json=payload).raise_for_status()
        first = client.post(
            f"/api/expenses/{payload['expense_id']}/decision", json=body
        )
        duplicate = client.post(
            f"/api/expenses/{payload['expense_id']}/decision", json=body
        )
        assert first.status_code == duplicate.status_code == 200
        assert duplicate.json()["status"] == "REJECTED"
    with psycopg.connect(_psycopg_url()) as connection:
        assert connection.execute(
            "SELECT status FROM approval_tasks WHERE expense_id=%s",
            (payload["expense_id"],),
        ).fetchone()[0] == "REJECTED"
        assert connection.execute(
            "SELECT count(*) FROM approval_decisions WHERE expense_id=%s",
            (payload["expense_id"],),
        ).fetchone()[0] == 1


def test_postgres_concurrent_identical_submit_and_changed_payload_conflict() -> None:
    payload = _payload("suspicious_expense.json", "PG-CONCURRENT-SUBMIT")
    headers = {
        "Idempotency-Key": "pg-concurrent-submit-key",
        "X-Correlation-ID": "pg-concurrent-submit-correlation",
    }
    barrier = Barrier(2)

    def submit() -> tuple[int, dict]:
        with TestClient(create_app(POSTGRES_URL), raise_server_exceptions=False) as client:
            barrier.wait(timeout=10)
            response = client.post(
                "/api/expenses/process", json=payload, headers=headers
            )
            return response.status_code, response.json()

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: submit(), range(2)))
    assert [status for status, _ in responses] == [200, 200]
    assert {body["expense_id"] for _, body in responses} == {payload["expense_id"]}
    counts = _counts()
    assert counts["expenses"] == 1
    assert counts["workflow_runs"] == 1
    assert counts["approval_tasks"] == 1
    assert counts["decision_provenance"] == 1
    assert counts["decision_risk_evidence"] == 6

    changed = {**payload, "amount": payload["amount"] + 1}
    with TestClient(create_app(POSTGRES_URL)) as client:
        conflict = client.post(
            "/api/expenses/process", json=changed, headers=headers
        )
    assert conflict.status_code == 409
    assert "Idempotency-Key" in conflict.json()["detail"]


def test_postgres_concurrent_identical_approvals_are_safe() -> None:
    payload = _payload("suspicious_expense.json", "PG-CONCURRENT-APPROVE")
    with TestClient(create_app(POSTGRES_URL)) as client:
        client.post("/api/expenses/process", json=payload).raise_for_status()
    body = {
        "decision": "approve",
        "approver": "Finance Director",
        "comment": "Same callback",
    }
    barrier = Barrier(2)

    def approve() -> tuple[int, dict]:
        with TestClient(create_app(POSTGRES_URL), raise_server_exceptions=False) as client:
            barrier.wait(timeout=10)
            response = client.post(
                f"/api/expenses/{payload['expense_id']}/decision", json=body
            )
            return response.status_code, response.json()

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: approve(), range(2)))
    assert [status for status, _ in responses] == [200, 200]
    assert {body["status"] for _, body in responses} == {"APPROVED"}
    with psycopg.connect(_psycopg_url()) as connection:
        assert connection.execute(
            "SELECT count(*) FROM approval_decisions"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT count(*) FROM decision_human_evidence"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT status FROM approval_tasks"
        ).fetchone()[0] == "APPROVED"
        assert connection.execute("SELECT status FROM expenses").fetchone()[0] == (
            "APPROVED"
        )


def test_postgres_competing_approval_and_rejection_are_consistent() -> None:
    payload = _payload("suspicious_expense.json", "PG-COMPETING-DECISION")
    with TestClient(create_app(POSTGRES_URL)) as client:
        client.post("/api/expenses/process", json=payload).raise_for_status()
    barrier = Barrier(2)
    bodies = [
        {"decision": "approve", "approver": "Director", "comment": "Approve"},
        {"decision": "reject", "approver": "Director", "comment": "Reject"},
    ]

    def decide(body: dict) -> tuple[int, dict]:
        with TestClient(create_app(POSTGRES_URL), raise_server_exceptions=False) as client:
            barrier.wait(timeout=10)
            response = client.post(
                f"/api/expenses/{payload['expense_id']}/decision", json=body
            )
            return response.status_code, response.json()

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(decide, bodies))
    assert sorted(status for status, _ in responses) == [200, 409]
    with psycopg.connect(_psycopg_url()) as connection:
        decision, task_status, expense_status = connection.execute(
            """
            SELECT d.decision, t.status, e.status
            FROM approval_decisions d
            JOIN approval_tasks t ON t.task_id=d.approval_task_id
            JOIN expenses e ON e.expense_id=d.expense_id
            """
        ).fetchone()
        expected = "APPROVED" if decision == "approve" else "REJECTED"
        assert task_status == expense_status == expected
        assert connection.execute(
            "SELECT count(*) FROM approval_decisions"
        ).fetchone()[0] == 1


def test_postgres_processing_and_approval_rollbacks_leave_no_partial_state(
    monkeypatch,
) -> None:
    application = create_app(POSTGRES_URL)
    repository = application.state.store.repository
    payload = _payload("normal_expense.json", "PG-ROLLBACK-PROCESS")

    def fail_events(*args, **kwargs):
        raise RuntimeError("forced processing rollback")

    monkeypatch.setattr(repository, "_add_processing_events", fail_events)
    with pytest.raises(RuntimeError, match="forced processing rollback"):
        repository.process_expense(
            payload,
            lambda item: {
                "expense_id": item["expense_id"],
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
    assert _counts() == {
        "expenses": 0,
        "workflow_runs": 0,
        "workflow_events": 0,
        "approval_tasks": 0,
        "approval_decisions": 0,
        "decision_provenance": 0,
        "decision_risk_evidence": 0,
    }

    monkeypatch.undo()
    first = _payload("normal_expense.json", "PG-ROLLBACK-SEED")
    second = _payload("suspicious_expense.json", "PG-ROLLBACK-APPROVAL")
    with TestClient(create_app(POSTGRES_URL)) as client:
        client.post("/api/expenses/process", json=first).raise_for_status()
        client.post(
            f"/api/expenses/{first['expense_id']}/decision",
            json={"decision": "approve", "approver": "Head", "comment": "Seed"},
        ).raise_for_status()
        client.post("/api/expenses/process", json=second).raise_for_status()
    with psycopg.connect(_psycopg_url()) as connection:
        existing_id = connection.execute(
            "SELECT decision_id FROM approval_decisions"
        ).fetchone()[0]

    with patch("app.db.repositories.workflows.uuid4", return_value=existing_id):
        with pytest.raises(IntegrityError):
            create_app(POSTGRES_URL).state.store.repository.decide(
                second["expense_id"],
                "approve",
                "Finance Director",
                "Forced rollback",
            )
    with psycopg.connect(_psycopg_url()) as connection:
        state = connection.execute(
            """
            SELECT e.status, e.current_decision, t.status
            FROM expenses e JOIN approval_tasks t USING (expense_id)
            WHERE e.expense_id=%s
            """,
            (second["expense_id"],),
        ).fetchone()
        assert state == ("ESCALATED", None, "PENDING")
        assert connection.execute(
            "SELECT count(*) FROM approval_decisions"
        ).fetchone()[0] == 1
