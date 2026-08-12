"""Legacy runtime SQLite migration safety contracts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3

from sqlalchemy import func, select

from app.db.models import ApprovalDecision, Expense, WorkflowEvent, WorkflowRun
from app.db.session import Database
from app.main import create_app
from automation.automation_flow import AutomationPipeline
from scripts.migrate_runtime_sqlite import migrate

PROJECT_DIR = Path(__file__).resolve().parents[1]


def _create_legacy_source(path: Path) -> dict:
    payload = json.loads(
        (PROJECT_DIR / "demo_payloads" / "suspicious_expense.json").read_text(
            encoding="utf-8"
        )
    )
    result = AutomationPipeline().process_single(payload)
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE runtime_expenses (
                expense_id TEXT PRIMARY KEY,
                input_payload TEXT NOT NULL,
                result TEXT NOT NULL,
                status TEXT NOT NULL,
                risk_level TEXT,
                approver_role TEXT,
                decision TEXT,
                decided_by TEXT,
                decision_comment TEXT,
                decided_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO runtime_expenses VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["expense_id"],
                json.dumps(payload),
                json.dumps(result),
                "APPROVED",
                "CRITICAL",
                "Finance Director + Compliance",
                "approve",
                "Finance Director",
                "Legacy approval",
                "2025-01-20T12:00:00+00:00",
                "2025-01-18T12:00:00+00:00",
                "2025-01-20T12:00:00+00:00",
            ),
        )
    return payload


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_migration_dry_run_changes_nothing(tmp_path: Path) -> None:
    source = tmp_path / "legacy.db"
    target = tmp_path / "target.db"
    _create_legacy_source(source)
    source_hash = _sha256(source)

    result = migrate(
        source,
        f"sqlite:///{target.as_posix()}",
        write=False,
    )
    assert result == {"records": 1, "imported": 0, "skipped": 0, "write": False}
    assert not target.exists()
    assert _sha256(source) == source_hash


def test_legacy_write_preserves_decision_and_rerun_is_idempotent(
    tmp_path: Path,
) -> None:
    source = tmp_path / "legacy.db"
    target = tmp_path / "target.db"
    payload = _create_legacy_source(source)
    source_hash = _sha256(source)
    target_url = f"sqlite:///{target.as_posix()}"

    first = migrate(source, target_url, write=True)
    second = migrate(source, target_url, write=True)
    assert first["imported"] == 1
    assert second["imported"] == 0
    assert second["skipped"] == 1
    assert _sha256(source) == source_hash

    database = Database(target_url)
    try:
        with database.session() as session:
            expense = session.scalar(select(Expense))
            run = session.scalar(select(WorkflowRun))
            decision = session.scalar(select(ApprovalDecision))
            assert expense.expense_id == payload["expense_id"]
            assert expense.status == "APPROVED"
            assert expense.current_decision == "approve"
            assert expense.decided_by == "Finance Director"
            assert expense.decision_comment == "Legacy approval"
            assert expense.decided_at.tzinfo is not None
            assert run.source_system == "legacy_sqlite_migration"
            assert session.scalar(select(func.count()).select_from(WorkflowRun)) == 1
            assert session.scalar(select(func.count()).select_from(WorkflowEvent)) == 1
            assert session.scalar(select(func.count()).select_from(ApprovalDecision)) == 1
            assert decision.comment == "Legacy approval"
    finally:
        database.dispose()


def test_sqlite_fallback_bootstraps_legacy_rows_without_removing_source(
    tmp_path: Path,
) -> None:
    source = tmp_path / "runtime.db"
    payload = _create_legacy_source(source)
    with sqlite3.connect(source) as connection:
        source_table_rows_before = connection.execute(
            "SELECT COUNT(*) FROM runtime_expenses"
        ).fetchone()[0]

    application = create_app(source)
    state = application.state.store.get(payload["expense_id"])
    assert state is not None
    assert state["status"] == "APPROVED"
    assert state["decision"] == "approve"
    first_updated_at = state["updated_at"]
    application.state.store.database.dispose()

    restarted = create_app(source)
    restarted_state = restarted.state.store.get(payload["expense_id"])
    assert restarted_state["updated_at"] == first_updated_at
    assert restarted_state["decision"] == "approve"
    with restarted.state.store.database.session() as session:
        assert session.scalar(select(func.count()).select_from(Expense)) == 1
        assert session.scalar(select(func.count()).select_from(WorkflowRun)) == 1
        assert session.scalar(select(func.count()).select_from(WorkflowEvent)) == 1
        assert session.scalar(select(func.count()).select_from(ApprovalDecision)) == 1
    restarted.state.store.database.dispose()
    with sqlite3.connect(source) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM runtime_expenses"
        ).fetchone()[0] == source_table_rows_before
