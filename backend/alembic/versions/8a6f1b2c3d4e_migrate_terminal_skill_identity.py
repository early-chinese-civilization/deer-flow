"""migrate terminal skill identity

Revision ID: 8a6f1b2c3d4e
Revises: 7d3a2b1c0e9f
Create Date: 2026-05-13 00:00:00.000000
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "8a6f1b2c3d4e"
down_revision = "7d3a2b1c0e9f"
branch_labels = None
depends_on = None

INTERNAL_SYSTEM_EXTERNAL_AUTH_ID = "system:deerflow"
SKILL_MIGRATION_NAMESPACE = uuid.UUID("f0df12b5-661f-4d22-92f7-8e80714f67e0")


def skill_uuid_for_definition_id(skill_definition_id: int) -> uuid.UUID:
    """Return the deterministic terminal Skill UUID for a legacy SkillDefinition."""
    return uuid.uuid5(SKILL_MIGRATION_NAMESPACE, f"skill_definition:{skill_definition_id}")


def _has_table(table_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return table_name in inspector.get_table_names()


def _has_index(table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def _has_constraint(table_name: str, constraint_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    constraints = inspector.get_pk_constraint(table_name).get("name")
    if constraints == constraint_name:
        return True
    return any(constraint["name"] == constraint_name for constraint in inspector.get_foreign_keys(table_name)) or any(constraint["name"] == constraint_name for constraint in inspector.get_unique_constraints(table_name))


def _relation_exists(relation_name: str) -> bool:
    return op.get_bind().execute(sa.text("select to_regclass(:relation_name)"), {"relation_name": relation_name}).scalar() is not None


def _rename_index_if_exists(old_name: str, new_name: str) -> None:
    if _relation_exists(old_name) and not _relation_exists(new_name):
        op.execute(sa.text(f'ALTER INDEX "{old_name}" RENAME TO "{new_name}"'))


def _rename_indexes(pairs: Iterable[tuple[str, str]]) -> None:
    for old_name, new_name in pairs:
        _rename_index_if_exists(old_name, new_name)


_LEGACY_INDEX_RENAMES = (
    ("skills_pkey", "legacy_skills_pkey"),
    ("ix_skills_user_id", "ix_legacy_skills_user_id"),
    ("ix_skills_owner_user_id", "ix_legacy_skills_owner_user_id"),
    ("ix_skills_skill_definition_id", "ix_legacy_skills_skill_definition_id"),
    ("ix_skills_deleted_at", "ix_legacy_skills_deleted_at"),
    ("uq_skills_user_definition_active", "uq_legacy_skills_user_definition_active"),
    ("uq_skills_user_name_legacy_active", "uq_legacy_skills_user_name_active"),
    ("uq_skills_user_name_active", "uq_legacy_skills_user_name_active"),
    ("uq_skills_public_owner_name_active", "uq_legacy_skills_public_owner_name_active"),
    ("uq_skills_system_name_active", "uq_legacy_skills_system_name_active"),
)


def _ensure_system_user() -> int:
    connection = op.get_bind()
    return int(
        connection.execute(
            sa.text(
                """
                INSERT INTO users (
                    external_auth_id,
                    username,
                    display_name,
                    email,
                    given_name,
                    family_name,
                    email_verified,
                    created_at,
                    updated_at
                )
                VALUES (
                    :external_auth_id,
                    'system-deerflow',
                    'DeerFlow System',
                    NULL,
                    NULL,
                    NULL,
                    FALSE,
                    NOW(),
                    NOW()
                )
                ON CONFLICT (external_auth_id) DO UPDATE
                SET username = EXCLUDED.username,
                    display_name = EXCLUDED.display_name,
                    updated_at = NOW()
                RETURNING id
                """
            ),
            {"external_auth_id": INTERNAL_SYSTEM_EXTERNAL_AUTH_ID},
        ).scalar_one()
    )


def _create_terminal_skills_table() -> None:
    if _has_table("skills"):
        return
    op.create_table(
        "skills",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, comment="Stable Skill identity"),
        sa.Column("owner_user_id", sa.BigInteger(), nullable=False, comment="System or community owner user ID"),
        sa.Column("name", sa.String(length=255), nullable=False, comment="Skill name"),
        sa.Column("display_name", sa.String(length=255), nullable=True, comment="Display name"),
        sa.Column("description", sa.Text(), nullable=True, comment="Skill description"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, comment="Created at"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, comment="Updated at"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True, comment="Soft delete timestamp"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], name="fk_skills_owner_user_id_users", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="skills_pkey"),
    )
    op.create_index(
        "uq_skills_owner_name_active",
        "skills",
        ["owner_user_id", "name"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index("ix_skills_owner_user_id", "skills", ["owner_user_id"])
    op.create_index("ix_skills_deleted_at", "skills", ["deleted_at"])


def _create_identity_map_table() -> None:
    if _has_table("skill_identity_migration_map"):
        return
    op.create_table(
        "skill_identity_migration_map",
        sa.Column("old_skill_definition_id", sa.BigInteger(), nullable=False, comment="Legacy SkillDefinition ID"),
        sa.Column("skill_id", postgresql.UUID(as_uuid=True), nullable=False, comment="Terminal Skill UUID"),
        sa.Column("old_skill_id", sa.BigInteger(), nullable=True, comment="Representative legacy skills row that contributed display/path migration input"),
        sa.Column("migration_source", sa.String(length=255), nullable=False, comment="Deterministic UUIDv5 source string"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()"), comment="Created at"),
        sa.ForeignKeyConstraint(
            ["old_skill_definition_id"],
            ["skill_definitions.id"],
            name="fk_skill_identity_migration_map_old_skill_definition_id_skill_definitions",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"], name="fk_skill_identity_migration_map_skill_id_skills", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["old_skill_id"], ["legacy_skills.id"], name="fk_skill_identity_migration_map_old_skill_id_legacy_skills", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("old_skill_definition_id", name="skill_identity_migration_map_pkey"),
        sa.UniqueConstraint("skill_id", name="uq_skill_identity_migration_map_skill_id"),
        sa.UniqueConstraint("migration_source", name="uq_skill_identity_migration_map_migration_source"),
    )
    op.create_index("ix_skill_identity_migration_map_skill_id", "skill_identity_migration_map", ["skill_id"])
    op.create_index("ix_skill_identity_migration_map_old_skill_id", "skill_identity_migration_map", ["old_skill_id"])


def _backfill_terminal_identity(system_user_id: int) -> None:
    connection = op.get_bind()
    rows = (
        connection.execute(
            sa.text(
                """
            SELECT sd.id AS old_skill_definition_id,
                   sd.name,
                   COALESCE(sd.display_name, sd.name) AS display_name,
                   sd.description,
                   COALESCE(sd.owner_user_id, :system_user_id) AS owner_user_id,
                   COALESCE(sd.created_at, NOW()) AS created_at,
                   COALESCE(sd.updated_at, NOW()) AS updated_at,
                   sd.deleted_at,
                   legacy.id AS old_skill_id
            FROM skill_definitions AS sd
            LEFT JOIN LATERAL (
                SELECT ls.id
                FROM legacy_skills AS ls
                WHERE ls.skill_definition_id = sd.id
                ORDER BY
                    CASE WHEN ls.deleted_at IS NULL THEN 0 ELSE 1 END,
                    CASE WHEN ls.user_id IS NULL THEN 0 ELSE 1 END,
                    ls.updated_at DESC NULLS LAST,
                    ls.created_at DESC NULLS LAST,
                    ls.id DESC
                LIMIT 1
            ) AS legacy ON TRUE
            ORDER BY sd.id
            """
            ),
            {"system_user_id": system_user_id},
        )
        .mappings()
        .all()
    )

    if not rows:
        return

    terminal_skill_values = []
    mapping_values = []
    for row in rows:
        old_skill_definition_id = int(row["old_skill_definition_id"])
        skill_id = skill_uuid_for_definition_id(old_skill_definition_id)
        migration_source = f"skill_definition:{old_skill_definition_id}"
        terminal_skill_values.append(
            {
                "id": skill_id,
                "owner_user_id": row["owner_user_id"],
                "name": row["name"],
                "display_name": row["display_name"],
                "description": row["description"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "deleted_at": row["deleted_at"],
            }
        )
        mapping_values.append(
            {
                "old_skill_definition_id": old_skill_definition_id,
                "skill_id": skill_id,
                "old_skill_id": row["old_skill_id"],
                "migration_source": migration_source,
            }
        )

    connection.execute(
        sa.text(
            """
            INSERT INTO skills (
                id,
                owner_user_id,
                name,
                display_name,
                description,
                created_at,
                updated_at,
                deleted_at
            )
            VALUES (
                :id,
                :owner_user_id,
                :name,
                :display_name,
                :description,
                :created_at,
                :updated_at,
                :deleted_at
            )
            ON CONFLICT (id) DO UPDATE
            SET owner_user_id = EXCLUDED.owner_user_id,
                name = EXCLUDED.name,
                display_name = EXCLUDED.display_name,
                description = EXCLUDED.description,
                updated_at = EXCLUDED.updated_at,
                deleted_at = EXCLUDED.deleted_at
            """
        ),
        terminal_skill_values,
    )
    connection.execute(
        sa.text(
            """
            INSERT INTO skill_identity_migration_map (
                old_skill_definition_id,
                skill_id,
                old_skill_id,
                migration_source
            )
            VALUES (
                :old_skill_definition_id,
                :skill_id,
                :old_skill_id,
                :migration_source
            )
            ON CONFLICT (old_skill_definition_id) DO UPDATE
            SET skill_id = EXCLUDED.skill_id,
                old_skill_id = EXCLUDED.old_skill_id,
                migration_source = EXCLUDED.migration_source
            """
        ),
        mapping_values,
    )


def upgrade() -> None:
    system_user_id = _ensure_system_user()
    if _has_table("skills") and not _has_table("legacy_skills"):
        op.rename_table("skills", "legacy_skills")
        _rename_indexes(_LEGACY_INDEX_RENAMES)

    _create_terminal_skills_table()
    _create_identity_map_table()
    _backfill_terminal_identity(system_user_id)


def downgrade() -> None:
    if _has_table("skill_identity_migration_map"):
        op.drop_index("ix_skill_identity_migration_map_old_skill_id", table_name="skill_identity_migration_map")
        op.drop_index("ix_skill_identity_migration_map_skill_id", table_name="skill_identity_migration_map")
        op.drop_table("skill_identity_migration_map")

    if _has_table("skills"):
        if _has_index("skills", "ix_skills_deleted_at"):
            op.drop_index("ix_skills_deleted_at", table_name="skills")
        if _has_index("skills", "ix_skills_owner_user_id"):
            op.drop_index("ix_skills_owner_user_id", table_name="skills")
        if _has_index("skills", "uq_skills_owner_name_active"):
            op.drop_index("uq_skills_owner_name_active", table_name="skills")
        if _has_constraint("skills", "fk_skills_owner_user_id_users"):
            op.drop_constraint("fk_skills_owner_user_id_users", "skills", type_="foreignkey")
        op.drop_table("skills")

    if _has_table("legacy_skills") and not _has_table("skills"):
        _rename_indexes(tuple((new_name, old_name) for old_name, new_name in _LEGACY_INDEX_RENAMES))
        op.rename_table("legacy_skills", "skills")
