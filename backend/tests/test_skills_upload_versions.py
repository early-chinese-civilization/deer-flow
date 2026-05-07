from __future__ import annotations

import asyncio
import io
import zipfile
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.gateway.db.models import Skill, SkillDefinition, SkillVersion, User
from app.gateway.routers import skills as skills_router


class FakeDb:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0
        self.flushed = 0

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1

    async def flush(self):
        self.flushed += 1


class FakeUploadFile:
    def __init__(self, filename: str, content: bytes):
        self.filename = filename
        self._content = content

    async def read(self) -> bytes:
        return self._content


def _user() -> User:
    return User(id=7, external_auth_id="sub", username="alice", display_name="Alice")


def _write_skill_dir(
    skill_dir: Path,
    *,
    version: str | None,
    marker: str = "SKILL_RUNTIME_OK_V1",
) -> None:
    skill_dir.mkdir(parents=True, exist_ok=True)
    version_line = f"version: {version}\n" if version is not None else ""
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: demo-skill\ndescription: Demo skill\n{version_line}---\n\n{marker}\n",
        encoding="utf-8",
    )


def _zip_skill_archive(skill_md: str) -> bytes:
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as zip_ref:
        zip_ref.writestr("demo-skill/SKILL.md", skill_md)
    return archive.getvalue()


def test_package_version_does_not_participate_in_platform_content_hash(tmp_path):
    v1 = tmp_path / "v1"
    v2 = tmp_path / "v2"
    changed = tmp_path / "changed"
    _write_skill_dir(v1, version="1.0.0", marker="SKILL_RUNTIME_OK_V1")
    _write_skill_dir(v2, version="2.0.0", marker="SKILL_RUNTIME_OK_V1")
    _write_skill_dir(changed, version="1.0.0", marker="SKILL_RUNTIME_OK_V2")

    v1_hash, v1_manifest_hash = skills_router._hash_skill_directory(v1)
    v2_hash, v2_manifest_hash = skills_router._hash_skill_directory(v2)
    changed_hash, _ = skills_router._hash_skill_directory(changed)

    assert v1_hash == v2_hash
    assert v1_manifest_hash != v2_manifest_hash
    assert changed_hash != v1_hash


def test_ensure_skill_version_creates_v1_then_v2_and_reuses_identical_content(tmp_path, monkeypatch):
    definition = SkillDefinition(id=1, name="demo-skill", display_name="demo-skill", description="Demo skill", owner_user_id=7)
    versions: list[SkillVersion] = []

    async def get_or_create(db, *, name, display_name, description, owner_user_id):
        assert name == "demo-skill"
        return definition

    async def get_by_definition_and_hash(db, *, skill_definition_id, content_hash):
        return next((version for version in versions if version.content_hash == content_hash), None)

    async def get_latest_for_definition(db, *, skill_definition_id):
        return versions[-1] if versions else None

    async def create_version(db, *, definition, source_package_version, description, content_hash, file_manifest_hash, artifact_uri, created_by_user_id):
        version = SkillVersion(
            id=len(versions) + 1,
            skill_definition_id=definition.id,
            version_number=len(versions) + 1,
            source_package_version=source_package_version,
            description=description,
            content_hash=content_hash,
            file_manifest_hash=file_manifest_hash,
            artifact_uri=artifact_uri,
            created_by_user_id=created_by_user_id,
        )
        versions.append(version)
        return version

    monkeypatch.setattr(skills_router.SkillDefinitionRepository, "get_or_create", get_or_create)
    monkeypatch.setattr(skills_router.SkillVersionRepository, "get_by_definition_and_hash", get_by_definition_and_hash)
    monkeypatch.setattr(skills_router.SkillVersionRepository, "get_latest_for_definition", get_latest_for_definition)
    monkeypatch.setattr(skills_router.SkillVersionRepository, "create_version", create_version)
    monkeypatch.setattr(skills_router, "_copy_version_artifact", lambda source_dir, artifact_uri: None)

    v1_dir = tmp_path / "v1"
    same_dir = tmp_path / "same"
    v2_dir = tmp_path / "v2"
    _write_skill_dir(v1_dir, version="pkg-a", marker="SKILL_RUNTIME_OK_V1")
    _write_skill_dir(same_dir, version="pkg-b", marker="SKILL_RUNTIME_OK_V1")
    _write_skill_dir(v2_dir, version="pkg-a", marker="SKILL_RUNTIME_OK_V2")

    async def run():
        v1, created_v1, _ = await skills_router._ensure_skill_version_from_dir(
            FakeDb(),
            user_id=7,
            skill_name="demo-skill",
            description="Demo skill",
            source_package_version="pkg-a",
            skill_dir=v1_dir,
        )
        same, created_same, _ = await skills_router._ensure_skill_version_from_dir(
            FakeDb(),
            user_id=7,
            skill_name="demo-skill",
            description="Demo skill",
            source_package_version="pkg-b",
            skill_dir=same_dir,
        )
        v2, created_v2, _ = await skills_router._ensure_skill_version_from_dir(
            FakeDb(),
            user_id=7,
            skill_name="demo-skill",
            description="Demo skill",
            source_package_version="pkg-a",
            skill_dir=v2_dir,
        )
        return v1, created_v1, same, created_same, v2, created_v2

    v1, created_v1, same, created_same, v2, created_v2 = asyncio.run(run())

    assert created_v1 is True
    assert v1.version_number == 1
    assert created_same is False
    assert same.id == v1.id
    assert created_v2 is True
    assert v2.version_number == 2
    assert v1.artifact_uri != v2.artifact_uri
    assert len(versions) == 2


