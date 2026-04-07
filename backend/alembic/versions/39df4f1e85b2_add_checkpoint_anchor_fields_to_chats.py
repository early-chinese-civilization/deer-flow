"""Add checkpoint anchor fields to chats table for Phase 2.5B.

Revision ID: 39df4f1e85b2
Revises: 6bb5f4b36f34
Create Date: 2026-04-06 09:17:38.321809
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "39df4f1e85b2"
down_revision: str | Sequence[str] | None = "6bb5f4b36f34"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add checkpoint anchor fields to chats table.

    These fields establish the link between product truth (chats/messages)
    and runtime truth (checkpointer). They enable targeted reconciliation
    and projection lag detection.
    """
    # Add latest_checkpoint_id: the checkpoint_id of the latest root checkpoint
    op.add_column(
        "chats",
        sa.Column(
            "latest_checkpoint_id",
            sa.String(length=255),
            nullable=True,
            comment="Latest root checkpoint ID from checkpointer",
        ),
    )

    # Add latest_checkpoint_at: when the latest checkpoint was created
    op.add_column(
        "chats",
        sa.Column(
            "latest_checkpoint_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Timestamp of latest checkpoint",
        ),
    )

    # Add projection_synced_at: when messages were last synced from checkpoint
    op.add_column(
        "chats",
        sa.Column(
            "projection_synced_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Last successful projection sync timestamp",
        ),
    )

    # Create index for lag detection queries
    op.create_index(
        "ix_chats_projection_lag",
        "chats",
        ["latest_checkpoint_at", "projection_synced_at"],
    )


def downgrade() -> None:
    """Remove checkpoint anchor fields from chats table."""
    op.drop_index("ix_chats_projection_lag", table_name="chats")
    op.drop_column("chats", "projection_synced_at")
    op.drop_column("chats", "latest_checkpoint_at")
    op.drop_column("chats", "latest_checkpoint_id")
