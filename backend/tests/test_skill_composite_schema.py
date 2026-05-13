from __future__ import annotations

from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from app.gateway.db.models import SkillInstall, SkillInstallation, SkillRelease, SkillVersion


def _unique_constraint_columns(table: sa.Table, name: str) -> tuple[str, ...]:
    for constraint in table.constraints:
        if isinstance(constraint, sa.UniqueConstraint) and constraint.name == name:
            return tuple(column.name for column in constraint.columns)
    raise AssertionError(f"Unique constraint {name} not found on {table.name}")


def _foreign_key_constraint_columns(table: sa.Table, name: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    for constraint in table.constraints:
        if isinstance(constraint, sa.ForeignKeyConstraint) and constraint.name == name:
            constrained = tuple(element.parent.name for element in constraint.elements)
            referred = tuple(f"{element.column.table.name}.{element.column.name}" for element in constraint.elements)
            return constrained, referred
    raise AssertionError(f"Foreign key constraint {name} not found on {table.name}")


def _unique_column_sets(table: sa.Table) -> set[tuple[str, ...]]:
    return {tuple(column.name for column in constraint.columns) for constraint in table.constraints if isinstance(constraint, sa.UniqueConstraint)}


def _foreign_key_column_sets(table: sa.Table) -> set[tuple[str, ...]]:
    return {tuple(element.parent.name for element in constraint.elements) for constraint in table.constraints if isinstance(constraint, sa.ForeignKeyConstraint)}


def test_skill_versions_scope_version_number_by_terminal_skill_id() -> None:
    columns = SkillVersion.__table__.columns

    assert isinstance(columns.skill_id.type, UUID)
    assert columns.skill_id.nullable is False
    assert columns.version_number.nullable is False
    assert any(fk.column.table.name == "skills" and fk.column.name == "id" for fk in columns.skill_id.foreign_keys)
    assert _unique_constraint_columns(SkillVersion.__table__, "uq_skill_versions_skill_version_number") == ("skill_id", "version_number")
    assert _unique_constraint_columns(SkillVersion.__table__, "uq_skill_versions_skill_content_hash") == ("skill_id", "content_hash")
    assert ("version_number",) not in _unique_column_sets(SkillVersion.__table__)


def test_skill_installations_reference_exact_terminal_version() -> None:
    columns = SkillInstallation.__table__.columns

    assert SkillInstall is SkillInstallation
    assert SkillInstallation.__tablename__ == "skill_installations"
    assert isinstance(columns.skill_id.type, UUID)
    assert columns.skill_id.nullable is False
    assert columns.version_number.nullable is False
    assert columns.status.nullable is False
    assert "current_version_id" in columns

    constrained, referred = _foreign_key_constraint_columns(SkillInstallation.__table__, "fk_skill_installations_skill_version_composite")
    assert constrained == ("skill_id", "version_number")
    assert referred == ("skill_versions.skill_id", "skill_versions.version_number")
    assert ("version_number",) not in _foreign_key_column_sets(SkillInstallation.__table__)


def test_skill_releases_reference_exact_terminal_version_with_status() -> None:
    columns = SkillRelease.__table__.columns

    assert isinstance(columns.skill_id.type, UUID)
    assert columns.skill_id.nullable is False
    assert columns.version_number.nullable is False
    assert columns.status.nullable is False
    assert columns.published_at.nullable is True
    assert columns.updated_at.nullable is False
    assert "skill_version_id" not in columns
    assert "artifact_path" not in columns

    constrained, referred = _foreign_key_constraint_columns(SkillRelease.__table__, "fk_skill_releases_skill_version_composite")
    assert constrained == ("skill_id", "version_number")
    assert referred == ("skill_versions.skill_id", "skill_versions.version_number")
    assert _unique_constraint_columns(SkillRelease.__table__, "uq_skill_releases_skill_version") == ("skill_id", "version_number")
    assert ("version_number",) not in _foreign_key_column_sets(SkillRelease.__table__)


def test_composite_skill_schema_migration_backfills_and_constrains_terminal_columns() -> None:
    migration_path = Path("alembic/versions/e5f6a7b8c9d0_migrate_composite_skill_version_schema.py")

    assert migration_path.exists()
    migration = migration_path.read_text(encoding="utf-8")
    assert "skill_identity_migration_map" in migration
    assert "skill_installations" in migration
    assert "agent_skills" in migration
    assert "skill_installation_id" in migration
    assert "fk_agent_skills_skill_installation_id_skill_installations" in migration
    assert "fk_skill_installations_skill_version_composite" in migration
    assert "fk_skill_releases_skill_version_composite" in migration
    assert "uq_skill_versions_skill_version_number" in migration
    assert "uq_skill_releases_skill_version" in migration
    assert "current_version_id = version.id" in migration
    assert "release.skill_version_id = version.id" in migration
    assert 'op.drop_column("skill_releases", "skill_version_id")' in migration
    assert 'op.drop_column("skill_releases", "artifact_path")' in migration
