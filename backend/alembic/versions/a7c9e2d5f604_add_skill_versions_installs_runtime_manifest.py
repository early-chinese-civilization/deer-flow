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
    op.execute(
        """
        INSERT INTO skill_definitions (name, display_name, description, owner_user_id, created_at, updated_at, deleted_at)
        SELECT s.name,
               COALESCE(MAX(s.display_name), s.name),
               MAX(s.description),
               MIN(COALESCE(s.owner_user_id, s.user_id)),
               MIN(s.created_at),
               MAX(s.updated_at),
               NULL
        FROM skills AS s
        WHERE s.deleted_at IS NULL
        GROUP BY s.name
        ON CONFLICT DO NOTHING
        """
    )

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
    op.execute(
        """
        INSERT INTO skill_versions (
            skill_definition_id,
            version_number,
            source_package_version,
            description,
            content_hash,
            file_manifest_hash,
            artifact_uri,
            created_by_user_id,
            created_at
        )
        SELECT sd.id,
               ROW_NUMBER() OVER (PARTITION BY sd.id ORDER BY s.created_at, s.id),
               NULL,
               s.description,
               'legacy-skill-' || s.id::text,
               'legacy-file-manifest-' || s.id::text,
               CASE
                   WHEN s.file_path LIKE 'artifacts/%' THEN s.file_path
                   ELSE 'artifacts/legacy/skills/' || s.id::text || '/' || s.name
               END,
               s.user_id,
               s.created_at
        FROM skills AS s
        JOIN skill_definitions AS sd ON sd.name = s.name AND sd.deleted_at IS NULL
        WHERE s.deleted_at IS NULL
        ON CONFLICT DO NOTHING
        """
    )

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
    op.execute(
        """
        INSERT INTO skill_installs (
            user_id,
            skill_definition_id,
            installed_version_id,
            current_version_id,
            created_at,
            updated_at,
            deleted_at
        )
        SELECT s.user_id,
               sv.skill_definition_id,
               sv.id,
               sv.id,
               s.created_at,
               s.updated_at,
               NULL
        FROM skills AS s
        JOIN skill_versions AS sv ON sv.content_hash = 'legacy-skill-' || s.id::text
        WHERE s.deleted_at IS NULL
          AND s.user_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1
              FROM skill_installs AS existing
              WHERE existing.user_id = s.user_id
                AND existing.skill_definition_id = sv.skill_definition_id
                AND existing.deleted_at IS NULL
          )
        """
    )

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
    op.execute(
        """
        INSERT INTO skill_installs (
            user_id,
            skill_definition_id,
            installed_version_id,
            current_version_id,
            created_at,
            updated_at,
            deleted_at
        )
        SELECT DISTINCT ON (a.user_id, sv.skill_definition_id)
               a.user_id,
               sv.skill_definition_id,
               sv.id,
               sv.id,
               ask.created_at,
               ask.created_at,
               NULL
        FROM agents_skills AS ask
        JOIN agents AS a ON a.id = ask.agent_id
        JOIN skills AS s ON s.id = ask.skill_id
        JOIN skill_versions AS sv ON sv.content_hash = 'legacy-skill-' || s.id::text
        WHERE ask.deleted_at IS NULL
          AND ask.skill_id IS NOT NULL
          AND a.user_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1
              FROM skill_installs AS existing
              WHERE existing.user_id = a.user_id
                AND existing.skill_definition_id = sv.skill_definition_id
                AND existing.deleted_at IS NULL
          )
        ORDER BY a.user_id, sv.skill_definition_id, ask.created_at, ask.id
        """
    )
    op.execute(
        """
        UPDATE agents_skills AS ask
        SET skill_install_id = si.id
        FROM (
            SELECT ask_inner.id AS agent_skill_id,
                   install.id AS skill_install_id
            FROM agents_skills AS ask_inner
            JOIN agents AS agent ON agent.id = ask_inner.agent_id
            JOIN skills AS skill ON skill.id = ask_inner.skill_id
            JOIN skill_versions AS version ON version.content_hash = 'legacy-skill-' || skill.id::text
            JOIN skill_installs AS install ON install.user_id = agent.user_id
                                          AND install.skill_definition_id = version.skill_definition_id
                                          AND install.deleted_at IS NULL
            WHERE ask_inner.deleted_at IS NULL
              AND ask_inner.skill_id IS NOT NULL
              AND ask_inner.skill_install_id IS NULL
        ) AS resolved
        WHERE ask.id = resolved.agent_skill_id
          AND ask.skill_id IS NOT NULL
          AND ask.skill_install_id IS NULL
          AND ask.deleted_at IS NULL
        """
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
