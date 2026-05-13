from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest
from fastapi import HTTPException

from app.gateway.db.models import Agent, AgentSkill, LegacySkill, SkillDefinition, SkillInstall, SkillVersion, User
from app.gateway.routers import agents as agents_router


def _definition(*, owner_user_id: int | None = 7) -> SkillDefinition:
    owner_user = (
        User(
            id=owner_user_id,
            external_auth_id=f"owner-{owner_user_id}",
            username=f"owner-{owner_user_id}",
            display_name="Demo Publisher",
        )
        if owner_user_id is not None
        else None
    )
    return SkillDefinition(
        id=10,
        name="probe-skill",
        display_name="Probe Skill",
        description="Probe description",
        owner_user_id=owner_user_id,
        source_type="legacy" if owner_user_id is None else "user",
        source_identifier="legacy" if owner_user_id is None else str(owner_user_id),
        owner_user=owner_user,
    )


def _version(definition: SkillDefinition, *, version_id: int, version_number: int) -> SkillVersion:
    return SkillVersion(
        id=version_id,
        skill_definition_id=definition.id,
        version_number=version_number,
        source_package_version="pkg-ignored",
        description=f"Platform v{version_number}",
        content_hash=f"hash-{version_number}",
        file_manifest_hash=f"manifest-{version_number}",
        artifact_uri=f"artifacts/skills/{definition.id}/v{version_number}/probe-skill",
        definition=definition,
    )


class _FakeDb:
    def __init__(self) -> None:
        self.rolled_back = False

    async def rollback(self) -> None:
        self.rolled_back = True


def _agent_with_install(*, current_version: SkillVersion | None, definition: SkillDefinition, install_deleted: bool = False) -> Agent:
    install = SkillInstall(
        id=201,
        user_id=22,
        skill_definition_id=definition.id,
        installed_version_id=101,
        current_version_id=101,
        definition=definition,
        current_version=current_version,
        deleted_at=datetime.now(UTC) if install_deleted else None,
    )
    return Agent(
        id=501,
        user_id=22,
        name="probe-agent",
        description="Probe agent",
        soul="Probe soul",
        agent_skills=[
            AgentSkill(
                id=601,
                agent_id=501,
                skill_install_id=install.id,
                skill_install=install,
                display_order=0,
                enabled=True,
            )
        ],
    )


def test_agent_response_skill_metadata_uses_bound_install_current_version() -> None:
    definition = _definition(owner_user_id=7)
    current_version = _version(definition, version_id=101, version_number=1)
    agent = _agent_with_install(current_version=current_version, definition=definition)

    response = agents_router._agent_to_response(
        agent,
        latest_versions_by_definition_id={definition.id: 102},
    )

    assert response.skills == ["probe-skill"]
    assert response.skill_metadata is not None
    metadata = response.skill_metadata[0]
    assert metadata.name == "probe-skill"
    assert metadata.skill_install_id == 201
    assert metadata.skill_definition_id == definition.id
    assert metadata.skill_version_id == 101
    assert metadata.current_platform_version == 1
    assert metadata.source == "skillhub"
    assert metadata.source_label == "Demo Publisher"
    assert metadata.update_available is True
    assert metadata.available is True
    assert metadata.status == "available"
    assert "artifact_uri" not in metadata.model_dump()
    assert "source_package_version" not in metadata.model_dump()


def test_agent_response_marks_incomplete_install_metadata_unavailable() -> None:
    definition = _definition(owner_user_id=22)
    agent = _agent_with_install(current_version=None, definition=definition)

    response = agents_router._agent_to_response(agent)

    assert response.skills == ["probe-skill"]
    assert response.skill_metadata is not None
    metadata = response.skill_metadata[0]
    assert metadata.name == "probe-skill"
    assert metadata.skill_install_id == 201
    assert metadata.skill_definition_id == definition.id
    assert metadata.skill_version_id is None
    assert metadata.current_platform_version is None
    assert metadata.source == "my_skills"
    assert metadata.update_available is None
    assert metadata.available is False
    assert metadata.status == "unavailable"


