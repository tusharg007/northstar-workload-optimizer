"""Local notification adapter smoke contracts."""

from fastapi.testclient import TestClient

from scripts.notification_sink import app


def test_notification_sink_health_receive_query_and_reset() -> None:
    with TestClient(app) as client:
        client.post("/test/reset").raise_for_status()
        assert client.get("/health").json() == {
            "status": "ok",
            "service": "northstar-notification-sink",
        }
        payload = {
            "notification_id": "notification-1",
            "task_id": "task-1",
            "type": "REMINDER",
            "escalation_level": 0,
            "status": "PENDING",
            "target_role": "Finance Director",
            "expense_id": "EXP-1",
            "approver_role": "Finance Director",
            "risk_level": "HIGH",
            "due_at": "2026-08-13T00:00:00+00:00",
            "safe_summary": {"expense_id": "EXP-1", "amount": 1000},
        }
        headers = {"Idempotency-Key": "northstar:notification:notification-1"}
        accepted = client.post("/notifications", json=payload, headers=headers)
        assert accepted.status_code == 200
        assert accepted.json()["provider_message_id"].startswith("local-")
        stored = client.get("/test/notifications").json()
        assert len(stored) == 1
        assert stored[0]["type"] == "REMINDER"
        assert "resume_url" not in stored[0]
        repeated = client.post("/notifications", json=payload, headers=headers)
        assert repeated.json()["deduplicated"] is True
        assert repeated.json()["provider_message_id"] == accepted.json()["provider_message_id"]
        assert len(client.get("/test/notifications").json()) == 1
        client.post("/test/reset").raise_for_status()
        assert client.get("/test/notifications").json() == []


def test_notification_sink_real_delivery_is_idempotent(monkeypatch) -> None:
    calls: list[dict] = []

    class StubRouter:
        def dispatch(self, notification: dict) -> dict:
            calls.append(notification)
            return {
                "provider_message_id": "resend-message-1",
                "channels": ["email"],
                "recipients": ["finance@example.com"],
            }

    monkeypatch.setattr(app.state, "router", StubRouter())
    payload = {
        "notification_id": "notification-email-1",
        "task_id": "task-email-1",
        "type": "APPROVAL_REQUEST",
        "escalation_level": 0,
        "status": "PENDING",
        "target_role": "Finance Director",
        "expense_id": "EXP-EMAIL-1",
        "approver_role": "Finance Director",
        "risk_level": "HIGH",
        "due_at": "2026-08-31T00:00:00+00:00",
        "safe_summary": {"expense_id": "EXP-EMAIL-1", "amount": 1000},
    }
    headers = {"Idempotency-Key": "northstar:notification:notification-email-1"}

    with TestClient(app) as client:
        client.post("/test/reset").raise_for_status()
        first = client.post("/notifications", json=payload, headers=headers)
        repeated = client.post("/notifications", json=payload, headers=headers)

    assert first.json() == {
        "status": "accepted",
        "provider_message_id": "resend-message-1",
        "deduplicated": False,
        "channels": ["email"],
        "recipients": ["finance@example.com"],
    }
    assert repeated.json() == {
        "status": "accepted",
        "provider_message_id": "resend-message-1",
        "deduplicated": True,
    }
    assert len(calls) == 1


def test_notification_sink_returns_combined_channel_result(monkeypatch) -> None:
    class StubRouter:
        def dispatch(self, _notification: dict) -> dict:
            return {
                "provider_message_id": "resend-message-2",
                "provider_message_ids": {
                    "email": "resend-message-2",
                    "slack": "slack-ok",
                },
                "channels": ["email", "slack"],
                "recipients": ["finance@example.com"],
            }

    monkeypatch.setattr(app.state, "router", StubRouter())
    payload = {
        "notification_id": "notification-multichannel-1",
        "task_id": "task-multichannel-1",
        "type": "APPROVAL_REQUEST",
        "escalation_level": 0,
        "status": "PENDING",
        "target_role": "Finance Director",
        "expense_id": "EXP-MULTICHANNEL-1",
        "approver_role": "Finance Director",
        "risk_level": "CRITICAL",
        "due_at": "2026-08-31T00:00:00+00:00",
        "safe_summary": {"expense_id": "EXP-MULTICHANNEL-1", "amount": 5000},
    }

    with TestClient(app) as client:
        client.post("/test/reset").raise_for_status()
        response = client.post(
            "/notifications",
            json=payload,
            headers={"Idempotency-Key": "northstar:notification:multichannel-1"},
        )

    assert response.json() == {
        "status": "accepted",
        "provider_message_id": "resend-message-2",
        "provider_message_ids": {
            "email": "resend-message-2",
            "slack": "slack-ok",
        },
        "deduplicated": False,
        "channels": ["email", "slack"],
        "recipients": ["finance@example.com"],
    }
