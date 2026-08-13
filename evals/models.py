"""Stable, versioned contracts for evaluation cases and reports."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Profile(StrEnum):
    FAST = "fast"
    POSTGRES = "postgres"
    LIVE = "live"


class Category(StrEnum):
    DECISION = "decision"
    RISK = "risk"
    CONTEXT_SAFETY = "context_safety"
    PROVENANCE = "provenance"
    HISTORICAL_CONTEXT = "historical_context"
    IDEMPOTENCY = "idempotency"
    RELIABILITY = "reliability"


class Scenario(StrEnum):
    DEFAULT = "default"
    POLICY_MISSING = "policy_missing"
    POLICY_MISMATCH = "policy_mismatch"
    POLICY_CONFLICT = "policy_conflict"
    POLICY_STALE = "policy_stale"
    OWNER_INACTIVE = "owner_inactive"
    TRUST_EXPIRED = "trust_expired"
    POLICY_DRIFT = "policy_drift"
    APPROVAL = "approval"
    IDEMPOTENT_REPLAY = "idempotent_replay"
    IDEMPOTENCY_CONFLICT = "idempotency_conflict"
    HISTORICAL_RESOLUTION = "historical_resolution"
    HISTORICAL_PROVENANCE = "historical_provenance"
    PROVENANCE_CORRUPTION = "provenance_corruption"
    OUTBOX_TRANSIENT_RESUME = "outbox_transient_resume"
    OUTBOX_TRANSIENT_NOTIFICATION = "outbox_transient_notification"
    OUTBOX_DEAD_LETTER = "outbox_dead_letter"
    OUTBOX_REPLAY = "outbox_replay"


class ExpectedOutcome(BaseModel):
    http_status: int = 200
    status: str | None = None
    risk_level: str | None = None
    approver_role: str | None = None
    triggered_signals: list[str] | None = None
    non_triggered_signals: list[str] | None = None
    abstained: bool = False
    reason_code: str | None = None
    error_code: str | None = None
    binding_state: str | None = None
    context_trust_state: str | None = None
    policy_keys: list[str] | None = None
    rule_keys: list[str] | None = None
    triggered_rules: list[str] | None = None
    provenance_complete: bool | None = None
    provenance_verified: bool | None = None
    human_evidence: bool | None = None
    idempotency_preserved: bool | None = None
    context_version: int | None = None
    reliability_outcome: str | None = None


class EvaluationCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]+$")
    category: Category
    description: str = Field(min_length=8)
    profiles: set[Profile]
    scenario: Scenario = Scenario.DEFAULT
    payload: dict[str, Any] | None = None
    expected: ExpectedOutcome

    @model_validator(mode="after")
    def validate_payload(self) -> "EvaluationCase":
        payload_free = {
            Scenario.HISTORICAL_RESOLUTION,
            Scenario.PROVENANCE_CORRUPTION,
        }
        if self.scenario not in payload_free and self.payload is None:
            raise ValueError(f"{self.scenario} requires a payload")
        return self


class DatasetManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_name: str
    dataset_version: str
    description: str
    benchmark_intent: str
    expected_decision_engine_version: str
    expected_risk_engine_version: str
    expected_risk_catalog_hash: str
    case_files: list[str]
    expected_case_count: int = Field(ge=24, le=40)
    metric_names: list[str]
    minimum_cases: int = Field(ge=24, le=40)
    maximum_cases: int = Field(ge=24, le=40)
    required_categories: set[Category]


class AssertionResult(BaseModel):
    name: str
    passed: bool
    expected: Any = None
    actual: Any = None


class CaseResult(BaseModel):
    case_id: str
    category: Category
    profile: Profile
    passed: bool
    duration_ms: int
    assertions: list[AssertionResult]
    expected: dict[str, Any] = Field(default_factory=dict)
    actual: dict[str, Any]
    failure_reasons: list[str] = Field(default_factory=list)
    correlation_id: str | None = None
    provenance_id: str | None = None
    error: str | None = None


class Metric(BaseModel):
    passed: int
    denominator: int
    rate: float
    threshold: float
    comparison: str = ">="
    meets_threshold: bool
    details: dict[str, Any] = Field(default_factory=dict)


class EvaluationReport(BaseModel):
    schema_version: str = "1"
    run_id: str
    dataset_version: str
    profile: Profile
    decision_engine_version: str
    risk_engine_version: str
    risk_catalog_hash: str
    build_revision: str | None = None
    started_at: datetime
    finished_at: datetime
    duration_ms: int
    passed: bool
    case_count: int
    passed_count: int
    failed_count: int
    metrics: dict[str, Metric]
    category_summaries: dict[str, dict[str, int]]
    cases: list[CaseResult]
    baseline_errors: list[str] = Field(default_factory=list)
    environment: dict[str, str]
