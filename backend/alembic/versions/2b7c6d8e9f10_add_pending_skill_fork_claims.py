"""add pending skill fork claims

Revision ID: 2b7c6d8e9f10
Revises: 9f4d2c7b1a63
Create Date: 2026-05-08 00:00:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "2b7c6d8e9f10"
down_revision = "9f4d2c7b1a63"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pending_skill_fork_claims",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("source_skill_definition_id", sa.BigInteger(), nullable=False),
        sa.Column("source_skill_version_id", sa.BigInteger(), nullable=False),
        sa.Column("claim_token_hash", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("source_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["source_skill_definition_id"], ["skill_definitions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_skill_version_id"], ["skill_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_pending_skill_fork_claims_user_status",
        "pending_skill_fork_claims",
        ["user_id", "status", "expires_at"],
    )
    op.create_index(
        "ix_pending_skill_fork_claims_source_version",
        "pending_skill_fork_claims",
        ["source_skill_version_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_pending_skill_fork_claims_source_version", table_name="pending_skill_fork_claims")
    op.drop_index("ix_pending_skill_fork_claims_user_status", table_name="pending_skill_fork_claims")
    op.drop_table("pending_skill_fork_claims")
