from __future__ import annotations

import asyncio
import zipfile
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.gateway.db.models import Agent, AgentSkill, RuntimeManifest, SkillDefinition, SkillInstall, SkillRelease, SkillVersion, User
from app.gateway.db.models import LegacySkill as Skill
from app.gateway.db.models import Skill as TerminalSkill
from app.gateway.db.repository import AgentRepository, MemoryRepository, RuntimeManifestResolutionError, build_runtime_manifest_hash
from app.gateway.routers import agents as agents_router
from app.gateway.routers import skills as skills_router
from deerflow.sandbox.tools import skill_load_tool
from deerflow.skills.hashing import hash_skill_file_manifest


def _write_artifact(skills_root: Path, artifact_uri: str, marker: str) -> str:
    artifact_dir = skills_root / artifact_uri
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "SKILL.md").write_text(marker, encoding="utf-8")
    return hash_skill_file_manifest(artifact_dir)


def _terminal_skill_id(definition_id: int) -> UUID:
    return UUID(int=definition_id)


def _terminal_skill(skill_id: UUID, *, name: str = "probe-skill", owner_user_id: int = 22) -> TerminalSkill:
    return TerminalSkill(id=skill_id, owner_user_id=owner_user_id, name=name, display_name=name)


def _write_terminal_artifact(skills_root: Path, skill_id: UUID, version_number: int, marker: str) -> str:
    return _write_artifact(skills_root, f"{skill_id}/{version_number}", marker)


def _runtime_config(skills_root: Path):
    return SimpleNamespace(
        skills=SimpleNamespace(
            container_path="/mnt/skills",
            get_skills_path=lambda: skills_root,
        )
    )


class _FakeManifestSession:
    def __init__(self) -> None:
        self.added = []

    def add(self, value) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        for value in self.added:
            if getattr(value, "id", None) is None:
                value.id = uuid4()

    async def refresh(self, value) -> None:
        return None


class _ApiFlowDb(_FakeManifestSession):
    def __init__(self) -> None:
        super().__init__()
        self.commits = 0
        self.rollbacks = 0

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


