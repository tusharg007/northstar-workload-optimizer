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
        accepted = client.post("/notifications", json=payload)
        assert accepted.status_code == 200
        assert accepted.json()["provider_message_id"].startswith("local-")
        stored = client.get("/test/notifications").json()
        assert len(stored) == 1
        assert stored[0]["type"] == "REMINDER"
        assert "resume_url" not in stored[0]
        client.post("/test/reset").raise_for_status()
        assert client.get("/test/notifications").json() == []
