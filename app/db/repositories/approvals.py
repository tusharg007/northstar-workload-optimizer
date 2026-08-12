"""Approval task and immutable decision query helpers."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ApprovalDecision, ApprovalTask


class ApprovalRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def pending_for_expense(self, expense_id: str) -> ApprovalTask | None:
        return self.session.scalar(
            select(ApprovalTask)
            .where(
                ApprovalTask.expense_id == expense_id,
                ApprovalTask.status == "PENDING",
            )
            .order_by(ApprovalTask.created_at.desc())
            .with_for_update()
        )

    def latest_decision(self, expense_id: str) -> ApprovalDecision | None:
        return self.session.scalar(
            select(ApprovalDecision)
            .where(ApprovalDecision.expense_id == expense_id)
            .order_by(ApprovalDecision.decided_at.desc())
        )