class _ApiFlowStore:
    def __init__(self) -> None:
        self.next_definition_id = 1
        self.next_version_id = 101
        self.next_install_id = 201
        self.next_skill_id = 301
        self.next_release_id = 401
        self.next_agent_id = 501
        self.next_agent_skill_id = 601
        self.definitions: list[SkillDefinition] = []
        self.versions: list[SkillVersion] = []
        self.installs: list[SkillInstall] = []
        self.skills: list[Skill] = []
        self.releases: list[SkillRelease] = []
        self.agents: list[Agent] = []

    def definition_by_id(self, definition_id: int) -> SkillDefinition:
        return next(definition for definition in self.definitions if definition.id == definition_id)

    def version_by_id(self, version_id: int) -> SkillVersion:
        return next(version for version in self.versions if version.id == version_id)

    def install_by_id(self, install_id: int) -> SkillInstall:
        return next(install for install in self.installs if install.id == install_id)

    def active_skill_by_id(self, skill_id: int) -> Skill | None:
        return next((skill for skill in self.skills if skill.id == skill_id and skill.deleted_at is None), None)

    def latest_release_for_definition(self, definition_id: int) -> SkillRelease | None:
        releases = [release for release in self.releases if release.status == "published" and release.skill_version is not None and release.skill_version.skill_definition_id == definition_id]
        return max(releases, key=lambda release: release.skill_version.version_number, default=None)

    async def get_or_create_definition(self, db, *, name, display_name, description, owner_user_id, source_type=None, source_identifier=None):
        source_type = source_type or ("user" if owner_user_id is not None else "legacy")
        source_identifier = source_identifier or (str(owner_user_id) if owner_user_id is not None else "legacy")
        definition = next(
            (item for item in self.definitions if item.name == name and item.source_type == source_type and item.source_identifier == source_identifier and item.deleted_at is None),
            None,
        )
        if definition is not None:
            definition.display_name = display_name or definition.display_name
            definition.description = description or definition.description
            return definition
        definition = SkillDefinition(
            id=self.next_definition_id,
            name=name,
            display_name=display_name,
            description=description,
            source_type=source_type,
            source_identifier=source_identifier,
            owner_user_id=owner_user_id,
        )
        self.next_definition_id += 1
        self.definitions.append(definition)
        return definition

    async def get_definition_by_name(self, db, *, name):
        return next((item for item in self.definitions if item.name == name and item.deleted_at is None), None)

    async def get_definition_by_name_and_owner(self, db, *, name, owner_user_id):
        source_type = "user" if owner_user_id is not None else "legacy"
        source_identifier = str(owner_user_id) if owner_user_id is not None else "legacy"
        return next(
            (item for item in self.definitions if item.name == name and item.source_type == source_type and item.source_identifier == source_identifier and item.deleted_at is None),
            None,
        )

    async def get_version_by_hash(self, db, *, skill_definition_id, content_hash):
        return next(
            (version for version in self.versions if version.skill_definition_id == skill_definition_id and version.content_hash == content_hash),
            None,
        )

    async def get_latest_version(self, db, *, skill_definition_id):
        versions = [version for version in self.versions if version.skill_definition_id == skill_definition_id]
        return max(versions, key=lambda version: version.version_number, default=None)

    async def get_version_by_id(self, db, *, skill_version_id):
        return next((version for version in self.versions if version.id == skill_version_id), None)

    async def get_version_by_skill_version(self, db, *, skill_id, version_number):
        return next((version for version in self.versions if version.skill_id == skill_id and version.version_number == version_number), None)

    async def create_version(
        self,
        db,
        *,
        definition,
        source_package_version,
        description,
        content_hash,
        file_manifest_hash,
        artifact_uri,
        created_by_user_id,
    ):
        latest = await self.get_latest_version(db, skill_definition_id=definition.id)
        version_number = 1 if latest is None else latest.version_number + 1
        terminal_artifact_uri = f"{_terminal_skill_id(definition.id)}/{version_number}"
        assert artifact_uri == terminal_artifact_uri
        version = SkillVersion(
            id=self.next_version_id,
            skill_id=_terminal_skill_id(definition.id),
            skill_definition_id=definition.id,
            version_number=version_number,
            source_package_version=source_package_version,
            description=description,
            content_hash=content_hash,
            file_manifest_hash=file_manifest_hash,
            artifact_uri=terminal_artifact_uri,
            created_by_user_id=created_by_user_id,
            definition=definition,
        )
        self.next_version_id += 1
        self.versions.append(version)
        return version

    async def get_install_by_user_and_definition(self, db, *, user_id, skill_definition_id):
        return next(
            (install for install in self.installs if install.user_id == user_id and install.skill_definition_id == skill_definition_id and install.deleted_at is None),
            None,
        )

    async def get_install_by_user_and_name(self, db, *, user_id, name):
        installs = await self.list_install_by_user_and_name(db, user_id=user_id, name=name)
        return installs[0] if installs else None

    async def list_install_by_user_and_name(self, db, *, user_id, name):
        definition_ids = [definition.id for definition in self.definitions if definition.name == name and definition.deleted_at is None]
        return [install for install in self.installs if install.user_id == user_id and install.skill_definition_id in definition_ids and install.deleted_at is None]

    async def get_install_by_id_for_user(self, db, *, user_id, skill_install_id):
        return next((install for install in self.installs if install.id == skill_install_id and install.user_id == user_id and install.deleted_at is None), None)

    async def get_install_by_user_and_skill_id(self, db, *, user_id, skill_id):
        return next((install for install in self.installs if install.user_id == user_id and install.skill_id == skill_id and install.deleted_at is None), None)

    async def upsert_install(self, db, *, user_id, definition, version):
        install = await self.get_install_by_user_and_skill_id(db, user_id=user_id, skill_id=version.skill_id)
        if install is None:
            install = SkillInstall(
                id=self.next_install_id,
                user_id=user_id,
                skill_id=version.skill_id,
                version_number=version.version_number,
                status="active",
                skill_definition_id=definition.id,
                installed_version_id=version.id,
                current_version_id=version.id,
                definition=definition,
                installed_version=version,
                current_version=version,
            )
            self.next_install_id += 1
            self.installs.append(install)
        else:
            install.skill_id = version.skill_id
            install.version_number = version.version_number
            install.status = "active"
            install.current_version_id = version.id
            install.current_version = version
        return install

    async def update_current_version(self, db, *, install, version):
        assert install.skill_id == version.skill_id
        install.version_number = version.version_number
        install.status = "active"
        install.current_version_id = version.id
        install.current_version = version
        return install

    async def get_user_skill_by_name(self, db, *, user_id, name):
        return next((skill for skill in self.skills if skill.user_id == user_id and skill.name == name and skill.deleted_at is None), None)

    async def list_user_skills_by_name(self, db, *, user_id, name):
        return [skill for skill in self.skills if skill.user_id == user_id and skill.name == name and skill.deleted_at is None]

    async def get_user_skill_by_definition(self, db, *, user_id, skill_definition_id):
        return next((skill for skill in self.skills if skill.user_id == user_id and skill.skill_definition_id == skill_definition_id and skill.deleted_at is None), None)

    async def get_public_skill_by_name(self, db, *, name):
        public_skills = [skill for skill in self.skills if skill.user_id is None and skill.name == name and skill.deleted_at is None]
        return max(public_skills, key=lambda skill: skill.id, default=None)

    async def get_public_skill_by_name_and_owner(self, db, *, name, owner_user_id):
        public_skills = [skill for skill in self.skills if skill.user_id is None and skill.name == name and (owner_user_id is None or skill.owner_user_id == owner_user_id) and skill.deleted_at is None]
        return max(public_skills, key=lambda skill: skill.id, default=None)

    async def get_public_skill_by_definition(self, db, *, skill_definition_id):
        public_skills = [skill for skill in self.skills if skill.user_id is None and skill.skill_definition_id == skill_definition_id and skill.deleted_at is None]
        return max(public_skills, key=lambda skill: skill.id, default=None)

    async def list_public_skills_by_name(self, db, *, name):
        return [skill for skill in self.skills if skill.user_id is None and skill.name == name and skill.deleted_at is None]

    async def list_public_skills_by_name_and_owner(self, db, *, name, owner_user_id):
        return [skill for skill in self.skills if skill.user_id is None and skill.name == name and skill.owner_user_id == owner_user_id and skill.deleted_at is None]

    async def create_skill(self, db, *, user_id, owner_user_id, name, display_name, description, file_path, skill_definition_id=None, commit=True):
        skill = Skill(
            id=self.next_skill_id,
            user_id=user_id,
            owner_user_id=owner_user_id,
            name=name,
            display_name=display_name,
            description=description,
            file_path=file_path,
            skill_definition_id=skill_definition_id,
        )
        self.next_skill_id += 1
        self.skills.append(skill)
        if commit:
            await db.commit()
        return skill

    async def get_skill_by_id(self, db, skill_id):
        return self.active_skill_by_id(skill_id)

    async def soft_delete_skill(self, db, *, skill, commit=True):
        from datetime import UTC, datetime

        skill.deleted_at = datetime.now(UTC)
        if commit:
            await db.commit()

    async def create_release(
        self,
        db,
        *,
        skill_name,
        package_version,
        description,
        release_notes=None,
        artifact_path,
        publisher_user_id,
        source_skill_id,
        published_skill_id,
        skill_version_id=None,
        skill_id=None,
        version_number=None,
        status="published",
        release_version=None,
        commit=True,
    ):
        version = self.version_by_id(skill_version_id)
        skill_id = skill_id or version.skill_id
        version_number = version_number or version.version_number
        existing = next((release for release in self.releases if release.skill_id == skill_id and release.version_number == version_number), None)
        if existing is not None:
            existing.skill_name = skill_name
            existing.package_version = package_version
            existing.description = description
            existing.release_notes = release_notes
            existing.status = status
            existing.artifact_path = artifact_path
            existing.publisher_user_id = publisher_user_id
            existing.source_skill_id = source_skill_id
            existing.published_skill_id = published_skill_id
            existing.skill_version_id = skill_version_id
            existing.skill_version = version
            if commit:
                await db.commit()
            return existing
        release = SkillRelease(
            id=self.next_release_id,
            skill_id=skill_id,
            version_number=version_number,
            skill_name=skill_name,
            release_version=release_version or f"rel-{self.next_release_id}",
            package_version=package_version,
            description=description,
            release_notes=release_notes,
            status=status,
            artifact_path=artifact_path,
            publisher_user_id=publisher_user_id,
            source_skill_id=source_skill_id,
            published_skill_id=published_skill_id,
            skill_version_id=skill_version_id,
            skill_version=version,
        )
        self.next_release_id += 1
        self.releases.append(release)
        if commit:
            await db.commit()
        return release

    async def get_latest_published_version_by_name(self, db, *, skill_name):
        release = await self.get_latest_published_release_by_name(db, skill_name=skill_name)
        return release.skill_version if release is not None else None

    async def get_latest_published_release_by_name(self, db, *, skill_name):
        releases = [release for release in self.releases if release.skill_name == skill_name and release.status == "published"]
        return max(releases, key=lambda release: release.skill_version.version_number, default=None)

    async def get_latest_release_for_public_skill(self, db, *, published_skill_id):
        releases = [release for release in self.releases if release.published_skill_id == published_skill_id and release.status == "published"]
        return max(releases, key=lambda release: release.skill_version.version_number, default=None)

    async def get_latest_published_release_for_definition(self, db, *, skill_definition_id):
        return self.latest_release_for_definition(skill_definition_id)

    async def get_published_release_by_version_id(self, db, *, skill_version_id):
        return next((release for release in self.releases if release.skill_version_id == skill_version_id and release.status == "published"), None)

    async def get_published_release_by_skill_version(self, db, *, skill_id, version_number):
        return next((release for release in self.releases if release.skill_id == skill_id and release.version_number == version_number and release.status == "published"), None)

    async def list_published_releases(self, db):
        return [release for release in self.releases if release.status == "published"]

    async def create_agent(self, db, *, user_id, name, description=None, soul=None, mcp_config=None, commit=True):
        agent = Agent(
            id=self.next_agent_id,
            user_id=user_id,
            name=name,
            description=description,
            soul=soul,
            mcp_config=mcp_config,
        )
        agent.agent_skills = []
        self.next_agent_id += 1
        self.agents.append(agent)
        if commit:
            await db.commit()
        return agent

    async def get_agent_by_name(self, db, *, user_id, name):
        return next((agent for agent in self.agents if agent.user_id == user_id and agent.name == name and agent.deleted_at is None), None)

    async def get_agent_by_id(self, db, agent_id):
        return next((agent for agent in self.agents if agent.id == agent_id and agent.deleted_at is None), None)

    async def replace_agent_skills(self, db, *, agent, skill_ids, skill_install_ids, system_skill_version_ids=None, commit=True):
        del skill_ids
        del system_skill_version_ids
        agent.agent_skills = [
            AgentSkill(
                id=self.next_agent_skill_id + display_order,
                agent_id=agent.id,
                skill_id=None,
                skill_install_id=install_id,
                display_order=display_order,
                enabled=True,
                skill_install=self.install_by_id(install_id),
            )
            for display_order, install_id in enumerate(skill_install_ids)
        ]
        self.next_agent_skill_id += len(agent.agent_skills)
        if commit:
            await db.commit()
        return agent

    async def list_bound_agents_for_install(self, db, *, user_id, skill_install_id):
        return [agent for agent in self.agents if agent.user_id == user_id and any(association.skill_install_id == skill_install_id and association.enabled and association.deleted_at is None for association in agent.agent_skills)]

    async def ensure_terminal_skill_for_legacy_definition(self, db, *, definition):
        return SimpleNamespace(id=_terminal_skill_id(definition.id))


