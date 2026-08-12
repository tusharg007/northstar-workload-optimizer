"""Backward-compatible facade over SQLAlchemy operational repositories."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url

from app.db.repositories.workflows import ProcessOutcome, WorkflowRepository
from app.db.session import Database, normalize_database_url


class RuntimeStore:
    """Preserve the Gate 0 store API while using SQLAlchemy exclusively."""

    def __init__(self, database_url: str | Path | None = None) -> None:
        resolved = normalize_database_url(database_url)
        is_sqlite = make_url(resolved).get_backend_name() == "sqlite"
        self.database = Database(resolved, create_schema=is_sqlite)
        self.repository = WorkflowRepository(self.database)
        self.db_path = Path(make_url(resolved).database) if is_sqlite else None
        if is_sqlite:
            self._bootstrap_legacy_rows()

    def _bootstrap_legacy_rows(self) -> None:
        """Copy legacy materialized rows once while preserving their source table."""
        if "runtime_expenses" not in inspect(self.database.engine).get_table_names():
            return
        with self.database.session() as session:
            rows = [
                dict(row)
                for row in session.execute(
                    text("SELECT * FROM runtime_expenses ORDER BY created_at")
                ).mappings()
            ]
        if not rows:
            return
        for row in rows:
            row["input_payload"] = json.loads(row["input_payload"])
            row["result"] = json.loads(row["result"])
        self.repository.import_legacy_rows(rows)

    def process(
        self,
        input_payload: dict,
        processor: Callable[[dict], dict],
        *,
        idempotency_key: str | None = None,
        correlation_id: str | None = None,
        source_system: str = "api",
    ) -> ProcessOutcome:
        return self.repository.process_expense(
            input_payload,
            processor,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
            source_system=source_system,
        )

    def upsert(
        self,
        expense_id: str,
        input_payload: dict,
        result: dict,
        status: str,
        risk_level: str | None,
        approver_role: str | None,
    ) -> dict:
        """Compatibility adapter for callers of the former sqlite3 store."""
        stored_result = {
            **result,
            "status": status,
            "anomaly": result.get("anomaly")
            or ({"risk_level": risk_level, "flags": []} if risk_level else None),
            "decision": result.get("decision")
            or (
                {"approver_role": approver_role, "approver_level": 0}
                if approver_role
                else None
            ),
        }
        payload = {**input_payload, "expense_id": expense_id}
        return self.process(payload, lambda _: stored_result).state

    def get(self, expense_id: str) -> dict | None:
        return self.repository.get(expense_id)

    def list(self, status: str | None = None) -> list[dict]:
        return self.repository.list(status)

    def update_decision(
        self,
        expense_id: str,
        decision: str,
        approver: str,
        comment: str,
    ) -> dict | None:
        return self.repository.decide(expense_id, decision, approver, comment)
