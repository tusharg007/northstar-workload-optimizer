"""Alembic upgrade, alignment, and downgrade contracts."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

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
        }.issubset(inspect(engine).get_table_names())
        command.check(config)
        command.downgrade(config, "-1")
        tables_at_gate3a = set(inspect(engine).get_table_names())
        assert "approval_notifications" in tables_at_gate3a
        assert "outbox_events" not in tables_at_gate3a
        assert "approval_tasks" in tables_at_gate3a
        command.upgrade(config, "head")
        assert "approval_notifications" in inspect(engine).get_table_names()
        assert "outbox_events" in inspect(engine).get_table_names()
        command.downgrade(config, "base")
        remaining = set(inspect(engine).get_table_names())
        assert "expenses" not in remaining
        assert "workflow_runs" not in remaining
    finally:
        engine.dispose()
