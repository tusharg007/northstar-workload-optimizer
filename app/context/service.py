"""Deterministic effective-time resolution for governed context."""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path

from app.context.exceptions import ContextConflictError, ContextNotFoundError
from app.context.trust import evaluate_trust
from app.db.base import ensure_utc, utc_now
from app.db.repositories.context import ContextRepository
from app.db.session import Database

PROJECT_DIR = Path(__file__).resolve().parents[2]
RISK_SIGNAL_PATH = PROJECT_DIR / "context" / "risk_signals.json"


class ContextService:
    """Read governed policy and semantic context without affecting decisions."""

    def __init__(self, database: Database) -> None:
        self.database = database
        self.repository = ContextRepository(database)

    def list_policies(self) -> list[dict]:
        return self.repository.list_policies()

    def get_policy(self, policy_key: str) -> dict:
        return self.repository.get_policy(policy_key)

    def policy_versions(self, policy_key: str) -> list[dict]:
        return self.repository.policy_versions(policy_key)

    def list_terms(self) -> list[dict]:
        return self.repository.list_terms()

    def get_term(self, term_key: str) -> dict:
        return self.repository.get_term(term_key)

    def term_versions(self, term_key: str) -> list[dict]:
        return self.repository.term_versions(term_key)

    def get_owner(self, owner_key: str) -> dict:
        return self.repository.get_owner(owner_key)

    @staticmethod
    def _select(rows: list[dict]) -> dict | None:
        certified = [row for row in rows if row["status"] == "CERTIFIED"]
        if len(certified) > 1:
            raise ContextConflictError("Multiple certified versions resolve for the requested time")
        if certified:
            return certified[0]
        if not rows:
            return None
        return max(rows, key=lambda row: row["version_number"])

    def resolve_policy(self, policy_key: str, as_of: datetime | None = None) -> dict:
        point = ensure_utc(as_of) or utc_now()
        summary = self.repository.get_policy(policy_key)
        selected = self._select(self.repository.policy_resolution_rows(policy_key, point))
        if selected is None:
            summary.pop("version_count", None)
            return {
                **summary,
                "as_of": point,
                "trust": {"state": "MISSING", "reasons": ["NO_APPLICABLE_VERSION"], "signals": []},
            }
        signals = selected.pop("signals")
        owner_active = selected.pop("owner_active")
        selected.pop("version_count", None)
        return {
            **selected,
            "as_of": point,
            "trust": evaluate_trust(
                version_status=selected["status"], review_due_at=selected["review_due_at"],
                owner_active=owner_active, signals=signals, as_of=point,
            ),
        }

    def resolve_business_term(self, term_key: str, as_of: datetime | None = None) -> dict:
        point = ensure_utc(as_of) or utc_now()
        summary = self.repository.get_term(term_key)
        selected = self._select(self.repository.term_resolution_rows(term_key, point))
        if selected is None:
            summary.pop("version_count", None)
            return {
                **summary,
                "as_of": point,
                "trust": {"state": "MISSING", "reasons": ["NO_APPLICABLE_VERSION"], "signals": []},
            }
        signals = selected.pop("signals")
        owner_active = selected.pop("owner_active")
        selected.pop("version_count", None)
        return {
            **selected,
            "as_of": point,
            "trust": evaluate_trust(
                version_status=selected["status"], review_due_at=selected["review_due_at"],
                owner_active=owner_active, signals=signals, as_of=point,
            ),
        }

    @staticmethod
    def risk_signal_catalog() -> list[dict]:
        return json.loads(RISK_SIGNAL_PATH.read_text(encoding="utf-8"))["signals"]

    def resolve_expense_context(self, expense_id: str, as_of: datetime | None = None) -> dict:
        from sqlalchemy import select
        from app.db.models import Expense
        with self.database.session() as session:
            row = session.scalar(select(Expense).where(Expense.expense_id == expense_id))
            if row is None:
                raise ContextNotFoundError("Expense not found")
            point = ensure_utc(as_of) or ensure_utc(row.created_at) or utc_now()
            observed_flags = list(((row.processing_result or {}).get("anomaly") or {}).get("flags", []))

        policies = [self.resolve_policy(item["policy_key"], point) for item in self.list_policies()]
        terms = [self.resolve_business_term(item["term_key"], point) for item in self.list_terms()]
        signals = []
        for definition in self.risk_signal_catalog():
            prefix = definition["observed_flag_prefix"]
            signals.append({
                **{key: value for key, value in definition.items() if key != "observed_flag_prefix"},
                "observed_flags": [flag for flag in observed_flags if flag.startswith(prefix)],
            })
        states = [item["trust"]["state"] for item in policies + terms]
        return {
            "expense_id": expense_id,
            "as_of": point,
            "policies": policies,
            "business_terms": terms,
            "trust_summary": {state: states.count(state) for state in sorted(set(states))},
            "risk_signal_definitions": signals,
            "decision_behavior_changed": False,
        }
