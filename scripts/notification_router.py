"""Route safe North Star notification payloads to configured providers."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import jinja2


DEFAULT_DIRECTORY: dict[str, str | list[str]] = {
    "Direct Manager": "manager@demo.northstar.local",
    "Department Head": "head@demo.northstar.local",
    "Finance Director": "finance@demo.northstar.local",
    "Finance Director + Compliance": "finance@demo.northstar.local",
    "VP / C-Suite": "vp@demo.northstar.local",
}

TEMPLATE_MAP = {
    "APPROVAL_REQUEST": "approval_request.html",
    "COMPLETED": "approval_completed.html",
    "REMINDER": "sla_reminder.html",
    "OVERDUE": "sla_reminder.html",
    "ESCALATION": "sla_escalation.html",
}

SUBJECT_MAP = {
    "APPROVAL_REQUEST": "🔔 [{{ risk_level }}] Expense Review Required — {{ amount }} {{ category }}",
    "COMPLETED": "✅ Expense {{ expense_id }} — {{ decision }}",
    "REMINDER": "⏰ Reminder: Expense {{ expense_id }} awaiting review",
    "OVERDUE": "⏰ Reminder: Expense {{ expense_id }} awaiting review",
    "ESCALATION": "🚨 ESCALATED: Expense {{ expense_id }} exceeded SLA",
}

RISK_COLORS = {
    "LOW": "#15803d",
    "MEDIUM": "#b45309",
    "HIGH": "#c2410c",
    "CRITICAL": "#b91c1c",
}


class NotificationRouter:
    """Route notifications to configured providers with a mock fallback."""

    def __init__(self) -> None:
        self.resend_api_key = os.environ.get("RESEND_API_KEY")
        self.slack_webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
        self.from_email = os.environ.get(
            "NOTIFICATION_FROM_EMAIL", "expenses@northstar.local"
        )
        self.frontend_url = os.environ.get(
            "FRONTEND_URL", "http://localhost:5173"
        ).rstrip("/")
        templates = Path(__file__).resolve().with_name("templates")
        self.jinja_env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(templates),
            autoescape=jinja2.select_autoescape(["html", "xml"]),
        )
        self.directory = self._load_directory()

    @staticmethod
    def _load_directory() -> dict[str, str | list[str]]:
        raw = os.environ.get("NOTIFICATION_DIRECTORY")
        if not raw:
            return dict(DEFAULT_DIRECTORY)
        try:
            configured = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError("NOTIFICATION_DIRECTORY must be valid JSON") from exc
        if not isinstance(configured, dict):
            raise ValueError("NOTIFICATION_DIRECTORY must be a JSON object")

        directory = dict(DEFAULT_DIRECTORY)
        for role, entry in configured.items():
            if not isinstance(role, str) or not role.strip():
                raise ValueError("NOTIFICATION_DIRECTORY roles must be non-empty strings")
            if isinstance(entry, str) and entry.strip():
                directory[role] = entry
            elif (
                isinstance(entry, list)
                and entry
                and all(isinstance(address, str) and address.strip() for address in entry)
            ):
                directory[role] = entry
            else:
                raise ValueError(
                    "NOTIFICATION_DIRECTORY values must be an email or non-empty email list"
                )
        return directory

    def resolve_recipients(self, target_role: str) -> list[str]:
        """Map a target role to one or more configured email addresses."""
        entry = self.directory.get(target_role, self.directory["Direct Manager"])
        return [entry] if isinstance(entry, str) else list(entry)

    @staticmethod
    def _notification_type(notification: dict[str, Any]) -> str:
        return str(
            notification.get("notification_type")
            or notification.get("type")
            or "APPROVAL_REQUEST"
        ).upper()

    def _template_context(self, notification: dict[str, Any]) -> dict[str, Any]:
        nested_payload = notification.get("payload")
        safe_summary = notification.get("safe_summary")
        context: dict[str, Any] = {}
        if isinstance(safe_summary, dict):
            context.update(safe_summary)
        if isinstance(nested_payload, dict):
            context.update(nested_payload)

        for key in (
            "expense_id",
            "risk_level",
            "target_role",
            "approver_role",
            "due_at",
            "status",
        ):
            if context.get(key) in (None, "") and notification.get(key) not in (
                None,
                "",
            ):
                context[key] = notification[key]

        risk_level = str(context.get("risk_level") or "UNKNOWN").upper()
        raw_decision = str(context.get("decision") or "Completed")
        context.update(
            {
                "frontend_url": self.frontend_url,
                "risk_level": risk_level,
                "risk_color": RISK_COLORS.get(risk_level, "#4b5563"),
                "target_role": context.get("target_role")
                or notification.get("target_role")
                or "Direct Manager",
                "decision": raw_decision.replace("_", " ").title(),
                "reviewer_name": context.get("reviewer_name")
                or context.get("approver")
                or notification.get("target_role")
                or "Not provided",
                "decision_comment": context.get("decision_comment")
                or context.get("comment")
                or "No comment provided",
                "decision_timestamp": context.get("decision_timestamp")
                or context.get("decided_at")
                or context.get("timestamp")
                or "Not provided",
                "new_reviewer_role": context.get("new_reviewer_role")
                or notification.get("target_role")
                or "Not provided",
                "anomaly_flags": context.get("anomaly_flags") or [],
            }
        )
        return context

    def render_template(
        self, notification_type: str, context: dict[str, Any]
    ) -> tuple[str, str]:
        """Return the rendered subject and HTML body for a notification."""
        normalized_type = notification_type.upper()
        template_name = TEMPLATE_MAP.get(normalized_type, "approval_request.html")
        subject_template = SUBJECT_MAP.get(
            normalized_type, SUBJECT_MAP["APPROVAL_REQUEST"]
        )
        subject = jinja2.Template(subject_template, autoescape=False).render(**context)
        html = self.jinja_env.get_template(template_name).render(**context)
        return subject, html

    def send_email(self, to: list[str], subject: str, html: str) -> str:
        """Send one email through Resend and return its provider message ID."""
        import resend

        resend.api_key = self.resend_api_key
        result = resend.Emails.send(
            {
                "from": self.from_email,
                "to": to,
                "subject": subject,
                "html": html,
            }
        )
        provider_id = (
            result.get("id") if isinstance(result, dict) else getattr(result, "id", None)
        )
        if not provider_id:
            raise RuntimeError("Resend response did not contain a message ID")
        return str(provider_id)

    def send_slack(self, notification: dict[str, Any]) -> str:
        """Send a Slack Block Kit message through an incoming webhook."""
        import urllib.request

        if not self.slack_webhook_url:
            raise RuntimeError("SLACK_WEBHOOK_URL is not configured")

        context = self._template_context(notification)
        risk_level = str(context.get("risk_level") or "LOW").upper()
        if risk_level == "UNKNOWN":
            risk_level = "LOW"
        risk_emoji = {
            "CRITICAL": "🔴",
            "HIGH": "🟠",
            "MEDIUM": "🟡",
            "LOW": "🟢",
        }.get(risk_level, "⚪")
        raw_amount = context.get("amount", 0)
        try:
            amount = f"${float(raw_amount):,.2f}"
        except (TypeError, ValueError):
            amount = str(raw_amount or "N/A")

        nested_payload = notification.get("payload")
        nested_summary = (
            nested_payload.get("safe_summary", "")
            if isinstance(nested_payload, dict)
            else ""
        )
        summary = nested_summary if isinstance(nested_summary, str) else ""
        if not summary:
            summary = str(context.get("routing_reason") or "")

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{risk_emoji} Expense Review Required",
                },
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Employee:*\n{context.get('employee_name') or 'N/A'}",
                    },
                    {"type": "mrkdwn", "text": f"*Amount:*\n{amount}"},
                    {
                        "type": "mrkdwn",
                        "text": f"*Risk:*\n{risk_emoji} {risk_level}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Category:*\n{context.get('category') or 'N/A'}",
                    },
                ],
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*Routing:* {notification.get('target_role') or context.get('target_role') or 'N/A'}"
                        f"\n{summary}"
                    ).rstrip(),
                },
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Review in Dashboard"},
                        "url": f"{self.frontend_url}/expenses/{context.get('expense_id') or ''}",
                        "style": "primary",
                    }
                ],
            },
        ]
        data = json.dumps({"blocks": blocks}).encode("utf-8")
        request = urllib.request.Request(
            self.slack_webhook_url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=10):
            pass
        return "slack-ok"

    def dispatch(self, notification: dict[str, Any]) -> dict[str, Any] | None:
        """Send through available risk-appropriate channels or use mock fallback."""
        notification_type = self._notification_type(notification)
        context = self._template_context(notification)
        risk_level = str(context.get("risk_level") or "LOW").upper()
        if risk_level == "UNKNOWN":
            risk_level = "LOW"
        channels: list[str] = []
        recipients: list[str] = []
        provider_ids: dict[str, str] = {}

        if self.resend_api_key:
            recipients = self.resolve_recipients(
                str(notification.get("target_role") or context.get("target_role") or "")
            )
            subject, html = self.render_template(notification_type, context)
            provider_ids["email"] = self.send_email(recipients, subject, html)
            channels.append("email")

        if risk_level in {"HIGH", "CRITICAL"} and self.slack_webhook_url:
            provider_ids["slack"] = self.send_slack(notification)
            channels.append("slack")

        if not channels:
            return None

        return {
            "provider_message_id": provider_ids[channels[0]],
            "provider_message_ids": provider_ids,
            "channels": channels,
            "recipients": recipients,
        }