def _skill_zip_bytes(
    *,
    name: str = "probe-skill",
    description: str,
    package_version: str,
    marker: str,
) -> bytes:
    content = f"---\nname: {name}\ndescription: {description}\nversion: {package_version}\n---\n\n# {name}\n\n{marker}\n"
    archive = BytesIO()
    with zipfile.ZipFile(archive, "w") as zip_file:
        zip_file.writestr(f"{name}/SKILL.md", content)
    archive.seek(0)
    return archive.getvalue()


def _install_api_flow_repositories(monkeypatch, store: _ApiFlowStore) -> None:
    async def no_memory(db, user_id):
        return None

    monkeypatch.setattr(skills_router.SkillDefinitionRepository, "get_or_create", store.get_or_create_definition)
    monkeypatch.setattr(skills_router.SkillDefinitionRepository, "get_by_name", store.get_definition_by_name)
    monkeypatch.setattr(skills_router.SkillDefinitionRepository, "get_by_name_and_owner", store.get_definition_by_name_and_owner)
    monkeypatch.setattr(skills_router.SkillVersionRepository, "get_by_definition_and_hash", store.get_version_by_hash)
    monkeypatch.setattr(skills_router.SkillVersionRepository, "get_latest_for_definition", store.get_latest_version)
    monkeypatch.setattr(skills_router.SkillVersionRepository, "create_version", store.create_version)
    monkeypatch.setattr(skills_router.SkillVersionRepository, "get_by_id", store.get_version_by_id)
    monkeypatch.setattr(skills_router.SkillVersionRepository, "get_by_skill_version", store.get_version_by_skill_version)
    monkeypatch.setattr(skills_router.TerminalSkillRepository, "ensure_for_legacy_definition", store.ensure_terminal_skill_for_legacy_definition)
    monkeypatch.setattr(skills_router.SkillInstallRepository, "get_by_user_and_definition", store.get_install_by_user_and_definition)
    monkeypatch.setattr(skills_router.SkillInstallRepository, "get_by_user_and_skill_id", store.get_install_by_user_and_skill_id)
    monkeypatch.setattr(skills_router.SkillInstallRepository, "get_by_user_and_name", store.get_install_by_user_and_name)
    monkeypatch.setattr(skills_router.SkillInstallRepository, "list_by_user_and_name", store.list_install_by_user_and_name)
    monkeypatch.setattr(agents_router.SkillInstallRepository, "list_by_user_and_name", store.list_install_by_user_and_name)
    monkeypatch.setattr(agents_router.SkillInstallRepository, "get_by_id_for_user", store.get_install_by_id_for_user)
    monkeypatch.setattr(skills_router.SkillInstallRepository, "upsert_install", store.upsert_install)
    monkeypatch.setattr(skills_router.SkillInstallRepository, "update_current_version", store.update_current_version)
    monkeypatch.setattr(skills_router.SkillRepository, "get_user_skill_by_name", store.get_user_skill_by_name)
    monkeypatch.setattr(skills_router.SkillRepository, "list_user_skills_by_name", store.list_user_skills_by_name)
    monkeypatch.setattr(skills_router.SkillRepository, "get_user_skill_by_definition", store.get_user_skill_by_definition)
    monkeypatch.setattr(skills_router.SkillRepository, "get_public_skill_by_name", store.get_public_skill_by_name)
    monkeypatch.setattr(skills_router.SkillRepository, "get_public_skill_by_name_and_owner", store.get_public_skill_by_name_and_owner)
    monkeypatch.setattr(skills_router.SkillRepository, "get_public_skill_by_definition", store.get_public_skill_by_definition)
    monkeypatch.setattr(skills_router.SkillRepository, "list_public_skills_by_name", store.list_public_skills_by_name)
    monkeypatch.setattr(skills_router.SkillRepository, "list_public_skills_by_name_and_owner", store.list_public_skills_by_name_and_owner)
    monkeypatch.setattr(skills_router.SkillRepository, "create_skill", store.create_skill)
    monkeypatch.setattr(skills_router.SkillRepository, "get_skill_by_id", store.get_skill_by_id)
    monkeypatch.setattr(skills_router.SkillRepository, "soft_delete_skill", store.soft_delete_skill)
    monkeypatch.setattr(skills_router.SkillRepository, "list_bound_agents_for_install", store.list_bound_agents_for_install)
    monkeypatch.setattr(skills_router.SkillReleaseRepository, "create_release", store.create_release)
    monkeypatch.setattr(skills_router.SkillReleaseRepository, "get_latest_published_version_by_name", store.get_latest_published_version_by_name)
    monkeypatch.setattr(skills_router.SkillReleaseRepository, "get_latest_release_for_public_skill", store.get_latest_release_for_public_skill)
    monkeypatch.setattr(skills_router.SkillReleaseRepository, "get_latest_published_release_for_definition", store.get_latest_published_release_for_definition)
    monkeypatch.setattr(skills_router.SkillReleaseRepository, "get_published_release_by_version_id", store.get_published_release_by_version_id)
    monkeypatch.setattr(skills_router.SkillReleaseRepository, "get_published_release_by_skill_version", store.get_published_release_by_skill_version)
    monkeypatch.setattr(skills_router.SkillReleaseRepository, "list_published_releases", store.list_published_releases)
    monkeypatch.setattr(agents_router.AgentRepository, "create_agent", store.create_agent)
    monkeypatch.setattr(agents_router.AgentRepository, "get_agent_by_name", store.get_agent_by_name)
    monkeypatch.setattr(agents_router.AgentRepository, "get_agent_by_id", store.get_agent_by_id)
    monkeypatch.setattr(agents_router.AgentRepository, "replace_agent_skills", store.replace_agent_skills)
    monkeypatch.setattr(agents_router.SkillInstallRepository, "get_by_user_and_name", store.get_install_by_user_and_name)
    monkeypatch.setattr(AgentRepository, "get_agent_by_name", store.get_agent_by_name)
    monkeypatch.setattr(MemoryRepository, "get_memory_by_user_id", no_memory)


