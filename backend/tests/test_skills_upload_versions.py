from __future__ import annotations

import asyncio
import io
import tempfile
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.gateway.db.models import Skill, User
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


def _user() -> User:
    return User(id=7, external_auth_id="sub", username="alice", display_name="Alice")


def _write_skill_dir(skill_dir: Path, *, version: str | None, description: str = "Demo skill") -> None:
    skill_dir.mkdir(parents=True, exist_ok=True)
    version_line = f"version: {version}\n" if version is not None else ""
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: demo-skill\ndescription: {description}\n{version_line}---\n\n# Demo Skill\n",
        encoding="utf-8",
    )


def _zip_skill_archive(skill_md: str) -> bytes:
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as zip_ref:
        zip_ref.writestr("demo-skill/SKILL.md", skill_md)
    return archive.getvalue()


class FakeUploadFile:
    def __init__(self, filename: str, content: bytes):
        self.filename = filename
        self._content = content

    async def read(self) -> bytes:
        return self._content


def test_check_upload_treats_same_name_new_version_as_update(tmp_path, monkeypatch):
    db = FakeDb()
    existing_skill = Skill(id=21, user_id=7, name="demo-skill", display_name="demo-skill", description="Old", file_path="private/7/demo-skill")
    existing_dir = tmp_path / "existing"
    upload_dir = tmp_path / "upload"
    target_dir = tmp_path / "target"
    _write_skill_dir(existing_dir, version="v1")
    _write_skill_dir(upload_dir, version="v2")
    temp_dir = tempfile.TemporaryDirectory(prefix="skill-upload-test-")

    async def parse_uploaded_skill_archive(upload_file):
        return "demo.zip", "demo-skill", "v2", upload_dir, temp_dir

    async def get_user_skill_by_name(db_arg, *, user_id, name):
        return existing_skill

    monkeypatch.setattr(skills_router, "_parse_uploaded_skill_archive", parse_uploaded_skill_archive)
    monkeypatch.setattr(skills_router.SkillRepository, "get_user_skill_by_name", get_user_skill_by_name)
    monkeypatch.setattr(skills_router, "_resolve_skill_record_dir", lambda skill: existing_dir)
    monkeypatch.setattr(skills_router, "_resolve_skill_dir", lambda raw_path: target_dir)

    async def run():
        return await skills_router.check_skill_upload(
            file=SimpleNamespace(filename="demo.zip"),
            current_user=_user(),
            db=db,
        )

    response = asyncio.run(run())

    assert response.exists is False
    assert response.same_version is False
    assert response.package_version == "v2"
    assert response.existing_package_version == "v1"
    assert "will be updated" in response.message


def test_check_upload_treats_same_name_same_version_as_duplicate(tmp_path, monkeypatch):
    db = FakeDb()
    existing_skill = Skill(id=21, user_id=7, name="demo-skill", display_name="demo-skill", description="Old", file_path="private/7/demo-skill")
    existing_dir = tmp_path / "existing"
    upload_dir = tmp_path / "upload"
    target_dir = tmp_path / "target"
    _write_skill_dir(existing_dir, version="v1")
    _write_skill_dir(upload_dir, version="v1")
    temp_dir = tempfile.TemporaryDirectory(prefix="skill-upload-test-")

    async def parse_uploaded_skill_archive(upload_file):
        return "demo.zip", "demo-skill", "v1", upload_dir, temp_dir

    async def get_user_skill_by_name(db_arg, *, user_id, name):
        return existing_skill

    monkeypatch.setattr(skills_router, "_parse_uploaded_skill_archive", parse_uploaded_skill_archive)
    monkeypatch.setattr(skills_router.SkillRepository, "get_user_skill_by_name", get_user_skill_by_name)
    monkeypatch.setattr(skills_router, "_resolve_skill_record_dir", lambda skill: existing_dir)
    monkeypatch.setattr(skills_router, "_resolve_skill_dir", lambda raw_path: target_dir)

    async def run():
        return await skills_router.check_skill_upload(
            file=SimpleNamespace(filename="demo.zip"),
            current_user=_user(),
            db=db,
        )

    response = asyncio.run(run())

    assert response.exists is True
    assert response.same_version is True
    assert response.package_version == "v1"
    assert response.existing_package_version == "v1"
    assert "already exists" in response.message


