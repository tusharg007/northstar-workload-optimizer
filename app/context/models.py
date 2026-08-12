"""Stable read contracts for the governed context API."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ContextModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OwnerView(ContextModel):
    owner_key: str
    display_name: str
    owner_type: str
    domain: str
    contact_reference: str | None
    active: bool


class TrustSignalView(ContextModel):
    signal_type: str
    status: str
    score: float | None
    observed_at: datetime
    expires_at: datetime | None
    source: str
    details: dict[str, Any]


class TrustView(ContextModel):
    state: str
    reasons: list[str]
    signals: list[TrustSignalView]


class PolicyRuleView(ContextModel):
    rule_key: str
    rule_name: str
    rule_type: str
    description: str
    parameters: dict[str, Any]
    severity: str
    business_term_key: str | None
    source_reference: str | None


class PolicySummary(ContextModel):
    policy_key: str
    policy_name: str
    domain: str
    description: str
    owner: OwnerView
    version_count: int


class PolicyVersionView(ContextModel):
    policy_version_id: str
    version_number: int
    status: str
    effective_from: datetime
    effective_to: datetime | None
    review_due_at: datetime | None
    certified_at: datetime | None
    source_reference: str
    content_hash: str
    metadata: dict[str, Any]
    rules: list[PolicyRuleView]


class ResolvedPolicy(ContextModel):
    policy_key: str
    policy_name: str
    domain: str
    description: str
    owner: OwnerView
    as_of: datetime
    policy_version_id: str | None = None
    version_number: int | None = None
    status: str | None = None
    effective_from: datetime | None = None
    effective_to: datetime | None = None
    review_due_at: datetime | None = None
    certified_at: datetime | None = None
    source_reference: str | None = None
    content_hash: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    rules: list[PolicyRuleView] = Field(default_factory=list)
    trust: TrustView


class TermSummary(ContextModel):
    term_key: str
    canonical_name: str
    domain: str
    owner: OwnerView
    version_count: int


class TermVersionView(ContextModel):
    term_version_id: str
    version_number: int
    definition: str
    status: str
    effective_from: datetime
    effective_to: datetime | None
    review_due_at: datetime | None
    certified_at: datetime | None
    source_reference: str
    content_hash: str


class ResolvedTerm(ContextModel):
    term_key: str
    canonical_name: str
    domain: str
    owner: OwnerView
    as_of: datetime
    term_version_id: str | None = None
    version_number: int | None = None
    definition: str | None = None
    status: str | None = None
    effective_from: datetime | None = None
    effective_to: datetime | None = None
    review_due_at: datetime | None = None
    certified_at: datetime | None = None
    source_reference: str | None = None
    content_hash: str | None = None
    trust: TrustView


class RiskSignalView(ContextModel):
    signal_key: str
    canonical_name: str
    description: str
    engine_component: str
    deterministic: bool
    category: str
    parameters: dict[str, Any]
    observed_flags: list[str] = Field(default_factory=list)


class ExpenseContextView(ContextModel):
    expense_id: str
    as_of: datetime
    policies: list[ResolvedPolicy]
    business_terms: list[ResolvedTerm]
    trust_summary: dict[str, int]
    risk_signal_definitions: list[RiskSignalView]
    decision_behavior_changed: bool = False
