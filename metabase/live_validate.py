"""Live Gate 6 validation against pinned Metabase and PostgreSQL."""

from __future__ import annotations

import json
import os
from pathlib import Path
from decimal import Decimal
from numbers import Number

import psycopg
from psycopg import sql

from metabase.client import MetabaseAPIError, MetabaseClient
from metabase.validate import validate

ROOT = Path(__file__).resolve().parent
MARKER = "northstar.logical-key:"


def required(name: str) -> str:
    value = os.getenv(name, "")
    if not value:
        raise RuntimeError(f"Required environment variable {name} is not set")
    return value


def items(body: object) -> list[dict]:
    if isinstance(body, list):
        return body
    if isinstance(body, dict) and isinstance(body.get("data"), list):
        return body["data"]
    raise RuntimeError(f"Expected list response, got {type(body).__name__}")


def logical_key(item: dict) -> str | None:
    description = str(item.get("description") or "")
    token = f"[{MARKER}"
    start = description.find(token)
    if start < 0:
        return None
    start += len(token)
    end = description.find("]", start)
    return description[start:end] if end > start else None


def result_rows(body: dict) -> list[dict]:
    data = body.get("data", {})
    columns = [column.get("name") for column in data.get("cols", [])]
    return [dict(zip(columns, row, strict=True)) for row in data.get("rows", [])]


def pg_rows(connection: psycopg.Connection, query: str) -> list[dict]:
    cursor = connection.execute(query)
    names = [column.name for column in cursor.description or ()]
    return [dict(zip(names, row, strict=True)) for row in cursor.fetchall()]


def normalized(rows: list[dict]) -> list[dict]:
    def value(item: object) -> str | None:
        if item is None:
            return None
        if isinstance(item, Number) and not isinstance(item, bool):
            return format(Decimal(str(item)).normalize(), "f")
        return str(item)

    return sorted(
        [{key: value(item) for key, item in row.items()} for row in rows],
        key=lambda item: json.dumps(item, sort_keys=True),
    )


HEADLINES = {
    "operations.total": "SELECT COUNT(*) AS total_expenses FROM observability.expense_operations",
    "operations.risk": "SELECT COALESCE(risk_level, 'UNCLASSIFIED') AS risk_level, COUNT(*) AS expense_count FROM observability.expense_operations GROUP BY risk_level ORDER BY expense_count DESC",
    "operations.attention_counts": "SELECT (SELECT COUNT(*) FROM observability.approval_sla WHERE status='PENDING') AS approval_backlog, (SELECT COUNT(*) FROM observability.workflow_failures WHERE status='OPEN') AS open_workflow_failures",
    "sla.pending": "SELECT COUNT(*) AS pending_approvals FROM observability.approval_sla WHERE status='PENDING'",
    "sla.overdue": "SELECT COUNT(*) AS overdue_approvals FROM observability.approval_sla WHERE overdue",
    "reliability.pending": "SELECT COUNT(*) AS pending_events FROM observability.reliability_outbox WHERE status='PENDING'",
    "reliability.dead_letter": "SELECT COUNT(*) AS dead_letter_events FROM observability.reliability_outbox WHERE status='DEAD_LETTER'",
    "context.policy_states": "SELECT trust_state, COUNT(*) AS policy_count FROM observability.context_policy_health WHERE is_latest_version GROUP BY trust_state ORDER BY policy_count DESC",
    "trace.decisions": "SELECT COUNT(*) AS decision_count FROM observability.decision_provenance_quality",
    "trace.completeness": "SELECT COUNT(*) FILTER (WHERE structurally_complete) AS structurally_complete, COUNT(*) AS total_decisions, ROUND(100.0 * COUNT(*) FILTER (WHERE structurally_complete) / NULLIF(COUNT(*), 0), 2) AS completeness_percent FROM observability.decision_provenance_quality",
    "trace.triggered": "SELECT COUNT(*) AS triggered_risk_signals FROM observability.risk_signal_activity WHERE triggered",
}


