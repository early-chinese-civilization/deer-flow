"""namespace skill definitions

Revision ID: 9f4d2c7b1a63
Revises: c1d2e3f4a5b6
Create Date: 2026-05-07 00:00:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "9f4d2c7b1a63"
down_revision = "c1d2e3f4a5b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("skill_definitions", sa.Column("source_type", sa.String(length=50), nullable=False, server_default="legacy"))
    op.add_column("skill_definitions", sa.Column("source_identifier", sa.String(length=255), nullable=False, server_default="legacy"))
    op.execute(
        """
        UPDATE skill_definitions
        SET source_type = 'user',
            source_identifier = owner_user_id::text
        WHERE owner_user_id IS NOT NULL
        """
    )
    op.alter_column("skill_definitions", "source_type", server_default=None)
    op.alter_column("skill_definitions", "source_identifier", server_default=None)
    op.drop_index("uq_skill_definitions_name_active", table_name="skill_definitions")
    op.execute(
        """
        INSERT INTO skill_definitions (
            name,
            display_name,
            description,
            source_type,
            source_identifier,
            owner_user_id,
            created_at,
            updated_at,
            deleted_at
        )
        SELECT desired.name,
               desired.display_name,
               desired.description,
               desired.source_type,
               desired.source_identifier,
               desired.owner_user_id,
               desired.created_at,
               desired.updated_at,
               NULL
        FROM (
            SELECT s.name,
                   COALESCE(MAX(s.display_name), s.name) AS display_name,
                   MAX(s.description) AS description,
                   CASE
                       WHEN COALESCE(s.owner_user_id, s.user_id) IS NULL THEN 'legacy'
                       ELSE 'user'
                   END AS source_type,
                   COALESCE(COALESCE(s.owner_user_id, s.user_id)::text, 'legacy') AS source_identifier,
                   MIN(COALESCE(s.owner_user_id, s.user_id)) AS owner_user_id,
                   MIN(s.created_at) AS created_at,
                   MAX(s.updated_at) AS updated_at
            FROM skills AS s
            WHERE s.deleted_at IS NULL
            GROUP BY s.name,
                     CASE
                         WHEN COALESCE(s.owner_user_id, s.user_id) IS NULL THEN 'legacy'
                         ELSE 'user'
                     END,
                     COALESCE(COALESCE(s.owner_user_id, s.user_id)::text, 'legacy')
        ) AS desired
        WHERE NOT EXISTS (
            SELECT 1
            FROM skill_definitions AS existing
            WHERE existing.name = desired.name
              AND existing.source_type = desired.source_type
              AND existing.source_identifier = desired.source_identifier
              AND existing.deleted_at IS NULL
        )
        """
    )
    op.create_index(
        "uq_skill_definitions_source_name_active",
        "skill_definitions",
        ["source_type", "source_identifier", "name"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index("ix_skill_definitions_source", "skill_definitions", ["source_type", "source_identifier"])

    op.add_column("skills", sa.Column("skill_definition_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        "fk_skills_skill_definition_id_skill_definitions",
        "skills",
        "skill_definitions",
        ["skill_definition_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.execute(
        """
        UPDATE skills AS s
        SET skill_definition_id = sv.skill_definition_id
        FROM skill_releases AS sr
        JOIN skill_versions AS sv ON sv.id = sr.skill_version_id
        WHERE sr.published_skill_id = s.id
          AND s.skill_definition_id IS NULL
        """
    )
    op.execute(
        """
        UPDATE skills AS s
        SET skill_definition_id = sd.id
        FROM skill_definitions AS sd
        WHERE s.skill_definition_id IS NULL
          AND s.name = sd.name
          AND (
              (s.user_id IS NOT NULL AND sd.source_type = 'user' AND sd.source_identifier = s.user_id::text)
              OR (s.user_id IS NULL AND s.owner_user_id IS NOT NULL AND sd.source_type = 'user' AND sd.source_identifier = s.owner_user_id::text)
              OR (sd.source_type = 'legacy' AND sd.source_identifier = 'legacy')
          )
        """
    )
    op.execute(
        """
        UPDATE skill_versions AS sv
        SET skill_definition_id = resolved.skill_definition_id
        FROM (
            SELECT s.id AS skill_id,
                   sd.id AS skill_definition_id
            FROM skills AS s
            JOIN skill_definitions AS sd
              ON sd.name = s.name
             AND sd.source_type = CASE
                 WHEN COALESCE(s.owner_user_id, s.user_id) IS NULL THEN 'legacy'
                 ELSE 'user'
             END
             AND sd.source_identifier = COALESCE(COALESCE(s.owner_user_id, s.user_id)::text, 'legacy')
             AND sd.deleted_at IS NULL
            WHERE s.deleted_at IS NULL
        ) AS resolved
        WHERE sv.content_hash = 'legacy-skill-' || resolved.skill_id::text
          AND sv.skill_definition_id <> resolved.skill_definition_id
        """
    )
    op.execute(
        """
        UPDATE skill_installs AS si
        SET skill_definition_id = sv.skill_definition_id
        FROM skill_versions AS sv
        WHERE si.current_version_id = sv.id
          AND si.deleted_at IS NULL
          AND si.skill_definition_id <> sv.skill_definition_id
          AND NOT EXISTS (
              SELECT 1
              FROM skill_installs AS existing
              WHERE existing.user_id = si.user_id
                AND existing.skill_definition_id = sv.skill_definition_id
                AND existing.id <> si.id
                AND existing.deleted_at IS NULL
          )
        """
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
        SET skill_install_id = resolved.skill_install_id
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
              AND (
                  ask_inner.skill_install_id IS NULL
                  OR ask_inner.skill_install_id <> install.id
              )
        ) AS resolved
        WHERE ask.id = resolved.agent_skill_id
          AND (
              ask.skill_install_id IS NULL
              OR ask.skill_install_id <> resolved.skill_install_id
          )
          AND ask.deleted_at IS NULL
        """
    )
    op.drop_index("uq_skills_user_name_active", table_name="skills")
    op.create_index(
        "uq_skills_user_definition_active",
        "skills",
        ["user_id", "skill_definition_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL AND user_id IS NOT NULL AND skill_definition_id IS NOT NULL"),
    )
    op.create_index(
        "uq_skills_user_name_legacy_active",
        "skills",
        ["user_id", "name"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL AND user_id IS NOT NULL AND skill_definition_id IS NULL"),
    )
    op.create_index("ix_skills_skill_definition_id", "skills", ["skill_definition_id"])


def downgrade() -> None:
    op.drop_index("ix_skills_skill_definition_id", table_name="skills")
    op.drop_index("uq_skills_user_name_legacy_active", table_name="skills")
    op.drop_index("uq_skills_user_definition_active", table_name="skills")
    op.create_index(
        "uq_skills_user_name_active",
        "skills",
        ["user_id", "name"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL AND user_id IS NOT NULL"),
    )
    op.drop_constraint("fk_skills_skill_definition_id_skill_definitions", "skills", type_="foreignkey")
    op.drop_column("skills", "skill_definition_id")

    op.drop_index("ix_skill_definitions_source", table_name="skill_definitions")
    op.drop_index("uq_skill_definitions_source_name_active", table_name="skill_definitions")
    op.create_index(
        "uq_skill_definitions_name_active",
        "skill_definitions",
        ["name"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.drop_column("skill_definitions", "source_identifier")
    op.drop_column("skill_definitions", "source_type")
