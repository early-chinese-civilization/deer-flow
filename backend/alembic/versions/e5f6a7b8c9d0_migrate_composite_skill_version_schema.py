"""migrate composite skill version schema

Revision ID: e5f6a7b8c9d0
Revises: 8a6f1b2c3d4e
Create Date: 2026-05-13 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Iterable

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "e5f6a7b8c9d0"
down_revision = "8a6f1b2c3d4e"
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return table_name in inspector.get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    if not _has_table(table_name):
        return False
    inspector = sa.inspect(op.get_bind())
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def _has_index(table_name: str, index_name: str) -> bool:
    if not _has_table(table_name):
        return False
    inspector = sa.inspect(op.get_bind())
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def _has_constraint(table_name: str, constraint_name: str) -> bool:
    if not _has_table(table_name):
        return False
    inspector = sa.inspect(op.get_bind())
    if inspector.get_pk_constraint(table_name).get("name") == constraint_name:
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


def _rename_constraint_if_exists(table_name: str, old_name: str, new_name: str) -> None:
    if _has_constraint(table_name, old_name) and not _has_constraint(table_name, new_name):
        op.execute(sa.text(f'ALTER TABLE "{table_name}" RENAME CONSTRAINT "{old_name}" TO "{new_name}"'))


def _assert_no_rows(sql: str, message: str) -> None:
    count = int(op.get_bind().execute(sa.text(sql)).scalar_one())
    if count:
        raise RuntimeError(message)


_INSTALL_INDEX_RENAMES = (
    ("skill_installs_pkey", "skill_installations_pkey"),
    ("uq_skill_installs_user_definition_active", "uq_skill_installations_user_definition_active"),
    ("ix_skill_installs_current_version_id", "ix_skill_installations_current_version_id"),
    ("ix_skill_installs_deleted_at", "ix_skill_installations_deleted_at"),
)


def _rename_skill_install_table() -> None:
    if _has_table("skill_installs") and not _has_table("skill_installations"):
        op.rename_table("skill_installs", "skill_installations")
    if _has_table("skill_installations"):
        _rename_constraint_if_exists("skill_installations", "skill_installs_pkey", "skill_installations_pkey")
        _rename_constraint_if_exists("agents_skills", "fk_agents_skills_skill_install_id_skill_installs", "fk_agents_skills_skill_install_id_skill_installations")
        _rename_indexes(_INSTALL_INDEX_RENAMES)


def _upgrade_skill_versions() -> None:
    if not _has_column("skill_versions", "skill_id"):
        op.add_column("skill_versions", sa.Column("skill_id", postgresql.UUID(as_uuid=True), nullable=True, comment="Terminal Skill UUID that scopes version_number"))

    op.execute(
        """
        UPDATE skill_versions AS sv
        SET skill_id = map.skill_id
        FROM skill_identity_migration_map AS map
        WHERE sv.skill_definition_id = map.old_skill_definition_id
          AND sv.skill_id IS NULL
        """
    )
    _assert_no_rows(
        "SELECT count(*) FROM skill_versions WHERE skill_id IS NULL",
        "Cannot migrate skill_versions: every row must map to skill_identity_migration_map.skill_id",
    )
    op.alter_column("skill_versions", "skill_id", existing_type=postgresql.UUID(as_uuid=True), nullable=False)

    if not _has_constraint("skill_versions", "fk_skill_versions_skill_id_skills"):
        op.create_foreign_key("fk_skill_versions_skill_id_skills", "skill_versions", "skills", ["skill_id"], ["id"], ondelete="CASCADE")
    if not _has_constraint("skill_versions", "uq_skill_versions_skill_version_number"):
        op.create_unique_constraint("uq_skill_versions_skill_version_number", "skill_versions", ["skill_id", "version_number"])
    if not _has_constraint("skill_versions", "uq_skill_versions_skill_content_hash"):
        op.create_unique_constraint("uq_skill_versions_skill_content_hash", "skill_versions", ["skill_id", "content_hash"])
    if not _has_index("skill_versions", "ix_skill_versions_skill_id_created"):
        op.create_index("ix_skill_versions_skill_id_created", "skill_versions", ["skill_id", "created_at"])


def _upgrade_skill_installations() -> None:
    _rename_skill_install_table()
    if not _has_column("skill_installations", "skill_id"):
        op.add_column("skill_installations", sa.Column("skill_id", postgresql.UUID(as_uuid=True), nullable=True, comment="Terminal Skill UUID selected by this installation"))
    if not _has_column("skill_installations", "version_number"):
        op.add_column("skill_installations", sa.Column("version_number", sa.Integer(), nullable=True, comment="Terminal runtime version number selected for this installation"))
    if not _has_column("skill_installations", "status"):
        op.add_column("skill_installations", sa.Column("status", sa.String(length=50), nullable=True, server_default="active", comment="Installation status"))

    op.execute(
        """
        UPDATE skill_installations AS install
        SET skill_id = version.skill_id,
            version_number = version.version_number,
            status = COALESCE(install.status, 'active')
        FROM skill_versions AS version
        WHERE install.current_version_id = version.id
          AND (install.skill_id IS NULL OR install.version_number IS NULL OR install.status IS NULL)
        """
    )
    _assert_no_rows(
        "SELECT count(*) FROM skill_installations WHERE skill_id IS NULL OR version_number IS NULL OR status IS NULL",
        "Cannot migrate skill_installations: every row must resolve current_version_id to skill_versions(skill_id, version_number)",
    )
    op.alter_column("skill_installations", "skill_id", existing_type=postgresql.UUID(as_uuid=True), nullable=False)
    op.alter_column("skill_installations", "version_number", existing_type=sa.Integer(), nullable=False)
    op.alter_column("skill_installations", "status", existing_type=sa.String(length=50), nullable=False, server_default=None)

    if not _has_constraint("skill_installations", "fk_skill_installations_skill_version_composite"):
        op.create_foreign_key(
            "fk_skill_installations_skill_version_composite",
            "skill_installations",
            "skill_versions",
            ["skill_id", "version_number"],
            ["skill_id", "version_number"],
            ondelete="RESTRICT",
        )
    if not _has_index("skill_installations", "uq_skill_installations_user_skill_active"):
        op.create_index(
            "uq_skill_installations_user_skill_active",
            "skill_installations",
            ["user_id", "skill_id"],
            unique=True,
            postgresql_where=sa.text("deleted_at IS NULL"),
        )
    if not _has_index("skill_installations", "ix_skill_installations_skill_version"):
        op.create_index("ix_skill_installations_skill_version", "skill_installations", ["skill_id", "version_number"])


def _upgrade_skill_releases() -> None:
    if not _has_column("skill_releases", "skill_id"):
        op.add_column("skill_releases", sa.Column("skill_id", postgresql.UUID(as_uuid=True), nullable=True, comment="Terminal Skill UUID published by this release row"))
    if not _has_column("skill_releases", "version_number"):
        op.add_column("skill_releases", sa.Column("version_number", sa.Integer(), nullable=True, comment="Terminal Skill version number published by this release row"))
    if not _has_column("skill_releases", "published_at"):
        op.add_column("skill_releases", sa.Column("published_at", sa.DateTime(timezone=True), nullable=True, comment="Published at"))
    if not _has_column("skill_releases", "updated_at"):
        op.add_column("skill_releases", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True, comment="Updated at"))

    op.execute(
        """
        UPDATE skill_releases AS release
        SET skill_id = version.skill_id,
            version_number = version.version_number,
            published_at = CASE
                WHEN release.status = 'published' THEN COALESCE(release.published_at, release.created_at)
                ELSE release.published_at
            END,
            updated_at = COALESCE(release.updated_at, release.created_at)
        FROM skill_versions AS version
        WHERE release.skill_version_id = version.id
          AND (release.skill_id IS NULL OR release.version_number IS NULL OR release.updated_at IS NULL)
        """
    )
    _assert_no_rows(
        "SELECT count(*) FROM skill_releases WHERE skill_id IS NULL OR version_number IS NULL OR updated_at IS NULL",
        "Cannot migrate skill_releases: every row must resolve skill_version_id to skill_versions(skill_id, version_number)",
    )
    op.execute(
        """
        WITH ranked AS (
            SELECT id,
                   ROW_NUMBER() OVER (
                       PARTITION BY skill_id, version_number
                       ORDER BY updated_at DESC NULLS LAST,
                                published_at DESC NULLS LAST,
                                created_at DESC NULLS LAST,
                                id DESC
                   ) AS row_number
            FROM skill_releases
        )
        DELETE FROM skill_releases AS release
        USING ranked
        WHERE release.id = ranked.id
          AND ranked.row_number > 1
        """
    )
    op.alter_column("skill_releases", "skill_id", existing_type=postgresql.UUID(as_uuid=True), nullable=False)
    op.alter_column("skill_releases", "version_number", existing_type=sa.Integer(), nullable=False)
    op.alter_column("skill_releases", "updated_at", existing_type=sa.DateTime(timezone=True), nullable=False)

    if not _has_constraint("skill_releases", "fk_skill_releases_skill_version_composite"):
        op.create_foreign_key(
            "fk_skill_releases_skill_version_composite",
            "skill_releases",
            "skill_versions",
            ["skill_id", "version_number"],
            ["skill_id", "version_number"],
            ondelete="RESTRICT",
        )
    if not _has_constraint("skill_releases", "uq_skill_releases_skill_version"):
        op.create_unique_constraint("uq_skill_releases_skill_version", "skill_releases", ["skill_id", "version_number"])
    if not _has_index("skill_releases", "ix_skill_releases_status_skill_version"):
        op.create_index("ix_skill_releases_status_skill_version", "skill_releases", ["status", "skill_id", "version_number"])


def upgrade() -> None:
    _upgrade_skill_versions()
    _upgrade_skill_installations()
    _upgrade_skill_releases()


def downgrade() -> None:
    if _has_index("skill_releases", "ix_skill_releases_status_skill_version"):
        op.drop_index("ix_skill_releases_status_skill_version", table_name="skill_releases")
    if _has_constraint("skill_releases", "uq_skill_releases_skill_version"):
        op.drop_constraint("uq_skill_releases_skill_version", "skill_releases", type_="unique")
    if _has_constraint("skill_releases", "fk_skill_releases_skill_version_composite"):
        op.drop_constraint("fk_skill_releases_skill_version_composite", "skill_releases", type_="foreignkey")
    for column_name in ("updated_at", "published_at", "version_number", "skill_id"):
        if _has_column("skill_releases", column_name):
            op.drop_column("skill_releases", column_name)

    if _has_index("skill_installations", "ix_skill_installations_skill_version"):
        op.drop_index("ix_skill_installations_skill_version", table_name="skill_installations")
    if _has_index("skill_installations", "uq_skill_installations_user_skill_active"):
        op.drop_index("uq_skill_installations_user_skill_active", table_name="skill_installations")
    if _has_constraint("skill_installations", "fk_skill_installations_skill_version_composite"):
        op.drop_constraint("fk_skill_installations_skill_version_composite", "skill_installations", type_="foreignkey")
    for column_name in ("status", "version_number", "skill_id"):
        if _has_column("skill_installations", column_name):
            op.drop_column("skill_installations", column_name)
    if _has_table("skill_installations") and not _has_table("skill_installs"):
        _rename_constraint_if_exists("agents_skills", "fk_agents_skills_skill_install_id_skill_installations", "fk_agents_skills_skill_install_id_skill_installs")
        _rename_constraint_if_exists("skill_installations", "skill_installations_pkey", "skill_installs_pkey")
        _rename_indexes(tuple((new_name, old_name) for old_name, new_name in _INSTALL_INDEX_RENAMES))
        op.rename_table("skill_installations", "skill_installs")

    if _has_index("skill_versions", "ix_skill_versions_skill_id_created"):
        op.drop_index("ix_skill_versions_skill_id_created", table_name="skill_versions")
    if _has_constraint("skill_versions", "uq_skill_versions_skill_content_hash"):
        op.drop_constraint("uq_skill_versions_skill_content_hash", "skill_versions", type_="unique")
    if _has_constraint("skill_versions", "uq_skill_versions_skill_version_number"):
        op.drop_constraint("uq_skill_versions_skill_version_number", "skill_versions", type_="unique")
    if _has_constraint("skill_versions", "fk_skill_versions_skill_id_skills"):
        op.drop_constraint("fk_skill_versions_skill_id_skills", "skill_versions", type_="foreignkey")
    if _has_column("skill_versions", "skill_id"):
        op.drop_column("skill_versions", "skill_id")
