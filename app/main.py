"""FastAPI wrapper around the existing North Star expense pipeline."""

from __future__ import annotations

import os
from pathlib import Path
import time
from datetime import datetime
from typing import Annotated, Literal

from fastapi import FastAPI, Header, HTTPException, Query, Response
from pydantic import AnyHttpUrl, BaseModel, Field

from automation.automation_flow import AutomationPipeline, ExpenseSubmission
from app.db.repositories import (
    DecisionConflictError,
    ExpenseConflictError,
    IdempotencyConflictError,
    ApprovalTaskNotFoundError,
    OrchestrationConflictError,
    OutboxConflictError,
    OutboxNotFoundError,
)
from app.db.session import DEFAULT_DATABASE_URL
from app.runtime_store import RuntimeStore
from app.context.exceptions import ContextConflictError, ContextNotFoundError
from app.context.models import (
    ExpenseContextView,
    OwnerView,
    PolicySummary,
    PolicyVersionView,
    ResolvedPolicy,
    ResolvedTerm,
    TermSummary,
    TermVersionView,
)

PROJECT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_RUNTIME_DB = PROJECT_DIR / "data" / "northstar_runtime.db"


class DecisionRequest(BaseModel):
    decision: Literal["approve", "reject"]
    approver: str = Field(min_length=1)
    comment: str = ""


class OrchestrationRegistrationRequest(BaseModel):
    n8n_execution_id: str = Field(min_length=1, max_length=64)
    resume_url: AnyHttpUrl


class OrchestrationCompletionRequest(BaseModel):
    n8n_execution_id: str = Field(min_length=1, max_length=64)


class NotificationReserveRequest(BaseModel):
    notification_type: Literal[
        "APPROVAL_REQUEST", "REMINDER", "OVERDUE", "ESCALATION", "COMPLETED"
    ]
    escalation_level: int = Field(default=0, ge=0, le=10)


class NotificationSentRequest(BaseModel):
    provider_message_id: str | None = Field(default=None, max_length=255)


class SLAEvaluationRequest(BaseModel):
    as_of: datetime | None = None


class OutboxClaimRequest(BaseModel):
    worker_id: str = Field(min_length=1, max_length=128)
    limit: int = Field(default=20, ge=1, le=100)
    lease_seconds: int | None = Field(default=None, ge=1, le=3600)


class OutboxAttemptRequest(BaseModel):
    worker_id: str = Field(min_length=1, max_length=128)
    status_code: int | None = Field(default=None, ge=100, le=599)
    error_category: str | None = Field(default=None, max_length=64)
    error_message: str | None = Field(default=None, max_length=4000)


class WorkflowFailureRequest(BaseModel):
    workflow_id: str = Field(min_length=1, max_length=128)
    workflow_name: str = Field(min_length=1, max_length=255)
    execution_id: str = Field(min_length=1, max_length=64)
    failed_node: str | None = Field(default=None, max_length=255)
    error_class: str | None = Field(default=None, max_length=128)
    safe_message: str = Field(min_length=1, max_length=4000)
    correlation_id: str | None = Field(default=None, max_length=128)
    expense_id: str | None = Field(default=None, max_length=128)


def _public_state(state: dict) -> dict:
    """Add concise workflow fields while preserving the stored pipeline result."""
    result = state["result"]
    anomaly = result.get("anomaly") or {}
    return {
        **state,
        "anomaly_flags": anomaly.get("flags", []),
        "message": _status_message(state["status"], state.get("approver_role")),
    }


def _status_message(status: str, approver_role: str | None) -> str:
    if status == "AUTO_APPROVED":
        return "Expense passed validation and was auto-approved."
    if status == "PENDING_APPROVAL":
        return f"Expense is awaiting review by {approver_role}."
    if status == "ESCALATED":
        return f"Expense risk triggered escalation to {approver_role}."
    if status == "APPROVED":
        return "Expense was approved."
    if status == "REJECTED":
        return "Expense was rejected."
    return "Expense failed validation."