def test_api_backed_max_flow_keeps_runtime_truth_on_install_current_version(tmp_path, monkeypatch):
    skills_root = tmp_path / "skills"
    store = _ApiFlowStore()
    db = _ApiFlowDb()
    publisher = User(id=7, external_auth_id="publisher", username="publisher", display_name="Publisher")
    installer = User(id=22, external_auth_id="installer", username="installer", display_name="Installer")
    current_user = {"value": publisher}
    monkeypatch.setattr("deerflow.config.get_app_config", lambda: _runtime_config(skills_root))
    monkeypatch.setattr(skills_router, "get_app_config", lambda: _runtime_config(skills_root))
    _install_api_flow_repositories(monkeypatch, store)

    async def db_override():
        return db

    app = FastAPI()
    app.include_router(skills_router.router)
    app.include_router(agents_router.router)
    app.dependency_overrides[skills_router.get_current_user] = lambda: current_user["value"]
    app.dependency_overrides[agents_router.get_current_user] = lambda: current_user["value"]
    app.dependency_overrides[skills_router.get_db] = db_override
    app.dependency_overrides[agents_router.get_db] = db_override

    def upload(marker: str, package_version: str) -> dict:
        response = client.post(
            "/api/skills/uploads",
            files=[
                (
                    "files",
                    (
                        "probe-skill.zip",
                        _skill_zip_bytes(
                            description=f"Probe {marker}",
                            package_version=package_version,
                            marker=marker,
                        ),
                        "application/zip",
                    ),
                )
            ],
        )
        assert response.status_code == 200, response.text
        result = response.json()["results"][0]
        assert result["success"] is True
        return result

    def manifest_and_load(expected_version: SkillVersion) -> tuple[RuntimeManifest, str, str, str, str]:
        def fail_scan(*args, **kwargs):
            raise AssertionError("runtime truth must use exact manifest artifacts, not filesystem scans")

        with (
            patch.object(Path, "glob", fail_scan),
        ):
            bundle = asyncio.run(
                AgentRepository.get_runtime_agent_bundle(
                    db,
                    user_id=installer.id,
                    agent_name="probe-agent",
                )
            )
            manifest = db.added[-1]
            runtime = _runtime_for_manifest(tmp_path, manifest)
            loaded = _load_skill(runtime, skills_root, manifest.manifest_json["skills"][0]["virtual_path"])
            public_denied = _load_skill(runtime, skills_root, "/mnt/skills/public/probe-skill/SKILL.md")
            legacy_denied = _load_skill(runtime, skills_root, "/mnt/skills/22/probe-skill/SKILL.md")
            missing_denied = _load_skill(runtime, skills_root, "/mnt/skills/missing-artifact/probe-skill/SKILL.md")

        assert bundle.manifest_id == str(manifest.id)
        assert bundle.manifest_hash == manifest.manifest_hash
        assert bundle.skills[0].skill_id == str(expected_version.skill_id)
        assert bundle.skills[0].version_number == expected_version.version_number
        return manifest, loaded, public_denied, legacy_denied, missing_denied

    with TestClient(app) as client:
        upload_v1 = upload("SKILL_RUNTIME_OK_V1", "99.0.0")
        assert upload_v1["platform_version"] == 1
        assert "skill_version_id" not in upload_v1
        v1 = next(version for version in store.versions if str(version.skill_id) == upload_v1["skill_id"] and version.version_number == upload_v1["version_number"])
        definition = store.definition_by_id(v1.skill_definition_id)
        publisher_install = asyncio.run(store.get_install_by_user_and_definition(db, user_id=publisher.id, skill_definition_id=definition.id))

        publish_v1 = client.post("/api/skills/probe-skill/publish", json={"release_notes": "publish v1"})
        assert publish_v1.status_code == 200, publish_v1.text
        release_v1 = store.releases[-1]

        current_user["value"] = installer
        install_v1 = client.post("/api/skills/install", json={"skill_id": str(v1.skill_id), "version_number": v1.version_number})
        assert install_v1.status_code == 200, install_v1.text
        installer_install = asyncio.run(store.get_install_by_user_and_definition(db, user_id=installer.id, skill_definition_id=definition.id))

        create_agent = client.post(
            "/api/agents",
            json={"name": "probe-agent", "description": "Probe Agent", "skill_install_ids": [installer_install.id], "soul": "probe"},
        )
        assert create_agent.status_code == 201, create_agent.text
        agent = asyncio.run(store.get_agent_by_name(db, user_id=installer.id, name="probe-agent"))
        agent_skill = agent.agent_skills[0]

        current_user["value"] = publisher
        upload_v2 = upload("SKILL_RUNTIME_OK_V2", "100.0.0")
        assert "skill_version_id" not in upload_v2
        v2 = next(version for version in store.versions if str(version.skill_id) == upload_v2["skill_id"] and version.version_number == upload_v2["version_number"])
        publish_v2 = client.post("/api/skills/probe-skill/publish", json={"release_notes": "publish v2"})
        assert publish_v2.status_code == 200, publish_v2.text
        release_v2 = store.releases[-1]

        _write_artifact(skills_root, "22/probe-skill", "SKILL_RUNTIME_OK_V2_LEGACY_CUSTOM")
        _write_artifact(skills_root, "probe-skill", "SKILL_RUNTIME_OK_V2_SAME_NAME_ROOT")
        (skills_root / "artifacts/skills/1/v-missing-skill-md/probe-skill").mkdir(parents=True)
        legacy_same_name_skill = Skill(
            id=999,
            user_id=installer.id,
            name="probe-skill",
            file_path="22/probe-skill",
        )
        agent_skill.skill_id = legacy_same_name_skill.id
        agent_skill.skill = Skill(
            id=999,
            user_id=installer.id,
            name="probe-skill",
            file_path="22/probe-skill",
        )

        assert definition.name == "probe-skill"
        assert v1.skill_definition_id == definition.id
        assert v2.skill_definition_id == definition.id
        assert v1.version_number == 1
        assert v2.version_number == 2
        assert v1.source_package_version == "99.0.0"
        assert v2.source_package_version == "100.0.0"
        assert v1.artifact_uri == f"{_terminal_skill_id(definition.id)}/1"
        assert v2.artifact_uri == f"{_terminal_skill_id(definition.id)}/2"
        assert publisher_install.current_version_id == v2.id
        assert release_v1.skill_version_id == v1.id
        assert release_v1.skill_id == v1.skill_id
        assert release_v1.version_number == v1.version_number
        assert release_v1.artifact_path == v1.artifact_uri
        assert release_v1.published_skill_id is None
        assert release_v2.skill_version_id == v2.id
        assert release_v2.skill_id == v2.skill_id
        assert release_v2.version_number == v2.version_number
        assert release_v2.artifact_path == v2.artifact_uri
        assert release_v2.published_skill_id is None
        assert installer_install.installed_version_id == v1.id
        assert installer_install.current_version_id == v1.id
        assert installer_install.skill_id == v1.skill_id
        assert installer_install.version_number == v1.version_number
        assert install_v1.json()["skill_install_id"] == installer_install.id
        assert agent_skill.skill_install_id == installer_install.id
        assert agent_skill.skill_id == legacy_same_name_skill.id

        before_update_manifest, before_update_load, public_denied, legacy_denied, missing_denied = manifest_and_load(v1)
        before_entry = before_update_manifest.manifest_json["skills"][0]
        assert before_update_manifest.user_id == installer.id
        assert before_update_manifest.agent_id == agent.id
        assert before_update_manifest.agent_name == "probe-agent"
        assert before_update_manifest.manifest_json["version"] == 2
        assert before_entry["skill_id"] == str(v1.skill_id)
        assert before_entry["version_number"] == 1
        assert before_entry["file_manifest_hash"] == v1.file_manifest_hash
        assert "skill_version_id" not in before_entry
        assert "skill_install_id" not in before_entry
        assert "artifact_uri" not in before_entry
        assert "file_path" not in before_entry
        assert before_update_manifest.manifest_hash == build_runtime_manifest_hash(before_update_manifest.manifest_json)
        assert "SKILL_RUNTIME_OK_V1" in before_update_load
        assert "SKILL_RUNTIME_OK_V2" not in before_update_load
        assert "SKILL_RUNTIME_OK_V2_SAME_NAME_ROOT" not in before_update_load
        assert "Permission denied" in public_denied
        assert "Permission denied" in legacy_denied
        assert "Permission denied" in missing_denied

        current_user["value"] = installer
        update = client.post(
            "/api/skills/probe-skill/update-install",
            json={"skill_install_id": installer_install.id, "skill_id": str(v2.skill_id), "version_number": v2.version_number},
        )
        assert update.status_code == 200, update.text
        assert "current_skill_version_id" not in update.json()
        assert "target_skill_version_id" not in update.json()
        assert update.json()["skill_id"] == str(v2.skill_id)
        assert update.json()["version_number"] == v2.version_number
        assert update.json()["update_available"] is False
        assert installer_install.current_version_id == v2.id
        assert installer_install.version_number == v2.version_number

        after_update_manifest, after_update_load, public_denied, legacy_denied, missing_denied = manifest_and_load(v2)
        after_entry = after_update_manifest.manifest_json["skills"][0]
        assert after_entry["skill_id"] == str(v2.skill_id)
        assert after_entry["version_number"] == 2
        assert after_entry["file_manifest_hash"] == v2.file_manifest_hash
        assert "skill_version_id" not in after_entry
        assert "skill_install_id" not in after_entry
        assert "artifact_uri" not in after_entry
        assert "file_path" not in after_entry
        assert after_update_manifest.manifest_hash == build_runtime_manifest_hash(after_update_manifest.manifest_json)
        assert "SKILL_RUNTIME_OK_V2" in after_update_load
        assert "SKILL_RUNTIME_OK_V1" not in after_update_load
        assert "SKILL_RUNTIME_OK_V2_SAME_NAME_ROOT" not in after_update_load
        assert "Permission denied" in public_denied
        assert "Permission denied" in legacy_denied
        assert "Permission denied" in missing_denied


