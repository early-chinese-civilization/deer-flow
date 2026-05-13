import asyncio
from pathlib import Path
from uuid import UUID

import pytest
from fastapi import HTTPException

from app.gateway.db.models import LegacySkill as Skill
from app.gateway.db.models import SkillDefinition, SkillInstall, SkillRelease, SkillVersion, User
from app.gateway.routers import skills as skills_router

DEMO_TERMINAL_SKILL_ID = UUID("11111111-1111-4111-8111-111111111111")


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
    version_dir = tmp_path / str(DEMO_TERMINAL_SKILL_ID) / str(version_number)
    _write_skill_dir(version_dir, version=source_package_version)
    definition = SkillDefinition(
        id=100,
        name="demo-skill",
        display_name="demo-skill",
        description="Published description",
        source_type="user",
        source_identifier="7",
        owner_user_id=7,
    )
    version = SkillVersion(
        id=200 + version_number,
        skill_id=DEMO_TERMINAL_SKILL_ID,
        skill_definition_id=100,
        version_number=version_number,
        source_package_version=source_package_version,
        description="Published description",
        content_hash=f"hash-{version_number}",
        file_manifest_hash=f"manifest-{version_number}",
        definition=definition,
    )
    install = SkillInstall(
        id=300,
        user_id=7,
        skill_id=version.skill_id,
        version_number=version.version_number,
        skill_definition_id=100,
        installed_version_id=version.id,
        current_version_id=version.id,
        definition=definition,
        current_version=version,
    )
    return definition, version, install, version_dir


def _version_relative_path(version: SkillVersion) -> str:
    return f"{version.skill_id}/{version.version_number}"


def test_publish_custom_skill_creates_release_for_current_skill_version(tmp_path, monkeypatch):
    definition, version, install, version_dir = _version(tmp_path, version_number=1)
    target_dir = tmp_path / "public" / "demo-skill"
    current_user = _user()
    custom_skill = Skill(id=11, user_id=7, skill_definition_id=definition.id, name="demo-skill", display_name="demo-skill", description="Old description", file_path="7/demo-skill")
    release = SkillRelease(
        id=30,
        skill_id=version.skill_id,
        version_number=version.version_number,
        skill_name="demo-skill",
        release_version="rel_fixed",
        package_version=version.source_package_version,
        description="Published description",
        release_notes="Published changelog",
        status="published",
        publisher_user_id=7,
        published_skill_id=None,
    )
    db = FakeDb()
    calls = {"soft_deleted": [], "created": [], "releases": []}

    async def get_user_skill_by_name(db_arg, *, user_id, name):
        return custom_skill

    async def list_user_skills_by_name(db_arg, *, user_id, name):
        return [custom_skill]

    async def get_user_skill_by_definition(db_arg, *, user_id, skill_definition_id):
        assert skill_definition_id == definition.id
        return custom_skill

    async def get_definition_by_name_and_owner(db_arg, *, name, owner_user_id):
        assert owner_user_id == 7
        return definition

    async def get_install_by_user_and_definition(db_arg, *, user_id, skill_definition_id):
        assert skill_definition_id == definition.id
        return install

    async def list_public_skills_by_name_and_owner(db_arg, *, name, owner_user_id):
        calls["public_listed"] = True
        return []

    async def soft_delete_skill(db_arg, *, skill, commit=True):
        calls["soft_deleted"].append((skill.id, commit))

    async def create_skill(db_arg, **kwargs):
        calls["created"].append(kwargs)

    async def get_skill_by_id(db_arg, skill_id):
        raise AssertionError("publish must not resolve a legacy public latest skill row")

    async def create_release(db_arg, **kwargs):
        calls["releases"].append(kwargs)
        return release

    monkeypatch.setattr(skills_router.SkillDefinitionRepository, "get_by_name_and_owner", get_definition_by_name_and_owner)
    monkeypatch.setattr(skills_router.SkillRepository, "get_user_skill_by_name", get_user_skill_by_name)
    monkeypatch.setattr(skills_router.SkillRepository, "list_user_skills_by_name", list_user_skills_by_name)
    monkeypatch.setattr(skills_router.SkillRepository, "get_user_skill_by_definition", get_user_skill_by_definition)
    monkeypatch.setattr(skills_router.SkillInstallRepository, "get_by_user_and_definition", get_install_by_user_and_definition)
    monkeypatch.setattr(skills_router.SkillRepository, "list_public_skills_by_name_and_owner", list_public_skills_by_name_and_owner)
    monkeypatch.setattr(skills_router.SkillRepository, "soft_delete_skill", soft_delete_skill)
    monkeypatch.setattr(skills_router.SkillRepository, "create_skill", create_skill)
    monkeypatch.setattr(skills_router.SkillRepository, "get_skill_by_id", get_skill_by_id)
    monkeypatch.setattr(skills_router.SkillReleaseRepository, "create_release", create_release)
    monkeypatch.setattr(skills_router, "_resolve_skill_dir", lambda raw_path: version_dir if raw_path == _version_relative_path(version) else target_dir)

    async def run():
        return await skills_router.publish_skill("demo-skill", current_user=current_user, db=db)

    response = asyncio.run(run())

    assert db.commits == 1
    assert not target_dir.exists()
    assert not calls.get("public_listed", False)
    assert calls["soft_deleted"] == []
    assert calls["created"] == []
    assert len(calls["releases"]) == 1
    release_kwargs = calls["releases"][0]
    assert release_kwargs["skill_id"] == version.skill_id
    assert release_kwargs["version_number"] == version.version_number
    assert release_kwargs["package_version"] == version.source_package_version
    assert "artifact_path" not in release_kwargs
    assert "skill_version_id" not in release_kwargs
    assert response.skill_id == str(version.skill_id)
    assert response.version_number == version.version_number
    assert response.platform_version == 1
    assert response.version == "1"
    assert response.package_version == "v1.2.3"


