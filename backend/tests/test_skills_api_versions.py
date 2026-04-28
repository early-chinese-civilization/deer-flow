import asyncio

import pytest
from fastapi import HTTPException

from app.gateway.db.models import Skill, SkillRelease, User
from app.gateway.routers import skills as skills_router


class FakeDb:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


def _user() -> User:
    return User(id=7, external_auth_id="sub", username="alice", display_name="Alice")


def _public_skill(skill_id: int, name: str = "demo-skill") -> Skill:
    return Skill(id=skill_id, user_id=None, owner_user_id=7, name=name, display_name=name, description="Public skill", file_path=f"public/{name}")


def _custom_skill(skill_id: int, name: str = "demo-skill") -> Skill:
    return Skill(id=skill_id, user_id=7, owner_user_id=None, name=name, display_name=name, description="Custom skill", file_path=f"7/{name}")


def _release(published_skill_id: int, package_version: str | None = "v1.2.3") -> SkillRelease:
    return SkillRelease(
        id=30,
        skill_name="demo-skill",
        release_version="rel_fixed",
        package_version=package_version,
        description="Public skill",
        status="published",
        artifact_path="public/demo-skill",
        publisher_user_id=7,
        source_skill_id=11,
        published_skill_id=published_skill_id,
    )


def test_list_skills_includes_public_latest_release_metadata_and_legacy_null(monkeypatch):
    db = FakeDb()
    current_user = _user()
    versioned_public = _public_skill(12, "demo-skill")
    legacy_public = _public_skill(99, "legacy-skill")
    calls = []

    async def list_visible_skills(db_arg, *, user_id):
        assert db_arg is db
        assert user_id == 7
        return [versioned_public, legacy_public]

    async def get_latest_release_for_public_skill(db_arg, *, published_skill_id):
        calls.append(published_skill_id)
        return _release(published_skill_id) if published_skill_id == 12 else None

    monkeypatch.setattr(skills_router.SkillRepository, "list_visible_skills", list_visible_skills)
    monkeypatch.setattr(skills_router.SkillReleaseRepository, "get_latest_release_for_public_skill", get_latest_release_for_public_skill)

    async def run():
        return await skills_router.list_skills(current_user=current_user, db=db)

    response = asyncio.run(run())

    by_name = {skill.name: skill for skill in response.skills}
    assert calls == [12, 99]
    assert by_name["demo-skill"].package_version == "v1.2.3"
    assert by_name["demo-skill"].release_version == "rel_fixed"
    assert by_name["demo-skill"].release_status == "published"
    assert by_name["demo-skill"].version == "v1.2.3"
    assert by_name["legacy-skill"].package_version is None
    assert by_name["legacy-skill"].release_version is None
    assert by_name["legacy-skill"].version is None


def test_list_skills_includes_custom_package_version_from_skill_md(tmp_path, monkeypatch):
    db = FakeDb()
    current_user = _user()
    custom = _custom_skill(21, "demo-skill")
    skill_dir = tmp_path / "custom" / "demo-skill"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: demo-skill\ndescription: Custom skill\nversion: custom-v1\n---\n\n# Demo Skill\n",
        encoding="utf-8",
    )

    async def list_visible_skills(db_arg, *, user_id):
        return [custom]

    monkeypatch.setattr(skills_router.SkillRepository, "list_visible_skills", list_visible_skills)
    monkeypatch.setattr(skills_router, "_resolve_skill_record_dir", lambda skill: skill_dir)

    async def run():
        return await skills_router.list_skills(current_user=current_user, db=db)

    response = asyncio.run(run())

    assert response.skills[0].category == "custom"
    assert response.skills[0].package_version == "custom-v1"
    assert response.skills[0].version == "custom-v1"
    assert response.skills[0].release_version is None


