"""SQLAlchemy models for durable operational state."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
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
