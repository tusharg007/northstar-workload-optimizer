"""Deterministic certification, ownership, and freshness aggregation."""

from __future__ import annotations

from datetime import datetime

from app.db.base import ensure_utc

REQUIRED_SIGNALS = {
    "CERTIFICATION",
    "FRESHNESS",
    "OWNERSHIP",
    "SOURCE_VERIFICATION",
}


def evaluate_trust(
    *,
    version_status: str,
    review_due_at: datetime | None,
    owner_active: bool,
    signals: list[dict],
    as_of: datetime,
) -> dict:
    point = ensure_utc(as_of)
    assert point is not None
    reasons: list[str] = []

    if version_status != "CERTIFIED":
        reasons.append("VERSION_NOT_CERTIFIED")
    if not owner_active:
        reasons.append("OWNER_INACTIVE")

    applicable = [
        signal
        for signal in signals
        if ensure_utc(signal["observed_at"]) <= point
    ]
    by_type = {signal["signal_type"]: signal for signal in applicable}
    missing = sorted(REQUIRED_SIGNALS - set(by_type))
    if missing:
        reasons.extend(f"MISSING_{signal}" for signal in missing)

    failed = sorted(
        signal["signal_type"]
        for signal in applicable
        if signal["status"] == "FAIL"
    )
    if failed:
        reasons.extend(f"FAILED_{signal}" for signal in failed)
        state = "CONFLICTED"
    else:
        expired = [
            signal
            for signal in applicable
            if signal.get("expires_at") is not None
            and ensure_utc(signal["expires_at"]) < point
        ]
        review_stale = review_due_at is not None and ensure_utc(review_due_at) < point
        freshness_expired = any(
            signal["signal_type"] == "FRESHNESS" for signal in expired
        )
        if review_stale:
            reasons.append("REVIEW_OVERDUE")
        if freshness_expired:
            reasons.append("FRESHNESS_SIGNAL_EXPIRED")
        for signal in expired:
            if signal["signal_type"] != "FRESHNESS":
                reasons.append(f"EXPIRED_{signal['signal_type']}")

        if review_stale or freshness_expired:
            state = "STALE"
        elif reasons or any(signal["status"] != "PASS" for signal in applicable):
            if any(signal["status"] != "PASS" for signal in applicable):
                reasons.append("REQUIRED_SIGNAL_NOT_PASSING")
            state = "UNVERIFIED"
        else:
            state = "TRUSTED"

    return {
        "state": state,
        "reasons": sorted(set(reasons)),
        "signals": signals,
    }