def _bound_agent_with_install(install: SkillInstall, *, legacy_skill: Skill | None = None) -> Agent:
    if install.status is None:
        install.status = "active"
    agent = Agent(id=10, user_id=22, name="probe-agent", soul="probe")
    agent.agent_skills = [
        AgentSkill(
            id=501,
            agent_id=10,
            skill_id=legacy_skill.id if legacy_skill is not None else None,
            skill_install_id=install.id,
            display_order=0,
            enabled=True,
            skill=legacy_skill,
            skill_install=install,
        )
    ]
    return agent


def _runtime_for_manifest(tmp_path: Path, manifest) -> SimpleNamespace:
    return SimpleNamespace(
        state={"thread_data": {"thread_id": "thread-1", "workspace_path": str(tmp_path)}},
        context={
            "runtime_agent": {
                "manifest_id": str(manifest.id),
                "manifest_hash": manifest.manifest_hash,
                "skills": manifest.manifest_json["skills"],
            }
        },
        config={},
    )


def _load_skill(runtime: SimpleNamespace, skills_root: Path, path: str) -> str:
    with (
        patch("deerflow.sandbox.tools._get_skills_container_path", return_value="/mnt/skills"),
        patch("deerflow.sandbox.tools._get_skills_host_path", return_value=str(skills_root)),
    ):
        return skill_load_tool.func(
            runtime=runtime,
            description="load probe",
            path=path,
        )


def test_runtime_manifest_resolves_installed_v1_then_manual_update_to_v2(tmp_path, monkeypatch):
    skills_root = tmp_path / "skills"
    skill_id = _terminal_skill_id(1)
    terminal_skill = _terminal_skill(skill_id)
    v1_file_manifest_hash = _write_terminal_artifact(skills_root, skill_id, 1, "SKILL_RUNTIME_OK_V1")
    v2_file_manifest_hash = _write_terminal_artifact(skills_root, skill_id, 2, "SKILL_RUNTIME_OK_V2")
    monkeypatch.setattr("deerflow.config.get_app_config", lambda: _runtime_config(skills_root))

    definition = SkillDefinition(id=1, name="probe-skill", description="Probe")
    v1 = SkillVersion(
        id=101,
        skill_id=skill_id,
        skill=terminal_skill,
        skill_definition_id=1,
        version_number=1,
        description="Probe",
        content_hash="hash-v1",
        file_manifest_hash=v1_file_manifest_hash,
        artifact_uri="artifacts/skills/1/v1-aaa/probe-skill",
        source_package_version="99.0.0",
        definition=definition,
    )
    v2 = SkillVersion(
        id=102,
        skill_id=skill_id,
        skill=terminal_skill,
        skill_definition_id=1,
        version_number=2,
        description="Probe",
        content_hash="hash-v2",
        file_manifest_hash=v2_file_manifest_hash,
        artifact_uri="artifacts/skills/1/v2-bbb/probe-skill",
        source_package_version="99.0.0",
        definition=definition,
    )
    install = SkillInstall(
        id=201,
        user_id=22,
        skill_id=skill_id,
        skill=terminal_skill,
        version_number=1,
        skill_definition_id=1,
        installed_version_id=101,
        current_version_id=101,
        definition=definition,
        current_version=v1,
    )
    agent = _bound_agent_with_install(install)

    before_publish = AgentRepository._active_runtime_skills(agent)
    public_latest_same_name_v2 = Skill(id=301, user_id=None, name="probe-skill", file_path="public/probe-skill")
    after_publish = AgentRepository._active_runtime_skills(agent)

    install.version_number = 2
    install.current_version_id = 102
    install.current_version = v2
    after_manual_update = AgentRepository._active_runtime_skills(agent)

    assert public_latest_same_name_v2.name == "probe-skill"
    assert before_publish[0].skill_id == str(skill_id)
    assert before_publish[0].version_number == 1
    assert before_publish[0].file_manifest_hash == v1_file_manifest_hash
    assert after_publish[0].version_number == 1
    assert after_manual_update[0].skill_id == str(skill_id)
    assert after_manual_update[0].version_number == 2
    assert after_manual_update[0].file_manifest_hash == v2_file_manifest_hash
    assert not hasattr(after_manual_update[0], "artifact_uri")
    assert not hasattr(after_manual_update[0], "skill_version_id")


