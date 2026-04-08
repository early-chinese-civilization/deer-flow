"""Add workspace tables and bind chats to them.

Revision ID: 53140ca65bbc
Revises: 39df4f1e85b2
Create Date: 2026-04-07 18:42:40.638156
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "53140ca65bbc"
down_revision: str | Sequence[str] | None = "39df4f1e85b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create workspace storage and attach chats via nullable foreign key."""
    op.create_table(
        "workspaces",
        sa.Column("id", sa.UUID(), nullable=False, comment="Workspace ID"),
        sa.Column("owner_user_id", sa.BigInteger(), nullable=False, comment="Owning user ID"),
        sa.Column("name", sa.String(length=255), nullable=True, comment="Workspace display name"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, comment="Created at"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, comment="Updated at"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_workspaces_owner_user_id"), "workspaces", ["owner_user_id"], unique=False)

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
        sa.UniqueConstraint(
            "workspace_id",
            "file_path",
            name="uq_workspace_files_workspace_path",
        ),
    )
    op.create_index(op.f("ix_workspace_files_workspace_id"), "workspace_files", ["workspace_id"], unique=False)

    # Backfill canonical workspaces for legacy chat rows before adding the FK.
    # chats.workspace_id already existed in older schemas as a hidden v1 field.
    op.execute(
        sa.text(
            """
            INSERT INTO workspaces (id, owner_user_id, name, created_at, updated_at)
            SELECT
                chats.workspace_id,
                MIN(chats.owner_user_id) AS owner_user_id,
                NULL AS name,
                NOW() AS created_at,
                NOW() AS updated_at
            FROM chats
            WHERE chats.workspace_id IS NOT NULL
            GROUP BY chats.workspace_id
            """
        )
    )

    op.create_foreign_key(
        "fk_chats_workspace_id",
        "chats",
        "workspaces",
        ["workspace_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """Drop workspace storage and remove chat-to-workspace binding."""
    op.drop_constraint("fk_chats_workspace_id", "chats", type_="foreignkey")
    op.drop_index(op.f("ix_workspace_files_workspace_id"), table_name="workspace_files")
    op.drop_table("workspace_files")
    op.drop_index(op.f("ix_workspaces_owner_user_id"), table_name="workspaces")
    op.drop_table("workspaces")
