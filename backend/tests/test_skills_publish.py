import asyncio
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.gateway.db.models import Skill, SkillDefinition, SkillInstall, SkillRelease, SkillVersion, User
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


def _write_skill_dir(skill_dir: Path, *, version: str | None = "v1.2.3", description: str = "Published description") -> None:
    skill_dir.mkdir(parents=True, exist_ok=True)
    version_line = f"version: {version}\n" if version is not None else ""
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: demo-skill\ndescription: {description}\n{version_line}---\n\n# Demo Skill\n",
        encoding="utf-8",
    )


def _user(user_id: int = 7) -> User:
    return User(id=user_id, external_auth_id=f"sub-{user_id}", username="alice", display_name="Alice")


def _version(tmp_path: Path, *, version_number: int = 1, source_package_version: str | None = "v1.2.3") -> tuple[SkillDefinition, SkillVersion, SkillInstall, Path]:
    artifact_dir = tmp_path / "artifacts" / "skills" / "100" / f"v{version_number}" / "demo-skill"
    _write_skill_dir(artifact_dir, version=source_package_version)
    definition = SkillDefinition(id=100, name="demo-skill", display_name="demo-skill", description="Published description")
    version = SkillVersion(
        id=200 + version_number,
        skill_definition_id=100,
        version_number=version_number,
        source_package_version=source_package_version,
        description="Published description",
        content_hash=f"hash-{version_number}",
        file_manifest_hash=f"manifest-{version_number}",
        artifact_uri=f"artifacts/skills/100/v{version_number}/demo-skill",
        definition=definition,
    )
    install = SkillInstall(
        id=300,
        user_id=7,
        skill_definition_id=100,
        installed_version_id=version.id,
        current_version_id=version.id,
        definition=definition,
        current_version=version,
    )
    return definition, version, install, artifact_dir


def test_publish_custom_skill_creates_release_for_current_skill_version(tmp_path, monkeypatch):
    _, version, install, artifact_dir = _version(tmp_path, version_number=1)
    target_dir = tmp_path / "public" / "demo-skill"
    current_user = _user()
    custom_skill = Skill(id=11, user_id=7, name="demo-skill", display_name="demo-skill", description="Old description", file_path="7/demo-skill")
    old_public_skill = Skill(id=10, user_id=None, owner_user_id=2, name="demo-skill", display_name="demo-skill", description="Old public", file_path="public/demo-skill")
    published_skill = Skill(id=12, user_id=None, owner_user_id=7, name="demo-skill", display_name="demo-skill", description="Published description", file_path="public/demo-skill")
    release = SkillRelease(
        id=30,
        skill_name="demo-skill",
        release_version="rel_fixed",
        package_version=version.source_package_version,
        description="Published description",
        release_notes="Published changelog",
        status="published",
        artifact_path=version.artifact_uri,
        publisher_user_id=7,
        source_skill_id=11,
        published_skill_id=12,
        skill_version_id=version.id,
    )
    db = FakeDb()
    calls = {"soft_deleted": [], "created": [], "releases": []}

    async def get_user_skill_by_name(db_arg, *, user_id, name):
        return custom_skill

    async def get_install_by_user_and_name(db_arg, *, user_id, name):
        return install

    async def list_public_skills_by_name(db_arg, *, name):
        return [old_public_skill]

    async def soft_delete_skill(db_arg, *, skill, commit=True):
        calls["soft_deleted"].append((skill.id, commit))

    async def create_skill(db_arg, **kwargs):
        calls["created"].append(kwargs)
        return published_skill

    async def get_skill_by_id(db_arg, skill_id):
        return published_skill

    async def create_release(db_arg, **kwargs):
        calls["releases"].append(kwargs)
        return release

    monkeypatch.setattr(skills_router.SkillRepository, "get_user_skill_by_name", get_user_skill_by_name)
    monkeypatch.setattr(skills_router.SkillInstallRepository, "get_by_user_and_name", get_install_by_user_and_name)
    monkeypatch.setattr(skills_router.SkillRepository, "list_public_skills_by_name", list_public_skills_by_name)
    monkeypatch.setattr(skills_router.SkillRepository, "soft_delete_skill", soft_delete_skill)
    monkeypatch.setattr(skills_router.SkillRepository, "create_skill", create_skill)
    monkeypatch.setattr(skills_router.SkillRepository, "get_skill_by_id", get_skill_by_id)
    monkeypatch.setattr(skills_router.SkillReleaseRepository, "create_release", create_release)
    monkeypatch.setattr(skills_router, "_resolve_skill_dir", lambda raw_path: artifact_dir if raw_path == version.artifact_uri else target_dir)

    async def run():
        return await skills_router.publish_skill("demo-skill", current_user=current_user, db=db)

    response = asyncio.run(run())

    assert db.commits == 1
    assert (target_dir / "SKILL.md").exists()
    assert calls["soft_deleted"] == [(10, False)]
    assert calls["releases"][0]["skill_version_id"] == version.id
    assert calls["releases"][0]["artifact_path"] == version.artifact_uri
    assert calls["releases"][0]["package_version"] == version.source_package_version
    assert response.platform_version == 1
    assert response.skill_version_id == version.id
    assert response.version == "1"
    assert response.package_version == "v1.2.3"


