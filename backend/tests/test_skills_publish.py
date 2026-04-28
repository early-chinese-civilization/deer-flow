import asyncio
from pathlib import Path

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


def _write_skill_dir(skill_dir: Path, *, version: str | None = "v1.2.3", description: str = "Published description") -> None:
    skill_dir.mkdir(parents=True, exist_ok=True)
    version_line = f"version: {version}\n" if version is not None else ""
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: demo-skill\ndescription: {description}\n{version_line}---\n\n# Demo Skill\n",
        encoding="utf-8",
    )


def test_publish_custom_skill_creates_release_and_returns_versioned_response(tmp_path, monkeypatch):
    source_dir = tmp_path / "source"
    target_dir = tmp_path / "public" / "demo-skill"
    _write_skill_dir(source_dir, version="v1.2.3")

    current_user = User(id=7, external_auth_id="sub", username="alice", display_name="Alice")
    custom_skill = Skill(id=11, user_id=7, name="demo-skill", display_name="demo-skill", description="Old description", file_path="private/7/demo-skill")
    old_public_skill = Skill(id=10, user_id=None, owner_user_id=2, name="demo-skill", display_name="demo-skill", description="Old public", file_path="public/demo-skill")
    published_skill = Skill(id=12, user_id=None, owner_user_id=7, name="demo-skill", display_name="demo-skill", description="Published description", file_path="public/demo-skill")
    release = SkillRelease(
        id=30,
        skill_name="demo-skill",
        release_version="rel_fixed",
        package_version="v1.2.3",
        description="Published description",
        release_notes="Published changelog",
        status="published",
        artifact_path="public/demo-skill",
        publisher_user_id=7,
        source_skill_id=11,
        published_skill_id=12,
    )
    db = FakeDb()
    calls = {"soft_deleted": [], "created": [], "releases": []}

    async def get_user_skill_by_name(db_arg, *, user_id, name):
        assert db_arg is db
        assert user_id == 7
        assert name == "demo-skill"
        return custom_skill

    async def list_public_skills_by_name(db_arg, *, name):
        assert db_arg is db
        assert name == "demo-skill"
        return [old_public_skill]

    async def soft_delete_skill(db_arg, *, skill, commit=True):
        calls["soft_deleted"].append((skill.id, commit))

    async def create_skill(db_arg, **kwargs):
        calls["created"].append(kwargs)
        assert kwargs["commit"] is False
        return published_skill

    async def get_skill_by_id(db_arg, skill_id):
        assert skill_id == 12
        return published_skill

    async def create_release(db_arg, **kwargs):
        calls["releases"].append(kwargs)
        assert kwargs["commit"] is False
        return release

    monkeypatch.setattr(skills_router.SkillRepository, "get_user_skill_by_name", get_user_skill_by_name)
    monkeypatch.setattr(skills_router.SkillRepository, "list_public_skills_by_name", list_public_skills_by_name)
    monkeypatch.setattr(skills_router.SkillRepository, "soft_delete_skill", soft_delete_skill)
    monkeypatch.setattr(skills_router.SkillRepository, "create_skill", create_skill)
    monkeypatch.setattr(skills_router.SkillRepository, "get_skill_by_id", get_skill_by_id)
    monkeypatch.setattr(skills_router.SkillReleaseRepository, "create_release", create_release)
    monkeypatch.setattr(skills_router, "_resolve_skill_record_dir", lambda skill: source_dir)
    monkeypatch.setattr(skills_router, "_resolve_skill_dir", lambda raw_path: target_dir)

    async def run():
        response = await skills_router.publish_skill("demo-skill", current_user=current_user, db=db)
        return response

    response = asyncio.run(run())

    assert db.commits == 1
    assert db.rollbacks == 0
    assert (target_dir / "SKILL.md").exists()
    assert calls["soft_deleted"] == [(10, False)]
    assert calls["created"] == [
        {
            "user_id": None,
            "owner_user_id": 7,
            "name": "demo-skill",
            "display_name": "demo-skill",
            "description": "Published description",
            "file_path": "public/demo-skill",
            "commit": False,
        }
    ]
    assert calls["releases"] == [
        {
            "skill_name": "demo-skill",
            "package_version": "v1.2.3",
            "description": "Published description",
            "release_notes": None,
            "artifact_path": "public/demo-skill",
            "publisher_user_id": 7,
            "source_skill_id": 11,
            "published_skill_id": 12,
            "commit": False,
        }
    ]
    assert response.name == "demo-skill"
    assert response.description == "Published description"
    assert response.package_version == "v1.2.3"
    assert response.release_version == "rel_fixed"
    assert response.release_status == "published"
    assert response.release_notes == "Published changelog"