def test_publish_normalizes_release_notes_and_keeps_platform_version(tmp_path, monkeypatch):
    definition, version, install, version_dir = _version(tmp_path, version_number=2, source_package_version=None)
    target_dir = tmp_path / "public" / "demo-skill"
    custom_skill = Skill(id=11, user_id=7, skill_definition_id=definition.id, name="demo-skill", display_name="demo-skill", description="Old", file_path="7/demo-skill")
    published_skill = Skill(id=12, user_id=None, owner_user_id=7, skill_definition_id=definition.id, name="demo-skill", display_name="demo-skill", description="Published description", file_path="public/demo-skill")
    release_kwargs = {}

    async def get_user_skill_by_name(db_arg, *, user_id, name):
        return custom_skill

    async def list_user_skills_by_name(db_arg, *, user_id, name):
        return [custom_skill]

    async def get_user_skill_by_definition(db_arg, *, user_id, skill_definition_id):
        return custom_skill

    async def get_definition_by_name_and_owner(db_arg, *, name, owner_user_id):
        return definition

    async def get_install_by_user_and_definition(db_arg, *, user_id, skill_definition_id):
        return install

    async def list_public_skills_by_name_and_owner(db_arg, *, name, owner_user_id):
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
            publisher_user_id=7,
            skill_id=version.skill_id,
            version_number=version.version_number,
        )

    monkeypatch.setattr(skills_router.SkillDefinitionRepository, "get_by_name_and_owner", get_definition_by_name_and_owner)
    monkeypatch.setattr(skills_router.SkillRepository, "get_user_skill_by_name", get_user_skill_by_name)
    monkeypatch.setattr(skills_router.SkillRepository, "list_user_skills_by_name", list_user_skills_by_name)
    monkeypatch.setattr(skills_router.SkillRepository, "get_user_skill_by_definition", get_user_skill_by_definition)
    monkeypatch.setattr(skills_router.SkillInstallRepository, "get_by_user_and_definition", get_install_by_user_and_definition)
    monkeypatch.setattr(skills_router.SkillRepository, "list_public_skills_by_name_and_owner", list_public_skills_by_name_and_owner)
    monkeypatch.setattr(skills_router.SkillRepository, "create_skill", create_skill)
    monkeypatch.setattr(skills_router.SkillRepository, "get_skill_by_id", get_skill_by_id)
    monkeypatch.setattr(skills_router.SkillReleaseRepository, "create_release", create_release)
    monkeypatch.setattr(skills_router, "_resolve_skill_dir", lambda raw_path: version_dir if raw_path == _version_relative_path(version) else target_dir)

    async def run():
        return await skills_router.publish_skill(
            "demo-skill",
            request=skills_router.SkillPublishRequest(release_notes="  Ship v2  "),
            current_user=_user(),
            db=FakeDb(),
        )

    response = asyncio.run(run())

    assert release_kwargs["release_notes"] == "Ship v2"
    assert release_kwargs["skill_id"] == version.skill_id
    assert release_kwargs["version_number"] == version.version_number
    assert "artifact_path" not in release_kwargs
    assert "skill_version_id" not in release_kwargs
    assert response.platform_version == 2
    assert response.version == "2"
    assert response.package_version is None


