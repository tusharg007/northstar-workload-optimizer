"""Add sanitized PostgreSQL observability views.

Revision ID: 20260813_0006
Revises: 20260813_0005
"""

from pathlib import Path
from typing import Sequence

from alembic import op

revision: str = "20260813_0006"
down_revision: str | None = "20260813_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

VIEW_FILES = (
    "expense_operations.sql",
    "approval_sla.sql",
    "reliability_outbox.sql",
    "delivery_attempts.sql",
    "workflow_failures.sql",
    "context_policy_health.sql",
    "context_term_health.sql",
    "decision_provenance_quality.sql",
    "risk_signal_activity.sql",
)
SQL_DIR = Path(__file__).resolve().parents[2] / "observability" / "sql"


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("CREATE SCHEMA observability")
    for filename in VIEW_FILES:
        op.execute((SQL_DIR / filename).read_text(encoding="utf-8"))


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("DROP SCHEMA IF EXISTS observability CASCADE")
