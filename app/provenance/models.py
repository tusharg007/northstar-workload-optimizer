"""Stable read contracts for immutable decision provenance."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class ProvenanceView(BaseModel):
    model_config = ConfigDict(extra="allow")
    provenance_id: str
    expense_id: str
    workflow_run_id: str
    correlation_id: str
    provenance_hash: str
    policies: list[dict[str, Any]]
    terms: list[dict[str, Any]]
    rules: list[dict[str, Any]]
    trust: list[dict[str, Any]]
    risk: list[dict[str, Any]]
    human_decisions: list[dict[str, Any]]


class ProvenanceTraceView(BaseModel):
    model_config = ConfigDict(extra="allow")
    expense_id: str
    provenance_status: str


class ProvenanceVerificationView(BaseModel):
    provenance_id: str
    status: str
    stored_hash: str
    recomputed_hash: str
    failures: list[str]


class LineageEventView(BaseModel):
    source: str
    event_type: str
    timestamp: datetime
    status: str | None = None
    sequence: int | None = None


class ExpenseLineageView(BaseModel):
    expense_id: str
    correlation_id: str
    workflow_run_id: str
    events: list[LineageEventView]