def test_publish_custom_skill_accepts_release_notes(tmp_path, monkeypatch):
    source_dir = tmp_path / "source"
    target_dir = tmp_path / "public" / "demo-skill"
    _write_skill_dir(source_dir, version="v1.2.4")

    current_user = User(id=7, external_auth_id="sub", username="alice", display_name="Alice")
    custom_skill = Skill(id=11, user_id=7, name="demo-skill", display_name="demo-skill", description="Old description", file_path="private/7/demo-skill")
    published_skill = Skill(id=12, user_id=None, owner_user_id=7, name="demo-skill", display_name="demo-skill", description="Published description", file_path="public/demo-skill")
    release = SkillRelease(
        id=31,
        skill_name="demo-skill",
        release_version="rel_notes",
        package_version="v1.2.4",
        description="Published description",
        release_notes="Fix prompt routing",
        status="published",
        artifact_path="public/demo-skill",
        publisher_user_id=7,
        source_skill_id=11,
        published_skill_id=12,
    )
    db = FakeDb()
    release_kwargs = {}

    async def get_user_skill_by_name(db_arg, *, user_id, name):
        return custom_skill

    async def list_public_skills_by_name(db_arg, *, name):
        return []

    async def create_skill(db_arg, **kwargs):
        return published_skill

    async def create_release(db_arg, **kwargs):
        release_kwargs.update(kwargs)
        return release

    async def get_skill_by_id(db_arg, skill_id):
        return published_skill

    monkeypatch.setattr(skills_router.SkillRepository, "get_user_skill_by_name", get_user_skill_by_name)
    monkeypatch.setattr(skills_router.SkillRepository, "list_public_skills_by_name", list_public_skills_by_name)
    monkeypatch.setattr(skills_router.SkillRepository, "create_skill", create_skill)
    monkeypatch.setattr(skills_router.SkillRepository, "get_skill_by_id", get_skill_by_id)
    monkeypatch.setattr(skills_router.SkillReleaseRepository, "create_release", create_release)
    monkeypatch.setattr(skills_router, "_resolve_skill_record_dir", lambda skill: source_dir)
    monkeypatch.setattr(skills_router, "_resolve_skill_dir", lambda raw_path: target_dir)

    async def run():
        return await skills_router.publish_skill(
            "demo-skill",
            request=skills_router.SkillPublishRequest(release_notes="  Fix prompt routing  "),
            current_user=current_user,
            db=db,
        )

    response = asyncio.run(run())

    assert release_kwargs["release_notes"] == "Fix prompt routing"
    assert response.release_notes == "Fix prompt routing"


