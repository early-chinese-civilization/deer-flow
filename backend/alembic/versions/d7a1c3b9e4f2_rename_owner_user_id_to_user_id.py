"""Rename owner_user_id columns to user_id.

Revision ID: d7a1c3b9e4f2
Revises: a9c1f6e3d2b4
Create Date: 2026-04-09 16:20:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d7a1c3b9e4f2"
down_revision: str | Sequence[str] | None = "a9c1f6e3d2b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _rename_column_if_exists(table_name: str, old_column: str, new_column: str) -> None:
    """Rename a column only when the old name still exists."""
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = '{table_name}'
                  AND column_name = '{old_column}'
            ) THEN
                ALTER TABLE {table_name} RENAME COLUMN {old_column} TO {new_column};
            END IF;
        END $$;
        """
    )


def upgrade() -> None:
    """Rename live business ownership columns and indexes to user_id."""
    _rename_column_if_exists("workspaces", "owner_user_id", "user_id")
    _rename_column_if_exists("threads", "owner_user_id", "user_id")

    op.execute("ALTER INDEX IF EXISTS ix_workspaces_owner_user_id RENAME TO ix_workspaces_user_id")
    op.execute("ALTER INDEX IF EXISTS ix_threads_owner_updated RENAME TO ix_threads_user_updated")


def downgrade() -> None:
    """Restore the old owner_user_id names."""
    _rename_column_if_exists("threads", "user_id", "owner_user_id")
    _rename_column_if_exists("workspaces", "user_id", "owner_user_id")

    op.execute("ALTER INDEX IF EXISTS ix_threads_user_updated RENAME TO ix_threads_owner_updated")
    op.execute("ALTER INDEX IF EXISTS ix_workspaces_user_id RENAME TO ix_workspaces_owner_user_id")
