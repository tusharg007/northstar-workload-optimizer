"""Tiny in-memory notification sink for local demos and integration tests only."""

from __future__ import annotations

from threading import Lock
from uuid import uuid4

from fastapi import FastAPI, Header
from pydantic import BaseModel, ConfigDict


class NotificationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    notification_id: str
    task_id: str
    type: str
    escalation_level: int
    status: str
    target_role: str
    expense_id: str
    approver_role: str
    risk_level: str | None
    due_at: str | None
    safe_summary: dict


app = FastAPI(title="North Star Local Notification Sink", version="1.0")
app.state.notifications = []
app.state.idempotency = {}
app.state.lock = Lock()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "northstar-notification-sink"}


@app.post("/notifications")
def receive_notification(
    payload: NotificationPayload,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=255),
) -> dict[str, str | bool]:
    with app.state.lock:
        existing = app.state.idempotency.get(idempotency_key)
        if existing is not None:
            return {"status": "accepted", "provider_message_id": existing, "deduplicated": True}
        provider_message_id = f"local-{uuid4()}"
        app.state.notifications.append(
            {**payload.model_dump(), "provider_message_id": provider_message_id, "idempotency_key": idempotency_key}
        )
        app.state.idempotency[idempotency_key] = provider_message_id
    return {"status": "accepted", "provider_message_id": provider_message_id, "deduplicated": False}


@app.get("/test/notifications")
def list_notifications() -> list[dict]:
    with app.state.lock:
        return list(app.state.notifications)


@app.post("/test/reset")
def reset_notifications() -> dict[str, str]:
    with app.state.lock:
        app.state.notifications.clear()
        app.state.idempotency.clear()
    return {"status": "reset"}
