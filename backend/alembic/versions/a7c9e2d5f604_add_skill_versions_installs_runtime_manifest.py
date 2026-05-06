"""add skill versions installs runtime manifest

Revision ID: a7c9e2d5f604
Revises: f4b8c3d2a901
Create Date: 2026-05-06 00:00:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "a7c9e2d5f604"
down_revision = "f4b8c3d2a901"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "skill_definitions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("owner_user_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_skill_definitions_name_active",
        "skill_definitions",
        ["name"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index("ix_skill_definitions_deleted_at", "skill_definitions", ["deleted_at"])

    op.create_table(
        "skill_versions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("skill_definition_id", sa.BigInteger(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("source_package_version", sa.String(length=255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("content_hash", sa.String(length=128), nullable=False),
        sa.Column("file_manifest_hash", sa.String(length=128), nullable=False),
        sa.Column("artifact_uri", sa.String(length=500), nullable=False),
        sa.Column("created_by_user_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["skill_definition_id"], ["skill_definitions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("skill_definition_id", "version_number", name="uq_skill_versions_definition_version"),
        sa.UniqueConstraint("skill_definition_id", "content_hash", name="uq_skill_versions_definition_content_hash"),
    )
    op.create_index("ix_skill_versions_definition_created", "skill_versions", ["skill_definition_id", "created_at"])

    op.create_table(
        "skill_installs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("skill_definition_id", sa.BigInteger(), nullable=False),
        sa.Column("installed_version_id", sa.BigInteger(), nullable=False),
        sa.Column("current_version_id", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["current_version_id"], ["skill_versions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["installed_version_id"], ["skill_versions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["skill_definition_id"], ["skill_definitions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_skill_installs_user_definition_active",
        "skill_installs",
        ["user_id", "skill_definition_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index("ix_skill_installs_current_version_id", "skill_installs", ["current_version_id"])
    op.create_index("ix_skill_installs_deleted_at", "skill_installs", ["deleted_at"])

    op.add_column("skill_releases", sa.Column("skill_version_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        "fk_skill_releases_skill_version_id_skill_versions",
        "skill_releases",
        "skill_versions",
        ["skill_version_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_skill_releases_skill_version_id", "skill_releases", ["skill_version_id"])

    op.add_column("agents_skills", sa.Column("skill_install_id", sa.BigInteger(), nullable=True))
    op.alter_column("agents_skills", "skill_id", existing_type=sa.BigInteger(), nullable=True)
    op.create_foreign_key(
        "fk_agents_skills_skill_install_id_skill_installs",
        "agents_skills",
        "skill_installs",
        ["skill_install_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_check_constraint(
        "ck_agents_skills_has_skill_or_install",
        "agents_skills",
        "skill_id IS NOT NULL OR skill_install_id IS NOT NULL",
    )
    op.create_index(
        "uq_agents_skill_installs_active",
        "agents_skills",
        ["agent_id", "skill_install_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL AND skill_install_id IS NOT NULL"),
    )
    op.create_index("ix_agents_skills_skill_install_id", "agents_skills", ["skill_install_id"])

    op.create_table(
        "runtime_manifests",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("agent_id", sa.BigInteger(), nullable=True),
        sa.Column("agent_name", sa.String(length=255), nullable=True),
        sa.Column("manifest_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_runtime_manifests_user_created", "runtime_manifests", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_runtime_manifests_user_created", table_name="runtime_manifests")
    op.drop_table("runtime_manifests")

    op.drop_index("ix_agents_skills_skill_install_id", table_name="agents_skills")
    op.drop_index("uq_agents_skill_installs_active", table_name="agents_skills")
    op.drop_constraint("ck_agents_skills_has_skill_or_install", "agents_skills", type_="check")
    op.drop_constraint("fk_agents_skills_skill_install_id_skill_installs", "agents_skills", type_="foreignkey")
    op.alter_column("agents_skills", "skill_id", existing_type=sa.BigInteger(), nullable=False)
    op.drop_column("agents_skills", "skill_install_id")

    op.drop_index("ix_skill_releases_skill_version_id", table_name="skill_releases")
    op.drop_constraint("fk_skill_releases_skill_version_id_skill_versions", "skill_releases", type_="foreignkey")
    op.drop_column("skill_releases", "skill_version_id")

    op.drop_index("ix_skill_installs_deleted_at", table_name="skill_installs")
    op.drop_index("ix_skill_installs_current_version_id", table_name="skill_installs")
    op.drop_index("uq_skill_installs_user_definition_active", table_name="skill_installs")
    op.drop_table("skill_installs")

    op.drop_index("ix_skill_versions_definition_created", table_name="skill_versions")
    op.drop_table("skill_versions")

    op.drop_index("ix_skill_definitions_deleted_at", table_name="skill_definitions")
    op.drop_index("uq_skill_definitions_name_active", table_name="skill_definitions")
    op.drop_table("skill_definitions")