def verify_permissions(admin_dsn: str, role: str, password: str) -> list[str]:
    dsn = admin_dsn.replace("postgresql+psycopg://", "postgresql://", 1)
    parameters = psycopg.conninfo.conninfo_to_dict(dsn)
    parameters.update(user=role, password=password)
    denied: list[str] = []
    with psycopg.connect(**parameters, autocommit=True) as connection:
        connection.execute("SELECT count(*) FROM observability.expense_operations").fetchone()
        statements = {
            "SELECT_BASE": "SELECT count(*) FROM expenses",
            "INSERT": "INSERT INTO expenses (expense_id) VALUES ('gate6-denied')",
            "UPDATE": "UPDATE expenses SET status='DENIED'",
            "DELETE": "DELETE FROM expenses",
            "TRUNCATE": "TRUNCATE expenses",
            "CREATE": "CREATE TABLE gate6_denied (id integer)",
            "ALTER": "ALTER TABLE expenses ADD COLUMN gate6_denied integer",
        }
        for label, statement in statements.items():
            try:
                connection.execute(statement)
            except psycopg.errors.InsufficientPrivilege:
                denied.append(label)
            else:
                raise RuntimeError(f"read-only principal unexpectedly allowed {label}")
    return denied


def main() -> int:
    try:
        static_errors = validate()
        if static_errors:
            raise RuntimeError("static validation failed: " + "; ".join(static_errors))
        manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
        client = MetabaseClient(os.getenv("METABASE_URL", "http://localhost:3000"))
        client.login(os.getenv("METABASE_ADMIN_EMAIL", "admin@northstar.local"), required("METABASE_ADMIN_PASSWORD"))
        properties = client.setup_properties()
        version = properties.get("version")
        cards = {logical_key(item): item for item in items(client.get("/api/card?f=all")) if logical_key(item)}
        dashboards = {logical_key(item): item for item in items(client.get("/api/dashboard")) if logical_key(item)}
        expected_question_keys = {item["key"] for item in manifest["questions"]}
        expected_dashboard_keys = {item["key"] for item in manifest["dashboards"]}
        if set(cards) != expected_question_keys or set(dashboards) != expected_dashboard_keys:
            raise RuntimeError("live logical inventory does not match manifest")
        results: dict[str, list[dict]] = {}
        for key, card in cards.items():
            results[key] = result_rows(client.post(f"/api/card/{card['id']}/query", {"parameters": []}))
        attachment_counts: dict[str, int] = {}
        for key, dashboard in dashboards.items():
            full = client.get(f"/api/dashboard/{dashboard['id']}")
            attachment_counts[key] = len(full.get("dashcards", []))
        expected_counts = {item["key"]: len(item["cards"]) for item in manifest["dashboards"]}
        if attachment_counts != expected_counts:
            raise RuntimeError(f"dashboard attachment mismatch: {attachment_counts} != {expected_counts}")
        admin_dsn = required("NORTHSTAR_DATABASE_URL")
        comparisons: dict[str, int] = {}
        with psycopg.connect(admin_dsn.replace("postgresql+psycopg://", "postgresql://", 1)) as connection:
            for key, query in HEADLINES.items():
                actual, expected = normalized(results[key]), normalized(pg_rows(connection, query))
                if actual != expected:
                    raise RuntimeError(f"headline mismatch for {key}: Metabase={actual}, PostgreSQL={expected}")
                comparisons[key] = len(actual)
        denied = verify_permissions(
            admin_dsn,
            os.getenv("NORTHSTAR_METABASE_DB_USER", "northstar_metabase_ro"),
            required("NORTHSTAR_METABASE_DB_PASSWORD"),
        )
        print(json.dumps({
            "status": "PASS", "metabase_version": version,
            "question_count": len(cards), "dashboard_count": len(dashboards),
            "dashboard_cards": attachment_counts, "questions_executed": len(results),
            "headline_comparisons": comparisons, "permission_denials": denied,
        }, sort_keys=True, default=str))
        return 0
    except (MetabaseAPIError, RuntimeError, psycopg.Error, ValueError) as exc:
        print(f"FAIL: live Metabase validation: {exc}")
        return 1
    finally:
        if "client" in locals():
            client.close()


if __name__ == "__main__":
    raise SystemExit(main())
