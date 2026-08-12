"""Alembic upgrade, alignment, and downgrade contracts."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

PROJECT_DIR = Path(__file__).resolve().parents[1]


def test_alembic_upgrade_check_and_downgrade(
    tmp_path: Path, monkeypatch
) -> None:
    database = tmp_path / "alembic.db"
    database_url = f"sqlite:///{database.as_posix()}"
    monkeypatch.setenv("NORTHSTAR_DATABASE_URL", database_url)
    config = Config(str(PROJECT_DIR / "alembic.ini"))

    command.upgrade(config, "head")
    engine = create_engine(database_url)
    try:
        assert {
            "expenses",
            "workflow_runs",
            "workflow_events",
            "approval_tasks",
            "approval_decisions",
            "approval_notifications",
            "outbox_events",
            "outbox_delivery_attempts",
            "workflow_failures",
            "governance_owners",
            "business_terms",
            "business_term_versions",
            "policy_definitions",
            "policy_versions",
            "policy_rules",
            "trust_signals",
        }.issubset(inspect(engine).get_table_names())
        command.check(config)
        command.downgrade(config, "-1")
        tables_at_gate3b = set(inspect(engine).get_table_names())
        assert "approval_notifications" in tables_at_gate3b
        assert "outbox_events" in tables_at_gate3b
        assert "policy_versions" not in tables_at_gate3b
        assert "approval_tasks" in tables_at_gate3b
        command.upgrade(config, "head")
        assert "approval_notifications" in inspect(engine).get_table_names()
        assert "outbox_events" in inspect(engine).get_table_names()
        assert "policy_versions" in inspect(engine).get_table_names()
        command.downgrade(config, "base")
        remaining = set(inspect(engine).get_table_names())
        assert "expenses" not in remaining
        assert "workflow_runs" not in remaining
    finally:
        engine.dispose()


def test_gate3b_data_survives_context_migration(tmp_path: Path, monkeypatch) -> None:
    database = tmp_path / "preserve.db"
    database_url = f"sqlite:///{database.as_posix()}"
    monkeypatch.setenv("NORTHSTAR_DATABASE_URL", database_url)
    config = Config(str(PROJECT_DIR / "alembic.ini"))
    command.upgrade(config, "20260813_0003")
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(text(
                "INSERT INTO workflow_failures "
                "(failure_id, workflow_id, workflow_name, execution_id, safe_message, first_seen_at, last_seen_at, occurrence_count, status) "
                "VALUES ('preserved', 'workflow', 'Workflow', 'execution', 'safe', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1, 'OPEN')"
            ))
        command.upgrade(config, "20260813_0004")
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT count(*) FROM workflow_failures WHERE failure_id='preserved'")) == 1
        command.downgrade(config, "20260813_0003")
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT count(*) FROM workflow_failures WHERE failure_id='preserved'")) == 1
    finally:
        engine.dispose()
