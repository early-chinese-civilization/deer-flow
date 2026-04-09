"""Add canonical threads table.

Revision ID: a9c1f6e3d2b4
Revises: 7b279560c2f2
Create Date: 2026-04-08 22:40:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a9c1f6e3d2b4"
down_revision: str | Sequence[str] | None = "7b279560c2f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the canonical threads table."""
    op.create_table(
        "threads",
        sa.Column("thread_id", sa.String(length=255), nullable=False, comment="Thread ID"),
        sa.Column("user_id", sa.BigInteger(), nullable=False, comment="User ID"),
        sa.Column("workspace_id", sa.UUID(), nullable=True, comment="Optional bound workspace ID"),
        sa.Column("title", sa.Text(), nullable=True, comment="Thread title"),
        sa.Column(
            "status",
            sa.String(length=50),
            nullable=False,
            comment="Thread status: idle, busy, interrupted, error",
        ),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
            comment="Thread metadata",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, comment="Created at"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, comment="Updated at"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("thread_id"),
    )
    op.create_index("ix_threads_user_updated", "threads", ["user_id", "updated_at"], unique=False)
    op.create_index("ix_threads_status", "threads", ["status"], unique=False)


def downgrade() -> None:
    """Drop the canonical threads table."""
    op.drop_index("ix_threads_status", table_name="threads")
    op.drop_index("ix_threads_user_updated", table_name="threads")
    op.drop_table("threads")
