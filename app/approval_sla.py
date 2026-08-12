"""Deterministic operational approval SLA calculations."""

from __future__ import annotations

from datetime import datetime, timedelta
import os

from app.db.base import ensure_utc


class ApprovalSLAService:
    """Calculate demo workflow deadlines without duplicating financial policy."""

    DEFAULT_SECONDS = {
        "CRITICAL": 4 * 60 * 60,
        "HIGH": 8 * 60 * 60,
        "MEDIUM": 24 * 60 * 60,
        "LOW": 48 * 60 * 60,
    }

    def __init__(self, durations: dict[str, int] | None = None) -> None:
        self.durations = durations or {
            risk: int(
                os.getenv(
                    f"NORTHSTAR_APPROVAL_SLA_{risk}_SECONDS", str(default)
                )
            )
            for risk, default in self.DEFAULT_SECONDS.items()
        }
        if any(seconds <= 0 for seconds in self.durations.values()):
            raise ValueError("Approval SLA durations must be positive")

    def due_at(self, created_at: datetime, risk_level: str | None) -> datetime:
        risk = (risk_level or "LOW").upper()
        seconds = self.durations.get(risk, self.durations["LOW"])
        normalized = ensure_utc(created_at)
        assert normalized is not None
        return normalized + timedelta(seconds=seconds)

    @staticmethod
    def stage(
        created_at: datetime, due_at: datetime, now: datetime
    ) -> tuple[str | None, int]:
        created = ensure_utc(created_at)
        due = ensure_utc(due_at)
        current = ensure_utc(now)
        assert created is not None and due is not None and current is not None
        window = (due - created).total_seconds()
        if window <= 0:
            return "ESCALATION", 1
        ratio = (current - created).total_seconds() / window
        if ratio >= 1.5:
            return "ESCALATION", 1
        if ratio >= 1.0:
            return "OVERDUE", 0
        if ratio >= 0.5:
            return "REMINDER", 0
        return None, 0
