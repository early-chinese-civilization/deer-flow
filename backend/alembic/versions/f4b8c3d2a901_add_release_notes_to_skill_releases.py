"""Add release notes to skill releases.

Revision ID: f4b8c3d2a901
Revises: e2a7c9d4f601
Create Date: 2026-04-28 18:22:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f4b8c3d2a901"
down_revision: str | Sequence[str] | None = "e2a7c9d4f601"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    """Store optional publish-event release notes."""
    if not _has_column("skill_releases", "release_notes"):
        op.add_column(
            "skill_releases",
            sa.Column("release_notes", sa.Text(), nullable=True, comment="Optional notes for this publish event"),
        )


def downgrade() -> None:
    """Remove publish-event release notes."""
    if _has_column("skill_releases", "release_notes"):
        op.drop_column("skill_releases", "release_notes")
