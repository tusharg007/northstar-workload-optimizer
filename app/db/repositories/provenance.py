"""Append-only persistence and verification for decision evidence."""

from __future__ import annotations

from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import utc_now
from app.db.models import (
    ApprovalDecision, ApprovalTask, DecisionHumanEvidence, DecisionPolicyEvidence,
    DecisionProvenance, DecisionRiskEvidence, DecisionRuleEvidence,
    DecisionTermEvidence, DecisionTrustEvidence, Expense, OutboxEvent,
    WorkflowEvent, WorkflowRun,
)
from app.db.session import Database
from app.provenance.hashing import evidence_hash, provenance_hash


def _id(kind: str, key: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"northstar-provenance:{kind}:{key}"))


def _state(row) -> dict:
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


class ProvenanceRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    @staticmethod
    def persist_automated(session: Session, bundle: dict) -> str:
        header = bundle["header"]
        provenance_id = _id("automated", header["workflow_run_id"])
        session.add(DecisionProvenance(provenance_id=provenance_id, **header))
        session.flush()
        for index, row in enumerate(bundle["policies"]):
            session.add(DecisionPolicyEvidence(evidence_id=_id("policy", f"{provenance_id}:{index}"), provenance_id=provenance_id, created_at=utc_now(), **row))
        for index, row in enumerate(bundle["terms"]):
            session.add(DecisionTermEvidence(evidence_id=_id("term", f"{provenance_id}:{index}"), provenance_id=provenance_id, created_at=utc_now(), **row))
        for index, row in enumerate(bundle["rules"]):
            session.add(DecisionRuleEvidence(evidence_id=_id("rule", f"{provenance_id}:{index}"), provenance_id=provenance_id, created_at=utc_now(), **row))
        for index, row in enumerate(bundle["trust"]):
            session.add(DecisionTrustEvidence(evidence_id=_id("trust", f"{provenance_id}:{index}"), provenance_id=provenance_id, created_at=utc_now(), **row))
        for index, row in enumerate(bundle["risk"]):
            session.add(DecisionRiskEvidence(evidence_id=_id("risk", f"{provenance_id}:{index}"), provenance_id=provenance_id, created_at=utc_now(), **row))
        session.flush()
        return provenance_id

    @staticmethod
    def add_human_evidence(session: Session, provenance_id: str, decision: ApprovalDecision) -> str:
        snapshot = {
            "decision": decision.decision, "decided_by": decision.decided_by,
            "comment": decision.comment, "decided_at": decision.decided_at,
        }
        human_id = _id("human", decision.decision_id)
        session.add(DecisionHumanEvidence(
            human_evidence_id=human_id, provenance_id=provenance_id,
            approval_decision_id=decision.decision_id, evidence_hash=evidence_hash(snapshot),
            created_at=utc_now(), **snapshot,
        ))
        session.flush()
        return human_id

    def by_expense(self, expense_id: str) -> dict | None:
        with self.database.session() as session:
            row = session.scalar(select(DecisionProvenance).where(DecisionProvenance.expense_id == expense_id))
            return self._complete(session, row) if row else None

    def by_id(self, provenance_id: str) -> dict | None:
        with self.database.session() as session:
            row = session.get(DecisionProvenance, provenance_id)
            return self._complete(session, row) if row else None

    @staticmethod
    def _complete(session: Session, row: DecisionProvenance) -> dict:
        provenance_id = row.provenance_id
        result = _state(row)
        result["policies"] = [_state(item) for item in session.scalars(select(DecisionPolicyEvidence).where(DecisionPolicyEvidence.provenance_id == provenance_id).order_by(DecisionPolicyEvidence.policy_key)).all()]
        result["terms"] = [_state(item) for item in session.scalars(select(DecisionTermEvidence).where(DecisionTermEvidence.provenance_id == provenance_id).order_by(DecisionTermEvidence.term_key)).all()]
        result["rules"] = [_state(item) for item in session.scalars(select(DecisionRuleEvidence).where(DecisionRuleEvidence.provenance_id == provenance_id).order_by(DecisionRuleEvidence.rule_key)).all()]
        result["trust"] = [_state(item) for item in session.scalars(select(DecisionTrustEvidence).where(DecisionTrustEvidence.provenance_id == provenance_id).order_by(DecisionTrustEvidence.target_key, DecisionTrustEvidence.signal_type)).all()]
        result["risk"] = [_state(item) for item in session.scalars(select(DecisionRiskEvidence).where(DecisionRiskEvidence.provenance_id == provenance_id).order_by(DecisionRiskEvidence.signal_key)).all()]
        result["human_decisions"] = [_state(item) for item in session.scalars(select(DecisionHumanEvidence).where(DecisionHumanEvidence.provenance_id == provenance_id).order_by(DecisionHumanEvidence.decided_at)).all()]
        return result

    def trace(self, expense_id: str) -> dict:
        with self.database.session() as session:
            expense = session.scalar(select(Expense).where(Expense.expense_id == expense_id))
            if expense is None:
                raise KeyError("Expense not found")
            provenance = session.scalar(select(DecisionProvenance).where(DecisionProvenance.expense_id == expense_id))
            if provenance is None:
                return {"expense_id": expense_id, "provenance_status": "LEGACY_UNAVAILABLE", "final_status": expense.status}
            run = session.get(WorkflowRun, provenance.workflow_run_id)
            task = session.scalar(select(ApprovalTask).where(ApprovalTask.workflow_run_id == provenance.workflow_run_id))
            decision = session.scalar(select(ApprovalDecision).where(ApprovalDecision.workflow_run_id == provenance.workflow_run_id))
            complete = self._complete(session, provenance)
            return {
                "expense_id": expense_id, "provenance_status": "AVAILABLE",
                "input": {"payload": expense.input_payload, "source_payload_hash": provenance.source_payload_hash, "transaction_date": expense.transaction_date},
                "workflow_run": _state(run) if run else None, "context": {"as_of": provenance.context_as_of, "resolved_at": provenance.context_resolved_at, "trust_state": provenance.context_trust_state},
                "policies": complete["policies"], "business_terms": complete["terms"], "rule_evaluations": complete["rules"], "trust_evidence": complete["trust"],
                "risk_engine": {"version": provenance.risk_engine_version, "catalog_hash": provenance.risk_catalog_hash, "signals": complete["risk"]},
                "automated_outcome": {"status": provenance.automated_status, "risk_level": provenance.risk_level, "approver_role": provenance.approver_role, "reason": provenance.automated_reason, "decision_engine_version": provenance.decision_engine_version},
                "approval_task": _state(task) if task else None, "approval_decision": _state(decision) if decision else None,
                "human_evidence": complete["human_decisions"], "final_status": expense.status,
                "provenance_id": provenance.provenance_id, "provenance_hash": provenance.provenance_hash,
            }

    def lineage(self, expense_id: str) -> dict:
        """Return a safe timeline composed only from persisted records."""
        with self.database.session() as session:
            expense = session.scalar(select(Expense).where(Expense.expense_id == expense_id))
            if expense is None:
                raise KeyError("Expense not found")
            run = session.scalar(
                select(WorkflowRun)
                .where(WorkflowRun.expense_id == expense_id)
                .order_by(WorkflowRun.created_at.desc())
            )
            if run is None:
                raise KeyError("Workflow run not found")
            events = [
                {
                    "source": "workflow",
                    "event_type": item.event_type,
                    "timestamp": item.created_at,
                    "status": None,
                    "sequence": item.sequence_number,
                }
                for item in session.scalars(
                    select(WorkflowEvent)
                    .where(WorkflowEvent.workflow_run_id == run.id)
                    .order_by(WorkflowEvent.sequence_number)
                ).all()
            ]
            provenance = session.scalar(
                select(DecisionProvenance).where(DecisionProvenance.workflow_run_id == run.id)
            )
            if provenance is not None:
                events.append({
                    "source": "provenance", "event_type": "DECISION_PROVENANCE_RECORDED",
                    "timestamp": provenance.created_at, "status": provenance.context_trust_state,
                    "sequence": None,
                })
            decision = session.scalar(
                select(ApprovalDecision).where(ApprovalDecision.workflow_run_id == run.id)
            )
            if decision is not None:
                events.append({
                    "source": "approval", "event_type": "HUMAN_DECISION_RECORDED",
                    "timestamp": decision.decided_at, "status": decision.decision.upper(),
                    "sequence": None,
                })
            for item in session.scalars(
                select(OutboxEvent)
                .where(OutboxEvent.correlation_id == run.correlation_id)
                .order_by(OutboxEvent.created_at)
            ).all():
                events.append({
                    "source": "outbox", "event_type": item.event_type,
                    "timestamp": item.created_at, "status": item.status, "sequence": None,
                })
            events.sort(key=lambda item: (item["timestamp"], item["sequence"] or 0, item["event_type"]))
            return {
                "expense_id": expense_id,
                "correlation_id": run.correlation_id,
                "workflow_run_id": run.id,
                "events": events,
            }

    def verify(self, provenance_id: str) -> dict:
        complete = self.by_id(provenance_id)
        if complete is None:
            raise KeyError("Decision provenance not found")
        evidence_specs = {
            "policies": ("snapshot_hash", ("policy_id", "policy_version_id", "policy_key", "policy_name", "version_number", "content_hash", "owner_key", "owner_display_name", "status", "effective_from", "effective_to", "trust_state")),
            "terms": ("snapshot_hash", ("business_term_id", "business_term_version_id", "term_key", "canonical_name", "definition", "version_number", "content_hash", "owner_key", "trust_state")),
            "rules": ("evidence_hash", ("policy_version_id", "policy_rule_id", "rule_key", "rule_name", "rule_type", "severity", "parameters", "evaluation_status", "triggered", "observed_value", "evaluation_details")),
            "trust": ("evidence_hash", ("trust_signal_id", "target_type", "target_key", "signal_type", "signal_status", "observed_at", "expires_at", "source", "details")),
            "risk": ("evidence_hash", ("signal_key", "canonical_name", "engine_component", "triggered", "observed_value", "threshold_or_reference", "details", "signal_definition_hash", "risk_catalog_hash")),
        }
        failures = []
        compact: dict[str, list[dict]] = {}
        for section, (hash_field, fields) in evidence_specs.items():
            compact[section] = complete[section]
            for row in complete[section]:
                if evidence_hash({key: row[key] for key in fields}) != row[hash_field]:
                    failures.append(f"{section}:{row.get('evidence_id')}")
        header = {key: complete[key] for key in (
            "source_payload_hash", "workflow_run_id", "correlation_id", "context_as_of",
            "automated_status", "risk_level", "approver_role", "automated_reason",
            "context_trust_state", "decision_engine_version", "risk_engine_version",
            "risk_catalog_hash", "build_revision",
        )}
        recomputed = provenance_hash(header, compact)
        if recomputed != complete["provenance_hash"]:
            failures.append("provenance_hash")
        for row in complete["human_decisions"]:
            human = {key: row[key] for key in ("decision", "decided_by", "comment", "decided_at")}
            if evidence_hash(human) != row["evidence_hash"]:
                failures.append(f"human:{row['human_evidence_id']}")
        return {"provenance_id": provenance_id, "status": "PASS" if not failures else "FAIL", "stored_hash": complete["provenance_hash"], "recomputed_hash": recomputed, "failures": failures}
