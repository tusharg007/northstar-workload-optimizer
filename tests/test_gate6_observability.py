"""Gate 6 static and PostgreSQL read-only observability contracts."""

from __future__ import annotations

import json
import os
from pathlib import Path

from alembic import command
from alembic.config import Config
import psycopg
from psycopg import sql
import pytest
from fastapi.testclient import TestClient

from app.context.seed import apply_seed, load_seed
from app.db.session import Database
from app.main import create_app
from metabase.validate import validate
from scripts.create_metabase_readonly_role import reconcile_role

ROOT = Path(__file__).resolve().parents[1]
POSTGRES_URL = os.getenv("NORTHSTAR_TEST_POSTGRES_URL")
EXPECTED_VIEWS = {
    "approval_sla", "context_policy_health", "context_term_health",
    "decision_provenance_quality", "delivery_attempts", "expense_operations",
    "reliability_outbox", "risk_signal_activity", "workflow_failures",
}
PROHIBITED_COLUMNS = {
    "n8n_wait_resume_url", "input_payload", "processing_result", "payload",
    "description", "payment_method", "decision_comment", "comment",
    "safe_message", "safe_error_message", "last_error_message", "details",
    "observed_value", "threshold_or_reference", "source_reference",
}


def _dsn() -> str:
    assert POSTGRES_URL
    return POSTGRES_URL.replace("postgresql+psycopg://", "postgresql://", 1)


def _config() -> Config:
    return Config(str(ROOT / "alembic.ini"))


def test_metabase_manifest_is_statically_valid() -> None:
    assert validate() == []


def test_gate6_migration_isolated_from_sqlite(tmp_path: Path, monkeypatch) -> None:
    url = f"sqlite:///{(tmp_path / 'gate6.db').as_posix()}"
    monkeypatch.setenv("NORTHSTAR_DATABASE_URL", url)
    command.upgrade(_config(), "head")
    assert create_app(url).state.store.database.engine.dialect.name == "sqlite"


@pytest.mark.skipif(not POSTGRES_URL, reason="NORTHSTAR_TEST_POSTGRES_URL is not configured")
def test_postgres_observability_migration_cycle_and_sensitive_columns(monkeypatch) -> None:
    monkeypatch.setenv("NORTHSTAR_DATABASE_URL", POSTGRES_URL or "")
    command.downgrade(_config(), "20260813_0005")
    with psycopg.connect(_dsn()) as connection:
        assert connection.execute("SELECT to_regnamespace('observability')").fetchone()[0] is None
    command.upgrade(_config(), "20260813_0006")
    with psycopg.connect(_dsn()) as connection:
        views = {row[0] for row in connection.execute("SELECT table_name FROM information_schema.views WHERE table_schema='observability'")}
        assert views == EXPECTED_VIEWS
        exposed = {row[0] for row in connection.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='observability'")}
        assert exposed.isdisjoint(PROHIBITED_COLUMNS)
        columns = {
            row[0]: {column[0] for column in connection.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_schema='observability' AND table_name=%s",
                (row[0],),
            )}
            for row in connection.execute("SELECT table_name FROM information_schema.views WHERE table_schema='observability'")
        }
        assert {"expense_id", "processing_duration_ms", "requires_human_review", "final_decision"} <= columns["expense_operations"]
        assert {"overdue", "sla_stage", "sla_remaining_seconds"} <= columns["approval_sla"]
        assert {"retry_pending", "lease_expired", "terminal_failure"} <= columns["reliability_outbox"]
        assert {"trust_state", "review_overdue", "freshness_expired"} <= columns["context_policy_health"]
        assert {"structurally_complete", "risk_evidence_count", "human_evidence_count"} <= columns["decision_provenance_quality"]
    command.downgrade(_config(), "20260813_0005")
    command.upgrade(_config(), "20260813_0006")


