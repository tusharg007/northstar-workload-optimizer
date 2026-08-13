"""SQLAlchemy models for durable operational state."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, JSON_TYPE, UTCDateTime, utc_now


class Expense(Base):
    __tablename__ = "expenses"
    __table_args__ = (
        UniqueConstraint("expense_id", name="uq_expenses_expense_id"),
        Index("ix_expenses_expense_id", "expense_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    expense_id: Mapped[str] = mapped_column(String(128))
    employee_id: Mapped[str] = mapped_column(String(128))
    employee_name: Mapped[str] = mapped_column(String(255))
    department: Mapped[str] = mapped_column(String(128))
    transaction_date: Mapped[date] = mapped_column(Date)
    merchant: Mapped[str] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(Text, default="")
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    currency: Mapped[str] = mapped_column(String(16), default="USD")
    payment_method: Mapped[str] = mapped_column(String(128))
    receipt_attached: Mapped[bool] = mapped_column(Boolean, default=False)
    input_payload: Mapped[dict] = mapped_column(JSON_TYPE)
    processing_result: Mapped[dict] = mapped_column(JSON_TYPE)
    status: Mapped[str] = mapped_column(String(64), index=True)
    risk_level: Mapped[str | None] = mapped_column(String(32), nullable=True)
    approver_role: Mapped[str | None] = mapped_column(String(255), nullable=True)
    current_decision: Mapped[str | None] = mapped_column(String(32), nullable=True)
    decided_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    decision_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    payload_hash: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utc_now, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utc_now, onupdate=utc_now, server_default=func.now()
    )


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    correlation_id: Mapped[str] = mapped_column(String(128), index=True)
    expense_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("expenses.expense_id", ondelete="CASCADE"), index=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True)
    source_system: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(64), index=True)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utc_now, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utc_now, onupdate=utc_now, server_default=func.now()
    )


class WorkflowEvent(Base):
    __tablename__ = "workflow_events"
    __table_args__ = (
        UniqueConstraint(
            "workflow_run_id", "sequence_number", name="uq_workflow_event_sequence"
        ),
        Index("ix_workflow_events_expense_id", "expense_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workflow_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workflow_runs.id", ondelete="CASCADE"), index=True
    )
    expense_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("expenses.expense_id", ondelete="CASCADE")
    )
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    sequence_number: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict] = mapped_column(JSON_TYPE)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utc_now, server_default=func.now()
    )


class ApprovalTask(Base):
    __tablename__ = "approval_tasks"
    __table_args__ = (
        UniqueConstraint("workflow_run_id", name="uq_approval_task_workflow_run"),
    )

    task_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    expense_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("expenses.expense_id", ondelete="CASCADE"), index=True
    )
    workflow_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workflow_runs.id", ondelete="CASCADE"), index=True
    )
    approver_role: Mapped[str] = mapped_column(String(255))
    approval_level: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), index=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utc_now, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utc_now, onupdate=utc_now, server_default=func.now()
    )
    due_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    orchestration_status: Mapped[str] = mapped_column(
        String(32), default="NOT_STARTED", server_default="NOT_STARTED", index=True
    )
    n8n_execution_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, unique=True
    )
    n8n_wait_resume_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    orchestration_claimed_at: Mapped[datetime | None] = mapped_column(
        UTCDateTime(), nullable=True
    )
    wait_registered_at: Mapped[datetime | None] = mapped_column(
        UTCDateTime(), nullable=True
    )
    orchestration_completed_at: Mapped[datetime | None] = mapped_column(
        UTCDateTime(), nullable=True
    )
    last_notification_at: Mapped[datetime | None] = mapped_column(
        UTCDateTime(), nullable=True
    )
    reminder_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    escalation_level: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )


class ApprovalDecision(Base):
    __tablename__ = "approval_decisions"
    __table_args__ = (
        UniqueConstraint("approval_task_id", name="uq_approval_decision_task"),
    )

    decision_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    approval_task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("approval_tasks.task_id", ondelete="RESTRICT"), index=True
    )
    expense_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("expenses.expense_id", ondelete="CASCADE"), index=True
    )
    workflow_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workflow_runs.id", ondelete="CASCADE"), index=True
    )
    decision: Mapped[str] = mapped_column(String(32))
    decided_by: Mapped[str] = mapped_column(String(255))
    comment: Mapped[str] = mapped_column(Text, default="")
    decided_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utc_now, server_default=func.now()
    )


class ApprovalNotification(Base):
    __tablename__ = "approval_notifications"
    __table_args__ = (
        UniqueConstraint(
            "approval_task_id",
            "notification_type",
            "escalation_level",
            name="uq_approval_notification_logical",
        ),
    )

    notification_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    approval_task_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("approval_tasks.task_id", ondelete="CASCADE"),
        index=True,
    )
    notification_type: Mapped[str] = mapped_column(String(32), index=True)
    escalation_level: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    status: Mapped[str] = mapped_column(
        String(32), default="PENDING", server_default="PENDING", index=True
    )
    target_role: Mapped[str] = mapped_column(String(255))
    payload: Mapped[dict] = mapped_column(JSON_TYPE)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utc_now, server_default=func.now()
    )
    sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    provider_message_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )


class OutboxEvent(Base):
    __tablename__ = "outbox_events"
    __table_args__ = (
        UniqueConstraint("delivery_key", name="uq_outbox_events_delivery_key"),
        Index("ix_outbox_events_due", "status", "next_attempt_at"),
        Index("ix_outbox_events_aggregate", "aggregate_type", "aggregate_id"),
        Index("ix_outbox_events_lease_expires_at", "lease_expires_at"),
    )

    outbox_event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(64))
    aggregate_type: Mapped[str] = mapped_column(String(64))
    aggregate_id: Mapped[str] = mapped_column(String(128))
    correlation_id: Mapped[str | None] = mapped_column(String(128), index=True)
    delivery_key: Mapped[str] = mapped_column(String(255))
    payload: Mapped[dict] = mapped_column(JSON_TYPE)
    status: Mapped[str] = mapped_column(String(32), default="PENDING")
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    max_attempts: Mapped[int] = mapped_column(Integer, default=4, server_default="4")
    next_attempt_at: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
    lease_owner: Mapped[str | None] = mapped_column(String(128))
    lease_acquired_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    lease_expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_error_category: Mapped[str | None] = mapped_column(String(64))
    last_error_message: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, server_default=func.now())
    delivered_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    dead_lettered_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    replay_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, onupdate=utc_now, server_default=func.now())


class OutboxDeliveryAttempt(Base):
    __tablename__ = "outbox_delivery_attempts"
    __table_args__ = (
        UniqueConstraint("outbox_event_id", "attempt_number", name="uq_outbox_attempt_number"),
    )

    attempt_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    outbox_event_id: Mapped[str] = mapped_column(String(36), ForeignKey("outbox_events.outbox_event_id", ondelete="CASCADE"), index=True)
    attempt_number: Mapped[int] = mapped_column(Integer)
    worker_id: Mapped[str] = mapped_column(String(128))
    started_at: Mapped[datetime] = mapped_column(UTCDateTime())
    completed_at: Mapped[datetime] = mapped_column(UTCDateTime())
    outcome: Mapped[str] = mapped_column(String(32))
    status_code: Mapped[int | None] = mapped_column(Integer)
    error_category: Mapped[str | None] = mapped_column(String(64))
    safe_error_message: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, server_default=func.now())


class WorkflowFailure(Base):
    __tablename__ = "workflow_failures"
    __table_args__ = (
        UniqueConstraint("workflow_id", "execution_id", name="uq_workflow_failure_execution"),
    )

    failure_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workflow_id: Mapped[str] = mapped_column(String(128))
    workflow_name: Mapped[str] = mapped_column(String(255))
    execution_id: Mapped[str] = mapped_column(String(64))
    failed_node: Mapped[str | None] = mapped_column(String(255))
    error_class: Mapped[str | None] = mapped_column(String(128))
    safe_message: Mapped[str] = mapped_column(String(500))
    correlation_id: Mapped[str | None] = mapped_column(String(128), index=True)
    expense_id: Mapped[str | None] = mapped_column(String(128), index=True)
    first_seen_at: Mapped[datetime] = mapped_column(UTCDateTime())
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime())
    occurrence_count: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    status: Mapped[str] = mapped_column(String(32), default="OPEN", server_default="OPEN")


class GovernanceOwner(Base):
    __tablename__ = "governance_owners"
    __table_args__ = (
        UniqueConstraint("owner_key", name="uq_governance_owners_owner_key"),
        CheckConstraint("owner_type IN ('TEAM', 'ROLE', 'PERSON')", name="owner_type"),
    )

    owner_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_key: Mapped[str] = mapped_column(String(128))
    display_name: Mapped[str] = mapped_column(String(255))
    owner_type: Mapped[str] = mapped_column(String(16))
    domain: Mapped[str] = mapped_column(String(128), index=True)
    contact_reference: Mapped[str | None] = mapped_column(String(255))
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, onupdate=utc_now, server_default=func.now())


class BusinessTerm(Base):
    __tablename__ = "business_terms"
    __table_args__ = (UniqueConstraint("term_key", name="uq_business_terms_term_key"),)

    term_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    term_key: Mapped[str] = mapped_column(String(128))
    canonical_name: Mapped[str] = mapped_column(String(255))
    domain: Mapped[str] = mapped_column(String(128), index=True)
    owner_id: Mapped[str] = mapped_column(String(36), ForeignKey("governance_owners.owner_id", ondelete="RESTRICT"), index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, onupdate=utc_now, server_default=func.now())


class BusinessTermVersion(Base):
    __tablename__ = "business_term_versions"
    __table_args__ = (
        UniqueConstraint("term_id", "version_number", name="uq_business_term_version"),
        CheckConstraint("status IN ('DRAFT', 'CERTIFIED', 'RETIRED')", name="status"),
        CheckConstraint("effective_to IS NULL OR effective_to >= effective_from", name="effective_window"),
        CheckConstraint("review_due_at IS NULL OR review_due_at >= effective_from", name="review_window"),
        Index("ix_business_term_versions_effective", "term_id", "status", "effective_from", "effective_to"),
    )

    term_version_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    term_id: Mapped[str] = mapped_column(String(36), ForeignKey("business_terms.term_id", ondelete="CASCADE"), index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    definition: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16))
    effective_from: Mapped[datetime] = mapped_column(UTCDateTime())
    effective_to: Mapped[datetime | None] = mapped_column(UTCDateTime())
    review_due_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    certified_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    source_reference: Mapped[str] = mapped_column(String(500))
    content_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, server_default=func.now())


class PolicyDefinition(Base):
    __tablename__ = "policy_definitions"
    __table_args__ = (UniqueConstraint("policy_key", name="uq_policy_definitions_policy_key"),)

    policy_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    policy_key: Mapped[str] = mapped_column(String(128))
    policy_name: Mapped[str] = mapped_column(String(255))
    domain: Mapped[str] = mapped_column(String(128), index=True)
    description: Mapped[str] = mapped_column(Text)
    owner_id: Mapped[str] = mapped_column(String(36), ForeignKey("governance_owners.owner_id", ondelete="RESTRICT"), index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, onupdate=utc_now, server_default=func.now())


class PolicyVersion(Base):
    __tablename__ = "policy_versions"
    __table_args__ = (
        UniqueConstraint("policy_id", "version_number", name="uq_policy_version"),
        CheckConstraint("status IN ('DRAFT', 'CERTIFIED', 'RETIRED')", name="status"),
        CheckConstraint("effective_to IS NULL OR effective_to >= effective_from", name="effective_window"),
        CheckConstraint("review_due_at IS NULL OR review_due_at >= effective_from", name="review_window"),
        Index("ix_policy_versions_effective", "policy_id", "status", "effective_from", "effective_to"),
    )

    policy_version_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    policy_id: Mapped[str] = mapped_column(String(36), ForeignKey("policy_definitions.policy_id", ondelete="CASCADE"), index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16))
    effective_from: Mapped[datetime] = mapped_column(UTCDateTime())
    effective_to: Mapped[datetime | None] = mapped_column(UTCDateTime())
    review_due_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    certified_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    source_reference: Mapped[str] = mapped_column(String(500))
    content_hash: Mapped[str] = mapped_column(String(64))
    context_metadata: Mapped[dict] = mapped_column("metadata", JSON_TYPE, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, server_default=func.now())


class PolicyRule(Base):
    __tablename__ = "policy_rules"
    __table_args__ = (UniqueConstraint("policy_version_id", "rule_key", name="uq_policy_rule"),)

    rule_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    policy_version_id: Mapped[str] = mapped_column(String(36), ForeignKey("policy_versions.policy_version_id", ondelete="CASCADE"), index=True)
    rule_key: Mapped[str] = mapped_column(String(128))
    rule_name: Mapped[str] = mapped_column(String(255))
    rule_type: Mapped[str] = mapped_column(String(64))
    description: Mapped[str] = mapped_column(Text)
    parameters: Mapped[dict] = mapped_column(JSON_TYPE)
    severity: Mapped[str] = mapped_column(String(32))
    business_term_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("business_terms.term_id", ondelete="SET NULL"), index=True)
    source_reference: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, server_default=func.now())


class TrustSignal(Base):
    __tablename__ = "trust_signals"
    __table_args__ = (
        CheckConstraint(
            "(policy_version_id IS NOT NULL AND business_term_version_id IS NULL) OR "
            "(policy_version_id IS NULL AND business_term_version_id IS NOT NULL)",
            name="exactly_one_target",
        ),
        CheckConstraint("status IN ('PASS', 'WARN', 'FAIL', 'UNKNOWN')", name="status"),
        CheckConstraint("score IS NULL OR (score >= 0 AND score <= 1)", name="score_range"),
        Index("ix_trust_signals_policy", "policy_version_id", "signal_type"),
        Index("ix_trust_signals_term", "business_term_version_id", "signal_type"),
    )

    trust_signal_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    policy_version_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("policy_versions.policy_version_id", ondelete="CASCADE"))
    business_term_version_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("business_term_versions.term_version_id", ondelete="CASCADE"))
    signal_type: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16))
    score: Mapped[float | None] = mapped_column(Float)
    observed_at: Mapped[datetime] = mapped_column(UTCDateTime())
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    source: Mapped[str] = mapped_column(String(255))
    details: Mapped[dict] = mapped_column(JSON_TYPE, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, server_default=func.now())


class DecisionProvenance(Base):
    __tablename__ = "decision_provenance"
    __table_args__ = (
        UniqueConstraint("workflow_run_id", name="uq_decision_provenance_workflow_run"),
        Index("ix_decision_provenance_expense_id", "expense_id"),
        Index("ix_decision_provenance_correlation_id", "correlation_id"),
    )
    provenance_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    expense_id: Mapped[str] = mapped_column(String(128), ForeignKey("expenses.expense_id", ondelete="RESTRICT"))
    workflow_run_id: Mapped[str] = mapped_column(String(36), ForeignKey("workflow_runs.id", ondelete="RESTRICT"))
    correlation_id: Mapped[str] = mapped_column(String(128))
    source_payload_hash: Mapped[str] = mapped_column(String(64))
    context_as_of: Mapped[datetime] = mapped_column(UTCDateTime())
    context_resolved_at: Mapped[datetime] = mapped_column(UTCDateTime())
    automated_status: Mapped[str] = mapped_column(String(64))
    risk_level: Mapped[str | None] = mapped_column(String(32))
    approver_role: Mapped[str | None] = mapped_column(String(255))
    automated_reason: Mapped[str | None] = mapped_column(Text)
    context_trust_state: Mapped[str] = mapped_column(String(32))
    decision_engine_version: Mapped[str] = mapped_column(String(128))
    risk_engine_version: Mapped[str] = mapped_column(String(128))
    risk_catalog_hash: Mapped[str] = mapped_column(String(64))
    build_revision: Mapped[str | None] = mapped_column(String(128))
    provenance_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, server_default=func.now())


class DecisionPolicyEvidence(Base):
    __tablename__ = "decision_policy_evidence"
    __table_args__ = (UniqueConstraint("provenance_id", "policy_version_id", name="uq_decision_policy_evidence"), Index("ix_decision_policy_key_version", "policy_key", "version_number"))
    evidence_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    provenance_id: Mapped[str] = mapped_column(String(36), ForeignKey("decision_provenance.provenance_id", ondelete="RESTRICT"))
    policy_id: Mapped[str] = mapped_column(String(36), ForeignKey("policy_definitions.policy_id", ondelete="RESTRICT"))
    policy_version_id: Mapped[str] = mapped_column(String(36), ForeignKey("policy_versions.policy_version_id", ondelete="RESTRICT"))
    policy_key: Mapped[str] = mapped_column(String(128)); policy_name: Mapped[str] = mapped_column(String(255))
    version_number: Mapped[int] = mapped_column(Integer); content_hash: Mapped[str] = mapped_column(String(64))
    owner_key: Mapped[str] = mapped_column(String(128)); owner_display_name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(16)); effective_from: Mapped[datetime] = mapped_column(UTCDateTime())
    effective_to: Mapped[datetime | None] = mapped_column(UTCDateTime()); trust_state: Mapped[str] = mapped_column(String(32))
    snapshot_hash: Mapped[str] = mapped_column(String(64)); created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, server_default=func.now())


class DecisionTermEvidence(Base):
    __tablename__ = "decision_term_evidence"
    __table_args__ = (UniqueConstraint("provenance_id", "business_term_version_id", name="uq_decision_term_evidence"), Index("ix_decision_term_key_version", "term_key", "version_number"))
    evidence_id: Mapped[str] = mapped_column(String(36), primary_key=True); provenance_id: Mapped[str] = mapped_column(String(36), ForeignKey("decision_provenance.provenance_id", ondelete="RESTRICT"))
    business_term_id: Mapped[str] = mapped_column(String(36), ForeignKey("business_terms.term_id", ondelete="RESTRICT")); business_term_version_id: Mapped[str] = mapped_column(String(36), ForeignKey("business_term_versions.term_version_id", ondelete="RESTRICT"))
    term_key: Mapped[str] = mapped_column(String(128)); canonical_name: Mapped[str] = mapped_column(String(255)); definition: Mapped[str] = mapped_column(Text)
    version_number: Mapped[int] = mapped_column(Integer); content_hash: Mapped[str] = mapped_column(String(64)); owner_key: Mapped[str] = mapped_column(String(128)); trust_state: Mapped[str] = mapped_column(String(32)); snapshot_hash: Mapped[str] = mapped_column(String(64)); created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, server_default=func.now())


class DecisionRuleEvidence(Base):
    __tablename__ = "decision_rule_evidence"
    __table_args__ = (UniqueConstraint("provenance_id", "policy_rule_id", name="uq_decision_rule_evidence"), CheckConstraint("evaluation_status IN ('PASSED','FAILED','TRIGGERED','NOT_APPLICABLE')", name="evaluation_status"), Index("ix_decision_rule_key_triggered", "rule_key", "triggered"))
    evidence_id: Mapped[str] = mapped_column(String(36), primary_key=True); provenance_id: Mapped[str] = mapped_column(String(36), ForeignKey("decision_provenance.provenance_id", ondelete="RESTRICT")); policy_version_id: Mapped[str] = mapped_column(String(36), ForeignKey("policy_versions.policy_version_id", ondelete="RESTRICT")); policy_rule_id: Mapped[str] = mapped_column(String(36), ForeignKey("policy_rules.rule_id", ondelete="RESTRICT"))
    rule_key: Mapped[str] = mapped_column(String(128)); rule_name: Mapped[str] = mapped_column(String(255)); rule_type: Mapped[str] = mapped_column(String(64)); severity: Mapped[str] = mapped_column(String(32)); parameters: Mapped[dict] = mapped_column(JSON_TYPE); evaluation_status: Mapped[str] = mapped_column(String(32)); triggered: Mapped[bool] = mapped_column(Boolean); observed_value: Mapped[dict | None] = mapped_column(JSON_TYPE); evaluation_details: Mapped[dict] = mapped_column(JSON_TYPE); evidence_hash: Mapped[str] = mapped_column(String(64)); created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, server_default=func.now())


class DecisionTrustEvidence(Base):
    __tablename__ = "decision_trust_evidence"
    __table_args__ = (Index("ix_decision_trust_target", "target_type", "target_key"),)
    evidence_id: Mapped[str] = mapped_column(String(36), primary_key=True); provenance_id: Mapped[str] = mapped_column(String(36), ForeignKey("decision_provenance.provenance_id", ondelete="RESTRICT")); trust_signal_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("trust_signals.trust_signal_id", ondelete="SET NULL")); target_type: Mapped[str] = mapped_column(String(32)); target_key: Mapped[str] = mapped_column(String(128)); signal_type: Mapped[str] = mapped_column(String(64)); signal_status: Mapped[str] = mapped_column(String(16)); observed_at: Mapped[datetime] = mapped_column(UTCDateTime()); expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime()); source: Mapped[str] = mapped_column(String(255)); details: Mapped[dict] = mapped_column(JSON_TYPE); evidence_hash: Mapped[str] = mapped_column(String(64)); created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, server_default=func.now())


class DecisionRiskEvidence(Base):
    __tablename__ = "decision_risk_evidence"
    __table_args__ = (UniqueConstraint("provenance_id", "signal_key", name="uq_decision_risk_evidence"), Index("ix_decision_risk_key_triggered", "signal_key", "triggered"))
    evidence_id: Mapped[str] = mapped_column(String(36), primary_key=True); provenance_id: Mapped[str] = mapped_column(String(36), ForeignKey("decision_provenance.provenance_id", ondelete="RESTRICT")); signal_key: Mapped[str] = mapped_column(String(128)); canonical_name: Mapped[str] = mapped_column(String(255)); engine_component: Mapped[str] = mapped_column(String(128)); triggered: Mapped[bool] = mapped_column(Boolean); observed_value: Mapped[dict | None] = mapped_column(JSON_TYPE); threshold_or_reference: Mapped[dict | None] = mapped_column(JSON_TYPE); details: Mapped[dict] = mapped_column(JSON_TYPE); signal_definition_hash: Mapped[str] = mapped_column(String(64)); risk_catalog_hash: Mapped[str] = mapped_column(String(64)); evidence_hash: Mapped[str] = mapped_column(String(64)); created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, server_default=func.now())


class DecisionHumanEvidence(Base):
    __tablename__ = "decision_human_evidence"
    __table_args__ = (UniqueConstraint("approval_decision_id", name="uq_decision_human_approval"),)
    human_evidence_id: Mapped[str] = mapped_column(String(36), primary_key=True); provenance_id: Mapped[str] = mapped_column(String(36), ForeignKey("decision_provenance.provenance_id", ondelete="RESTRICT")); approval_decision_id: Mapped[str] = mapped_column(String(36), ForeignKey("approval_decisions.decision_id", ondelete="RESTRICT")); decision: Mapped[str] = mapped_column(String(16)); decided_by: Mapped[str] = mapped_column(String(255)); comment: Mapped[str] = mapped_column(Text); decided_at: Mapped[datetime] = mapped_column(UTCDateTime()); evidence_hash: Mapped[str] = mapped_column(String(64)); created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, server_default=func.now())
