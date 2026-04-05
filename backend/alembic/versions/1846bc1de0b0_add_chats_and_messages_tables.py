"""Add chats and messages tables for Phase 2 ownership tracking.

Revision ID: 1846bc1de0b0
Revises: f5df985ff456
Create Date: 2026-04-05 14:51:15.338658
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1846bc1de0b0"
down_revision: str | Sequence[str] | None = "f5df985ff456"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the Phase 2 chats/messages product tables."""
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
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, comment="Created at"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, comment="Updated at"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("thread_id"),
    )
    op.create_index("ix_chats_owner_updated", "chats", ["owner_user_id", "updated_at"], unique=False)
    op.create_index(op.f("ix_chats_owner_user_id"), "chats", ["owner_user_id"], unique=False)
    op.create_index(op.f("ix_chats_workspace_id"), "chats", ["workspace_id"], unique=False)

    op.create_table(
        "messages",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="Message ID"),
        sa.Column("thread_id", sa.UUID(), nullable=False, comment="Thread ID"),
        sa.Column("role", sa.String(length=50), nullable=False, comment="Message role"),
        sa.Column("content", sa.Text(), nullable=False, comment="Message content"),
        sa.Column(
            "seq",
            sa.BigInteger(),
            nullable=False,
            comment="Final display order within the thread",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, comment="Created at"),
        sa.ForeignKeyConstraint(["thread_id"], ["chats.thread_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("thread_id", "seq", name="uq_messages_thread_seq"),
    )
    op.create_index("ix_messages_thread_created", "messages", ["thread_id", "created_at"], unique=False)
    op.create_index(op.f("ix_messages_thread_id"), "messages", ["thread_id"], unique=False)


def downgrade() -> None:
    """Drop the Phase 2 chats/messages tables."""
    op.drop_index(op.f("ix_messages_thread_id"), table_name="messages")
    op.drop_index("ix_messages_thread_created", table_name="messages")
    op.drop_table("messages")
    op.drop_index(op.f("ix_chats_workspace_id"), table_name="chats")
    op.drop_index(op.f("ix_chats_owner_user_id"), table_name="chats")
    op.drop_index("ix_chats_owner_updated", table_name="chats")
    op.drop_table("chats")