@pytest.mark.skipif(not POSTGRES_URL, reason="NORTHSTAR_TEST_POSTGRES_URL is not configured")
def test_observability_fixture_metrics_and_trust_semantics(monkeypatch) -> None:
    monkeypatch.setenv("NORTHSTAR_DATABASE_URL", POSTGRES_URL or "")
    command.upgrade(_config(), "head")
    database = Database(POSTGRES_URL)
    apply_seed(database, load_seed(ROOT / "context" / "registry.seed.json"), write=True)
    payload = json.loads((ROOT / "demo_payloads" / "suspicious_expense.json").read_text(encoding="utf-8"))
    payload["expense_id"] = "G6-VIEW-CRITICAL"
    with psycopg.connect(_dsn(), autocommit=True) as connection:
        connection.execute("TRUNCATE approval_decisions, approval_tasks, workflow_events, workflow_runs, expenses RESTART IDENTITY CASCADE")
    with TestClient(create_app(POSTGRES_URL)) as client:
        response = client.post("/api/expenses/process", json=payload)
        assert response.status_code == 200
    with psycopg.connect(_dsn(), autocommit=True) as connection:
        connection.execute("UPDATE approval_tasks SET due_at=CURRENT_TIMESTAMP - INTERVAL '1 minute' WHERE expense_id=%s", (payload["expense_id"],))
        operations = connection.execute("SELECT risk_level, requires_human_review FROM observability.expense_operations WHERE expense_id=%s", (payload["expense_id"],)).fetchone()
        sla = connection.execute("SELECT status, overdue, sla_stage FROM observability.approval_sla WHERE expense_id=%s", (payload["expense_id"],)).fetchone()
        provenance = connection.execute("SELECT structurally_complete, risk_evidence_count FROM observability.decision_provenance_quality WHERE expense_id=%s", (payload["expense_id"],)).fetchone()
        triggered = connection.execute("SELECT count(*) FROM observability.risk_signal_activity WHERE expense_id=%s AND triggered", (payload["expense_id"],)).fetchone()[0]
        assert operations == ("CRITICAL", True)
        assert sla == ("PENDING", True, "ESCALATION")
        assert provenance[0] is True and provenance[1] > 0
        assert triggered > 0
        trusted = connection.execute("SELECT trust_state FROM observability.context_policy_health WHERE is_latest_version").fetchall()
        assert trusted and {row[0] for row in trusted} == {"TRUSTED"}
        policy_version = connection.execute("SELECT policy_version_id FROM observability.context_policy_health WHERE is_latest_version LIMIT 1").fetchone()[0]
        connection.execute("BEGIN")
        connection.execute("UPDATE policy_versions SET review_due_at=CURRENT_TIMESTAMP - INTERVAL '1 day' WHERE policy_version_id=%s", (policy_version,))
        assert connection.execute("SELECT trust_state FROM observability.context_policy_health WHERE policy_version_id=%s", (policy_version,)).fetchone()[0] == "STALE"
        connection.execute("ROLLBACK")


@pytest.mark.skipif(not POSTGRES_URL, reason="NORTHSTAR_TEST_POSTGRES_URL is not configured")
def test_exact_metabase_role_can_only_select_observability(monkeypatch) -> None:
    monkeypatch.setenv("NORTHSTAR_DATABASE_URL", POSTGRES_URL or "")
    command.upgrade(_config(), "head")
    role, password = "northstar_metabase_ro_test", "gate6-disposable-password"
    with psycopg.connect(_dsn(), autocommit=True) as admin:
        admin.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(role)))
    try:
        reconcile_role(POSTGRES_URL or "", role, password)
        parsed = psycopg.conninfo.conninfo_to_dict(_dsn())
        parsed.update(user=role, password=password)
        with psycopg.connect(**parsed, autocommit=True) as connection:
            connection.execute("SELECT count(*) FROM observability.expense_operations").fetchone()
            for statement in (
                "SELECT count(*) FROM expenses",
                "INSERT INTO expenses (expense_id) VALUES ('denied')",
                "UPDATE expenses SET status='DENIED'",
                "DELETE FROM expenses",
                "TRUNCATE expenses",
                "CREATE TABLE denied_table (id integer)",
                "ALTER TABLE expenses ADD COLUMN denied_column integer",
            ):
                with pytest.raises(psycopg.errors.InsufficientPrivilege):
                    connection.execute(statement)
    finally:
        with psycopg.connect(_dsn(), autocommit=True) as admin:
            if admin.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (role,)).fetchone():
                admin.execute(sql.SQL("DROP OWNED BY {}") .format(sql.Identifier(role)))
                admin.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))
