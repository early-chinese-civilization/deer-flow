"""Make messages a final truth table keyed by source message id.

Revision ID: 6bb5f4b36f34
Revises: 1846bc1de0b0
Create Date: 2026-04-05 22:10:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6bb5f4b36f34"
down_revision: str | Sequence[str] | None = "1846bc1de0b0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add a stable upstream message id for idempotent message sync."""
    op.add_column(
        "messages",
        sa.Column(
            "source_message_id",
            sa.String(length=255),
            nullable=True,
            comment="Stable upstream message identifier",
        ),
    )
    op.execute(
        """
        UPDATE messages
        SET source_message_id = CONCAT('legacy:', seq::text)
        WHERE source_message_id IS NULL
        """
    )
    op.alter_column("messages", "source_message_id", nullable=False)
    op.create_unique_constraint(
        "uq_messages_thread_source_message",
        "messages",
        ["thread_id", "source_message_id"],
    )


def downgrade() -> None:
    """Remove the source-message uniqueness contract."""
    op.drop_constraint("uq_messages_thread_source_message", "messages", type_="unique")
    op.drop_column("messages", "source_message_id")