def test_publish_blank_release_notes_are_stored_as_null(tmp_path, monkeypatch):
    source_dir = tmp_path / "source"
    target_dir = tmp_path / "public" / "demo-skill"
    _write_skill_dir(source_dir, version="v1.2.5")

    current_user = User(id=7, external_auth_id="sub", username="alice", display_name="Alice")
    custom_skill = Skill(id=11, user_id=7, name="demo-skill", display_name="demo-skill", description="Old description", file_path="private/7/demo-skill")
    published_skill = Skill(id=12, user_id=None, owner_user_id=7, name="demo-skill", display_name="demo-skill", description="Published description", file_path="public/demo-skill")
    release = SkillRelease(
        id=32,
        skill_name="demo-skill",
        release_version="rel_blank_notes",
        package_version="v1.2.5",
        description="Published description",
        release_notes=None,
        status="published",
        artifact_path="public/demo-skill",
        publisher_user_id=7,
        source_skill_id=11,
        published_skill_id=12,
    )
    db = FakeDb()
    release_kwargs = {}

    async def get_user_skill_by_name(db_arg, *, user_id, name):
        return custom_skill

    async def list_public_skills_by_name(db_arg, *, name):
        return []

    async def create_skill(db_arg, **kwargs):
        return published_skill

    async def create_release(db_arg, **kwargs):
        release_kwargs.update(kwargs)
        return release

    async def get_skill_by_id(db_arg, skill_id):
        return published_skill

    monkeypatch.setattr(skills_router.SkillRepository, "get_user_skill_by_name", get_user_skill_by_name)
    monkeypatch.setattr(skills_router.SkillRepository, "list_public_skills_by_name", list_public_skills_by_name)
    monkeypatch.setattr(skills_router.SkillRepository, "create_skill", create_skill)
    monkeypatch.setattr(skills_router.SkillRepository, "get_skill_by_id", get_skill_by_id)
    monkeypatch.setattr(skills_router.SkillReleaseRepository, "create_release", create_release)
    monkeypatch.setattr(skills_router, "_resolve_skill_record_dir", lambda skill: source_dir)
    monkeypatch.setattr(skills_router, "_resolve_skill_dir", lambda raw_path: target_dir)

    async def run():
        return await skills_router.publish_skill(
            "demo-skill",
            request=skills_router.SkillPublishRequest(release_notes="   "),
            current_user=current_user,
            db=db,
        )

    response = asyncio.run(run())

    assert release_kwargs["release_notes"] is None
    assert response.release_notes is None


def test_publish_unversioned_skill_returns_release_version_as_display_version(tmp_path, monkeypatch):
    source_dir = tmp_path / "source"
    target_dir = tmp_path / "public" / "demo-skill"
    _write_skill_dir(source_dir, version=None)

    current_user = User(id=7, external_auth_id="sub", username="alice", display_name="Alice")
    custom_skill = Skill(id=11, user_id=7, name="demo-skill", display_name="demo-skill", description="Old description", file_path="private/7/demo-skill")
    published_skill = Skill(id=12, user_id=None, owner_user_id=7, name="demo-skill", display_name="demo-skill", description="Published description", file_path="public/demo-skill")
    release = SkillRelease(
        id=33,
        skill_name="demo-skill",
        release_version="rel_unversioned",
        package_version=None,
        description="Published description",
        release_notes=None,
        status="published",
        artifact_path="public/demo-skill",
        publisher_user_id=7,
        source_skill_id=11,
        published_skill_id=12,
    )
    db = FakeDb()
    release_kwargs = {}

    async def get_user_skill_by_name(db_arg, *, user_id, name):
        return custom_skill

    async def list_public_skills_by_name(db_arg, *, name):
        return []

    async def create_skill(db_arg, **kwargs):
        return published_skill

    async def create_release(db_arg, **kwargs):
        release_kwargs.update(kwargs)
        return release

    async def get_skill_by_id(db_arg, skill_id):
        return published_skill

    monkeypatch.setattr(skills_router.SkillRepository, "get_user_skill_by_name", get_user_skill_by_name)
    monkeypatch.setattr(skills_router.SkillRepository, "list_public_skills_by_name", list_public_skills_by_name)
    monkeypatch.setattr(skills_router.SkillRepository, "create_skill", create_skill)
    monkeypatch.setattr(skills_router.SkillRepository, "get_skill_by_id", get_skill_by_id)
    monkeypatch.setattr(skills_router.SkillReleaseRepository, "create_release", create_release)
    monkeypatch.setattr(skills_router, "_resolve_skill_record_dir", lambda skill: source_dir)
    monkeypatch.setattr(skills_router, "_resolve_skill_dir", lambda raw_path: target_dir)

    async def run():
        return await skills_router.publish_skill("demo-skill", current_user=current_user, db=db)

    response = asyncio.run(run())

    assert release_kwargs["package_version"] is None
    assert response.package_version is None
    assert response.release_version == "rel_unversioned"
    assert response.version == "rel_unversioned"


def test_publish_custom_skill_missing_returns_404(monkeypatch):
    async def get_user_skill_by_name(db_arg, *, user_id, name):
        return None

    db = FakeDb()
    current_user = User(id=7, external_auth_id="sub", username="alice", display_name="Alice")
    monkeypatch.setattr(skills_router.SkillRepository, "get_user_skill_by_name", get_user_skill_by_name)

    async def run():
        with pytest.raises(HTTPException) as exc_info:
            await skills_router.publish_skill("missing-skill", current_user=current_user, db=db)
        return exc_info.value

    exc = asyncio.run(run())

    assert exc.status_code == 404
    assert db.rollbacks == 1