def test_runtime_manifest_uses_skill_identity_for_same_name_virtual_roots(tmp_path, monkeypatch):
    skills_root = tmp_path / "skills"
    first_skill_id = _terminal_skill_id(1)
    second_skill_id = _terminal_skill_id(2)
    first_skill = _terminal_skill(first_skill_id, name="same-skill")
    second_skill = _terminal_skill(second_skill_id, name="same-skill")
    first_file_manifest_hash = _write_terminal_artifact(skills_root, first_skill_id, 1, "FIRST_SOURCE")
    second_file_manifest_hash = _write_terminal_artifact(skills_root, second_skill_id, 1, "SECOND_SOURCE")
    monkeypatch.setattr("deerflow.config.get_app_config", lambda: _runtime_config(skills_root))

    first_definition = SkillDefinition(id=1, name="same-skill", description="First")
    second_definition = SkillDefinition(id=2, name="same-skill", description="Second")
    first_version = SkillVersion(
        id=101,
        skill_id=first_skill_id,
        skill=first_skill,
        skill_definition_id=1,
        version_number=1,
        description="First",
        content_hash="first-hash",
        file_manifest_hash=first_file_manifest_hash,
        artifact_uri="artifacts/skills/1/v1-aaa/same-skill",
        definition=first_definition,
    )
    second_version = SkillVersion(
        id=102,
        skill_id=second_skill_id,
        skill=second_skill,
        skill_definition_id=2,
        version_number=1,
        description="Second",
        content_hash="second-hash",
        file_manifest_hash=second_file_manifest_hash,
        artifact_uri="artifacts/skills/2/v1-bbb/same-skill",
        definition=second_definition,
    )
    first_install = SkillInstall(
        id=201,
        user_id=22,
        skill_id=first_skill_id,
        skill=first_skill,
        version_number=1,
        status="active",
        skill_definition_id=1,
        installed_version_id=101,
        current_version_id=101,
        definition=first_definition,
        current_version=first_version,
    )
    second_install = SkillInstall(
        id=202,
        user_id=22,
        skill_id=second_skill_id,
        skill=second_skill,
        version_number=1,
        status="active",
        skill_definition_id=2,
        installed_version_id=102,
        current_version_id=102,
        definition=second_definition,
        current_version=second_version,
    )
    agent = Agent(id=10, user_id=22, name="same-name-agent", soul="probe")
    agent.agent_skills = [
        AgentSkill(id=501, agent_id=10, skill_install_id=201, display_order=0, enabled=True, skill_install=first_install),
        AgentSkill(id=502, agent_id=10, skill_install_id=202, display_order=1, enabled=True, skill_install=second_install),
    ]

    descriptors = AgentRepository._active_runtime_skills(agent)
    manifest = asyncio.run(AgentRepository._create_runtime_manifest(_FakeManifestSession(), user_id=22, agent=agent, skills=descriptors))
    runtime = _runtime_for_manifest(tmp_path, manifest)
    first_entry, second_entry = manifest.manifest_json["skills"]

    assert first_entry["name"] == second_entry["name"] == "same-skill"
    assert first_entry["skill_id"] == str(first_skill_id)
    assert second_entry["skill_id"] == str(second_skill_id)
    assert first_entry["virtual_path"] == f"/mnt/skills/same-skill--{first_skill_id}-v1/SKILL.md"
    assert second_entry["virtual_path"] == f"/mnt/skills/same-skill--{second_skill_id}-v1/SKILL.md"
    assert first_entry["virtual_path"] != second_entry["virtual_path"]
    assert _load_skill(runtime, skills_root, first_entry["virtual_path"]) == "FIRST_SOURCE"
    assert _load_skill(runtime, skills_root, second_entry["virtual_path"]) == "SECOND_SOURCE"


def test_runtime_manifest_rejects_direct_system_skill_without_install(tmp_path, monkeypatch):
    skills_root = tmp_path / "skills"
    monkeypatch.setattr("deerflow.config.get_app_config", lambda: _runtime_config(skills_root))

    definition = SkillDefinition(id=9, name="system-skill", description="System skill", source_type="legacy", source_identifier="legacy", owner_user_id=None)
    version = SkillVersion(
        id=901,
        skill_id=_terminal_skill_id(9),
        skill_definition_id=definition.id,
        version_number=1,
        description="System skill",
        content_hash="system-hash",
        file_manifest_hash="system-hash",
        artifact_uri="artifacts/skills/9/v1-system/system-skill",
        source_package_version=None,
        definition=definition,
    )
    agent = Agent(id=10, user_id=22, name="system-agent", soul="probe")
    agent.agent_skills = [
        AgentSkill(id=501, agent_id=10, system_skill_definition_id=definition.id, system_skill_version_id=version.id, system_skill_definition=definition, system_skill_version=version, display_order=0, enabled=True)
    ]

    with pytest.raises(RuntimeManifestResolutionError, match="direct system skill binding"):
        AgentRepository._active_runtime_skills(agent)


def test_skills_max_flow_backend_truth_uses_install_manifest_and_terminal_storage(tmp_path, monkeypatch):
    skills_root = tmp_path / "skills"
    skill_id = _terminal_skill_id(1)
    terminal_skill = _terminal_skill(skill_id)
    public_latest_uri = "public/probe-skill"
    legacy_custom_uri = "22/probe-skill"
    v1_file_manifest_hash = _write_terminal_artifact(skills_root, skill_id, 1, "SKILL_RUNTIME_OK_V1")
    v2_file_manifest_hash = _write_terminal_artifact(skills_root, skill_id, 2, "SKILL_RUNTIME_OK_V2")
    _write_artifact(skills_root, public_latest_uri, "SKILL_RUNTIME_OK_V2_PUBLIC_LATEST")
    _write_artifact(skills_root, legacy_custom_uri, "SKILL_RUNTIME_OK_V2_LEGACY_CUSTOM")
    monkeypatch.setattr("deerflow.config.get_app_config", lambda: _runtime_config(skills_root))

    def _fail_scan(*args, **kwargs):
        raise AssertionError("runtime resolution must use exact terminal descriptors, not filesystem scans")

    monkeypatch.setattr(Path, "glob", _fail_scan)

    definition = SkillDefinition(id=1, name="probe-skill", description="Probe")
    v1 = SkillVersion(
        id=101,
        skill_id=skill_id,
        skill=terminal_skill,
        skill_definition_id=1,
        version_number=1,
        description="Probe v1",
        content_hash="hash-v1",
        file_manifest_hash=v1_file_manifest_hash,
        artifact_uri="artifacts/skills/1/v1-aaa/probe-skill",
        source_package_version=None,
        definition=definition,
    )
    v2 = SkillVersion(
        id=102,
        skill_id=skill_id,
        skill=terminal_skill,
        skill_definition_id=1,
        version_number=2,
        description="Probe v2",
        content_hash="hash-v2",
        file_manifest_hash=v2_file_manifest_hash,
        artifact_uri="artifacts/skills/1/v2-bbb/probe-skill",
        source_package_version=None,
        definition=definition,
    )
    release_v2 = SkillRelease(id=402, skill_id=skill_id, version_number=2, skill_name="probe-skill", release_version="rel-v2", status="published", artifact_path=v2.artifact_uri, skill_version_id=v2.id, skill_version=v2)
    install = SkillInstall(
        id=201,
        user_id=22,
        skill_id=skill_id,
        skill=terminal_skill,
        version_number=1,
        skill_definition_id=definition.id,
        installed_version_id=v1.id,
        current_version_id=v1.id,
        definition=definition,
        installed_version=v1,
        current_version=v1,
    )
    public_latest_same_name_v2 = Skill(id=301, user_id=None, name="probe-skill", file_path=public_latest_uri)
    agent = _bound_agent_with_install(install, legacy_skill=public_latest_same_name_v2)

    before_update_skills = AgentRepository._active_runtime_skills(agent)
    before_update_manifest = asyncio.run(AgentRepository._create_runtime_manifest(_FakeManifestSession(), user_id=22, agent=agent, skills=before_update_skills))
    before_update_runtime = _runtime_for_manifest(tmp_path, before_update_manifest)
    before_virtual_path = before_update_manifest.manifest_json["skills"][0]["virtual_path"]

    assert before_update_manifest.manifest_json == {
        "version": 2,
        "skills": [
            {
                "name": "probe-skill",
                "description": "Probe v1",
                "skill_id": str(skill_id),
                "version_number": 1,
                "file_manifest_hash": v1_file_manifest_hash,
                "virtual_path": f"/mnt/skills/probe-skill--{skill_id}-v1/SKILL.md",
            }
        ],
    }
    assert before_update_manifest.manifest_hash == build_runtime_manifest_hash(before_update_manifest.manifest_json)
    assert _load_skill(before_update_runtime, skills_root, before_virtual_path) == "SKILL_RUNTIME_OK_V1"
    assert "Permission denied" in _load_skill(before_update_runtime, skills_root, "/mnt/skills/public/probe-skill/SKILL.md")
    assert "Permission denied" in _load_skill(before_update_runtime, skills_root, "/mnt/skills/22/probe-skill/SKILL.md")

    assert release_v2.status == "published"
    assert install.version_number == 1
    assert AgentRepository._active_runtime_skills(agent)[0].version_number == 1

    install.version_number = 2
    install.current_version_id = v2.id
    install.current_version = v2
    after_update_skills = AgentRepository._active_runtime_skills(agent)
    after_update_manifest = asyncio.run(AgentRepository._create_runtime_manifest(_FakeManifestSession(), user_id=22, agent=agent, skills=after_update_skills))
    after_virtual_path = after_update_manifest.manifest_json["skills"][0]["virtual_path"]

    assert after_update_manifest.manifest_json["skills"][0]["skill_id"] == str(skill_id)
    assert after_update_manifest.manifest_json["skills"][0]["version_number"] == 2
    assert after_update_manifest.manifest_json["skills"][0]["file_manifest_hash"] == v2_file_manifest_hash
    assert after_virtual_path == f"/mnt/skills/probe-skill--{skill_id}-v2/SKILL.md"
    assert _load_skill(_runtime_for_manifest(tmp_path, after_update_manifest), skills_root, after_virtual_path) == "SKILL_RUNTIME_OK_V2"


