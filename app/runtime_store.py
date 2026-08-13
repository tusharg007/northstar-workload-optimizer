"""Backward-compatible facade over SQLAlchemy operational repositories."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable
from uuid import uuid4

from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url

from app.db.repositories.workflows import ProcessOutcome, WorkflowRepository
from app.db.repositories.orchestration import ApprovalOrchestrationRepository
from app.db.repositories.reliability import OutboxRepository
from app.db.repositories.provenance import ProvenanceRepository
from app.context.service import ContextService
from app.context.binding import bind_policies, safety_reason
from app.context.exceptions import ContextConflictError, ContextNotFoundError, ContextSafetyError
from app.context.seed import apply_seed, load_seed
from automation.policy_manifest import policy_execution_manifest
from app.db.session import Database, normalize_database_url


class RuntimeStore:
    """Preserve the Gate 0 store API while using SQLAlchemy exclusively."""

    def __init__(self, database_url: str | Path | None = None) -> None:
        resolved = normalize_database_url(database_url)
        is_sqlite = make_url(resolved).get_backend_name() == "sqlite"
        self.database = Database(resolved, create_schema=is_sqlite)
        self.repository = WorkflowRepository(self.database)
        self.orchestration = ApprovalOrchestrationRepository(self.database)
        self.outbox = OutboxRepository(self.database)
        self.context = ContextService(self.database)
        self.provenance = ProvenanceRepository(self.database)
        self.db_path = Path(make_url(resolved).database) if is_sqlite else None
        if is_sqlite:
            seed_path = Path(__file__).resolve().parents[1] / "context" / "registry.seed.json"
            apply_seed(self.database, load_seed(seed_path), write=True)
            self._bootstrap_legacy_rows()

    def _bootstrap_legacy_rows(self) -> None:
        """Copy legacy materialized rows once while preserving their source table."""
        if "runtime_expenses" not in inspect(self.database.engine).get_table_names():
            return
        with self.database.session() as session:
            rows = [
                dict(row)
                for row in session.execute(
                    text("SELECT * FROM runtime_expenses ORDER BY created_at")
                ).mappings()
            ]
        if not rows:
            return
        for row in rows:
            row["input_payload"] = json.loads(row["input_payload"])
            row["result"] = json.loads(row["result"])
        self.repository.import_legacy_rows(rows)

    def process(
        self,
        input_payload: dict,
        processor: Callable[[dict], dict],
        *,
        idempotency_key: str | None = None,
        correlation_id: str | None = None,
        source_system: str = "api",
    ) -> ProcessOutcome:
        correlation = correlation_id or str(uuid4())
        context_bundle: dict = {}

        def governed_processor(payload: dict) -> dict:
            from app.db.base import utc_now

            point = utc_now()
            policies = []
            conflict = False
            for policy_key in policy_execution_manifest():
                try:
                    policies.append(self.context.resolve_policy(policy_key, point))
                except ContextNotFoundError:
                    continue
                except ContextConflictError:
                    conflict = True
            binding = {"state": "CONFLICTED", "policies": []} if conflict else bind_policies(policies)
            if binding["state"] != "MATCHED":
                reason_code, safe_reason = safety_reason(binding["state"])
                raise ContextSafetyError(reason_code, safe_reason, correlation)

            term_keys = sorted({
                rule["business_term_key"]
                for policy in policies for rule in policy.get("rules", [])
                if rule.get("business_term_key")
            })
            terms = []
            for term_key in term_keys:
                try:
                    term = self.context.resolve_business_term(term_key, point)
                except (ContextNotFoundError, ContextConflictError):
                    raise ContextSafetyError("POLICY_UNTRUSTED", "Required governed business definition is not authoritative.", correlation)
                if term["trust"]["state"] != "TRUSTED":
                    raise ContextSafetyError("POLICY_UNTRUSTED", "Required governed business definition is not trusted and current.", correlation)
                terms.append(term)
            context_bundle.update({"context_as_of": point, "policies": policies, "terms": terms})
            return processor(payload)

        return self.repository.process_expense(
            input_payload,
            governed_processor,
            idempotency_key=idempotency_key,
            correlation_id=correlation,
            source_system=source_system,
            context_bundle=context_bundle,
        )

    def upsert(
        self,
        expense_id: str,
        input_payload: dict,
        result: dict,
        status: str,
        risk_level: str | None,
        approver_role: str | None,
    ) -> dict:
        """Compatibility adapter for callers of the former sqlite3 store."""
        stored_result = {
            **result,
            "status": status,
            "anomaly": result.get("anomaly")
            or ({"risk_level": risk_level, "flags": []} if risk_level else None),
            "decision": result.get("decision")
            or (
                {"approver_role": approver_role, "approver_level": 0}
                if approver_role
                else None
            ),
        }
        payload = {**input_payload, "expense_id": expense_id}
        # Compatibility imports did not execute the governed engine, so do not
        # manufacture Gate 4B provenance for them.
        return self.repository.process_expense(payload, lambda _: stored_result).state

    def get(self, expense_id: str) -> dict | None:
        return self.repository.get(expense_id)

    def list(self, status: str | None = None) -> list[dict]:
        return self.repository.list(status)

    def update_decision(
        self,
        expense_id: str,
        decision: str,
        approver: str,
        comment: str,
    ) -> dict | None:
        return self.repository.decide(expense_id, decision, approver, comment)
