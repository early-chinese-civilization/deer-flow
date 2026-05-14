from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

from sqlalchemy import BigInteger
from sqlalchemy.dialects.postgresql import UUID

from app.gateway.db.models import INTERNAL_SYSTEM_EXTERNAL_AUTH_ID, LegacySkill, Skill, SkillIdentityMigrationMap


def _load_identity_migration_module():
    migration_path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "8a6f1b2c3d4e_migrate_terminal_skill_identity.py"
    spec = importlib.util.spec_from_file_location("migrate_terminal_skill_identity", migration_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_terminal_skill_model_uses_uuid_identity() -> None:
    assert Skill.__tablename__ == "skills"
    assert isinstance(Skill.__table__.c.id.type, UUID)
    assert Skill.__table__.c.id.type.as_uuid is True
    assert Skill.__table__.c.owner_user_id.nullable is False
    assert "user_id" not in Skill.__table__.c
    assert "file_path" not in Skill.__table__.c
    assert "skill_definition_id" not in Skill.__table__.c


def test_terminal_skill_model_does_not_use_owner_name_as_identity() -> None:
    assert "uq_skills_owner_name_active" not in {index.name for index in Skill.__table__.indexes}


def test_legacy_skill_bridge_keeps_old_bigint_migration_input() -> None:
    assert LegacySkill.__tablename__ == "legacy_skills"
    assert isinstance(LegacySkill.__table__.c.id.type, BigInteger)
    assert "user_id" in LegacySkill.__table__.c
    assert "file_path" in LegacySkill.__table__.c
    assert "skill_definition_id" in LegacySkill.__table__.c


def test_skill_identity_map_links_skill_definition_to_terminal_uuid() -> None:
    columns = SkillIdentityMigrationMap.__table__.c
    assert isinstance(columns.old_skill_definition_id.type, BigInteger)
    assert isinstance(columns.skill_id.type, UUID)
    assert isinstance(columns.old_skill_id.type, BigInteger)
    assert columns.migration_source.nullable is False
    assert any(fk.column.table.name == "skill_definitions" and fk.column.name == "id" for fk in columns.old_skill_definition_id.foreign_keys)
    assert any(fk.column.table.name == "skills" and fk.column.name == "id" for fk in columns.skill_id.foreign_keys)
    assert any(fk.column.table.name == "legacy_skills" and fk.column.name == "id" for fk in columns.old_skill_id.foreign_keys)
    assert {fk.constraint.name for fk in columns.old_skill_definition_id.foreign_keys} == {"fk_skill_id_map_definition"}
    assert {fk.constraint.name for fk in columns.skill_id.foreign_keys} == {"fk_skill_id_map_skill"}
    assert {fk.constraint.name for fk in columns.old_skill_id.foreign_keys} == {"fk_skill_id_map_legacy_skill"}


def test_skill_identity_migration_uuidv5_values_are_fixed() -> None:
    migration = _load_identity_migration_module()

    assert INTERNAL_SYSTEM_EXTERNAL_AUTH_ID == "system:deerflow"
    assert migration.INTERNAL_SYSTEM_EXTERNAL_AUTH_ID == "system:deerflow"
    assert migration.SKILL_MIGRATION_NAMESPACE == uuid.UUID("f0df12b5-661f-4d22-92f7-8e80714f67e0")
    assert migration.skill_uuid_for_definition_id(1) == uuid.UUID("5cf6bd2e-db83-5d23-8426-970dc01cdcc6")
    assert migration.skill_uuid_for_definition_id(42) == uuid.UUID("1346cead-618e-5097-9bd3-e2ec1b959fd9")