def test_ensure_skill_version_keeps_same_name_different_owners_distinct(tmp_path, monkeypatch):
    definitions: list[SkillDefinition] = []
    versions: list[SkillVersion] = []

    async def get_or_create(db, *, name, display_name, description, owner_user_id, source_type=None, source_identifier=None):
        source_type = source_type or "user"
        source_identifier = source_identifier or str(owner_user_id)
        existing = next(
            (
                definition
                for definition in definitions
                if definition.name == name and definition.source_type == source_type and definition.source_identifier == source_identifier
            ),
            None,
        )
        if existing is not None:
            return existing
        definition = SkillDefinition(
            id=len(definitions) + 1,
            name=name,
            display_name=display_name,
            description=description,
            source_type=source_type,
            source_identifier=source_identifier,
            owner_user_id=owner_user_id,
        )
        definitions.append(definition)
        return definition

    async def get_by_definition_and_hash(db, *, skill_definition_id, content_hash):
        return next((version for version in versions if version.skill_definition_id == skill_definition_id and version.content_hash == content_hash), None)

    async def get_latest_for_definition(db, *, skill_definition_id):
        scoped = [version for version in versions if version.skill_definition_id == skill_definition_id]
        return scoped[-1] if scoped else None

    async def create_version(db, *, definition, source_package_version, description, content_hash, file_manifest_hash, artifact_uri, created_by_user_id):
        version = SkillVersion(
            id=len(versions) + 1,
            skill_definition_id=definition.id,
            version_number=1,
            source_package_version=source_package_version,
            description=description,
            content_hash=content_hash,
            file_manifest_hash=file_manifest_hash,
            artifact_uri=artifact_uri,
            created_by_user_id=created_by_user_id,
            definition=definition,
        )
        versions.append(version)
        return version

    monkeypatch.setattr(skills_router.SkillDefinitionRepository, "get_or_create", get_or_create)
    monkeypatch.setattr(skills_router.SkillVersionRepository, "get_by_definition_and_hash", get_by_definition_and_hash)
    monkeypatch.setattr(skills_router.SkillVersionRepository, "get_latest_for_definition", get_latest_for_definition)
    monkeypatch.setattr(skills_router.SkillVersionRepository, "create_version", create_version)
    monkeypatch.setattr(skills_router, "_copy_version_artifact", lambda source_dir, artifact_uri: None)

    skill_dir = tmp_path / "same-name"
    _write_skill_dir(skill_dir, version="pkg-a", marker="SAME_RUNTIME")

    async def run():
        owner_a = await skills_router._ensure_skill_version_from_dir(
            FakeDb(),
            user_id=7,
            skill_name="demo-skill",
            description="Owner A",
            source_package_version="pkg-a",
            skill_dir=skill_dir,
        )
        owner_b = await skills_router._ensure_skill_version_from_dir(
            FakeDb(),
            user_id=8,
            skill_name="demo-skill",
            description="Owner B",
            source_package_version="pkg-a",
            skill_dir=skill_dir,
        )
        return owner_a, owner_b

    (version_a, created_a, definition_a), (version_b, created_b, definition_b) = asyncio.run(run())

    assert created_a is True
    assert created_b is True
    assert definition_a.name == definition_b.name == "demo-skill"
    assert definition_a.id != definition_b.id
    assert definition_a.source_identifier == "7"
    assert definition_b.source_identifier == "8"
    assert version_a.skill_definition_id == definition_a.id
    assert version_b.skill_definition_id == definition_b.id


