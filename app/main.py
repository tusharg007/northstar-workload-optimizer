"""FastAPI wrapper around the existing North Star expense pipeline."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from automation.automation_flow import AutomationPipeline, ExpenseSubmission
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
    resolved_db = db_path or os.getenv("NORTHSTAR_RUNTIME_DB", str(DEFAULT_RUNTIME_DB))
    store = RuntimeStore(resolved_db)
    application = FastAPI(title="North Star Expense Service", version="2.0.0")
    application.state.store = store

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "northstar"}

    @application.post("/api/expenses/process")
    def process_expense(expense: ExpenseSubmission) -> dict:
        payload = expense.model_dump()
        result = AutomationPipeline().process_single(payload)
        anomaly = result.get("anomaly") or {}
        decision = result.get("decision") or {}
        state = store.upsert(
            expense_id=expense.expense_id,
            input_payload=payload,
            result=result,
            status=result["status"],
            risk_level=anomaly.get("risk_level"),
            approver_role=decision.get("approver_role"),
        )
        return _public_state(state)

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
        state = store.update_decision(
            expense_id=expense_id,
            decision=body.decision,
            approver=body.approver,
            comment=body.comment,
        )
        if state is None:
            raise HTTPException(status_code=404, detail="Expense not found")
        return _public_state(state)

    return application


app = create_app()