def test_publish_normalizes_release_notes_and_keeps_platform_version(tmp_path, monkeypatch):
    _, version, install, artifact_dir = _version(tmp_path, version_number=2, source_package_version=None)
    target_dir = tmp_path / "public" / "demo-skill"
    custom_skill = Skill(id=11, user_id=7, name="demo-skill", display_name="demo-skill", description="Old", file_path="7/demo-skill")
    published_skill = Skill(id=12, user_id=None, owner_user_id=7, name="demo-skill", display_name="demo-skill", description="Published description", file_path="public/demo-skill")
    release_kwargs = {}

    async def get_user_skill_by_name(db_arg, *, user_id, name):
        return custom_skill

    async def get_install_by_user_and_name(db_arg, *, user_id, name):
        return install

    async def list_public_skills_by_name(db_arg, *, name):
        return []

    async def create_skill(db_arg, **kwargs):
        return published_skill

    async def get_skill_by_id(db_arg, skill_id):
        return published_skill

    async def create_release(db_arg, **kwargs):
        release_kwargs.update(kwargs)
        return SkillRelease(
            id=31,
            skill_name="demo-skill",
            release_version="rel_notes",
            package_version=None,
            description="Published description",
            release_notes=kwargs["release_notes"],
            status="published",
            artifact_path=version.artifact_uri,
            publisher_user_id=7,
            source_skill_id=11,
            published_skill_id=12,
            skill_version_id=version.id,
        )

    monkeypatch.setattr(skills_router.SkillRepository, "get_user_skill_by_name", get_user_skill_by_name)
    monkeypatch.setattr(skills_router.SkillInstallRepository, "get_by_user_and_name", get_install_by_user_and_name)
    monkeypatch.setattr(skills_router.SkillRepository, "list_public_skills_by_name", list_public_skills_by_name)
    monkeypatch.setattr(skills_router.SkillRepository, "create_skill", create_skill)
    monkeypatch.setattr(skills_router.SkillRepository, "get_skill_by_id", get_skill_by_id)
    monkeypatch.setattr(skills_router.SkillReleaseRepository, "create_release", create_release)
    monkeypatch.setattr(skills_router, "_resolve_skill_dir", lambda raw_path: artifact_dir if raw_path == version.artifact_uri else target_dir)

    async def run():
        return await skills_router.publish_skill(
            "demo-skill",
            request=skills_router.SkillPublishRequest(release_notes="  Ship v2  "),
            current_user=_user(),
            db=FakeDb(),
        )

    response = asyncio.run(run())

    assert release_kwargs["release_notes"] == "Ship v2"
    assert release_kwargs["skill_version_id"] == version.id
    assert response.platform_version == 2
    assert response.version == "2"
    assert response.package_version is None


def test_publish_missing_install_hard_fails_without_public_latest_fallback(monkeypatch):
    db = FakeDb()
    custom_skill = Skill(id=11, user_id=7, name="demo-skill", display_name="demo-skill", description="Old", file_path="7/demo-skill")

    async def get_user_skill_by_name(db_arg, *, user_id, name):
        return custom_skill

    async def get_install_by_user_and_name(db_arg, *, user_id, name):
        return None

    monkeypatch.setattr(skills_router.SkillRepository, "get_user_skill_by_name", get_user_skill_by_name)
    monkeypatch.setattr(skills_router.SkillInstallRepository, "get_by_user_and_name", get_install_by_user_and_name)

    async def run():
        with pytest.raises(HTTPException) as exc_info:
            await skills_router.publish_skill("demo-skill", current_user=_user(), db=db)
        return exc_info.value

    exc = asyncio.run(run())

    assert exc.status_code == 409
    assert "no installed platform version" in exc.detail
    assert db.rollbacks == 1


def test_publish_rejects_invalid_source_metadata_before_db_side_effects(tmp_path, monkeypatch):
    _, version, install, artifact_dir = _version(tmp_path, version_number=1)
    (artifact_dir / "SKILL.md").write_text(
        "---\nname: demo-skill\ndescription: Published description\nversion: 1.2\n---\n\n# Demo Skill\n",
        encoding="utf-8",
    )
    db = FakeDb()
    custom_skill = Skill(id=11, user_id=7, name="demo-skill", display_name="demo-skill", description="Old", file_path="7/demo-skill")

    async def get_user_skill_by_name(db_arg, *, user_id, name):
        return custom_skill

    async def get_install_by_user_and_name(db_arg, *, user_id, name):
        return install

    async def list_public_skills_by_name(db_arg, *, name):
        raise AssertionError("invalid metadata should not query public rows")

    monkeypatch.setattr(skills_router.SkillRepository, "get_user_skill_by_name", get_user_skill_by_name)
    monkeypatch.setattr(skills_router.SkillInstallRepository, "get_by_user_and_name", get_install_by_user_and_name)
    monkeypatch.setattr(skills_router.SkillRepository, "list_public_skills_by_name", list_public_skills_by_name)
    monkeypatch.setattr(skills_router, "_resolve_skill_dir", lambda raw_path: artifact_dir)

    async def run():
        with pytest.raises(HTTPException) as exc_info:
            await skills_router.publish_skill("demo-skill", current_user=_user(), db=db)
        return exc_info.value

    exc = asyncio.run(run())

    assert exc.status_code == 400
    assert "Version must be a string" in exc.detail
    assert db.rollbacks == 1
