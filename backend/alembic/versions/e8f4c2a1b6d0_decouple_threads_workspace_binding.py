"""Decouple thread/workspace schema bindings.

Revision ID: e8f4c2a1b6d0
Revises: d7a1c3b9e4f2
Create Date: 2026-04-09 16:45:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e8f4c2a1b6d0"
down_revision: str | Sequence[str] | None = "d7a1c3b9e4f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Drop the one-thread-one-workspace constraint and use SET NULL semantics."""
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'threads'
                  AND column_name = 'workspace_id'
                  AND is_nullable = 'NO'
            ) THEN
                ALTER TABLE threads ALTER COLUMN workspace_id DROP NOT NULL;
            END IF;
        END $$;
        """
    )
    op.execute("ALTER TABLE threads DROP CONSTRAINT IF EXISTS threads_workspace_id_key")
    op.execute("ALTER TABLE threads DROP CONSTRAINT IF EXISTS threads_workspace_id_fkey")
    op.execute(
        """
        ALTER TABLE threads
        ADD CONSTRAINT threads_workspace_id_fkey
        FOREIGN KEY (workspace_id) REFERENCES workspaces (id) ON DELETE SET NULL
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM information_schema.table_constraints
                WHERE table_schema = 'public'
                  AND table_name = 'workspaces'
                  AND constraint_name = 'workspaces_owner_user_id_fkey'
            ) THEN
                ALTER TABLE workspaces RENAME CONSTRAINT workspaces_owner_user_id_fkey TO workspaces_user_id_fkey;
            END IF;
            IF EXISTS (
                SELECT 1
                FROM information_schema.table_constraints
                WHERE table_schema = 'public'
                  AND table_name = 'threads'
                  AND constraint_name = 'threads_owner_user_id_fkey'
            ) THEN
                ALTER TABLE threads RENAME CONSTRAINT threads_owner_user_id_fkey TO threads_user_id_fkey;
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    """Restore the old one-to-one workspace binding."""
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM information_schema.table_constraints
                WHERE table_schema = 'public'
                  AND table_name = 'threads'
                  AND constraint_name = 'threads_user_id_fkey'
            ) THEN
                ALTER TABLE threads RENAME CONSTRAINT threads_user_id_fkey TO threads_owner_user_id_fkey;
            END IF;
            IF EXISTS (
                SELECT 1
                FROM information_schema.table_constraints
                WHERE table_schema = 'public'
                  AND table_name = 'workspaces'
                  AND constraint_name = 'workspaces_user_id_fkey'
            ) THEN
                ALTER TABLE workspaces RENAME CONSTRAINT workspaces_user_id_fkey TO workspaces_owner_user_id_fkey;
            END IF;
        END $$;
        """
    )
    op.execute("ALTER TABLE threads DROP CONSTRAINT IF EXISTS threads_workspace_id_fkey")
    op.execute(
        """
        ALTER TABLE threads
        ADD CONSTRAINT threads_workspace_id_fkey
        FOREIGN KEY (workspace_id) REFERENCES workspaces (id) ON DELETE CASCADE
        """
    )
    op.execute("ALTER TABLE threads ADD CONSTRAINT threads_workspace_id_key UNIQUE (workspace_id)")
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'threads'
                  AND column_name = 'workspace_id'
                  AND is_nullable = 'YES'
            ) THEN
                ALTER TABLE threads ALTER COLUMN workspace_id SET NOT NULL;
            END IF;
        END $$;
        """
    )
