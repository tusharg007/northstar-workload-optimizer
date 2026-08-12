"""Deterministic retry, lease, and safe-error policy for integration delivery."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import os
import re

from app.db.base import ensure_utc, utc_now


@dataclass(frozen=True)
class FailureClassification:
    outcome: str
    category: str
    safe_message: str


class ReliabilityPolicy:
    DEFAULT_DELAYS = (0, 15, 60, 300)

    def __init__(self) -> None:
        raw = os.getenv("NORTHSTAR_OUTBOX_RETRY_SECONDS", "0,15,60,300")
        try:
            delays = tuple(int(part.strip()) for part in raw.split(","))
        except ValueError as exc:
            raise ValueError("NORTHSTAR_OUTBOX_RETRY_SECONDS must be integers") from exc
        if not delays or any(delay < 0 for delay in delays):
            raise ValueError("Outbox retry delays must be non-negative")
        self.delays = delays
        self.max_attempts = int(os.getenv("NORTHSTAR_OUTBOX_MAX_ATTEMPTS", "4"))
        self.lease_seconds = int(os.getenv("NORTHSTAR_OUTBOX_LEASE_SECONDS", "30"))
        if self.max_attempts <= 0 or self.lease_seconds <= 0:
            raise ValueError("Outbox attempts and lease duration must be positive")

    def lease_expires_at(self, now: datetime | None = None) -> datetime:
        current = ensure_utc(now) or utc_now()
        return current + timedelta(seconds=self.lease_seconds)

    def next_attempt_at(self, completed_attempts: int, now: datetime | None = None) -> datetime:
        current = ensure_utc(now) or utc_now()
        index = min(completed_attempts, len(self.delays) - 1)
        return current + timedelta(seconds=self.delays[index])

    @staticmethod
    def sanitize(message: str | None, *, limit: int = 500) -> str:
        text = re.sub(r"\s+", " ", str(message or "Delivery failed")).strip()
        text = re.sub(r"(?i)(https?://[^\s]+/webhook-waiting/)[^\s]+", r"\1[REDACTED]", text)
        text = re.sub(r"(?i)(postgres(?:ql)?(?:\+\w+)?://)[^\s]+", r"\1[REDACTED]", text)
        text = re.sub(r"(?i)(password|token|secret|api[_-]?key)\s*[=:]\s*[^\s,;]+", r"\1=[REDACTED]", text)
        return text[:limit]

    def classify(self, status_code: int | None, category: str | None, message: str | None) -> FailureClassification:
        supplied = (category or "").upper()
        if supplied in {"CONNECTION_ERROR", "TIMEOUT"}:
            return FailureClassification("RETRYABLE_FAILURE", supplied, self.sanitize(message))
        if status_code in {408, 425, 429}:
            return FailureClassification("RETRYABLE_FAILURE", f"HTTP_{status_code}", self.sanitize(message))
        if status_code is not None and 500 <= status_code <= 599:
            return FailureClassification("RETRYABLE_FAILURE", "HTTP_5XX", self.sanitize(message))
        if status_code is not None and 400 <= status_code <= 499:
            return FailureClassification("PERMANENT_FAILURE", "HTTP_4XX", self.sanitize(message))
        if supplied in {"INVALID_TARGET", "PERMANENT"}:
            return FailureClassification("PERMANENT_FAILURE", "INVALID_TARGET", self.sanitize(message))
        return FailureClassification("RETRYABLE_FAILURE", supplied or "UNKNOWN", self.sanitize(message))
