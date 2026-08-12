"""Durable SQLite state for the North Star automation demo."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class RuntimeStore:
    """Small sqlite3 repository for processed expenses and decisions."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=5)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        """Create the runtime schema if it does not already exist."""
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS runtime_expenses (
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
                "CREATE INDEX IF NOT EXISTS idx_runtime_status "
                "ON runtime_expenses(status)"
            )

    def upsert(
        self,
        expense_id: str,
        input_payload: dict[str, Any],
        result: dict[str, Any],
        status: str,
        risk_level: str | None,
        approver_role: str | None,
    ) -> dict[str, Any]:
        """Insert or refresh one pipeline result without deleting the database."""
        now = _utc_now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO runtime_expenses (
                    expense_id, input_payload, result, status, risk_level,
                    approver_role, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(expense_id) DO UPDATE SET
                    input_payload = excluded.input_payload,
                    result = excluded.result,
                    status = excluded.status,
                    risk_level = excluded.risk_level,
                    approver_role = excluded.approver_role,
                    decision = NULL,
                    decided_by = NULL,
                    decision_comment = NULL,
                    decided_at = NULL,
                    updated_at = excluded.updated_at
                """,
                (
                    expense_id,
                    json.dumps(input_payload),
                    json.dumps(result),
                    status,
                    risk_level,
                    approver_role,
                    now,
                    now,
                ),
            )
        state = self.get(expense_id)
        assert state is not None
        return state

    def get(self, expense_id: str) -> dict[str, Any] | None:
        """Return one expense, decoding its JSON columns."""
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM runtime_expenses WHERE expense_id = ?",
                (expense_id,),
            ).fetchone()
        return self._decode(row) if row else None

    def list(self, status: str | None = None) -> list[dict[str, Any]]:
        """Return newest expenses, optionally filtered by exact status."""
        query = "SELECT * FROM runtime_expenses"
        parameters: tuple[str, ...] = ()
        if status:
            query += " WHERE status = ?"
            parameters = (status,)
        query += " ORDER BY created_at DESC"
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [self._decode(row) for row in rows]

    def update_decision(
        self,
        expense_id: str,
        decision: str,
        approver: str,
        comment: str,
    ) -> dict[str, Any] | None:
        """Record an approval or rejection and return the updated state."""
        now = _utc_now()
        status = "APPROVED" if decision == "approve" else "REJECTED"
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE runtime_expenses
                SET status = ?, decision = ?, decided_by = ?,
                    decision_comment = ?, decided_at = ?, updated_at = ?
                WHERE expense_id = ?
                """,
                (status, decision, approver, comment, now, now, expense_id),
            )
        if cursor.rowcount == 0:
            return None
        return self.get(expense_id)

    @staticmethod
    def _decode(row: sqlite3.Row) -> dict[str, Any]:
        state = dict(row)
        state["input_payload"] = json.loads(state["input_payload"])
        state["result"] = json.loads(state["result"])
        return state

