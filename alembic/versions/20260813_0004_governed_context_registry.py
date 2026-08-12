"""Add the governed context registry.

Revision ID: 20260813_0004
Revises: 20260813_0003
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260813_0004"
down_revision: str | None = "20260813_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
JSON_TYPE = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "governance_owners",
        sa.Column("owner_id", sa.String(36), primary_key=True),
        sa.Column("owner_key", sa.String(128), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("owner_type", sa.String(16), nullable=False),
        sa.Column("domain", sa.String(128), nullable=False),
        sa.Column("contact_reference", sa.String(255)),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("owner_type IN ('TEAM', 'ROLE', 'PERSON')", name="owner_type"),
        sa.UniqueConstraint("owner_key", name="uq_governance_owners_owner_key"),
    )
    op.create_index("ix_governance_owners_domain", "governance_owners", ["domain"])

    op.create_table(
        "business_terms",
        sa.Column("term_id", sa.String(36), primary_key=True),
        sa.Column("term_key", sa.String(128), nullable=False),
        sa.Column("canonical_name", sa.String(255), nullable=False),
        sa.Column("domain", sa.String(128), nullable=False),
        sa.Column("owner_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["governance_owners.owner_id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("term_key", name="uq_business_terms_term_key"),
    )
    op.create_index("ix_business_terms_domain", "business_terms", ["domain"])
    op.create_index("ix_business_terms_owner_id", "business_terms", ["owner_id"])

    op.create_table(
        "business_term_versions",
        sa.Column("term_version_id", sa.String(36), primary_key=True),
        sa.Column("term_id", sa.String(36), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("definition", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_to", sa.DateTime(timezone=True)),
        sa.Column("review_due_at", sa.DateTime(timezone=True)),
        sa.Column("certified_at", sa.DateTime(timezone=True)),
        sa.Column("source_reference", sa.String(500), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('DRAFT', 'CERTIFIED', 'RETIRED')", name="status"),
        sa.CheckConstraint("effective_to IS NULL OR effective_to >= effective_from", name="effective_window"),
        sa.CheckConstraint("review_due_at IS NULL OR review_due_at >= effective_from", name="review_window"),
        sa.ForeignKeyConstraint(["term_id"], ["business_terms.term_id"], ondelete="CASCADE"),
        sa.UniqueConstraint("term_id", "version_number", name="uq_business_term_version"),
    )
    op.create_index("ix_business_term_versions_term_id", "business_term_versions", ["term_id"])
    op.create_index("ix_business_term_versions_effective", "business_term_versions", ["term_id", "status", "effective_from", "effective_to"])

    op.create_table(
        "policy_definitions",
        sa.Column("policy_id", sa.String(36), primary_key=True),
        sa.Column("policy_key", sa.String(128), nullable=False),
        sa.Column("policy_name", sa.String(255), nullable=False),
        sa.Column("domain", sa.String(128), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("owner_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["governance_owners.owner_id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("policy_key", name="uq_policy_definitions_policy_key"),
    )
    op.create_index("ix_policy_definitions_domain", "policy_definitions", ["domain"])
    op.create_index("ix_policy_definitions_owner_id", "policy_definitions", ["owner_id"])

    op.create_table(
        "policy_versions",
        sa.Column("policy_version_id", sa.String(36), primary_key=True),
        sa.Column("policy_id", sa.String(36), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_to", sa.DateTime(timezone=True)),
        sa.Column("review_due_at", sa.DateTime(timezone=True)),
        sa.Column("certified_at", sa.DateTime(timezone=True)),
        sa.Column("source_reference", sa.String(500), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("metadata", JSON_TYPE, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('DRAFT', 'CERTIFIED', 'RETIRED')", name="status"),
        sa.CheckConstraint("effective_to IS NULL OR effective_to >= effective_from", name="effective_window"),
        sa.CheckConstraint("review_due_at IS NULL OR review_due_at >= effective_from", name="review_window"),
        sa.ForeignKeyConstraint(["policy_id"], ["policy_definitions.policy_id"], ondelete="CASCADE"),
        sa.UniqueConstraint("policy_id", "version_number", name="uq_policy_version"),
    )
    op.create_index("ix_policy_versions_policy_id", "policy_versions", ["policy_id"])
    op.create_index("ix_policy_versions_effective", "policy_versions", ["policy_id", "status", "effective_from", "effective_to"])

    op.create_table(
        "policy_rules",
        sa.Column("rule_id", sa.String(36), primary_key=True),
        sa.Column("policy_version_id", sa.String(36), nullable=False),
        sa.Column("rule_key", sa.String(128), nullable=False),
        sa.Column("rule_name", sa.String(255), nullable=False),
        sa.Column("rule_type", sa.String(64), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("parameters", JSON_TYPE, nullable=False),
        sa.Column("severity", sa.String(32), nullable=False),
        sa.Column("business_term_id", sa.String(36)),
        sa.Column("source_reference", sa.String(500)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["policy_version_id"], ["policy_versions.policy_version_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["business_term_id"], ["business_terms.term_id"], ondelete="SET NULL"),
        sa.UniqueConstraint("policy_version_id", "rule_key", name="uq_policy_rule"),
    )
    op.create_index("ix_policy_rules_policy_version_id", "policy_rules", ["policy_version_id"])
    op.create_index("ix_policy_rules_business_term_id", "policy_rules", ["business_term_id"])

    op.create_table(
        "trust_signals",
        sa.Column("trust_signal_id", sa.String(36), primary_key=True),
        sa.Column("policy_version_id", sa.String(36)),
        sa.Column("business_term_version_id", sa.String(36)),
        sa.Column("signal_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("score", sa.Float()),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("source", sa.String(255), nullable=False),
        sa.Column("details", JSON_TYPE, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("(policy_version_id IS NOT NULL AND business_term_version_id IS NULL) OR (policy_version_id IS NULL AND business_term_version_id IS NOT NULL)", name="exactly_one_target"),
        sa.CheckConstraint("status IN ('PASS', 'WARN', 'FAIL', 'UNKNOWN')", name="status"),
        sa.CheckConstraint("score IS NULL OR (score >= 0 AND score <= 1)", name="score_range"),
        sa.ForeignKeyConstraint(["policy_version_id"], ["policy_versions.policy_version_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["business_term_version_id"], ["business_term_versions.term_version_id"], ondelete="CASCADE"),
    )
    op.create_index("ix_trust_signals_policy", "trust_signals", ["policy_version_id", "signal_type"])
    op.create_index("ix_trust_signals_term", "trust_signals", ["business_term_version_id", "signal_type"])


def downgrade() -> None:
    op.drop_table("trust_signals")
    op.drop_table("policy_rules")
    op.drop_table("policy_versions")
    op.drop_table("policy_definitions")
    op.drop_table("business_term_versions")
    op.drop_table("business_terms")
    op.drop_table("governance_owners")
