"""add system skill agent bindings

Revision ID: 7d3a2b1c0e9f
Revises: 2b7c6d8e9f10
Create Date: 2026-05-08 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "7d3a2b1c0e9f"
down_revision = "2b7c6d8e9f10"
branch_labels = None
depends_on = None


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def _has_check_constraint(table_name: str, constraint_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(constraint["name"] == constraint_name for constraint in inspector.get_check_constraints(table_name))


def _has_index(table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def upgrade() -> None:
    if not _has_column("agents_skills", "system_skill_definition_id"):
        op.add_column(
            "agents_skills",
            sa.Column("system_skill_definition_id", sa.BigInteger(), nullable=True, comment="Direct system SkillDefinition binding for platform-provided skills"),
        )
    if not _has_column("agents_skills", "system_skill_version_id"):
        op.add_column(
            "agents_skills",
            sa.Column("system_skill_version_id", sa.BigInteger(), nullable=True, comment="Direct system SkillVersion binding resolved by runtime manifest"),
        )

    op.create_foreign_key(
        "fk_agents_skills_system_skill_definition_id_skill_definitions",
        "agents_skills",
        "skill_definitions",
        ["system_skill_definition_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_agents_skills_system_skill_version_id_skill_versions",
        "agents_skills",
        "skill_versions",
        ["system_skill_version_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    if _has_check_constraint("agents_skills", "ck_agents_skills_has_skill_or_install"):
        op.drop_constraint("ck_agents_skills_has_skill_or_install", "agents_skills", type_="check")
    op.create_check_constraint(
        "ck_agents_skills_has_skill_or_install",
        "agents_skills",
        "skill_id IS NOT NULL OR skill_install_id IS NOT NULL OR system_skill_version_id IS NOT NULL",
    )
    op.create_check_constraint(
        "ck_agents_skills_system_version_has_definition",
        "agents_skills",
        "system_skill_version_id IS NULL OR system_skill_definition_id IS NOT NULL",
    )

    if not _has_index("agents_skills", "uq_agents_system_skill_versions_active"):
        op.create_index(
            "uq_agents_system_skill_versions_active",
            "agents_skills",
            ["agent_id", "system_skill_version_id"],
            unique=True,
            postgresql_where=sa.text("deleted_at IS NULL AND system_skill_version_id IS NOT NULL"),
        )
    if not _has_index("agents_skills", "ix_agents_skills_system_skill_version_id"):
        op.create_index("ix_agents_skills_system_skill_version_id", "agents_skills", ["system_skill_version_id"])


def downgrade() -> None:
    if _has_index("agents_skills", "ix_agents_skills_system_skill_version_id"):
        op.drop_index("ix_agents_skills_system_skill_version_id", table_name="agents_skills")
    if _has_index("agents_skills", "uq_agents_system_skill_versions_active"):
        op.drop_index("uq_agents_system_skill_versions_active", table_name="agents_skills")
    if _has_check_constraint("agents_skills", "ck_agents_skills_system_version_has_definition"):
        op.drop_constraint("ck_agents_skills_system_version_has_definition", "agents_skills", type_="check")
    if _has_check_constraint("agents_skills", "ck_agents_skills_has_skill_or_install"):
        op.drop_constraint("ck_agents_skills_has_skill_or_install", "agents_skills", type_="check")
    op.create_check_constraint(
        "ck_agents_skills_has_skill_or_install",
        "agents_skills",
        "skill_id IS NOT NULL OR skill_install_id IS NOT NULL",
    )
    op.drop_constraint("fk_agents_skills_system_skill_version_id_skill_versions", "agents_skills", type_="foreignkey")
    op.drop_constraint("fk_agents_skills_system_skill_definition_id_skill_definitions", "agents_skills", type_="foreignkey")
    if _has_column("agents_skills", "system_skill_version_id"):
        op.drop_column("agents_skills", "system_skill_version_id")
    if _has_column("agents_skills", "system_skill_definition_id"):
        op.drop_column("agents_skills", "system_skill_definition_id")