def test_publish_missing_install_hard_fails_without_public_latest_fallback(monkeypatch):
    db = FakeDb()
    definition = SkillDefinition(id=100, name="demo-skill", source_type="user", source_identifier="7", owner_user_id=7)
    custom_skill = Skill(id=11, user_id=7, skill_definition_id=definition.id, name="demo-skill", display_name="demo-skill", description="Old", file_path="7/demo-skill")

    async def get_user_skill_by_name(db_arg, *, user_id, name):
        return custom_skill

    async def list_user_skills_by_name(db_arg, *, user_id, name):
        return [custom_skill]

    async def get_user_skill_by_definition(db_arg, *, user_id, skill_definition_id):
        return custom_skill

    async def get_definition_by_name_and_owner(db_arg, *, name, owner_user_id):
        return definition

    async def get_install_by_user_and_definition(db_arg, *, user_id, skill_definition_id):
        return None

    monkeypatch.setattr(skills_router.SkillDefinitionRepository, "get_by_name_and_owner", get_definition_by_name_and_owner)
    monkeypatch.setattr(skills_router.SkillRepository, "get_user_skill_by_name", get_user_skill_by_name)
    monkeypatch.setattr(skills_router.SkillRepository, "list_user_skills_by_name", list_user_skills_by_name)
    monkeypatch.setattr(skills_router.SkillRepository, "get_user_skill_by_definition", get_user_skill_by_definition)
    monkeypatch.setattr(skills_router.SkillInstallRepository, "get_by_user_and_definition", get_install_by_user_and_definition)

    async def run():
        with pytest.raises(HTTPException) as exc_info:
            await skills_router.publish_skill("demo-skill", current_user=_user(), db=db)
        return exc_info.value

    exc = asyncio.run(run())

    assert exc.status_code == 409
    assert "no installed platform version" in exc.detail
    assert db.rollbacks == 1