def test_runtime_manifest_rejects_legacy_skill_binding_without_install(tmp_path, monkeypatch):
    skills_root = tmp_path / "skills"
    monkeypatch.setattr("deerflow.config.get_app_config", lambda: _runtime_config(skills_root))

    agent = Agent(id=10, user_id=22, name="probe-agent")
    agent.agent_skills = [
        AgentSkill(
            id=501,
            agent_id=10,
            skill_id=301,
            display_order=0,
            enabled=True,
            skill=Skill(id=301, user_id=22, name="probe-skill", file_path="22/probe-skill"),
        )
    ]

    with pytest.raises(RuntimeManifestResolutionError, match="without an active install"):
        AgentRepository._active_runtime_skills(agent)


def test_runtime_manifest_rejects_missing_artifact(tmp_path, monkeypatch):
    skills_root = tmp_path / "skills"
    monkeypatch.setattr("deerflow.config.get_app_config", lambda: _runtime_config(skills_root))

    skill_id = _terminal_skill_id(1)
    terminal_skill = _terminal_skill(skill_id)
    definition = SkillDefinition(id=1, name="probe-skill", description="Probe")
    missing = SkillVersion(
        id=101,
        skill_id=skill_id,
        skill=terminal_skill,
        skill_definition_id=1,
        version_number=1,
        description="Probe",
        content_hash="hash-v1",
        file_manifest_hash="manifest-v1",
        artifact_uri="artifacts/skills/1/missing/probe-skill",
        definition=definition,
    )
    install = SkillInstall(
        id=201,
        user_id=22,
        skill_id=skill_id,
        skill=terminal_skill,
        version_number=1,
        skill_definition_id=1,
        installed_version_id=101,
        current_version_id=101,
        definition=definition,
        current_version=missing,
    )

    with pytest.raises(RuntimeManifestResolutionError, match="terminal storage root is missing"):
        AgentRepository._active_runtime_skills(_bound_agent_with_install(install))


def test_runtime_manifest_rejects_artifact_file_manifest_hash_mismatch(tmp_path, monkeypatch):
    skills_root = tmp_path / "skills"
    skill_id = _terminal_skill_id(1)
    terminal_skill = _terminal_skill(skill_id)
    _write_terminal_artifact(skills_root, skill_id, 1, "SKILL_RUNTIME_OK_V1")
    monkeypatch.setattr("deerflow.config.get_app_config", lambda: _runtime_config(skills_root))

    definition = SkillDefinition(id=1, name="probe-skill", description="Probe")
    version = SkillVersion(
        id=101,
        skill_id=skill_id,
        skill=terminal_skill,
        skill_definition_id=1,
        version_number=1,
        description="Probe",
        content_hash="hash-v1",
        file_manifest_hash="wrong-file-manifest-hash",
        artifact_uri="artifacts/skills/1/v1-aaa/probe-skill",
        definition=definition,
    )
    install = SkillInstall(
        id=201,
        user_id=22,
        skill_id=skill_id,
        skill=terminal_skill,
        version_number=1,
        skill_definition_id=1,
        installed_version_id=101,
        current_version_id=101,
        definition=definition,
        current_version=version,
    )

    with pytest.raises(RuntimeManifestResolutionError, match="terminal storage file manifest hash mismatch"):
        AgentRepository._active_runtime_skills(_bound_agent_with_install(install))


def test_runtime_manifest_accepts_terminal_skill_version_artifact_uri(tmp_path, monkeypatch):
    skills_root = tmp_path / "skills"
    skill_id = UUID("12345678-1234-5678-1234-567812345678")
    terminal_skill = _terminal_skill(skill_id)
    file_manifest_hash = _write_terminal_artifact(skills_root, skill_id, 1, "SKILL_RUNTIME_OK_V1")
    monkeypatch.setattr("deerflow.config.get_app_config", lambda: _runtime_config(skills_root))

    definition = SkillDefinition(id=1, name="probe-skill", description="Probe")
    version = SkillVersion(
        id=101,
        skill_id=skill_id,
        skill=terminal_skill,
        skill_definition_id=1,
        version_number=1,
        description="Probe",
        content_hash="hash-v1",
        file_manifest_hash=file_manifest_hash,
        artifact_uri="artifacts/skills/1/v1-aaa/probe-skill",
        definition=definition,
    )
    install = SkillInstall(
        id=201,
        user_id=22,
        skill_id=skill_id,
        skill=terminal_skill,
        version_number=1,
        skill_definition_id=1,
        installed_version_id=101,
        current_version_id=101,
        definition=definition,
        current_version=version,
    )

    descriptors = AgentRepository._active_runtime_skills(_bound_agent_with_install(install))

    assert descriptors[0].skill_id == str(skill_id)
    assert descriptors[0].version_number == 1
    assert not hasattr(descriptors[0], "artifact_uri")


def test_runtime_manifest_rejects_missing_current_version(tmp_path, monkeypatch):
    skills_root = tmp_path / "skills"
    monkeypatch.setattr("deerflow.config.get_app_config", lambda: _runtime_config(skills_root))

    definition = SkillDefinition(id=1, name="probe-skill", description="Probe")
    install = SkillInstall(
        id=201,
        user_id=22,
        skill_id=_terminal_skill_id(1),
        version_number=1,
        skill_definition_id=1,
        installed_version_id=101,
        current_version_id=None,
        definition=definition,
        current_version=None,
    )

    with pytest.raises(RuntimeManifestResolutionError, match="without an active install"):
        AgentRepository._active_runtime_skills(_bound_agent_with_install(install))