def test_get_skill_includes_public_latest_release_metadata(monkeypatch):
    db = FakeDb()
    current_user = _user()
    public = _public_skill(12, "demo-skill")

    async def get_visible_skill_by_name(db_arg, *, user_id, name):
        assert name == "demo-skill"
        return public

    async def get_latest_release_for_public_skill(db_arg, *, published_skill_id):
        assert published_skill_id == 12
        return _release(published_skill_id)

    monkeypatch.setattr(skills_router.SkillRepository, "get_visible_skill_by_name", get_visible_skill_by_name)
    monkeypatch.setattr(skills_router.SkillReleaseRepository, "get_latest_release_for_public_skill", get_latest_release_for_public_skill)

    async def run():
        return await skills_router.get_skill("demo-skill", current_user=current_user, db=db)

    response = asyncio.run(run())

    assert response.package_version == "v1.2.3"
    assert response.release_version == "rel_fixed"
    assert response.version == "v1.2.3"


def test_download_public_skill_response_includes_source_release_metadata(tmp_path, monkeypatch):
    db = FakeDb()
    current_user = _user()
    source_dir = tmp_path / "public" / "demo-skill"
    target_dir = tmp_path / "custom" / "demo-skill"
    source_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / "SKILL.md").write_text(
        "---\nname: demo-skill\ndescription: Public skill\nversion: v1.2.3\n---\n\n# Demo Skill\n",
        encoding="utf-8",
    )
    public = _public_skill(12, "demo-skill")
    created = _custom_skill(21, "demo-skill")

    async def get_download_source_skill(db_arg, *, skill_name, owner_user_id):
        assert skill_name == "demo-skill"
        return public

    async def get_user_skill_by_name(db_arg, *, user_id, name):
        return None

    async def create_skill(db_arg, **kwargs):
        assert kwargs["commit"] is False
        return created

    async def get_skill_by_id(db_arg, skill_id):
        assert skill_id == 21
        return created

    async def get_latest_release_for_public_skill(db_arg, *, published_skill_id):
        assert published_skill_id == 12
        return _release(published_skill_id)

    monkeypatch.setattr(skills_router, "_get_download_source_skill", get_download_source_skill)
    monkeypatch.setattr(skills_router.SkillRepository, "get_user_skill_by_name", get_user_skill_by_name)
    monkeypatch.setattr(skills_router.SkillRepository, "create_skill", create_skill)
    monkeypatch.setattr(skills_router.SkillRepository, "get_skill_by_id", get_skill_by_id)
    monkeypatch.setattr(skills_router.SkillReleaseRepository, "get_latest_release_for_public_skill", get_latest_release_for_public_skill)
    monkeypatch.setattr(skills_router, "_resolve_skill_record_dir", lambda skill: source_dir)
    monkeypatch.setattr(skills_router, "_resolve_skill_dir", lambda raw_path: target_dir)

    async def run():
        return await skills_router.download_skill("demo-skill", skills_router.SkillDownloadRequest(overwrite=False), current_user=current_user, db=db)

    response = asyncio.run(run())

    assert db.commits == 1
    assert (target_dir / "SKILL.md").exists()
    assert response.category == "custom"
    assert response.package_version == "v1.2.3"
    assert response.release_version == "rel_fixed"
    assert response.version == "v1.2.3"


def test_download_public_skill_existing_custom_without_overwrite_still_returns_409(tmp_path, monkeypatch):
    db = FakeDb()
    current_user = _user()
    target_dir = tmp_path / "custom" / "demo-skill"
    target_dir.mkdir(parents=True, exist_ok=True)
    public = _public_skill(12, "demo-skill")
    existing = _custom_skill(21, "demo-skill")

    async def get_download_source_skill(db_arg, *, skill_name, owner_user_id):
        return public

    async def get_user_skill_by_name(db_arg, *, user_id, name):
        return existing

    monkeypatch.setattr(skills_router, "_get_download_source_skill", get_download_source_skill)
    monkeypatch.setattr(skills_router.SkillRepository, "get_user_skill_by_name", get_user_skill_by_name)
    monkeypatch.setattr(skills_router, "_resolve_skill_dir", lambda raw_path: target_dir)

    async def run():
        with pytest.raises(HTTPException) as exc_info:
            await skills_router.download_skill("demo-skill", skills_router.SkillDownloadRequest(overwrite=False), current_user=current_user, db=db)
        return exc_info.value

    exc = asyncio.run(run())

    assert exc.status_code == 409
    assert "already exists" in exc.detail
    assert db.rollbacks == 1
