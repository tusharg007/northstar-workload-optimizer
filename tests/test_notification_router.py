"""Real-email routing contracts without contacting Resend."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

import pytest

from scripts.notification_router import NotificationRouter


@pytest.fixture(autouse=True)
def clear_notification_provider_environment(monkeypatch) -> None:
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("NOTIFICATION_DIRECTORY", raising=False)


def notification(notification_type: str = "APPROVAL_REQUEST") -> dict:
    return {
        "notification_id": "notification-1",
        "type": notification_type,
        "target_role": "Finance Director",
        "expense_id": "EXP-1",
        "risk_level": "HIGH",
        "due_at": "2026-08-31T12:00:00+00:00",
        "safe_summary": {
            "expense_id": "EXP-1",
            "employee_name": "Jordan Lee",
            "amount": 3000,
            "currency": "USD",
            "category": "Software",
            "risk_level": "HIGH",
        },
    }


def test_router_without_api_key_signals_mock_fallback(monkeypatch) -> None:
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    router = NotificationRouter()
    assert router.dispatch(notification()) is None


def test_advisory_briefing_reaches_email_and_is_html_escaped():
    router = NotificationRouter()
    payload = notification()
    payload["safe_summary"]["executive_summary"] = "Review <script>alert(1)</script> carefully."
    _, html = router.render_template("APPROVAL_REQUEST", router._template_context(payload))
    assert "AI advisory briefing" in html
    assert "&lt;script&gt;" in html
    assert "<script>" not in html


def test_directory_override_and_unknown_role_fallback(monkeypatch) -> None:
    monkeypatch.setenv(
        "NOTIFICATION_DIRECTORY",
        json.dumps(
            {
                "Finance Director": ["finance@example.com", "audit@example.com"],
                "Direct Manager": "fallback@example.com",
            }
        ),
    )
    router = NotificationRouter()
    assert router.resolve_recipients("Finance Director") == [
        "finance@example.com",
        "audit@example.com",
    ]
    assert router.resolve_recipients("Unknown Role") == ["fallback@example.com"]


def test_invalid_directory_fails_clearly(monkeypatch) -> None:
    monkeypatch.setenv("NOTIFICATION_DIRECTORY", "not-json")
    with pytest.raises(ValueError, match="valid JSON"):
        NotificationRouter()


@pytest.mark.parametrize(
    ("notification_type", "subject_fragment", "body_fragment"),
    [
        ("APPROVAL_REQUEST", "Expense Review Required", "Review Now"),
        ("COMPLETED", "Expense EXP-1", "Expense Decision Completed"),
        ("REMINDER", "awaiting review", "Expense Review Reminder"),
        ("OVERDUE", "awaiting review", "Expense Review Reminder"),
        ("ESCALATION", "exceeded SLA", "Expense SLA Escalation"),
    ],
)
def test_all_notification_templates_render(
    monkeypatch, notification_type: str, subject_fragment: str, body_fragment: str
) -> None:
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    router = NotificationRouter()
    context = router._template_context(notification(notification_type))
    subject, html = router.render_template(notification_type, context)
    assert subject_fragment in subject
    assert body_fragment in html
    assert "EXP-1" in html
    assert "http://localhost:5173/expenses/EXP-1" in html


def test_dispatch_uses_resend_result_and_supports_nested_payload(monkeypatch) -> None:
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    router = NotificationRouter()
    captured: dict = {}

    def fake_send(to: list[str], subject: str, html: str) -> str:
        captured.update(to=to, subject=subject, html=html)
        return "resend-message-1"

    monkeypatch.setattr(router, "send_email", fake_send)
    result = router.dispatch(
        {
            "notification_type": "APPROVAL_REQUEST",
            "target_role": "Department Head",
            "risk_level": "CRITICAL",
            "payload": {
                "expense_id": "EXP-NESTED",
                "employee_name": "Alex Rivera",
                "amount": 900,
                "category": "Travel",
            },
        }
    )

    assert result == {
        "provider_message_id": "resend-message-1",
        "provider_message_ids": {"email": "resend-message-1"},
        "channels": ["email"],
        "recipients": ["head@demo.northstar.local"],
    }
    assert captured["to"] == ["head@demo.northstar.local"]
    assert "CRITICAL" in captured["subject"]
    assert "EXP-NESTED" in captured["html"]


def test_send_email_uses_official_resend_sdk_contract(monkeypatch) -> None:
    import resend

    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    monkeypatch.setenv("NOTIFICATION_FROM_EMAIL", "verified@example.com")
    router = NotificationRouter()
    captured: dict = {}

    def fake_resend_send(params: dict) -> dict[str, str]:
        captured.update(params)
        return {"id": "resend-sdk-message-1"}

    monkeypatch.setattr(resend.Emails, "send", fake_resend_send)

    assert (
        router.send_email(["finance@example.com"], "Review required", "<p>Safe</p>")
        == "resend-sdk-message-1"
    )
    assert resend.api_key == "re_test"
    assert captured == {
        "from": "verified@example.com",
        "to": ["finance@example.com"],
        "subject": "Review required",
        "html": "<p>Safe</p>",
    }


def test_send_slack_posts_professional_block_kit_with_timeout(monkeypatch) -> None:
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.test/services/example")
    router = NotificationRouter()
    captured: dict = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

    def fake_urlopen(request: urllib.request.Request, timeout: int):
        captured["url"] = request.full_url
        captured["method"] = request.get_method()
        captured["content_type"] = request.get_header("Content-type")
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    assert router.send_slack(notification()) == "slack-ok"
    assert captured["url"] == "https://hooks.slack.test/services/example"
    assert captured["method"] == "POST"
    assert captured["content_type"] == "application/json"
    assert captured["timeout"] == 10
    blocks = captured["body"]["blocks"]
    assert [block["type"] for block in blocks] == [
        "header",
        "section",
        "section",
        "actions",
    ]
    assert blocks[0]["text"]["text"] == "🟠 Expense Review Required"
    assert "$3,000.00" in blocks[1]["fields"][1]["text"]
    assert blocks[3]["elements"][0]["url"] == (
        "http://localhost:5173/expenses/EXP-1"
    )


def test_high_risk_dispatches_to_email_and_slack(monkeypatch) -> None:
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.test/services/example")
    router = NotificationRouter()
    monkeypatch.setattr(router, "send_email", lambda *_args: "email-message-1")
    monkeypatch.setattr(router, "send_slack", lambda _notification: "slack-ok")

    assert router.dispatch(notification()) == {
        "provider_message_id": "email-message-1",
        "provider_message_ids": {
            "email": "email-message-1",
            "slack": "slack-ok",
        },
        "channels": ["email", "slack"],
        "recipients": ["finance@demo.northstar.local"],
    }


def test_low_risk_dispatches_to_email_only(monkeypatch) -> None:
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.test/services/example")
    router = NotificationRouter()
    low_risk = notification()
    low_risk["risk_level"] = "LOW"
    low_risk["safe_summary"]["risk_level"] = "LOW"
    monkeypatch.setattr(router, "send_email", lambda *_args: "email-message-1")

    def fail_if_called(_notification: dict) -> str:
        raise AssertionError("LOW risk must not be sent to Slack")

    monkeypatch.setattr(router, "send_slack", fail_if_called)

    assert router.dispatch(low_risk) == {
        "provider_message_id": "email-message-1",
        "provider_message_ids": {"email": "email-message-1"},
        "channels": ["email"],
        "recipients": ["finance@demo.northstar.local"],
    }


@pytest.mark.parametrize("risk_level", ["HIGH", "CRITICAL"])
def test_slack_only_dispatch_for_high_risk(monkeypatch, risk_level: str) -> None:
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.test/services/example")
    router = NotificationRouter()
    high_risk = notification()
    high_risk["risk_level"] = risk_level
    high_risk["safe_summary"]["risk_level"] = risk_level
    monkeypatch.setattr(router, "send_slack", lambda _notification: "slack-ok")

    assert router.dispatch(high_risk) == {
        "provider_message_id": "slack-ok",
        "provider_message_ids": {"slack": "slack-ok"},
        "channels": ["slack"],
        "recipients": [],
    }


@pytest.mark.parametrize("risk_level", ["LOW", "MEDIUM"])
def test_slack_only_falls_back_to_mock_for_lower_risk(
    monkeypatch, risk_level: str
) -> None:
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.test/services/example")
    router = NotificationRouter()
    lower_risk = notification()
    lower_risk["risk_level"] = risk_level
    lower_risk["safe_summary"]["risk_level"] = risk_level

    assert router.dispatch(lower_risk) is None


def test_slack_transport_error_propagates_for_outbox_retry(monkeypatch) -> None:
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.test/services/example")
    router = NotificationRouter()

    def fail_request(_request: urllib.request.Request, timeout: int):
        assert timeout == 10
        raise urllib.error.URLError("Slack unavailable")

    monkeypatch.setattr(urllib.request, "urlopen", fail_request)

    with pytest.raises(urllib.error.URLError, match="Slack unavailable"):
        router.send_slack(notification())
