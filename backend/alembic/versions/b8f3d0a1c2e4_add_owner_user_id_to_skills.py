"""Add owner_user_id to skills and replace the public unique index.

Revision ID: b8f3d0a1c2e4
Revises: d140aa88cac5
Create Date: 2026-04-17 16:20:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b8f3d0a1c2e4"
down_revision: str | Sequence[str] | None = "d140aa88cac5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def _has_index(table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def _has_foreign_key(table_name: str, fk_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(foreign_key["name"] == fk_name for foreign_key in inspector.get_foreign_keys(table_name))


def upgrade() -> None:
    """Add skill publisher ownership metadata and new uniqueness semantics."""
    if not _has_column("skills", "owner_user_id"):
        op.add_column(
            "skills",
            sa.Column("owner_user_id", sa.BigInteger(), nullable=True, comment="Publisher user ID for public skills"),
        )

    if not _has_foreign_key("skills", "fk_skills_owner_user_id_users"):
        op.create_foreign_key(
            "fk_skills_owner_user_id_users",
            "skills",
            "users",
            ["owner_user_id"],
            ["id"],
            ondelete="SET NULL",
        )

    if _has_index("skills", "uq_skills_system_name_active"):
        op.drop_index("uq_skills_system_name_active", table_name="skills")

    if not _has_index("skills", "ix_skills_owner_user_id"):
        op.create_index("ix_skills_owner_user_id", "skills", ["owner_user_id"], unique=False)

    if not _has_index("skills", "uq_skills_public_owner_name_active"):
        op.create_index(
            "uq_skills_public_owner_name_active",
            "skills",
            ["owner_user_id", "name"],
            unique=True,
            postgresql_where=sa.text("deleted_at IS NULL AND user_id IS NULL AND owner_user_id IS NOT NULL"),
        )


def downgrade() -> None:
    """Remove owner_user_id from skills and restore the old public uniqueness semantics."""
    if _has_index("skills", "uq_skills_public_owner_name_active"):
        op.drop_index("uq_skills_public_owner_name_active", table_name="skills")

    if _has_index("skills", "ix_skills_owner_user_id"):
        op.drop_index("ix_skills_owner_user_id", table_name="skills")

    if not _has_index("skills", "uq_skills_system_name_active"):
        op.create_index(
            "uq_skills_system_name_active",
            "skills",
            ["name"],
            unique=True,
            postgresql_where=sa.text("deleted_at IS NULL AND user_id IS NULL"),
        )

    if _has_foreign_key("skills", "fk_skills_owner_user_id_users"):
        op.drop_constraint("fk_skills_owner_user_id_users", "skills", type_="foreignkey")

    if _has_column("skills", "owner_user_id"):
        op.drop_column("skills", "owner_user_id")
