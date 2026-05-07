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
