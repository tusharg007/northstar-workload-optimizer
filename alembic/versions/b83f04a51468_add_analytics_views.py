"""add analytics views

Revision ID: b83f04a51468
Revises: 20260813_0006
Create Date: 2026-08-31 20:25:32.663633
"""

from typing import Sequence

from alembic import op


revision: str = "b83f04a51468"
down_revision: str | None = "20260813_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    op.execute(
        """
        CREATE VIEW observability.daily_expense_summary AS
        SELECT
            DATE(e.created_at) AS report_date,
            e.department,
            e.category,
            e.risk_level,
            e.status,
            COUNT(*) AS expense_count,
            SUM(e.amount) AS total_amount,
            AVG(e.amount) AS avg_amount
        FROM expenses e
        GROUP BY
            DATE(e.created_at),
            e.department,
            e.category,
            e.risk_level,
            e.status
        """
    )
    op.execute(
        """
        CREATE VIEW observability.approval_turnaround AS
        SELECT
            e.risk_level,
            e.status,
            AVG(
                EXTRACT(EPOCH FROM (
                    at.orchestration_completed_at - at.created_at
                ))
            ) AS avg_seconds,
            PERCENTILE_CONT(0.95) WITHIN GROUP (
                ORDER BY EXTRACT(EPOCH FROM (
                    at.orchestration_completed_at - at.created_at
                ))
            ) AS p95_seconds,
            COUNT(*) AS decision_count
        FROM expenses e
        JOIN approval_tasks at ON e.expense_id = at.expense_id
        WHERE at.orchestration_completed_at IS NOT NULL
        GROUP BY e.risk_level, e.status
        """
    )
    op.execute(
        """
        CREATE VIEW observability.risk_distribution AS
        SELECT
            risk_level,
            COUNT(*) AS count,
            ROUND(
                COUNT(*) * 100.0 / NULLIF(SUM(COUNT(*)) OVER (), 0),
                1
            ) AS percentage
        FROM expenses
        GROUP BY risk_level
        """
    )
    op.execute(
        """
        CREATE VIEW observability.department_spend AS
        SELECT
            department,
            DATE_TRUNC('month', created_at) AS month,
            SUM(amount) AS total_spend,
            COUNT(*) AS expense_count,
            AVG(amount) AS avg_expense
        FROM expenses
        GROUP BY department, DATE_TRUNC('month', created_at)
        """
    )

    # The role is created after migrations in a fresh Compose deployment. Grant
    # immediately on upgrades where it already exists; the role reconciler grants
    # all observability views when creating it on a fresh deployment.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_roles WHERE rolname = 'northstar_metabase_ro'
            ) THEN
                EXECUTE 'GRANT SELECT ON '
                    'observability.daily_expense_summary, '
                    'observability.approval_turnaround, '
                    'observability.risk_distribution, '
                    'observability.department_spend '
                    'TO northstar_metabase_ro';
            END IF;
        END
        $$
        """
    )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    op.execute("DROP VIEW IF EXISTS observability.department_spend")
    op.execute("DROP VIEW IF EXISTS observability.risk_distribution")
    op.execute("DROP VIEW IF EXISTS observability.approval_turnaround")
    op.execute("DROP VIEW IF EXISTS observability.daily_expense_summary")