def test_agent_response_marks_deleted_install_metadata_unavailable() -> None:
    definition = _definition(owner_user_id=22)
    current_version = _version(definition, version_id=101, version_number=1)
    agent = _agent_with_install(current_version=current_version, definition=definition, install_deleted=True)

    response = agents_router._agent_to_response(
        agent,
        latest_versions_by_definition_id={definition.id: 102},
    )

    assert response.skills == ["probe-skill"]
    assert response.skill_metadata is not None
    metadata = response.skill_metadata[0]
    assert metadata.name == "probe-skill"
    assert metadata.skill_install_id == 201
    assert metadata.skill_version_id == 101
    assert metadata.current_platform_version == 1
    assert metadata.update_available is None
    assert metadata.available is False
    assert metadata.status == "unavailable"
    assert agents_router._collect_bound_definition_ids([agent]) == set()


def test_agent_response_keeps_legacy_skill_binding_visible_but_unavailable() -> None:
    agent = Agent(
        id=501,
        user_id=22,
        name="legacy-agent",
        agent_skills=[
            AgentSkill(
                id=601,
                agent_id=501,
                skill_id=301,
                skill=LegacySkill(id=301, user_id=22, name="legacy-skill", description="Legacy", file_path="custom/legacy-skill"),
                display_order=0,
                enabled=True,
            )
        ],
    )

    response = agents_router._agent_to_response(agent)

    assert response.skills == ["legacy-skill"]
    assert response.skill_metadata is not None
    metadata = response.skill_metadata[0]
    assert metadata.name == "legacy-skill"
    assert metadata.skill_install_id is None
    assert metadata.source == "unknown"
    assert metadata.available is False
    assert metadata.status == "unavailable"


def test_agent_response_labels_official_skill_source_without_namespace() -> None:
    definition = _definition(owner_user_id=None)
    current_version = _version(definition, version_id=101, version_number=1)
    agent = Agent(
        id=501,
        user_id=22,
        name="probe-agent",
        agent_skills=[
            AgentSkill(
                id=601,
                agent_id=501,
                system_skill_definition_id=definition.id,
                system_skill_version_id=current_version.id,
                system_skill_definition=definition,
                system_skill_version=current_version,
                display_order=0,
                enabled=True,
            )
        ],
    )

    response = agents_router._agent_to_response(agent)

    assert response.skills == ["probe-skill"]
    assert response.skill_metadata is not None
    metadata = response.skill_metadata[0]
    assert metadata.skill_install_id is None
    assert metadata.system_skill_definition_id == definition.id
    assert metadata.system_skill_version_id == current_version.id
    assert metadata.source == "system"
    assert metadata.source_label == "System"
    assert metadata.current_platform_version == 1
    assert metadata.available is True


def test_agent_request_resolves_system_skill_definition_without_install(monkeypatch) -> None:
    definition = _definition(owner_user_id=None)
    version = _version(definition, version_id=101, version_number=1)

    async def get_latest_published_release_for_definition(_db, *, skill_definition_id):
        assert skill_definition_id == definition.id
        return type("Release", (), {"skill_version": version})()

    async def get_by_id_for_user(*_args, **_kwargs):
        raise AssertionError("system skill binding must not resolve or create user installs")

    monkeypatch.setattr(agents_router.SkillReleaseRepository, "get_latest_published_release_for_definition", get_latest_published_release_for_definition)
    monkeypatch.setattr(agents_router.SkillInstallRepository, "get_by_id_for_user", get_by_id_for_user)

    result = asyncio.run(
        agents_router._resolve_system_skill_version_ids_for_request(
            object(),
            system_skill_version_ids=None,
            system_skill_definition_ids=[definition.id],
        )
    )

    assert result == [version.id]


def test_agent_metadata_publish_v2_keeps_bound_runtime_on_installed_v1_until_manual_update() -> None:
    definition = _definition(owner_user_id=7)
    installed_v1 = _version(definition, version_id=101, version_number=1)
    published_v2 = _version(definition, version_id=102, version_number=2)
    agent = _agent_with_install(current_version=installed_v1, definition=definition)

    response = agents_router._agent_to_response(
        agent,
        latest_versions_by_definition_id={definition.id: published_v2.id},
    )

    assert response.skill_metadata is not None
    metadata = response.skill_metadata[0]
    assert metadata.skill_version_id == installed_v1.id
    assert metadata.current_platform_version == 1
    assert metadata.update_available is True