@pytest.mark.parametrize(
    ("source_type", "source_identifier", "owner_user_id", "expected_detail"),
    [
        ("user", "8", 8, "installed from Community Space"),
        ("legacy", "legacy", None, "installed from Community Space"),
    ],
)
def test_publish_rejects_installed_community_source_identity_before_release(source_type, source_identifier, owner_user_id, expected_detail, monkeypatch):
    db = FakeDb()
    source_owner = User(id=8, external_auth_id="sub-8", username="bob", display_name="Bob")
    definition = SkillDefinition(
        id=100,
        name="demo-skill",
        source_type=source_type,
        source_identifier=source_identifier,
        owner_user_id=owner_user_id,
        owner_user=source_owner if owner_user_id is not None else None,
    )
    version = SkillVersion(
        id=201,
        skill_definition_id=definition.id,
        version_number=1,
        source_package_version=None,
        description="Installed community source",
        content_hash="source-content",
        file_manifest_hash="source-manifest",
        definition=definition,
    )
    install = SkillInstall(
        id=300,
        user_id=7,
        skill_definition_id=definition.id,
        installed_version_id=version.id,
        current_version_id=version.id,
        definition=definition,
        current_version=version,
    )

    async def get_definition_by_name_and_owner(db_arg, *, name, owner_user_id):
        assert owner_user_id == 7
        return None

    async def list_installs_by_name(db_arg, *, user_id, name):
        assert user_id == 7
        return [install]

    async def list_public_skills_by_name_and_owner(db_arg, *, name, owner_user_id):
        raise AssertionError("installed publish authorization must fail before public listing lookup")

    async def create_release(db_arg, **kwargs):
        raise AssertionError("installed publish authorization must fail before release creation")

    monkeypatch.setattr(skills_router.SkillDefinitionRepository, "get_by_name_and_owner", get_definition_by_name_and_owner)
    monkeypatch.setattr(skills_router.SkillInstallRepository, "list_by_user_and_name", list_installs_by_name)
    monkeypatch.setattr(skills_router.SkillRepository, "list_public_skills_by_name_and_owner", list_public_skills_by_name_and_owner)
    monkeypatch.setattr(skills_router.SkillReleaseRepository, "create_release", create_release)

    async def run():
        with pytest.raises(HTTPException) as exc_info:
            await skills_router.publish_skill("demo-skill", current_user=_user(), db=db)
        return exc_info.value

    exc = asyncio.run(run())

    assert exc.status_code == 403
    assert expected_detail in exc.detail
    assert db.rollbacks == 1
    assert db.commits == 0

def test_publish_rejects_invalid_source_metadata_before_db_side_effects(tmp_path, monkeypatch):
    definition, version, install, artifact_dir = _version(tmp_path, version_number=1)
    (artifact_dir / "SKILL.md").write_text(
        "---\nname: demo-skill\ndescription: Published description\nversion: 1.2\n---\n\n# Demo Skill\n",
        encoding="utf-8",
    )
    db = FakeDb()
    custom_skill = Skill(id=11, user_id=7, skill_definition_id=definition.id, name="demo-skill", display_name="demo-skill", description="Old", file_path="7/demo-skill")

    async def get_user_skill_by_name(db_arg, *, user_id, name):
        return custom_skill

    async def list_user_skills_by_name(db_arg, *, user_id, name):
        return [custom_skill]

    async def get_user_skill_by_definition(db_arg, *, user_id, skill_definition_id):
        return custom_skill

    async def get_definition_by_name_and_owner(db_arg, *, name, owner_user_id):
        return definition

    async def get_install_by_user_and_definition(db_arg, *, user_id, skill_definition_id):
        return install

    async def list_public_skills_by_name_and_owner(db_arg, *, name, owner_user_id):
        raise AssertionError("invalid metadata should not query public rows")

    monkeypatch.setattr(skills_router.SkillDefinitionRepository, "get_by_name_and_owner", get_definition_by_name_and_owner)
    monkeypatch.setattr(skills_router.SkillRepository, "get_user_skill_by_name", get_user_skill_by_name)
    monkeypatch.setattr(skills_router.SkillRepository, "list_user_skills_by_name", list_user_skills_by_name)
    monkeypatch.setattr(skills_router.SkillRepository, "get_user_skill_by_definition", get_user_skill_by_definition)
    monkeypatch.setattr(skills_router.SkillInstallRepository, "get_by_user_and_definition", get_install_by_user_and_definition)
    monkeypatch.setattr(skills_router.SkillRepository, "list_public_skills_by_name_and_owner", list_public_skills_by_name_and_owner)
    monkeypatch.setattr(skills_router, "_resolve_skill_dir", lambda raw_path: artifact_dir)

    async def run():
        with pytest.raises(HTTPException) as exc_info:
            await skills_router.publish_skill("demo-skill", current_user=_user(), db=db)
        return exc_info.value

    exc = asyncio.run(run())

    assert exc.status_code == 400
    assert "Version must be a string" in exc.detail
    assert db.rollbacks == 1
