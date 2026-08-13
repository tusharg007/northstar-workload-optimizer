"""Create deterministic Gate 6 demo activity through application services."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.models import GovernanceOwner, PolicyDefinition, PolicyVersion, TrustSignal
from app.db.session import Database
from app.main import create_app

ROOT = Path(__file__).resolve().parents[1]
UTC = timezone.utc


def payload(name: str, expense_id: str) -> dict:
    value = json.loads((ROOT / "demo_payloads" / name).read_text(encoding="utf-8"))
    value["expense_id"] = expense_id
    return value


def ensure_expense(client: TestClient, name: str, expense_id: str) -> dict:
    response = client.post("/api/expenses/process", json=payload(name, expense_id))
    if response.status_code not in {200, 409}:
        raise RuntimeError(f"expense {expense_id} failed: {response.status_code} {response.text}")
    return client.get(f"/api/expenses/{expense_id}").json()


def ensure_decision(client: TestClient, expense_id: str, decision: str) -> None:
    current = client.get(f"/api/expenses/{expense_id}").json()
    if current["status"] in {"APPROVED", "REJECTED"}:
        return
    response = client.post(
        f"/api/expenses/{expense_id}/decision",
        json={"decision": decision, "approver": "Gate 6 Demo Operator", "comment": "Deterministic observability fixture"},
    )
    if response.status_code != 200:
        raise RuntimeError(f"decision for {expense_id} failed: {response.status_code} {response.text}")


def ensure_context_fixtures(database: Database) -> None:
    now = datetime.now(UTC)
    fixtures = (
        ("g6-owner-stale", "G6_STALE_OWNER", "Gate 6 Stale Context Owner", True, "g6-policy-stale", "G6_STALE_POLICY", "Gate 6 Stale Policy", "g6-version-stale", "CERTIFIED", now - timedelta(days=1), True),
        ("g6-owner-unverified", "G6_INACTIVE_OWNER", "Gate 6 Inactive Context Owner", False, "g6-policy-unverified", "G6_UNVERIFIED_POLICY", "Gate 6 Unverified Policy", "g6-version-unverified", "DRAFT", now + timedelta(days=30), False),
    )
    with database.transaction() as session:
        for owner_id, owner_key, owner_name, active, policy_id, policy_key, policy_name, version_id, status, review_due, add_signals in fixtures:
            if session.get(GovernanceOwner, owner_id) is None:
                session.add(GovernanceOwner(owner_id=owner_id, owner_key=owner_key, display_name=owner_name, owner_type="TEAM", domain="GATE_6_DEMO", active=active))
            if session.get(PolicyDefinition, policy_id) is None:
                session.add(PolicyDefinition(policy_id=policy_id, policy_key=policy_key, policy_name=policy_name, domain="GATE_6_DEMO", description="Non-decision Gate 6 observability fixture", owner_id=owner_id))
            if session.get(PolicyVersion, version_id) is None:
                session.add(PolicyVersion(policy_version_id=version_id, policy_id=policy_id, version_number=1, status=status, effective_from=now - timedelta(days=30), effective_to=None, review_due_at=review_due, certified_at=now - timedelta(days=30) if status == "CERTIFIED" else None, source_reference="gate6://observability-fixture", content_hash=("a" if add_signals else "b") * 64, context_metadata={"fixture": "gate6"}))
            if add_signals:
                for index, signal_type in enumerate(("CERTIFICATION", "FRESHNESS", "OWNERSHIP", "SOURCE_VERIFICATION"), start=1):
                    signal_id = f"g6-stale-signal-{index}"
                    if session.get(TrustSignal, signal_id) is None:
                        session.add(TrustSignal(trust_signal_id=signal_id, policy_version_id=version_id, business_term_version_id=None, signal_type=signal_type, status="PASS", score=1.0, observed_at=now - timedelta(days=30), expires_at=now + timedelta(days=30), source="gate6-fixture", details={}))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.getenv("NORTHSTAR_DATABASE_URL"))
    args = parser.parse_args()
    if not args.database_url or not args.database_url.startswith("postgresql"):
        parser.error("Gate 6 demo fixture requires a PostgreSQL --database-url or NORTHSTAR_DATABASE_URL")
    database = Database(args.database_url)
    app = create_app(args.database_url)
    with TestClient(app) as client:
        for name, expense_id in (
            ("normal_expense.json", "G6-LOW-PENDING"),
            ("suspicious_expense.json", "G6-CRITICAL-PENDING"),
            ("normal_expense.json", "G6-LOW-APPROVED"),
            ("suspicious_expense.json", "G6-CRITICAL-REJECTED"),
        ):
            ensure_expense(client, name, expense_id)
        ensure_decision(client, "G6-LOW-APPROVED", "approve")
        ensure_decision(client, "G6-CRITICAL-REJECTED", "reject")
        task = client.get("/api/internal/approval-tasks/by-expense/G6-LOW-PENDING").json()
        reserve = client.post(
            f"/api/internal/approval-tasks/{task['task_id']}/notifications/reserve",
            json={"notification_type": "REMINDER", "escalation_level": 0},
        )
        if reserve.status_code not in {200, 409}:
            raise RuntimeError(f"notification reservation failed: {reserve.text}")
        client.post("/api/internal/workflow-failures", json={
            "workflow_id": "gate6-demo-workflow", "workflow_name": "Gate 6 Demo Workflow",
            "execution_id": "gate6-demo-execution", "failed_node": "HTTP Request",
            "error_class": "ProviderUnavailable", "safe_message": "Synthetic safe provider timeout",
            "correlation_id": "gate6-demo-correlation", "expense_id": "G6-CRITICAL-PENDING",
        }).raise_for_status()
    with database.transaction() as session:
        session.execute(__import__("sqlalchemy").text("UPDATE approval_tasks SET due_at=CURRENT_TIMESTAMP - INTERVAL '5 minutes' WHERE expense_id='G6-CRITICAL-PENDING' AND status='PENDING'"))
    pending = app.state.store.outbox.claim_due("gate6-demo-worker", 20)
    for index, event in enumerate(pending):
        if index == 0:
            app.state.store.outbox.success(event["outbox_event_id"], "gate6-demo-worker", status_code=200)
        elif index == 1:
            app.state.store.outbox.failure(event["outbox_event_id"], "gate6-demo-worker", status_code=400, error_category="PROVIDER_REJECTED", error_message="Synthetic permanent rejection")
        else:
            app.state.store.outbox.failure(event["outbox_event_id"], "gate6-demo-worker", status_code=503, error_category="PROVIDER_UNAVAILABLE", error_message="Synthetic retryable outage")
    ensure_context_fixtures(database)
    print(json.dumps({"status": "PASS", "expenses": 4, "approved": 1, "rejected": 1, "pending": 2, "context_fixtures": ["STALE", "UNVERIFIED"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