def test_publish_copy_failure_does_not_update_public_latest(tmp_path, monkeypatch, caplog):
    source_dir = tmp_path / "source"
    target_dir = tmp_path / "public" / "demo-skill"
    _write_skill_dir(source_dir, version="v2.0.0", description="New description")
    _write_skill_dir(target_dir, version="v1.0.0", description="Old public description")
    old_content = (target_dir / "SKILL.md").read_text(encoding="utf-8")

    db = FakeDb()
    current_user = User(id=7, external_auth_id="sub", username="alice", display_name="Alice")
    custom_skill = Skill(id=11, user_id=7, name="demo-skill", display_name="demo-skill", description="Old description", file_path="private/7/demo-skill")
    old_public_skill = Skill(id=10, user_id=None, owner_user_id=2, name="demo-skill", display_name="demo-skill", description="Old public", file_path="public/demo-skill")
    calls = {"soft_deleted": 0, "created": 0, "release": 0}

    async def get_user_skill_by_name(db_arg, *, user_id, name):
        return custom_skill

    async def list_public_skills_by_name(db_arg, *, name):
        return [old_public_skill]

    async def soft_delete_skill(db_arg, *, skill, commit=True):
        calls["soft_deleted"] += 1

    async def create_skill(db_arg, **kwargs):
        calls["created"] += 1
        raise AssertionError("copy failure should not create public latest")

    async def create_release(db_arg, **kwargs):
        calls["release"] += 1
        raise AssertionError("copy failure should not create release")

    def replace_skill_directory(source, target):
        raise OSError("copy failed")

    monkeypatch.setattr(skills_router.SkillRepository, "get_user_skill_by_name", get_user_skill_by_name)
    monkeypatch.setattr(skills_router.SkillRepository, "list_public_skills_by_name", list_public_skills_by_name)
    monkeypatch.setattr(skills_router.SkillRepository, "soft_delete_skill", soft_delete_skill)
    monkeypatch.setattr(skills_router.SkillRepository, "create_skill", create_skill)
    monkeypatch.setattr(skills_router.SkillReleaseRepository, "create_release", create_release)
    monkeypatch.setattr(skills_router, "_resolve_skill_record_dir", lambda skill: source_dir)
    monkeypatch.setattr(skills_router, "_resolve_skill_dir", lambda raw_path: target_dir)
    monkeypatch.setattr(skills_router, "_replace_skill_directory", replace_skill_directory)

    async def run():
        with pytest.raises(HTTPException) as exc_info:
            await skills_router.publish_skill("demo-skill", current_user=current_user, db=db)
        return exc_info.value

    with caplog.at_level("ERROR", logger="app.gateway.routers.skills"):
        exc = asyncio.run(run())

    assert exc.status_code == 500
    assert exc.detail == "Failed to publish skill"
    assert db.commits == 0
    assert db.rollbacks == 1
    assert calls == {"soft_deleted": 0, "created": 0, "release": 0}
    assert (target_dir / "SKILL.md").read_text(encoding="utf-8") == old_content
    assert "phase=copy_public_artifact" in caplog.text


