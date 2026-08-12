"""Create the Gate 1 operational persistence schema.

Revision ID: 20260812_0001
Revises: None
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260812_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON_TYPE = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "expenses",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("expense_id", sa.String(length=128), nullable=False),
        sa.Column("employee_id", sa.String(length=128), nullable=False),
        sa.Column("employee_name", sa.String(length=255), nullable=False),
        sa.Column("department", sa.String(length=128), nullable=False),
        sa.Column("transaction_date", sa.Date(), nullable=False),
        sa.Column("merchant", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=16), server_default="USD", nullable=False),
        sa.Column("payment_method", sa.String(length=128), nullable=False),
        sa.Column("receipt_attached", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("input_payload", JSON_TYPE, nullable=False),
        sa.Column("processing_result", JSON_TYPE, nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("risk_level", sa.String(length=32), nullable=True),
        sa.Column("approver_role", sa.String(length=255), nullable=True),
        sa.Column("current_decision", sa.String(length=32), nullable=True),
        sa.Column("decided_by", sa.String(length=255), nullable=True),
        sa.Column("decision_comment", sa.Text(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_expenses"),
        sa.UniqueConstraint("expense_id", name="uq_expenses_expense_id"),
    )
    op.create_index("ix_expenses_expense_id", "expenses", ["expense_id"])
    op.create_index("ix_expenses_payload_hash", "expenses", ["payload_hash"])
    op.create_index("ix_expenses_status", "expenses", ["status"])

    op.create_table(
        "workflow_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("correlation_id", sa.String(length=128), nullable=False),
        sa.Column("expense_id", sa.String(length=128), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("source_system", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["expense_id"], ["expenses.expense_id"],
            name="fk_workflow_runs_expense_id_expenses", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_workflow_runs"),
        sa.UniqueConstraint("idempotency_key", name="uq_workflow_runs_idempotency_key"),
    )
    op.create_index("ix_workflow_runs_correlation_id", "workflow_runs", ["correlation_id"])
    op.create_index("ix_workflow_runs_expense_id", "workflow_runs", ["expense_id"])
    op.create_index("ix_workflow_runs_status", "workflow_runs", ["status"])

    op.create_table(
        "workflow_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("workflow_run_id", sa.String(length=36), nullable=False),
        sa.Column("expense_id", sa.String(length=128), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("payload", JSON_TYPE, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["expense_id"], ["expenses.expense_id"],
            name="fk_workflow_events_expense_id_expenses", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["workflow_run_id"], ["workflow_runs.id"],
            name="fk_workflow_events_workflow_run_id_workflow_runs", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_workflow_events"),
        sa.UniqueConstraint(
            "workflow_run_id", "sequence_number", name="uq_workflow_event_sequence"
        ),
    )
    op.create_index("ix_workflow_events_event_type", "workflow_events", ["event_type"])
    op.create_index("ix_workflow_events_expense_id", "workflow_events", ["expense_id"])
    op.create_index("ix_workflow_events_workflow_run_id", "workflow_events", ["workflow_run_id"])

    op.create_table(
        "approval_tasks",
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("expense_id", sa.String(length=128), nullable=False),
        sa.Column("workflow_run_id", sa.String(length=36), nullable=False),
        sa.Column("approver_role", sa.String(length=255), nullable=False),
        sa.Column("approval_level", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["expense_id"], ["expenses.expense_id"],
            name="fk_approval_tasks_expense_id_expenses", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["workflow_run_id"], ["workflow_runs.id"],
            name="fk_approval_tasks_workflow_run_id_workflow_runs", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("task_id", name="pk_approval_tasks"),
        sa.UniqueConstraint("workflow_run_id", name="uq_approval_task_workflow_run"),
    )
    op.create_index("ix_approval_tasks_expense_id", "approval_tasks", ["expense_id"])
    op.create_index("ix_approval_tasks_status", "approval_tasks", ["status"])
    op.create_index("ix_approval_tasks_workflow_run_id", "approval_tasks", ["workflow_run_id"])

    op.create_table(
        "approval_decisions",
        sa.Column("decision_id", sa.String(length=36), nullable=False),
        sa.Column("approval_task_id", sa.String(length=36), nullable=False),
        sa.Column("expense_id", sa.String(length=128), nullable=False),
        sa.Column("workflow_run_id", sa.String(length=36), nullable=False),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("decided_by", sa.String(length=255), nullable=False),
        sa.Column("comment", sa.Text(), server_default="", nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["approval_task_id"], ["approval_tasks.task_id"],
            name="fk_approval_decisions_approval_task_id_approval_tasks", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["expense_id"], ["expenses.expense_id"],
            name="fk_approval_decisions_expense_id_expenses", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["workflow_run_id"], ["workflow_runs.id"],
            name="fk_approval_decisions_workflow_run_id_workflow_runs", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("decision_id", name="pk_approval_decisions"),
        sa.UniqueConstraint("approval_task_id", name="uq_approval_decision_task"),
    )
    op.create_index("ix_approval_decisions_approval_task_id", "approval_decisions", ["approval_task_id"])
    op.create_index("ix_approval_decisions_expense_id", "approval_decisions", ["expense_id"])
    op.create_index("ix_approval_decisions_workflow_run_id", "approval_decisions", ["workflow_run_id"])


def downgrade() -> None:
    op.drop_table("approval_decisions")
    op.drop_table("approval_tasks")
    op.drop_table("workflow_events")
    op.drop_table("workflow_runs")
    op.drop_table("expenses")