def test_runtime_manifest_rejects_version_from_another_definition(tmp_path, monkeypatch):
    skills_root = tmp_path / "skills"
    install_skill_id = _terminal_skill_id(1)
    version_skill_id = _terminal_skill_id(2)
    install_skill = _terminal_skill(install_skill_id)
    version_skill = _terminal_skill(version_skill_id)
    monkeypatch.setattr("deerflow.config.get_app_config", lambda: _runtime_config(skills_root))

    install_definition = SkillDefinition(id=1, name="probe-skill", description="Probe")
    version_definition = SkillDefinition(id=2, name="probe-skill", description="Other Probe")
    mismatched_version = SkillVersion(
        id=101,
        skill_id=version_skill_id,
        skill=version_skill,
        skill_definition_id=2,
        version_number=1,
        description="Probe",
        content_hash="hash-v1",
        file_manifest_hash="manifest-v1",
        artifact_uri="artifacts/skills/2/v1-other/probe-skill",
        definition=version_definition,
    )
    install = SkillInstall(
        id=201,
        user_id=22,
        skill_id=install_skill_id,
        skill=install_skill,
        version_number=1,
        skill_definition_id=1,
        installed_version_id=101,
        current_version_id=101,
        definition=install_definition,
        current_version=mismatched_version,
    )

    with pytest.raises(RuntimeManifestResolutionError, match="another terminal Skill version"):
        AgentRepository._active_runtime_skills(_bound_agent_with_install(install))


def test_runtime_manifest_rejects_missing_skill_md(tmp_path, monkeypatch):
    skills_root = tmp_path / "skills"
    skill_id = _terminal_skill_id(1)
    terminal_skill = _terminal_skill(skill_id)
    (skills_root / str(skill_id) / "1").mkdir(parents=True)
    monkeypatch.setattr("deerflow.config.get_app_config", lambda: _runtime_config(skills_root))

    definition = SkillDefinition(id=1, name="probe-skill", description="Probe")
    version = SkillVersion(
        id=101,
        skill_id=skill_id,
        skill=terminal_skill,
        skill_definition_id=1,
        version_number=1,
        description="Probe",
        content_hash="hash-v1",
        file_manifest_hash="manifest-v1",
        artifact_uri="artifacts/skills/1/v1-no-skill-md/probe-skill",
        definition=definition,
    )
    install = SkillInstall(
        id=201,
        user_id=22,
        skill_id=skill_id,
        skill=terminal_skill,
        version_number=1,
        skill_definition_id=1,
        installed_version_id=101,
        current_version_id=101,
        definition=definition,
        current_version=version,
    )

    with pytest.raises(RuntimeManifestResolutionError, match="missing SKILL.md"):
        AgentRepository._active_runtime_skills(_bound_agent_with_install(install))


@pytest.mark.parametrize(
    "artifact_uri",
    [
        "artifacts/skills/1/v1/probe-skill",
        "public/probe-skill",
        "22/probe-skill",
        "custom/probe-skill",
        "probe-skill",
        "artifacts/../public/probe-skill",
    ],
)
def test_runtime_manifest_rejects_legacy_storage_roots_even_when_artifact_uri_points_there(tmp_path, monkeypatch, artifact_uri):
    skills_root = tmp_path / "skills"
    _write_artifact(skills_root, artifact_uri, "fallback should never authorize")
    monkeypatch.setattr("deerflow.config.get_app_config", lambda: _runtime_config(skills_root))

    skill_id = _terminal_skill_id(1)
    terminal_skill = _terminal_skill(skill_id)
    definition = SkillDefinition(id=1, name="probe-skill", description="Probe")
    version = SkillVersion(
        id=101,
        skill_id=skill_id,
        skill=terminal_skill,
        skill_definition_id=1,
        version_number=1,
        description="Probe",
        content_hash="hash-v1",
        file_manifest_hash="manifest-v1",
        artifact_uri=artifact_uri,
        definition=definition,
    )
    install = SkillInstall(
        id=201,
        user_id=22,
        skill_id=skill_id,
        skill=terminal_skill,
        version_number=1,
        skill_definition_id=1,
        installed_version_id=101,
        current_version_id=101,
        definition=definition,
        current_version=version,
    )

    with pytest.raises(RuntimeManifestResolutionError, match="terminal storage root is missing"):
        AgentRepository._active_runtime_skills(_bound_agent_with_install(install))


def test_skill_load_reads_manifest_artifact_and_denies_public_latest_same_name(tmp_path):
    skills_root = tmp_path / "skills"
    skill_id = _terminal_skill_id(1)
    public_uri = "public/probe-skill"
    v1_file_manifest_hash = _write_terminal_artifact(skills_root, skill_id, 1, "SKILL_RUNTIME_OK_V1")
    _write_artifact(skills_root, public_uri, "SKILL_RUNTIME_OK_V2")

    runtime = SimpleNamespace(
        state={"thread_data": {"thread_id": "thread-1", "workspace_path": str(tmp_path)}},
        context={
            "runtime_agent": {
                "manifest_id": "manifest-1",
                "skills": [
                    {
                        "name": "probe-skill",
                        "skill_id": str(skill_id),
                        "version_number": 1,
                        "file_manifest_hash": v1_file_manifest_hash,
                        "virtual_path": f"/mnt/skills/probe-skill--{skill_id}-v1/SKILL.md",
                    }
                ],
            }
        },
        config={},
    )

    from unittest.mock import patch

    with (
        patch("deerflow.sandbox.tools._get_skills_container_path", return_value="/mnt/skills"),
        patch("deerflow.sandbox.tools._get_skills_host_path", return_value=str(skills_root)),
    ):
        loaded = skill_load_tool.func(
            runtime=runtime,
            description="load probe",
            path=f"/mnt/skills/probe-skill--{skill_id}-v1/SKILL.md",
        )
        denied = skill_load_tool.func(
            runtime=runtime,
            description="load public latest",
            path="/mnt/skills/public/probe-skill/SKILL.md",
        )

    assert loaded == "SKILL_RUNTIME_OK_V1"
    assert "Permission denied" in denied


def test_skill_load_rejects_manifest_artifact_hash_drift(tmp_path):
    skills_root = tmp_path / "skills"
    skill_id = _terminal_skill_id(1)
    expected_hash = _write_terminal_artifact(skills_root, skill_id, 1, "SKILL_RUNTIME_OK_V1")
    (skills_root / str(skill_id) / "1" / "SKILL.md").write_text("DRIFTED", encoding="utf-8")

    runtime = SimpleNamespace(
        state={"thread_data": {"thread_id": "thread-1", "workspace_path": str(tmp_path)}},
        context={
            "runtime_agent": {
                "manifest_id": "manifest-1",
                "skills": [
                    {
                        "name": "probe-skill",
                        "skill_id": str(skill_id),
                        "version_number": 1,
                        "file_manifest_hash": expected_hash,
                        "virtual_path": f"/mnt/skills/probe-skill--{skill_id}-v1/SKILL.md",
                    }
                ],
            }
        },
        config={},
    )

    from unittest.mock import patch

    with (
        patch("deerflow.sandbox.tools._get_skills_container_path", return_value="/mnt/skills"),
        patch("deerflow.sandbox.tools._get_skills_host_path", return_value=str(skills_root)),
    ):
        loaded = skill_load_tool.func(
            runtime=runtime,
            description="load drifted probe",
            path=f"/mnt/skills/probe-skill--{skill_id}-v1/SKILL.md",
        )

    assert "file manifest hash mismatch" in loaded