def test_publish_release_failure_restores_previous_public_artifact_and_logs_phase(tmp_path, monkeypatch, caplog):
    source_dir = tmp_path / "source"
    target_dir = tmp_path / "public" / "demo-skill"
    _write_skill_dir(source_dir, version="v2.0.0", description="New description")
    _write_skill_dir(target_dir, version="v1.0.0", description="Old public description")
    old_content = (target_dir / "SKILL.md").read_text(encoding="utf-8")

    db = FakeDb()
    current_user = User(id=7, external_auth_id="sub", username="alice", display_name="Alice")
    custom_skill = Skill(id=11, user_id=7, name="demo-skill", display_name="demo-skill", description="Old description", file_path="private/7/demo-skill")
    old_public_skill = Skill(id=10, user_id=None, owner_user_id=2, name="demo-skill", display_name="demo-skill", description="Old public", file_path="public/demo-skill")
    published_skill = Skill(id=12, user_id=None, owner_user_id=7, name="demo-skill", display_name="demo-skill", description="New description", file_path="public/demo-skill")
    calls = {"soft_deleted": 0, "created": 0, "release": 0}

    async def get_user_skill_by_name(db_arg, *, user_id, name):
        return custom_skill

    async def list_public_skills_by_name(db_arg, *, name):
        return [old_public_skill]

    async def soft_delete_skill(db_arg, *, skill, commit=True):
        calls["soft_deleted"] += 1

    async def create_skill(db_arg, **kwargs):
        calls["created"] += 1
        return published_skill

    async def create_release(db_arg, **kwargs):
        calls["release"] += 1
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(skills_router.SkillRepository, "get_user_skill_by_name", get_user_skill_by_name)
    monkeypatch.setattr(skills_router.SkillRepository, "list_public_skills_by_name", list_public_skills_by_name)
    monkeypatch.setattr(skills_router.SkillRepository, "soft_delete_skill", soft_delete_skill)
    monkeypatch.setattr(skills_router.SkillRepository, "create_skill", create_skill)
    monkeypatch.setattr(skills_router.SkillReleaseRepository, "create_release", create_release)
    monkeypatch.setattr(skills_router, "_resolve_skill_record_dir", lambda skill: source_dir)
    monkeypatch.setattr(skills_router, "_resolve_skill_dir", lambda raw_path: target_dir)

    async def run():
        with pytest.raises(HTTPException) as exc_info:
            await skills_router.publish_skill("demo-skill", current_user=current_user, db=db)
        return exc_info.value

    with caplog.at_level("ERROR", logger="app.gateway.routers.skills"):
        exc = asyncio.run(run())

    assert exc.status_code == 500
    assert exc.detail == "Failed to publish skill"
    assert db.commits == 0
    assert db.rollbacks == 1
    assert calls == {"soft_deleted": 1, "created": 1, "release": 1}
    assert (target_dir / "SKILL.md").read_text(encoding="utf-8") == old_content
    assert "phase=create_release_record" in caplog.text
    assert "skill_name=demo-skill" in caplog.text
    assert "publisher_user_id=7" in caplog.text


def test_publish_commit_failure_restores_previous_public_artifact_and_logs_phase(tmp_path, monkeypatch, caplog):
    source_dir = tmp_path / "source"
    target_dir = tmp_path / "public" / "demo-skill"
    _write_skill_dir(source_dir, version="v2.0.0", description="New description")
    _write_skill_dir(target_dir, version="v1.0.0", description="Old public description")
    old_content = (target_dir / "SKILL.md").read_text(encoding="utf-8")

    class CommitFailingDb(FakeDb):
        async def commit(self):
            raise RuntimeError("commit failed")

    db = CommitFailingDb()
    current_user = User(id=7, external_auth_id="sub", username="alice", display_name="Alice")
    custom_skill = Skill(id=11, user_id=7, name="demo-skill", display_name="demo-skill", description="Old description", file_path="private/7/demo-skill")
    old_public_skill = Skill(id=10, user_id=None, owner_user_id=2, name="demo-skill", display_name="demo-skill", description="Old public", file_path="public/demo-skill")
    published_skill = Skill(id=12, user_id=None, owner_user_id=7, name="demo-skill", display_name="demo-skill", description="New description", file_path="public/demo-skill")
    release = SkillRelease(
        id=34,
        skill_name="demo-skill",
        release_version="rel_commit_failure",
        package_version="v2.0.0",
        description="New description",
        release_notes=None,
        status="published",
        artifact_path="public/demo-skill",
        publisher_user_id=7,
        source_skill_id=11,
        published_skill_id=12,
    )

    async def get_user_skill_by_name(db_arg, *, user_id, name):
        return custom_skill

    async def list_public_skills_by_name(db_arg, *, name):
        return [old_public_skill]

    async def soft_delete_skill(db_arg, *, skill, commit=True):
        return None

    async def create_skill(db_arg, **kwargs):
        return published_skill

    async def create_release(db_arg, **kwargs):
        return release

    monkeypatch.setattr(skills_router.SkillRepository, "get_user_skill_by_name", get_user_skill_by_name)
    monkeypatch.setattr(skills_router.SkillRepository, "list_public_skills_by_name", list_public_skills_by_name)
    monkeypatch.setattr(skills_router.SkillRepository, "soft_delete_skill", soft_delete_skill)
    monkeypatch.setattr(skills_router.SkillRepository, "create_skill", create_skill)
    monkeypatch.setattr(skills_router.SkillReleaseRepository, "create_release", create_release)
    monkeypatch.setattr(skills_router, "_resolve_skill_record_dir", lambda skill: source_dir)
    monkeypatch.setattr(skills_router, "_resolve_skill_dir", lambda raw_path: target_dir)

    async def run():
        with pytest.raises(HTTPException) as exc_info:
            await skills_router.publish_skill("demo-skill", current_user=current_user, db=db)
        return exc_info.value

    with caplog.at_level("ERROR", logger="app.gateway.routers.skills"):
        exc = asyncio.run(run())

    assert exc.status_code == 500
    assert exc.detail == "Failed to publish skill"
    assert db.rollbacks == 1
    assert (target_dir / "SKILL.md").read_text(encoding="utf-8") == old_content
    assert "phase=commit_publish" in caplog.text
    assert "release_version=rel_commit_failure" in caplog.text


