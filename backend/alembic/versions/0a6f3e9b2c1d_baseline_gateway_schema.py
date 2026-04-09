"""Baseline Gateway schema for users, workspaces, workspace files, and threads.

Revision ID: 0a6f3e9b2c1d
Revises:
Create Date: 2026-04-09 20:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0a6f3e9b2c1d"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the current Gateway-owned PostgreSQL schema from a single baseline."""
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="User ID"),
        sa.Column("external_auth_id", sa.String(length=255), nullable=False, comment="Keycloak subject (sub)"),
        sa.Column("username", sa.String(length=255), nullable=False, comment="Username"),
        sa.Column("display_name", sa.String(length=255), nullable=False, comment="Display name"),
        sa.Column("email", sa.String(length=255), nullable=True, comment="Email address"),
        sa.Column("given_name", sa.String(length=255), nullable=True, comment="Given name"),
        sa.Column("family_name", sa.String(length=255), nullable=True, comment="Family name"),
        sa.Column("email_verified", sa.Boolean(), nullable=False, comment="Email verified"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, comment="Created at"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, comment="Updated at"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_external_auth_id", "users", ["external_auth_id"], unique=True)

    op.create_table(
        "workspaces",
        sa.Column("id", sa.UUID(), nullable=False, comment="Workspace ID"),
        sa.Column("user_id", sa.BigInteger(), nullable=False, comment="User ID"),
        sa.Column("name", sa.String(length=255), nullable=True, comment="Workspace display name"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, comment="Created at"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, comment="Updated at"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_workspaces_user_id", "workspaces", ["user_id"], unique=False)

    op.create_table(
        "workspace_files",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="File ID"),
        sa.Column("workspace_id", sa.UUID(), nullable=False, comment="Workspace ID"),
        sa.Column("file_path", sa.Text(), nullable=False, comment="Relative path within workspace"),
        sa.Column("content", sa.LargeBinary(), nullable=False, comment="File content"),
        sa.Column("file_size", sa.BigInteger(), nullable=False, comment="File size in bytes"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, comment="Created at"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, comment="Updated at"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "file_path", name="uq_workspace_files_workspace_path"),
    )
    op.create_index("ix_workspace_files_workspace_id", "workspace_files", ["workspace_id"], unique=False)

    op.create_table(
        "threads",
        sa.Column("thread_id", sa.String(length=255), nullable=False, comment="Thread ID"),
        sa.Column("user_id", sa.BigInteger(), nullable=False, comment="User ID"),
        sa.Column("workspace_id", sa.UUID(), nullable=True, comment="Optional bound workspace ID"),
        sa.Column("title", sa.Text(), nullable=True, comment="Thread title"),
        sa.Column("status", sa.String(length=50), nullable=False, comment="Thread status: idle, busy, interrupted, error"),
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
    """Drop the Gateway baseline schema."""
    op.drop_index("ix_threads_status", table_name="threads")
    op.drop_index("ix_threads_user_updated", table_name="threads")
    op.drop_table("threads")
    op.drop_index("ix_workspace_files_workspace_id", table_name="workspace_files")
    op.drop_table("workspace_files")
    op.drop_index("ix_workspaces_user_id", table_name="workspaces")
    op.drop_table("workspaces")
    op.drop_index("ix_users_external_auth_id", table_name="users")
    op.drop_table("users")
