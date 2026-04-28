"""Add immutable skill release records.

Revision ID: e2a7c9d4f601
Revises: b8f3d0a1c2e4
Create Date: 2026-04-28 16:12:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e2a7c9d4f601"
down_revision: str | Sequence[str] | None = "b8f3d0a1c2e4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_table(table_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return table_name in inspector.get_table_names()


def _has_index(table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def upgrade() -> None:
    """Create skill release history table."""
    if not _has_table("skill_releases"):
        op.create_table(
            "skill_releases",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="Skill release ID"),
            sa.Column("skill_name", sa.String(length=255), nullable=False, comment="Published skill name"),
            sa.Column("release_version", sa.String(length=64), nullable=False, comment="System-generated immutable release version"),
            sa.Column("package_version", sa.String(length=255), nullable=True, comment="Optional SKILL.md package version"),
            sa.Column("description", sa.Text(), nullable=True, comment="Skill description at publish time"),
            sa.Column("status", sa.String(length=50), nullable=False, comment="Release status"),
            sa.Column("artifact_path", sa.String(length=500), nullable=False, comment="Published artifact filesystem path"),
            sa.Column("publisher_user_id", sa.BigInteger(), nullable=True, comment="Publisher user ID"),
            sa.Column("source_skill_id", sa.BigInteger(), nullable=True, comment="Source custom skill ID"),
            sa.Column("published_skill_id", sa.BigInteger(), nullable=True, comment="Public latest skill row produced by this release"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, comment="Created at"),
            sa.ForeignKeyConstraint(["publisher_user_id"], ["users.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["source_skill_id"], ["skills.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["published_skill_id"], ["skills.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("release_version", name="uq_skill_releases_release_version"),
        )

    if not _has_index("skill_releases", "ix_skill_releases_skill_name_created"):
        op.create_index("ix_skill_releases_skill_name_created", "skill_releases", ["skill_name", "created_at"], unique=False)
    if not _has_index("skill_releases", "ix_skill_releases_published_skill_id"):
        op.create_index("ix_skill_releases_published_skill_id", "skill_releases", ["published_skill_id"], unique=False)
    if not _has_index("skill_releases", "ix_skill_releases_status"):
        op.create_index("ix_skill_releases_status", "skill_releases", ["status"], unique=False)


def downgrade() -> None:
    """Drop skill release history table."""
    if _has_table("skill_releases"):
        if _has_index("skill_releases", "ix_skill_releases_status"):
            op.drop_index("ix_skill_releases_status", table_name="skill_releases")
        if _has_index("skill_releases", "ix_skill_releases_published_skill_id"):
            op.drop_index("ix_skill_releases_published_skill_id", table_name="skill_releases")
        if _has_index("skill_releases", "ix_skill_releases_skill_name_created"):
            op.drop_index("ix_skill_releases_skill_name_created", table_name="skill_releases")
        op.drop_table("skill_releases")