def test_agent_skill_name_resolution_rejects_missing_or_uninstalled_names(monkeypatch) -> None:
    async def list_by_user_and_name(_db, *, user_id, name):
        assert user_id == 22
        assert name == "missing-skill"
        return []

    monkeypatch.setattr(agents_router.SkillInstallRepository, "list_by_user_and_name", list_by_user_and_name)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            agents_router._resolve_skill_install_ids(
                object(),
                user_id=22,
                skill_names=["missing-skill"],
            )
        )

    assert exc_info.value.status_code == 400
    assert "Skill install 'missing-skill' not found" == exc_info.value.detail


def test_agent_skill_install_id_resolution_selects_collision_install(monkeypatch) -> None:
    install = SkillInstall(id=202, user_id=22, skill_definition_id=11, installed_version_id=101, current_version_id=101)

    async def get_by_id_for_user(_db, *, user_id, skill_install_id):
        assert user_id == 22
        assert skill_install_id == 202
        return install

    async def list_by_user_and_name(*_args, **_kwargs):
        raise AssertionError("install-id-only requests must not fall back to name lookup")

    monkeypatch.setattr(agents_router.SkillInstallRepository, "get_by_id_for_user", get_by_id_for_user)
    monkeypatch.setattr(agents_router.SkillInstallRepository, "list_by_user_and_name", list_by_user_and_name)

    result = asyncio.run(
        agents_router._resolve_skill_install_ids_for_request(
            object(),
            user_id=22,
            skill_install_ids=[202],
            skill_names=None,
        )
    )

    assert result == [202]


def test_create_agent_rejects_uninstalled_skill_name_and_rolls_back(monkeypatch) -> None:
    async def get_agent_by_name(_db, *, user_id, name):
        assert user_id == 22
        assert name == "probe-agent"
        return None

    async def create_agent(_db, **kwargs):
        assert kwargs["user_id"] == 22
        assert kwargs["name"] == "probe-agent"
        assert kwargs["commit"] is False
        return Agent(id=501, user_id=22, name="probe-agent", agent_skills=[])

    async def list_by_user_and_name(_db, *, user_id, name):
        assert user_id == 22
        assert name == "missing-skill"
        return []

    monkeypatch.setattr(agents_router.AgentRepository, "get_agent_by_name", get_agent_by_name)
    monkeypatch.setattr(agents_router.AgentRepository, "create_agent", create_agent)
    monkeypatch.setattr(agents_router.SkillInstallRepository, "list_by_user_and_name", list_by_user_and_name)

    db = _FakeDb()
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            agents_router.create_agent_endpoint(
                agents_router.AgentCreateRequest(name="Probe-Agent", skills=["missing-skill"], soul="Probe soul"),
                current_user=User(id=22),
                db=db,
            )
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Skill install 'missing-skill' not found"
    assert db.rolled_back is True


def test_update_agent_rejects_uninstalled_skill_name_and_rolls_back(monkeypatch) -> None:
    agent = Agent(id=501, user_id=22, name="probe-agent", agent_skills=[])

    async def get_agent_by_name(_db, *, user_id, name):
        assert user_id == 22
        assert name == "probe-agent"
        return agent

    async def update_agent(_db, **kwargs):
        assert kwargs["agent"] is agent
        assert kwargs["commit"] is False
        return agent

    async def list_by_user_and_name(_db, *, user_id, name):
        assert user_id == 22
        assert name == "missing-skill"
        return []

    monkeypatch.setattr(agents_router.AgentRepository, "get_agent_by_name", get_agent_by_name)
    monkeypatch.setattr(agents_router.AgentRepository, "update_agent", update_agent)
    monkeypatch.setattr(agents_router.SkillInstallRepository, "list_by_user_and_name", list_by_user_and_name)

    db = _FakeDb()
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            agents_router.update_agent(
                "Probe-Agent",
                agents_router.AgentUpdateRequest(skills=["missing-skill"]),
                current_user=User(id=22),
                db=db,
            )
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Skill install 'missing-skill' not found"
    assert db.rolled_back is True
