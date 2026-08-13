"""Add immutable decision provenance evidence.

Revision ID: 20260813_0005
Revises: 20260813_0004
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260813_0005"
down_revision: str | None = "20260813_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
JSON_TYPE = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "decision_provenance",
        sa.Column("provenance_id", sa.String(36), primary_key=True),
        sa.Column("expense_id", sa.String(128), nullable=False),
        sa.Column("workflow_run_id", sa.String(36), nullable=False),
        sa.Column("correlation_id", sa.String(128), nullable=False),
        sa.Column("source_payload_hash", sa.String(64), nullable=False),
        sa.Column("context_as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("context_resolved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("automated_status", sa.String(64), nullable=False),
        sa.Column("risk_level", sa.String(32)),
        sa.Column("approver_role", sa.String(255)),
        sa.Column("automated_reason", sa.Text()),
        sa.Column("context_trust_state", sa.String(32), nullable=False),
        sa.Column("decision_engine_version", sa.String(128), nullable=False),
        sa.Column("risk_engine_version", sa.String(128), nullable=False),
        sa.Column("risk_catalog_hash", sa.String(64), nullable=False),
        sa.Column("build_revision", sa.String(128)),
        sa.Column("provenance_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["expense_id"], ["expenses.expense_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["workflow_run_id"], ["workflow_runs.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("workflow_run_id", name="uq_decision_provenance_workflow_run"),
    )
    op.create_index("ix_decision_provenance_expense_id", "decision_provenance", ["expense_id"])
    op.create_index("ix_decision_provenance_correlation_id", "decision_provenance", ["correlation_id"])

    op.create_table(
        "decision_policy_evidence",
        sa.Column("evidence_id", sa.String(36), primary_key=True),
        sa.Column("provenance_id", sa.String(36), nullable=False),
        sa.Column("policy_id", sa.String(36), nullable=False),
        sa.Column("policy_version_id", sa.String(36), nullable=False),
        sa.Column("policy_key", sa.String(128), nullable=False),
        sa.Column("policy_name", sa.String(255), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("owner_key", sa.String(128), nullable=False),
        sa.Column("owner_display_name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_to", sa.DateTime(timezone=True)),
        sa.Column("trust_state", sa.String(32), nullable=False),
        sa.Column("snapshot_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["provenance_id"], ["decision_provenance.provenance_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["policy_id"], ["policy_definitions.policy_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["policy_version_id"], ["policy_versions.policy_version_id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("provenance_id", "policy_version_id", name="uq_decision_policy_evidence"),
    )
    op.create_index("ix_decision_policy_key_version", "decision_policy_evidence", ["policy_key", "version_number"])

    op.create_table(
        "decision_term_evidence",
        sa.Column("evidence_id", sa.String(36), primary_key=True),
        sa.Column("provenance_id", sa.String(36), nullable=False),
        sa.Column("business_term_id", sa.String(36), nullable=False),
        sa.Column("business_term_version_id", sa.String(36), nullable=False),
        sa.Column("term_key", sa.String(128), nullable=False),
        sa.Column("canonical_name", sa.String(255), nullable=False),
        sa.Column("definition", sa.Text(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("owner_key", sa.String(128), nullable=False),
        sa.Column("trust_state", sa.String(32), nullable=False),
        sa.Column("snapshot_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["provenance_id"], ["decision_provenance.provenance_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["business_term_id"], ["business_terms.term_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["business_term_version_id"], ["business_term_versions.term_version_id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("provenance_id", "business_term_version_id", name="uq_decision_term_evidence"),
    )
    op.create_index("ix_decision_term_key_version", "decision_term_evidence", ["term_key", "version_number"])

    op.create_table(
        "decision_rule_evidence",
        sa.Column("evidence_id", sa.String(36), primary_key=True),
        sa.Column("provenance_id", sa.String(36), nullable=False),
        sa.Column("policy_version_id", sa.String(36), nullable=False),
        sa.Column("policy_rule_id", sa.String(36), nullable=False),
        sa.Column("rule_key", sa.String(128), nullable=False),
        sa.Column("rule_name", sa.String(255), nullable=False),
        sa.Column("rule_type", sa.String(64), nullable=False),
        sa.Column("severity", sa.String(32), nullable=False),
        sa.Column("parameters", JSON_TYPE, nullable=False),
        sa.Column("evaluation_status", sa.String(32), nullable=False),
        sa.Column("triggered", sa.Boolean(), nullable=False),
        sa.Column("observed_value", JSON_TYPE),
        sa.Column("evaluation_details", JSON_TYPE, nullable=False),
        sa.Column("evidence_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["provenance_id"], ["decision_provenance.provenance_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["policy_version_id"], ["policy_versions.policy_version_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["policy_rule_id"], ["policy_rules.rule_id"], ondelete="RESTRICT"),
        sa.CheckConstraint("evaluation_status IN ('PASSED','FAILED','TRIGGERED','NOT_APPLICABLE')", name="evaluation_status"),
        sa.UniqueConstraint("provenance_id", "policy_rule_id", name="uq_decision_rule_evidence"),
    )
    op.create_index("ix_decision_rule_key_triggered", "decision_rule_evidence", ["rule_key", "triggered"])

    op.create_table(
        "decision_trust_evidence",
        sa.Column("evidence_id", sa.String(36), primary_key=True),
        sa.Column("provenance_id", sa.String(36), nullable=False),
        sa.Column("trust_signal_id", sa.String(36)),
        sa.Column("target_type", sa.String(32), nullable=False),
        sa.Column("target_key", sa.String(128), nullable=False),
        sa.Column("signal_type", sa.String(64), nullable=False),
        sa.Column("signal_status", sa.String(16), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("source", sa.String(255), nullable=False),
        sa.Column("details", JSON_TYPE, nullable=False),
        sa.Column("evidence_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["provenance_id"], ["decision_provenance.provenance_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["trust_signal_id"], ["trust_signals.trust_signal_id"], ondelete="SET NULL"),
    )
    op.create_index("ix_decision_trust_target", "decision_trust_evidence", ["target_type", "target_key"])

    op.create_table(
        "decision_risk_evidence",
        sa.Column("evidence_id", sa.String(36), primary_key=True),
        sa.Column("provenance_id", sa.String(36), nullable=False),
        sa.Column("signal_key", sa.String(128), nullable=False),
        sa.Column("canonical_name", sa.String(255), nullable=False),
        sa.Column("engine_component", sa.String(128), nullable=False),
        sa.Column("triggered", sa.Boolean(), nullable=False),
        sa.Column("observed_value", JSON_TYPE),
        sa.Column("threshold_or_reference", JSON_TYPE),
        sa.Column("details", JSON_TYPE, nullable=False),
        sa.Column("signal_definition_hash", sa.String(64), nullable=False),
        sa.Column("risk_catalog_hash", sa.String(64), nullable=False),
        sa.Column("evidence_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["provenance_id"], ["decision_provenance.provenance_id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("provenance_id", "signal_key", name="uq_decision_risk_evidence"),
    )
    op.create_index("ix_decision_risk_key_triggered", "decision_risk_evidence", ["signal_key", "triggered"])

    op.create_table(
        "decision_human_evidence",
        sa.Column("human_evidence_id", sa.String(36), primary_key=True),
        sa.Column("provenance_id", sa.String(36), nullable=False),
        sa.Column("approval_decision_id", sa.String(36), nullable=False),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("decided_by", sa.String(255), nullable=False),
        sa.Column("comment", sa.Text(), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evidence_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["provenance_id"], ["decision_provenance.provenance_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["approval_decision_id"], ["approval_decisions.decision_id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("approval_decision_id", name="uq_decision_human_approval"),
    )


def downgrade() -> None:
    op.drop_table("decision_human_evidence")
    op.drop_table("decision_risk_evidence")
    op.drop_table("decision_trust_evidence")
    op.drop_table("decision_rule_evidence")
    op.drop_table("decision_term_evidence")
    op.drop_table("decision_policy_evidence")
    op.drop_table("decision_provenance")