def test_user_skill_definition_lookup_ignores_same_name_other_source(monkeypatch):
    other_source_skill = Skill(id=10, user_id=7, skill_definition_id=900, name="demo-skill", display_name="demo-skill", description="Other source", file_path="artifacts/skills/900/v1/demo-skill")

    async def get_user_skill_by_definition(db, *, user_id, skill_definition_id):
        assert user_id == 7
        assert skill_definition_id == 100
        return None

    async def list_user_skills_by_name(db, *, user_id, name):
        assert user_id == 7
        assert name == "demo-skill"
        return [other_source_skill]

    monkeypatch.setattr(skills_router.SkillRepository, "get_user_skill_by_definition", get_user_skill_by_definition)
    monkeypatch.setattr(skills_router.SkillRepository, "list_user_skills_by_name", list_user_skills_by_name)

    result = asyncio.run(
        skills_router._get_user_skill_by_definition_or_legacy(
            FakeDb(),
            user_id=7,
            skill_name="demo-skill",
            skill_definition_id=100,
        )
    )

    assert result is None


def test_user_skill_definition_lookup_preserves_legacy_name_only_fallback(monkeypatch):
    legacy_skill = Skill(id=11, user_id=7, skill_definition_id=None, name="demo-skill", display_name="demo-skill", description="Legacy", file_path="7/demo-skill")

    async def get_user_skill_by_definition(db, *, user_id, skill_definition_id):
        return None

    async def list_user_skills_by_name(db, *, user_id, name):
        return [legacy_skill]

    monkeypatch.setattr(skills_router.SkillRepository, "get_user_skill_by_definition", get_user_skill_by_definition)
    monkeypatch.setattr(skills_router.SkillRepository, "list_user_skills_by_name", list_user_skills_by_name)

    result = asyncio.run(
        skills_router._get_user_skill_by_definition_or_legacy(
            FakeDb(),
            user_id=7,
            skill_name="demo-skill",
            skill_definition_id=100,
        )
    )

    assert result is legacy_skill


def test_version_artifact_copy_does_not_overwrite_prior_platform_version(tmp_path, monkeypatch):
    skills_root = tmp_path / "skills"
    monkeypatch.setattr(skills_router, "_resolve_skill_dir", lambda artifact_uri: skills_root / artifact_uri)
    v1_dir = tmp_path / "v1"
    v2_dir = tmp_path / "v2"
    _write_skill_dir(v1_dir, version="pkg-a", marker="SKILL_RUNTIME_OK_V1")
    _write_skill_dir(v2_dir, version="pkg-a", marker="SKILL_RUNTIME_OK_V2")
    v1_uri = "artifacts/skills/1/v1-aaa/demo-skill"
    v2_uri = "artifacts/skills/1/v2-bbb/demo-skill"

    skills_router._copy_version_artifact(v1_dir, v1_uri)
    skills_router._copy_version_artifact(v2_dir, v2_uri)

    assert "SKILL_RUNTIME_OK_V1" in (skills_root / v1_uri / "SKILL.md").read_text(encoding="utf-8")
    assert "SKILL_RUNTIME_OK_V2" in (skills_root / v2_uri / "SKILL.md").read_text(encoding="utf-8")


def test_check_upload_rejects_non_string_package_version():
    archive = _zip_skill_archive("---\nname: demo-skill\ndescription: Demo skill\nversion: 1.2\n---\n\n# Demo Skill\n")

    async def run():
        with pytest.raises(HTTPException) as exc_info:
            await skills_router.check_skill_upload(
                file=FakeUploadFile("demo.zip", archive),
                current_user=_user(),
                db=FakeDb(),
            )
        return exc_info.value

    exc = asyncio.run(run())

    assert exc.status_code == 400
    assert "Version must be a string" in exc.detail


def test_upload_rejects_non_string_package_version():
    archive = _zip_skill_archive("---\nname: demo-skill\ndescription: Demo skill\nversion: 1.2\n---\n\n# Demo Skill\n")
    db = FakeDb()

    async def run():
        return await skills_router.upload_skills(
            files=[FakeUploadFile("demo.zip", archive)],
            overwrite_names=None,
            current_user=_user(),
            db=db,
        )

    response = asyncio.run(run())

    assert db.commits == 0
    assert db.rollbacks == 1
    assert response.results[0].success is False
    assert "Version must be a string" in response.results[0].message
