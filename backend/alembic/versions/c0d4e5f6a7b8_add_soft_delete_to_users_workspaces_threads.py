"""Add soft-delete columns to users, workspaces, and threads.

Revision ID: c0d4e5f6a7b8
Revises: b8f3d0a1c2e4
Create Date: 2026-05-07 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c0d4e5f6a7b8"
down_revision: str | Sequence[str] | None = "b8f3d0a1c2e4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def _has_index(table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def _add_soft_delete_column(table_name: str) -> None:
    if not _has_column(table_name, "deleted_at"):
        op.add_column(
            table_name,
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True, comment="Soft delete timestamp"),
        )

    index_name = f"ix_{table_name}_deleted_at"
    if not _has_index(table_name, index_name):
        op.create_index(index_name, table_name, ["deleted_at"], unique=False)


def upgrade() -> None:
    """Add soft-delete support to the core ownership tables."""
    for table_name in ("users", "workspaces", "threads"):
        _add_soft_delete_column(table_name)


def downgrade() -> None:
    """Remove soft-delete support from the core ownership tables."""
    for table_name in ("threads", "workspaces", "users"):
        index_name = f"ix_{table_name}_deleted_at"
        if _has_index(table_name, index_name):
            op.drop_index(index_name, table_name=table_name)
        if _has_column(table_name, "deleted_at"):
            op.drop_column(table_name, "deleted_at")
