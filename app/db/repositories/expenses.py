"""Expense materialized-state persistence helpers."""

from __future__ import annotations

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.db.base import ensure_utc
from app.db.models import Expense


def _iso(value) -> str | None:
    normalized = ensure_utc(value)
    return normalized.isoformat() if normalized else None


class ExpenseRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, expense_id: str, *, for_update: bool = False) -> Expense | None:
        statement = select(Expense).where(Expense.expense_id == expense_id)
        if for_update:
            statement = statement.with_for_update()
        return self.session.scalar(statement)

    def list(self, status: str | None = None) -> list[Expense]:
        statement: Select = select(Expense)
        if status:
            statement = statement.where(Expense.status == status)
        statement = statement.order_by(Expense.created_at.desc())
        return list(self.session.scalars(statement))

    @staticmethod
    def to_state(expense: Expense) -> dict:
        """Preserve the frozen Gate 0 public persistence shape."""
        return {
            "expense_id": expense.expense_id,
            "input_payload": expense.input_payload,
            "result": expense.processing_result,
            "status": expense.status,
            "risk_level": expense.risk_level,
            "approver_role": expense.approver_role,
            "decision": expense.current_decision,
            "decided_by": expense.decided_by,
            "decision_comment": expense.decision_comment,
            "decided_at": _iso(expense.decided_at),
            "created_at": _iso(expense.created_at),
            "updated_at": _iso(expense.updated_at),
        }
