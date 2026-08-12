"""FastAPI wrapper around the existing North Star expense pipeline."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, Header, HTTPException, Query, Response
from pydantic import BaseModel, Field

from automation.automation_flow import AutomationPipeline, ExpenseSubmission
from app.db.repositories import (
    DecisionConflictError,
    ExpenseConflictError,
    IdempotencyConflictError,
)
from app.db.session import DEFAULT_DATABASE_URL
from app.runtime_store import RuntimeStore

PROJECT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_RUNTIME_DB = PROJECT_DIR / "data" / "northstar_runtime.db"


class DecisionRequest(BaseModel):
    decision: Literal["approve", "reject"]
    approver: str = Field(min_length=1)
    comment: str = ""


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

    return application


app = create_app()
