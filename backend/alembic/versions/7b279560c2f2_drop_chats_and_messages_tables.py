"""Drop chats and messages tables after Store-first thread simplification.

Revision ID: 7b279560c2f2
Revises: 53140ca65bbc
Create Date: 2026-04-08 18:40:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7b279560c2f2"
down_revision: str | Sequence[str] | None = "53140ca65bbc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Remove the legacy PG thread projection tables."""
    op.drop_table("messages")
    op.drop_table("chats")


def downgrade() -> None:
    """Recreate the legacy PG thread projection tables."""
    op.create_table(
        "chats",
        sa.Column("thread_id", sa.UUID(), nullable=False, comment="LangGraph thread ID"),
        sa.Column("owner_user_id", sa.BigInteger(), nullable=False, comment="Owning user ID"),
        sa.Column(
            "workspace_id",
            sa.UUID(),
            nullable=True,
            comment="Hidden workspace ID for v1 auto-created workspaces",
        ),
        sa.Column("agent_id", sa.Text(), nullable=True, comment="Bound agent identifier"),
        sa.Column(
            "agent_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="Frozen agent snapshot",
        ),
        sa.Column("title", sa.Text(), nullable=True, comment="Chat title"),
        sa.Column(
            "status",
            sa.String(length=50),
            nullable=False,
            comment="Chat status: idle, busy, interrupted, error",
        ),
        sa.Column(
            "latest_checkpoint_id",
            sa.String(length=255),
            nullable=True,
            comment="Latest root checkpoint ID from checkpointer",
        ),
        sa.Column(
            "latest_checkpoint_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Timestamp of latest checkpoint",
        ),
        sa.Column(
            "projection_synced_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Last successful projection sync timestamp",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, comment="Created at"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, comment="Updated at"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("thread_id"),
    )
    op.create_index("ix_chats_owner_updated", "chats", ["owner_user_id", "updated_at"], unique=False)
    op.create_index("ix_chats_projection_lag", "chats", ["latest_checkpoint_at", "projection_synced_at"], unique=False)
    op.create_index(op.f("ix_chats_owner_user_id"), "chats", ["owner_user_id"], unique=False)
    op.create_index(op.f("ix_chats_workspace_id"), "chats", ["workspace_id"], unique=False)

    op.create_table(
        "messages",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="Message ID"),
        sa.Column("thread_id", sa.UUID(), nullable=False, comment="Thread ID"),
        sa.Column(
            "source_message_id",
            sa.String(length=255),
            nullable=False,
            comment="Stable upstream message identifier",
        ),
        sa.Column("role", sa.String(length=50), nullable=False, comment="Message role"),
        sa.Column("content", sa.Text(), nullable=False, comment="Message content"),
        sa.Column("seq", sa.BigInteger(), nullable=False, comment="Final display order within the thread"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, comment="Created at"),
        sa.ForeignKeyConstraint(["thread_id"], ["chats.thread_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("thread_id", "seq", name="uq_messages_thread_seq"),
        sa.UniqueConstraint(
            "thread_id",
            "source_message_id",
            name="uq_messages_thread_source_message",
        ),
    )
    op.create_index("ix_messages_thread_created", "messages", ["thread_id", "created_at"], unique=False)
    op.create_index(op.f("ix_messages_thread_id"), "messages", ["thread_id"], unique=False)
