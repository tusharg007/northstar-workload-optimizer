"""Add durable HITL orchestration and notification state.

Revision ID: 20260812_0002
Revises: 20260812_0001
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260812_0002"
down_revision: str | None = "20260812_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON_TYPE = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    with op.batch_alter_table("approval_tasks") as batch:
        batch.add_column(sa.Column(
            "orchestration_status",
            sa.String(length=32),
            server_default="NOT_STARTED",
            nullable=False,
        ))
        batch.add_column(sa.Column("n8n_execution_id", sa.String(length=64)))
        batch.add_column(sa.Column("n8n_wait_resume_url", sa.Text()))
        batch.add_column(
            sa.Column("orchestration_claimed_at", sa.DateTime(timezone=True))
        )
        batch.add_column(sa.Column("wait_registered_at", sa.DateTime(timezone=True)))
        batch.add_column(
            sa.Column("orchestration_completed_at", sa.DateTime(timezone=True))
        )
        batch.add_column(sa.Column("last_notification_at", sa.DateTime(timezone=True)))
        batch.add_column(
            sa.Column("reminder_count", sa.Integer(), server_default="0", nullable=False)
        )
        batch.add_column(
            sa.Column("escalation_level", sa.Integer(), server_default="0", nullable=False)
        )
        batch.create_index(
            "ix_approval_tasks_orchestration_status", ["orchestration_status"]
        )
        batch.create_unique_constraint(
            "uq_approval_tasks_n8n_execution_id", ["n8n_execution_id"]
        )

    op.create_table(
        "approval_notifications",
        sa.Column("notification_id", sa.String(length=36), nullable=False),
        sa.Column("approval_task_id", sa.String(length=36), nullable=False),
        sa.Column("notification_type", sa.String(length=32), nullable=False),
        sa.Column(
            "escalation_level", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column("status", sa.String(length=32), server_default="PENDING", nullable=False),
        sa.Column("target_role", sa.String(length=255), nullable=False),
        sa.Column("payload", JSON_TYPE, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("provider_message_id", sa.String(length=255)),
        sa.ForeignKeyConstraint(
            ["approval_task_id"],
            ["approval_tasks.task_id"],
            name="fk_approval_notifications_approval_task_id_approval_tasks",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("notification_id", name="pk_approval_notifications"),
        sa.UniqueConstraint(
            "approval_task_id",
            "notification_type",
            "escalation_level",
            name="uq_approval_notification_logical",
        ),
    )
    op.create_index(
        "ix_approval_notifications_approval_task_id",
        "approval_notifications",
        ["approval_task_id"],
    )
    op.create_index(
        "ix_approval_notifications_notification_type",
        "approval_notifications",
        ["notification_type"],
    )
    op.create_index(
        "ix_approval_notifications_status",
        "approval_notifications",
        ["status"],
    )


def downgrade() -> None:
    op.drop_table("approval_notifications")
    with op.batch_alter_table("approval_tasks") as batch:
        batch.drop_constraint(
            "uq_approval_tasks_n8n_execution_id", type_="unique"
        )
        batch.drop_index("ix_approval_tasks_orchestration_status")
        for name in (
            "escalation_level",
            "reminder_count",
            "last_notification_at",
            "orchestration_completed_at",
            "wait_registered_at",
            "orchestration_claimed_at",
            "n8n_wait_resume_url",
            "n8n_execution_id",
            "orchestration_status",
        ):
            batch.drop_column(name)
