"""Add transactional outbox, delivery attempts, and workflow failures.

Revision ID: 20260813_0003
Revises: 20260812_0002
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260813_0003"
down_revision: str | None = "20260812_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
JSON_TYPE = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "outbox_events",
        sa.Column("outbox_event_id", sa.String(36), primary_key=True),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("aggregate_type", sa.String(64), nullable=False),
        sa.Column("aggregate_id", sa.String(128), nullable=False),
        sa.Column("correlation_id", sa.String(128)),
        sa.Column("delivery_key", sa.String(255), nullable=False),
        sa.Column("payload", JSON_TYPE, nullable=False),
        sa.Column("status", sa.String(32), server_default="PENDING", nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default="4", nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_owner", sa.String(128)),
        sa.Column("lease_acquired_at", sa.DateTime(timezone=True)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("last_error_category", sa.String(64)),
        sa.Column("last_error_message", sa.String(500)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True)),
        sa.Column("dead_lettered_at", sa.DateTime(timezone=True)),
        sa.Column("replay_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("delivery_key", name="uq_outbox_events_delivery_key"),
    )
    op.create_index("ix_outbox_events_due", "outbox_events", ["status", "next_attempt_at"])
    op.create_index("ix_outbox_events_aggregate", "outbox_events", ["aggregate_type", "aggregate_id"])
    op.create_index("ix_outbox_events_correlation_id", "outbox_events", ["correlation_id"])
    op.create_index("ix_outbox_events_next_attempt_at", "outbox_events", ["next_attempt_at"])
    op.create_index("ix_outbox_events_lease_expires_at", "outbox_events", ["lease_expires_at"])

    op.create_table(
        "outbox_delivery_attempts",
        sa.Column("attempt_id", sa.String(36), primary_key=True),
        sa.Column("outbox_event_id", sa.String(36), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("worker_id", sa.String(128), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column("status_code", sa.Integer()),
        sa.Column("error_category", sa.String(64)),
        sa.Column("safe_error_message", sa.String(500)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["outbox_event_id"], ["outbox_events.outbox_event_id"], ondelete="CASCADE", name="fk_outbox_delivery_attempts_outbox_event_id_outbox_events"),
        sa.UniqueConstraint("outbox_event_id", "attempt_number", name="uq_outbox_attempt_number"),
    )
    op.create_index("ix_outbox_delivery_attempts_outbox_event_id", "outbox_delivery_attempts", ["outbox_event_id"])

    op.create_table(
        "workflow_failures",
        sa.Column("failure_id", sa.String(36), primary_key=True),
        sa.Column("workflow_id", sa.String(128), nullable=False),
        sa.Column("workflow_name", sa.String(255), nullable=False),
        sa.Column("execution_id", sa.String(64), nullable=False),
        sa.Column("failed_node", sa.String(255)),
        sa.Column("error_class", sa.String(128)),
        sa.Column("safe_message", sa.String(500), nullable=False),
        sa.Column("correlation_id", sa.String(128)),
        sa.Column("expense_id", sa.String(128)),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("occurrence_count", sa.Integer(), server_default="1", nullable=False),
        sa.Column("status", sa.String(32), server_default="OPEN", nullable=False),
        sa.UniqueConstraint("workflow_id", "execution_id", name="uq_workflow_failure_execution"),
    )
    op.create_index("ix_workflow_failures_correlation_id", "workflow_failures", ["correlation_id"])
    op.create_index("ix_workflow_failures_expense_id", "workflow_failures", ["expense_id"])


def downgrade() -> None:
    op.drop_table("workflow_failures")
    op.drop_table("outbox_delivery_attempts")
    op.drop_table("outbox_events")