def test_publish_uses_current_user_scope_when_loading_custom_skill(monkeypatch):
    db = FakeDb()
    bob = User(id=8, external_auth_id="bob-sub", username="bob", display_name="Bob")
    calls = []

    async def get_user_skill_by_name(db_arg, *, user_id, name):
        calls.append((user_id, name))
        return None

    monkeypatch.setattr(skills_router.SkillRepository, "get_user_skill_by_name", get_user_skill_by_name)

    async def run():
        with pytest.raises(HTTPException) as exc_info:
            await skills_router.publish_skill("demo-skill", current_user=bob, db=db)
        return exc_info.value

    exc = asyncio.run(run())

    assert calls == [(8, "demo-skill")]
    assert exc.status_code == 404
    assert db.rollbacks == 1


def test_publish_invalid_metadata_returns_400_before_copying(tmp_path, monkeypatch):
    source_dir = tmp_path / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / "SKILL.md").write_text(
        "---\nname: demo-skill\ndescription: Published description\nversion: 1.2\n---\n\n# Demo Skill\n",
        encoding="utf-8",
    )

    db = FakeDb()
    current_user = User(id=7, external_auth_id="sub", username="alice", display_name="Alice")
    custom_skill = Skill(id=11, user_id=7, name="demo-skill", display_name="demo-skill", description="Old description", file_path="private/7/demo-skill")
    calls = {"copied": 0, "created": 0, "release": 0}

    async def get_user_skill_by_name(db_arg, *, user_id, name):
        return custom_skill

    async def list_public_skills_by_name(db_arg, *, name):
        return []

    async def create_skill(db_arg, **kwargs):
        calls["created"] += 1
        raise AssertionError("invalid metadata should not create public latest")

    async def create_release(db_arg, **kwargs):
        calls["release"] += 1
        raise AssertionError("invalid metadata should not create release")

    def replace_skill_directory(source, target):
        calls["copied"] += 1
        raise AssertionError("invalid metadata should not copy artifact")

    monkeypatch.setattr(skills_router.SkillRepository, "get_user_skill_by_name", get_user_skill_by_name)
    monkeypatch.setattr(skills_router.SkillRepository, "list_public_skills_by_name", list_public_skills_by_name)
    monkeypatch.setattr(skills_router.SkillRepository, "create_skill", create_skill)
    monkeypatch.setattr(skills_router.SkillReleaseRepository, "create_release", create_release)
    monkeypatch.setattr(skills_router, "_resolve_skill_record_dir", lambda skill: source_dir)
    monkeypatch.setattr(skills_router, "_replace_skill_directory", replace_skill_directory)

    async def run():
        with pytest.raises(HTTPException) as exc_info:
            await skills_router.publish_skill("demo-skill", current_user=current_user, db=db)
        return exc_info.value

    exc = asyncio.run(run())

    assert exc.status_code == 400
    assert "Version must be a string" in exc.detail
    assert calls == {"copied": 0, "created": 0, "release": 0}
    assert db.rollbacks == 1