def create_app(db_path: str | Path | None = None) -> FastAPI:
    """Create an API instance; tests can inject an isolated database path."""
    resolved_db = db_path or os.getenv("NORTHSTAR_DATABASE_URL", DEFAULT_DATABASE_URL)
    store = RuntimeStore(resolved_db)
    application = FastAPI(title="North Star Expense Service", version="2.0.0")
    application.state.store = store

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "northstar"}

    def context_call(operation):
        try:
            return operation()
        except ContextNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ContextConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @application.get("/api/context/policies", response_model=list[PolicySummary])
    def list_context_policies() -> list[dict]:
        return store.context.list_policies()

    @application.get("/api/context/policies/{policy_key}", response_model=PolicySummary)
    def get_context_policy(policy_key: str) -> dict:
        return context_call(lambda: store.context.get_policy(policy_key))

    @application.get("/api/context/policies/{policy_key}/versions", response_model=list[PolicyVersionView])
    def list_context_policy_versions(policy_key: str) -> list[dict]:
        return context_call(lambda: store.context.policy_versions(policy_key))

    @application.get("/api/context/policies/{policy_key}/resolve", response_model=ResolvedPolicy)
    def resolve_context_policy(policy_key: str, as_of: datetime | None = Query(default=None)) -> dict:
        return context_call(lambda: store.context.resolve_policy(policy_key, as_of))

    @application.get("/api/context/terms", response_model=list[TermSummary])
    def list_context_terms() -> list[dict]:
        return store.context.list_terms()

    @application.get("/api/context/terms/{term_key}", response_model=TermSummary)
    def get_context_term(term_key: str) -> dict:
        return context_call(lambda: store.context.get_term(term_key))

    @application.get("/api/context/terms/{term_key}/versions", response_model=list[TermVersionView])
    def list_context_term_versions(term_key: str) -> list[dict]:
        return context_call(lambda: store.context.term_versions(term_key))

    @application.get("/api/context/terms/{term_key}/resolve", response_model=ResolvedTerm)
    def resolve_context_term(term_key: str, as_of: datetime | None = Query(default=None)) -> dict:
        return context_call(lambda: store.context.resolve_business_term(term_key, as_of))

    @application.get("/api/context/owners/{owner_key}", response_model=OwnerView)
    def get_context_owner(owner_key: str) -> dict:
        return context_call(lambda: store.context.get_owner(owner_key))

    @application.get("/api/context/expenses/{expense_id}", response_model=ExpenseContextView)
    def get_expense_context(expense_id: str, as_of: datetime | None = Query(default=None)) -> dict:
        return context_call(lambda: store.context.resolve_expense_context(expense_id, as_of))

    @application.post("/api/expenses/process")
    def process_expense(
        expense: ExpenseSubmission,
        response: Response,
        idempotency_key: Annotated[
            str | None,
            Header(alias="Idempotency-Key", min_length=1, max_length=255),
        ] = None,
        correlation_id: Annotated[
            str | None,
            Header(
                alias="X-Correlation-ID",
                min_length=1,
                max_length=128,
                pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$",
            ),
        ] = None,
    ) -> dict:
        payload = expense.model_dump()
        try:
            outcome = store.process(
                payload,
                AutomationPipeline().process_single,
                idempotency_key=idempotency_key,
                correlation_id=correlation_id,
            )
        except (IdempotencyConflictError, ExpenseConflictError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        response.headers["X-Correlation-ID"] = outcome.correlation_id
        return _public_state(outcome.state)

    @application.get("/api/expenses/{expense_id}/explanation")
    def explain_expense(expense_id: str) -> dict:
        state = store.get(expense_id)
        if state is None:
            raise HTTPException(status_code=404, detail="Expense not found")
        result = state["result"]
        anomaly = result.get("anomaly") or {}
        routing = result.get("decision") or {}
        return {
            "expense_id": expense_id,
            "status": state["status"],
            "risk_level": state["risk_level"],
            "anomaly_flags": anomaly.get("flags", []),
            "routing_decision": routing,
            "approver": state.get("decided_by") or state.get("approver_role"),
            "reason": routing.get("reason")
            or "Expense did not reach routing because validation failed.",
        }

    @application.get("/api/expenses/{expense_id}")
    def get_expense(expense_id: str) -> dict:
        state = store.get(expense_id)
        if state is None:
            raise HTTPException(status_code=404, detail="Expense not found")
        return _public_state(state)

    @application.get("/api/expenses")
    def list_expenses(status: str | None = Query(default=None)) -> list[dict]:
        return [_public_state(state) for state in store.list(status=status)]

    @application.post("/api/expenses/{expense_id}/decision")
    def decide_expense(expense_id: str, body: DecisionRequest) -> dict:
        try:
            state = store.update_decision(
                expense_id=expense_id,
                decision=body.decision,
                approver=body.approver,
                comment=body.comment,
            )
        except DecisionConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if state is None:
            raise HTTPException(status_code=404, detail="Expense not found")
        return _public_state(state)

    # Trusted-network-only integration endpoints. Authentication is deferred to
    # the security gate; none of these values are included in public responses.
    @application.get("/api/internal/approval-tasks/by-expense/{expense_id}")
    def internal_approval_task(expense_id: str) -> dict:
        try:
            return store.orchestration.get_by_expense(expense_id)
        except ApprovalTaskNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @application.post(
        "/api/internal/approval-tasks/by-expense/{expense_id}/orchestration/claim"
    )
    def claim_approval_orchestration(expense_id: str) -> dict:
        try:
            outcome = store.orchestration.claim_by_expense(expense_id)
        except ApprovalTaskNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {**outcome.task, "launch_required": outcome.launch_required}

    @application.post(
        "/api/internal/approval-tasks/{task_id}/orchestration/register"
    )
    def register_approval_orchestration(
        task_id: str, body: OrchestrationRegistrationRequest
    ) -> dict:
        # Opt-in integration-test hook for the registration/decision race. It
        # is inert in normal runtimes and bounded to avoid accidental hangs.
        delay_ms = max(
            0,
            min(
                int(
                    os.getenv(
                        "NORTHSTAR_TEST_ORCHESTRATION_REGISTRATION_DELAY_MS", "0"
                    )
                ),
                5000,
            ),
        )
        if delay_ms > 0:
            time.sleep(delay_ms / 1000)
        try:
            outcome = store.orchestration.register(
                task_id, body.n8n_execution_id, str(body.resume_url)
            )
        except ApprovalTaskNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except OrchestrationConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {
            **outcome.task,
            "should_wait": outcome.should_wait,
            "replayed": outcome.replayed,
        }

    @application.post(
        "/api/internal/approval-tasks/{task_id}/orchestration/complete"
    )
    def complete_approval_orchestration(
        task_id: str, body: OrchestrationCompletionRequest
    ) -> dict:
        try:
            return store.orchestration.complete(task_id, body.n8n_execution_id)
        except ApprovalTaskNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except OrchestrationConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @application.get("/api/internal/approval-tasks/pending")
    def pending_approval_tasks() -> list[dict]:
        return store.orchestration.pending()

    @application.post(
        "/api/internal/approval-tasks/sla/notifications/reserve"
    )
    def reserve_sla_notifications(body: SLAEvaluationRequest) -> dict:
        return {
            "notifications": store.orchestration.reserve_sla_notifications(
                now=body.as_of
            )
        }

    @application.post(
        "/api/internal/approval-tasks/{task_id}/notifications/reserve"
    )
    def reserve_approval_notification(
        task_id: str, body: NotificationReserveRequest
    ) -> dict:
        try:
            return store.orchestration.reserve_notification(
                task_id,
                body.notification_type,
                escalation_level=body.escalation_level,
            )
        except ApprovalTaskNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @application.post(
        "/api/internal/approval-notifications/{notification_id}/sent"
    )
    def mark_approval_notification_sent(
        notification_id: str, body: NotificationSentRequest
    ) -> dict:
        try:
            return store.orchestration.mark_notification_sent(
                notification_id, body.provider_message_id
            )
        except ApprovalTaskNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @application.get("/api/internal/approval-notifications/{notification_id}")
    def get_approval_notification(notification_id: str) -> dict:
        try:
            return store.orchestration.get_notification(notification_id)
        except ApprovalTaskNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @application.post("/api/internal/outbox/claim")
    def claim_outbox(body: OutboxClaimRequest) -> dict:
        return {"events": store.outbox.claim_due(body.worker_id, body.limit, body.lease_seconds)}

    @application.get("/api/internal/outbox/dead-letter")
    def list_dead_letters() -> list[dict]:
        return store.outbox.dead_letters()

    @application.post("/api/internal/outbox/{event_id}/claim")
    def claim_one_outbox(event_id: str, body: OutboxClaimRequest) -> dict:
        try:
            return store.outbox.claim_one(event_id, body.worker_id, body.lease_seconds)
        except OutboxNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except OutboxConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @application.get("/api/internal/outbox/{event_id}/delivery-target")
    def outbox_delivery_target(event_id: str) -> dict:
        try:
            return store.outbox.delivery_target(event_id)
        except OutboxNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except OutboxConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @application.get("/api/internal/outbox/{event_id}")
    def get_outbox(event_id: str) -> dict:
        try:
            return store.outbox.get(event_id)
        except OutboxNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @application.get("/api/internal/outbox/by-delivery-key/{delivery_key:path}")
    def get_outbox_by_delivery_key(delivery_key: str) -> dict:
        try:
            return store.outbox.get_by_delivery_key(delivery_key)
        except OutboxNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @application.post("/api/internal/outbox/{event_id}/success")
    def outbox_success(event_id: str, body: OutboxAttemptRequest) -> dict:
        try:
            return store.outbox.success(event_id, body.worker_id, status_code=body.status_code)
        except OutboxNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except OutboxConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @application.post("/api/internal/outbox/{event_id}/failure")
    def outbox_failure(event_id: str, body: OutboxAttemptRequest) -> dict:
        try:
            return store.outbox.failure(event_id, body.worker_id, status_code=body.status_code, error_category=body.error_category, error_message=body.error_message)
        except OutboxNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except OutboxConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @application.post("/api/internal/outbox/{event_id}/replay")
    def replay_outbox(event_id: str) -> dict:
        try:
            return store.outbox.replay(event_id)
        except OutboxNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except OutboxConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @application.post("/api/internal/reliability/reconcile")
    def reconcile_reliability() -> dict:
        return store.outbox.reconcile()

    @application.post("/api/internal/workflow-failures")
    def record_workflow_failure(body: WorkflowFailureRequest) -> dict:
        return store.outbox.record_workflow_failure(body.model_dump())

    @application.get("/api/internal/workflow-failures")
    def list_workflow_failures(status: str | None = Query(default=None)) -> list[dict]:
        return store.outbox.workflow_failures(status)

    return application


app = create_app()
