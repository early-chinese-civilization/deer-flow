from __future__ import annotations

from uuid import UUID

import pytest

from deerflow.skills.hashing import hash_skill_directory
from deerflow.skills.storage_migration import (
    SkillStorageMigrationError,
    SkillVersionStorageMigrationItem,
    migrate_skill_version_storage_item,
)

SKILL_ID = UUID("12345678-1234-5678-1234-567812345678")


def _write_skill(skill_dir, marker: str) -> tuple[str, str]:
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: demo-skill\ndescription: Demo skill\n---\n\n{marker}\n",
        encoding="utf-8",
    )
    return hash_skill_directory(skill_dir)


def test_migrate_skill_version_storage_item_copies_legacy_artifact_to_terminal_path(tmp_path):
    source_dir = tmp_path / "artifacts" / "skills" / "1" / "v1-hash" / "demo-skill"
    content_hash, file_manifest_hash = _write_skill(source_dir, "SKILL_RUNTIME_OK_V1")

    result = migrate_skill_version_storage_item(
        tmp_path,
        SkillVersionStorageMigrationItem(
            skill_id=SKILL_ID,
            version_number=1,
            source_path="artifacts/skills/1/v1-hash/demo-skill",
            content_hash=content_hash,
            file_manifest_hash=file_manifest_hash,
        ),
    )

    assert result.action == "copied"
    assert result.terminal_path == f"{SKILL_ID}/1"
    assert (tmp_path / str(SKILL_ID) / "1" / "SKILL.md").is_file()
    assert (source_dir / "SKILL.md").is_file()


def test_migrate_skill_version_storage_item_verifies_existing_terminal_path(tmp_path):
    terminal_dir = tmp_path / str(SKILL_ID) / "1"
    content_hash, file_manifest_hash = _write_skill(terminal_dir, "SKILL_RUNTIME_OK_V1")

    result = migrate_skill_version_storage_item(
        tmp_path,
        SkillVersionStorageMigrationItem(
            skill_id=SKILL_ID,
            version_number=1,
            source_path="public/demo-skill",
            content_hash=content_hash,
            file_manifest_hash=file_manifest_hash,
        ),
    )

    assert result.action == "verified"
    assert result.terminal_path == f"{SKILL_ID}/1"


def test_migrate_skill_version_storage_item_fails_on_existing_terminal_mismatch(tmp_path):
    source_dir = tmp_path / "custom" / "demo-skill"
    terminal_dir = tmp_path / str(SKILL_ID) / "1"
    content_hash, file_manifest_hash = _write_skill(source_dir, "SKILL_RUNTIME_OK_V1")
    _write_skill(terminal_dir, "SKILL_RUNTIME_OK_V2")

    with pytest.raises(SkillStorageMigrationError, match="content_hash mismatch"):
        migrate_skill_version_storage_item(
            tmp_path,
            SkillVersionStorageMigrationItem(
                skill_id=SKILL_ID,
                version_number=1,
                source_path="custom/demo-skill",
                content_hash=content_hash,
                file_manifest_hash=file_manifest_hash,
            ),
        )


@pytest.mark.parametrize(
    "source_path",
    [
        "public/demo-skill",
        "7/demo-skill",
        "custom/demo-skill",
        "local/demo-skill",
        "artifacts/legacy/skills/legacy-id/demo-skill",
    ],
)
def test_migrate_skill_version_storage_item_accepts_legacy_source_roots(tmp_path, source_path):
    source_dir = tmp_path / source_path
    content_hash, file_manifest_hash = _write_skill(source_dir, "SKILL_RUNTIME_OK_V1")

    result = migrate_skill_version_storage_item(
        tmp_path,
        SkillVersionStorageMigrationItem(
            skill_id=SKILL_ID,
            version_number=1,
            source_path=source_path,
            content_hash=content_hash,
            file_manifest_hash=file_manifest_hash,
        ),
    )

    assert result.action == "copied"


def test_migrate_skill_version_storage_item_rejects_unknown_source_root(tmp_path):
    source_dir = tmp_path / "workspaces" / "demo-skill"
    content_hash, file_manifest_hash = _write_skill(source_dir, "SKILL_RUNTIME_OK_V1")

    with pytest.raises(SkillStorageMigrationError, match="Unsupported legacy Skill source path"):
        migrate_skill_version_storage_item(
            tmp_path,
            SkillVersionStorageMigrationItem(
                skill_id=SKILL_ID,
                version_number=1,
                source_path="workspaces/demo-skill",
                content_hash=content_hash,
                file_manifest_hash=file_manifest_hash,
            ),
        )