def test_upload_same_name_new_version_updates_existing_skill_without_new_row(tmp_path, monkeypatch):
    db = FakeDb()
    existing_skill = Skill(id=21, user_id=7, name="demo-skill", display_name="demo-skill", description="Old", file_path="private/7/demo-skill")
    existing_dir = tmp_path / "existing"
    upload_dir = tmp_path / "upload"
    target_dir = tmp_path / "target"
    _write_skill_dir(existing_dir, version="v1")
    _write_skill_dir(upload_dir, version="v2", description="New description")
    temp_dir = tempfile.TemporaryDirectory(prefix="skill-upload-test-")
    calls = {"created": 0, "soft_deleted": 0, "rebound": 0}

    async def parse_uploaded_skill_archive(upload_file):
        return "demo.zip", "demo-skill", "v2", upload_dir, temp_dir

    async def get_user_skill_by_name(db_arg, *, user_id, name):
        return existing_skill

    async def create_skill(db_arg, **kwargs):
        calls["created"] += 1
        raise AssertionError("new package version should update the current skill row")

    async def soft_delete_skill(db_arg, **kwargs):
        calls["soft_deleted"] += 1

    async def rebind_agent_skills(db_arg, **kwargs):
        calls["rebound"] += 1

    monkeypatch.setattr(skills_router, "_parse_uploaded_skill_archive", parse_uploaded_skill_archive)
    monkeypatch.setattr(skills_router.SkillRepository, "get_user_skill_by_name", get_user_skill_by_name)
    monkeypatch.setattr(skills_router.SkillRepository, "create_skill", create_skill)
    monkeypatch.setattr(skills_router.SkillRepository, "soft_delete_skill", soft_delete_skill)
    monkeypatch.setattr(skills_router.SkillRepository, "rebind_agent_skills", rebind_agent_skills)
    monkeypatch.setattr(skills_router, "_resolve_skill_record_dir", lambda skill: existing_dir)
    monkeypatch.setattr(skills_router, "_resolve_skill_dir", lambda raw_path: target_dir)

    async def run():
        return await skills_router.upload_skills(
            files=[SimpleNamespace(filename="demo.zip")],
            overwrite_names=None,
            current_user=_user(),
            db=db,
        )

    response = asyncio.run(run())

    assert db.commits == 1
    assert db.flushed == 1
    assert calls == {"created": 0, "soft_deleted": 0, "rebound": 0}
    assert existing_skill.description == "New description"
    assert existing_skill.file_path == "7/demo-skill"
    assert (target_dir / "SKILL.md").exists()
    assert response.results[0].success is True
    assert response.results[0].action == "updated"
    assert response.results[0].package_version == "v2"


def test_upload_same_name_same_version_requires_overwrite(tmp_path, monkeypatch):
    db = FakeDb()
    existing_skill = Skill(id=21, user_id=7, name="demo-skill", display_name="demo-skill", description="Old", file_path="private/7/demo-skill")
    existing_dir = tmp_path / "existing"
    upload_dir = tmp_path / "upload"
    target_dir = tmp_path / "target"
    _write_skill_dir(existing_dir, version="v1")
    _write_skill_dir(upload_dir, version="v1")
    temp_dir = tempfile.TemporaryDirectory(prefix="skill-upload-test-")

    async def parse_uploaded_skill_archive(upload_file):
        return "demo.zip", "demo-skill", "v1", upload_dir, temp_dir

    async def get_user_skill_by_name(db_arg, *, user_id, name):
        return existing_skill

    monkeypatch.setattr(skills_router, "_parse_uploaded_skill_archive", parse_uploaded_skill_archive)
    monkeypatch.setattr(skills_router.SkillRepository, "get_user_skill_by_name", get_user_skill_by_name)
    monkeypatch.setattr(skills_router, "_resolve_skill_record_dir", lambda skill: existing_dir)
    monkeypatch.setattr(skills_router, "_resolve_skill_dir", lambda raw_path: target_dir)

    async def run():
        return await skills_router.upload_skills(
            files=[SimpleNamespace(filename="demo.zip")],
            overwrite_names=None,
            current_user=_user(),
            db=db,
        )

    response = asyncio.run(run())

    assert db.commits == 0
    assert response.results[0].success is False
    assert response.results[0].action == "skipped"
    assert "already exists" in response.results[0].message


def test_check_upload_rejects_non_string_package_version():
    archive = _zip_skill_archive(
        "---\nname: demo-skill\ndescription: Demo skill\nversion: 1.2\n---\n\n# Demo Skill\n"
    )

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
    archive = _zip_skill_archive(
        "---\nname: demo-skill\ndescription: Demo skill\nversion: 1.2\n---\n\n# Demo Skill\n"
    )
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
