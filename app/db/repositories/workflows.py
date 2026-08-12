"""Transactional workflow persistence and idempotency semantics."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Callable
from uuid import NAMESPACE_URL, uuid4, uuid5

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.base import utc_now
from app.db.models import (
    ApprovalDecision,
    ApprovalTask,
    Expense,
    WorkflowEvent,
    WorkflowRun,
)
from app.db.repositories.approvals import ApprovalRepository
from app.db.repositories.expenses import ExpenseRepository
from app.db.session import Database


class IdempotencyConflictError(Exception):
    """An idempotency key was reused with different input."""


class ExpenseConflictError(Exception):
    """An expense business ID was reused with materially different input."""


class DecisionConflictError(Exception):
    """A completed approval was called again with a different decision."""


@dataclass(frozen=True)
class ProcessOutcome:
    state: dict
    correlation_id: str
    replayed: bool


@dataclass(frozen=True)
class LegacyImportOutcome:
    imported: int
    skipped: int


def canonical_payload_hash(payload: dict) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def derived_idempotency_key(expense_id: str, payload_hash: str) -> str:
    return f"api:{expense_id}:{payload_hash}"


class WorkflowRepository:
    """Owns atomic processing and approval transactions."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def process_expense(
        self,
        payload: dict,
        processor: Callable[[dict], dict],
        *,
        idempotency_key: str | None = None,
        correlation_id: str | None = None,
        source_system: str = "api",
    ) -> ProcessOutcome:
        payload_hash = canonical_payload_hash(payload)
        key = idempotency_key or derived_idempotency_key(
            payload["expense_id"], payload_hash
        )
        replay = self._find_replay(key, payload["expense_id"], payload_hash)
        if replay is not None:
            return replay

        result = processor(payload)
        correlation = correlation_id or str(uuid4())
        try:
            return self._commit_processing(
                payload,
                result,
                payload_hash=payload_hash,
                idempotency_key=key,
                correlation_id=correlation,
                source_system=source_system,
            )
        except IntegrityError:
            replay = self._find_replay(key, payload["expense_id"], payload_hash)
            if replay is not None:
                return replay
            raise

    def _find_replay(
        self, idempotency_key: str, expense_id: str, payload_hash: str
    ) -> ProcessOutcome | None:
        with self.database.session() as session:
            run = session.scalar(
                select(WorkflowRun).where(
                    WorkflowRun.idempotency_key == idempotency_key
                )
            )
            if run is not None:
                expense = ExpenseRepository(session).get(run.expense_id)
                if (
                    expense is None
                    or run.expense_id != expense_id
                    or expense.payload_hash != payload_hash
                ):
                    raise IdempotencyConflictError(
                        "Idempotency-Key was already used with a different payload"
                    )
                return ProcessOutcome(
                    ExpenseRepository.to_state(expense), run.correlation_id, True
                )

            expense = ExpenseRepository(session).get(expense_id)
            if expense is None:
                return None
            if expense.payload_hash != payload_hash:
                raise ExpenseConflictError(
                    "expense_id was already processed with a different payload"
                )
            existing_run = session.scalar(
                select(WorkflowRun)
                .where(WorkflowRun.expense_id == expense_id)
                .order_by(WorkflowRun.created_at.asc())
            )
            return ProcessOutcome(
                ExpenseRepository.to_state(expense),
                existing_run.correlation_id if existing_run else str(uuid4()),
                True,
            )

    def _commit_processing(
        self,
        payload: dict,
        result: dict,
        *,
        payload_hash: str,
        idempotency_key: str,
        correlation_id: str,
        source_system: str,
    ) -> ProcessOutcome:
        now = utc_now()
        anomaly = result.get("anomaly") or {}
        decision = result.get("decision") or {}
        with self.database.transaction() as session:
            expense = Expense(
                expense_id=payload["expense_id"],
                employee_id=payload.get("employee_id", ""),
                employee_name=payload.get("employee_name", ""),
                department=payload.get("department", ""),
                transaction_date=date.fromisoformat(
                    payload.get("transaction_date", "1970-01-01")
                ),
                merchant=payload.get("merchant", ""),
                category=payload.get("category", ""),
                description=payload.get("description", ""),
                amount=Decimal(str(payload.get("amount", 0))),
                currency=payload.get("currency", "USD"),
                payment_method=payload.get("payment_method", ""),
                receipt_attached=bool(payload.get("receipt_attached", False)),
                input_payload=payload,
                processing_result=result,
                status=result["status"],
                risk_level=anomaly.get("risk_level"),
                approver_role=decision.get("approver_role"),
                payload_hash=payload_hash,
                created_at=now,
                updated_at=now,
            )
            session.add(expense)
            session.flush()

            run = WorkflowRun(
                id=str(uuid4()),
                correlation_id=correlation_id,
                expense_id=expense.expense_id,
                idempotency_key=idempotency_key,
                source_system=source_system,
                status=result["status"],
                started_at=now,
                completed_at=now,
                created_at=now,
                updated_at=now,
            )
            session.add(run)
            session.flush()
            self._add_processing_events(session, run, result, now)

            if result["status"] in {"PENDING_APPROVAL", "ESCALATED"}:
                session.add(
                    ApprovalTask(
                        task_id=str(uuid4()),
                        expense_id=expense.expense_id,
                        workflow_run_id=run.id,
                        approver_role=decision.get("approver_role") or "Unassigned",
                        approval_level=int(decision.get("approver_level") or 0),
                        status="PENDING",
                        created_at=now,
                        updated_at=now,
                    )
                )
            session.flush()
            state = ExpenseRepository.to_state(expense)
        return ProcessOutcome(state, correlation_id, False)

    def _add_processing_events(
        self,
        session: Session,
        run: WorkflowRun,
        result: dict,
        created_at,
    ) -> None:
        events: list[tuple[str, dict]] = [
            ("EXPENSE_RECEIVED", {"source_system": run.source_system}),
            ("VALIDATION_COMPLETED", result.get("validation") or {}),
        ]
        if result.get("anomaly") is not None:
            events.append(("RISK_EVALUATED", result["anomaly"]))
        if result.get("decision") is not None:
            events.append(("APPROVAL_ROUTED", result["decision"]))
        if result["status"] == "AUTO_APPROVED":
            events.append(("AUTO_APPROVED", {}))
        elif result["status"] in {"PENDING_APPROVAL", "ESCALATED"}:
            events.append(
                (
                    "APPROVAL_REQUIRED",
                    {
                        "approver_role": (result.get("decision") or {}).get(
                            "approver_role"
                        ),
                        "status": result["status"],
                    },
                )
            )
        for sequence, (event_type, event_payload) in enumerate(events, start=1):
            session.add(
                WorkflowEvent(
                    workflow_run_id=run.id,
                    expense_id=run.expense_id,
                    event_type=event_type,
                    sequence_number=sequence,
                    payload=event_payload,
                    created_at=created_at,
                )
            )

    def get(self, expense_id: str) -> dict | None:
        with self.database.session() as session:
            expense = ExpenseRepository(session).get(expense_id)
            return ExpenseRepository.to_state(expense) if expense else None

    def list(self, status: str | None = None) -> list[dict]:
        with self.database.session() as session:
            return [
                ExpenseRepository.to_state(expense)
                for expense in ExpenseRepository(session).list(status)
            ]

    def decide(
        self, expense_id: str, decision: str, approver: str, comment: str
    ) -> dict | None:
        now = utc_now()
        with self.database.transaction() as session:
            expenses = ExpenseRepository(session)
            expense = expenses.get(expense_id, for_update=True)
            if expense is None:
                return None

            approvals = ApprovalRepository(session)
            task = approvals.pending_for_expense(expense_id)
            if task is None:
                existing = approvals.latest_decision(expense_id)
                if existing is not None and (
                    existing.decision == decision
                    and existing.decided_by == approver
                    and existing.comment == comment
                ):
                    return ExpenseRepository.to_state(expense)
                raise DecisionConflictError(
                    "Expense has no actionable approval task or was already decided"
                )

            run = session.get(WorkflowRun, task.workflow_run_id)
            if run is None:
                raise RuntimeError("Approval task has no workflow run")
            status = "APPROVED" if decision == "approve" else "REJECTED"
            session.add(
                ApprovalDecision(
                    decision_id=str(uuid4()),
                    approval_task_id=task.task_id,
                    expense_id=expense_id,
                    workflow_run_id=run.id,
                    decision=decision,
                    decided_by=approver,
                    comment=comment,
                    decided_at=now,
                )
            )
            task.status = status
            task.updated_at = now
            expense.status = status
            expense.current_decision = decision
            expense.decided_by = approver
            expense.decision_comment = comment
            expense.decided_at = now
            expense.updated_at = now
            run.status = status
            run.updated_at = now
            next_sequence = (
                session.scalar(
                    select(func.max(WorkflowEvent.sequence_number)).where(
                        WorkflowEvent.workflow_run_id == run.id
                    )
                )
                or 0
            ) + 1
            session.add(
                WorkflowEvent(
                    workflow_run_id=run.id,
                    expense_id=expense_id,
                    event_type="APPROVAL_DECIDED",
                    sequence_number=next_sequence,
                    payload={
                        "decision": decision,
                        "decided_by": approver,
                        "comment": comment,
                    },
                    created_at=now,
                )
            )
            session.flush()
            return ExpenseRepository.to_state(expense)

    def workflow_run_for_expense(self, expense_id: str) -> WorkflowRun | None:
        with self.database.session() as session:
            return session.scalar(
                select(WorkflowRun)
                .where(WorkflowRun.expense_id == expense_id)
                .order_by(WorkflowRun.created_at.asc())
            )

    def import_legacy_rows(self, rows: list[dict]) -> LegacyImportOutcome:
        """Import validated legacy rows in one all-or-nothing transaction."""
        imported = 0
        skipped = 0
        with self.database.transaction() as session:
            expenses = ExpenseRepository(session)
            for row in rows:
                payload = row["input_payload"]
                result = row["result"]
                payload_hash = canonical_payload_hash(payload)
                existing = expenses.get(row["expense_id"])
                if existing is not None:
                    if existing.payload_hash != payload_hash:
                        raise ExpenseConflictError(
                            f"Legacy expense {row['expense_id']} conflicts with target"
                        )
                    skipped += 1
                    continue

                created_at = _parse_legacy_timestamp(row["created_at"])
                updated_at = _parse_legacy_timestamp(row["updated_at"])
                decided_at = _parse_legacy_timestamp(row.get("decided_at"), optional=True)
                expense = Expense(
                    expense_id=row["expense_id"],
                    employee_id=payload.get("employee_id", ""),
                    employee_name=payload.get("employee_name", ""),
                    department=payload.get("department", ""),
                    transaction_date=date.fromisoformat(
                        payload.get("transaction_date", "1970-01-01")
                    ),
                    merchant=payload.get("merchant", ""),
                    category=payload.get("category", ""),
                    description=payload.get("description", ""),
                    amount=Decimal(str(payload.get("amount", 0))),
                    currency=payload.get("currency", "USD"),
                    payment_method=payload.get("payment_method", ""),
                    receipt_attached=bool(payload.get("receipt_attached", False)),
                    input_payload=payload,
                    processing_result=result,
                    status=row["status"],
                    risk_level=row.get("risk_level"),
                    approver_role=row.get("approver_role"),
                    current_decision=row.get("decision"),
                    decided_by=row.get("decided_by"),
                    decision_comment=row.get("decision_comment"),
                    decided_at=decided_at,
                    payload_hash=payload_hash,
                    created_at=created_at,
                    updated_at=updated_at,
                )
                session.add(expense)
                session.flush()

                identity = f"northstar:legacy:{row['expense_id']}:{payload_hash}"
                run_id = str(uuid5(NAMESPACE_URL, identity))
                run = WorkflowRun(
                    id=run_id,
                    correlation_id=f"legacy-{run_id}",
                    expense_id=row["expense_id"],
                    idempotency_key=f"legacy:{row['expense_id']}:{payload_hash}",
                    source_system="legacy_sqlite_migration",
                    status=row["status"],
                    started_at=created_at,
                    completed_at=updated_at,
                    created_at=created_at,
                    updated_at=updated_at,
                )
                session.add(run)
                session.flush()
                session.add(
                    WorkflowEvent(
                        workflow_run_id=run_id,
                        expense_id=row["expense_id"],
                        event_type="LEGACY_STATE_IMPORTED",
                        sequence_number=1,
                        payload={
                            "legacy_status": row["status"],
                            "provenance": "limited_to_materialized_legacy_row",
                        },
                        created_at=created_at,
                    )
                )

                if row["status"] in {
                    "PENDING_APPROVAL",
                    "ESCALATED",
                    "APPROVED",
                    "REJECTED",
                }:
                    task_id = str(uuid5(NAMESPACE_URL, identity + ":approval-task"))
                    task_status = {
                        "PENDING_APPROVAL": "PENDING",
                        "ESCALATED": "PENDING",
                        "APPROVED": "APPROVED",
                        "REJECTED": "REJECTED",
                    }[row["status"]]
                    routing = result.get("decision") or {}
                    session.add(
                        ApprovalTask(
                            task_id=task_id,
                            expense_id=row["expense_id"],
                            workflow_run_id=run_id,
                            approver_role=row.get("approver_role") or "Unassigned",
                            approval_level=int(routing.get("approver_level") or 0),
                            status=task_status,
                            created_at=created_at,
                            updated_at=updated_at,
                        )
                    )
                    session.flush()
                    if row.get("decision") and row.get("decided_by") and decided_at:
                        session.add(
                            ApprovalDecision(
                                decision_id=str(
                                    uuid5(NAMESPACE_URL, identity + ":decision")
                                ),
                                approval_task_id=task_id,
                                expense_id=row["expense_id"],
                                workflow_run_id=run_id,
                                decision=row["decision"],
                                decided_by=row["decided_by"],
                                comment=row.get("decision_comment") or "",
                                decided_at=decided_at,
                            )
                        )
                imported += 1
            session.flush()
        return LegacyImportOutcome(imported=imported, skipped=skipped)


def _parse_legacy_timestamp(
    value: str | datetime | None, *, optional: bool = False
) -> datetime | None:
    if value is None:
        if optional:
            return None
        raise ValueError("Legacy row is missing a required timestamp")
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
