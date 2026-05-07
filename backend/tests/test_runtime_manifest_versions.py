from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest

from app.gateway.db.models import Agent, AgentSkill, Skill, SkillDefinition, SkillInstall, SkillRelease, SkillVersion
from app.gateway.db.repository import AgentRepository, RuntimeManifestResolutionError
from deerflow.sandbox.tools import skill_load_tool


def _write_artifact(skills_root: Path, artifact_uri: str, marker: str) -> None:
    artifact_dir = skills_root / artifact_uri
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "SKILL.md").write_text(marker, encoding="utf-8")


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


def _bound_agent_with_install(install: SkillInstall, *, legacy_skill: Skill | None = None) -> Agent:
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
    v1_uri = "artifacts/skills/1/v1-aaa/probe-skill"
    v2_uri = "artifacts/skills/1/v2-bbb/probe-skill"
    _write_artifact(skills_root, v1_uri, "SKILL_RUNTIME_OK_V1")
    _write_artifact(skills_root, v2_uri, "SKILL_RUNTIME_OK_V2")
    monkeypatch.setattr("deerflow.config.get_app_config", lambda: _runtime_config(skills_root))

    definition = SkillDefinition(id=1, name="probe-skill", description="Probe")
    v1 = SkillVersion(
        id=101,
        skill_definition_id=1,
        version_number=1,
        description="Probe",
        content_hash="hash-v1",
        file_manifest_hash="manifest-v1",
        artifact_uri=v1_uri,
        source_package_version="99.0.0",
        definition=definition,
    )
    v2 = SkillVersion(
        id=102,
        skill_definition_id=1,
        version_number=2,
        description="Probe",
        content_hash="hash-v2",
        file_manifest_hash="manifest-v2",
        artifact_uri=v2_uri,
        source_package_version="99.0.0",
        definition=definition,
    )
    install = SkillInstall(
        id=201,
        user_id=22,
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

    install.current_version_id = 102
    install.current_version = v2
    after_manual_update = AgentRepository._active_runtime_skills(agent)

    assert public_latest_same_name_v2.name == "probe-skill"
    assert before_publish[0].skill_version_id == 101
    assert before_publish[0].version_number == 1
    assert before_publish[0].file_path == v1_uri
    assert after_publish[0].skill_version_id == 101
    assert after_manual_update[0].skill_version_id == 102
    assert after_manual_update[0].version_number == 2
    assert after_manual_update[0].file_path == v2_uri


def test_skills_max_flow_backend_truth_uses_install_manifest_and_exact_artifacts(tmp_path, monkeypatch):
    """Max-flow backend truth at the current repository/runtime/tool boundary.

    Follow-up: when route-level fixtures can create real rows for upload, publish,
    install, bind, and update, lift this into an API-backed integration test.
    """
    skills_root = tmp_path / "skills"
    v1_uri = "artifacts/skills/1/v1-aaa/probe-skill"
    v2_uri = "artifacts/skills/1/v2-bbb/probe-skill"
    public_latest_uri = "public/probe-skill"
    legacy_custom_uri = "22/probe-skill"
    same_name_root_uri = "probe-skill"
    _write_artifact(skills_root, v1_uri, "SKILL_RUNTIME_OK_V1")
    _write_artifact(skills_root, v2_uri, "SKILL_RUNTIME_OK_V2")
    _write_artifact(skills_root, public_latest_uri, "SKILL_RUNTIME_OK_V2_PUBLIC_LATEST")
    _write_artifact(skills_root, legacy_custom_uri, "SKILL_RUNTIME_OK_V2_LEGACY_CUSTOM")
    _write_artifact(skills_root, same_name_root_uri, "SKILL_RUNTIME_OK_V2_SAME_NAME_ROOT")
    monkeypatch.setattr("deerflow.config.get_app_config", lambda: _runtime_config(skills_root))

    def _fail_scan(*args, **kwargs):
        raise AssertionError("runtime resolution must use exact manifest artifact paths, not filesystem scans")

    monkeypatch.setattr(Path, "glob", _fail_scan)
    monkeypatch.setattr(Path, "rglob", _fail_scan)

    definition = SkillDefinition(id=1, name="probe-skill", description="Probe")
    v1 = SkillVersion(
        id=101,
        skill_definition_id=1,
        version_number=1,
        description="Probe v1",
        content_hash="hash-v1",
        file_manifest_hash="manifest-v1",
        artifact_uri=v1_uri,
        source_package_version=None,
        definition=definition,
    )
    v2 = SkillVersion(
        id=102,
        skill_definition_id=1,
        version_number=2,
        description="Probe v2",
        content_hash="hash-v2",
        file_manifest_hash="manifest-v2",
        artifact_uri=v2_uri,
        source_package_version=None,
        definition=definition,
    )
    release_v1 = SkillRelease(
        id=401,
        skill_name="probe-skill",
        release_version="rel-v1",
        package_version=None,
        description="Probe v1",
        release_notes="publish v1",
        status="published",
        artifact_path=v1_uri,
        publisher_user_id=11,
        skill_version_id=v1.id,
        skill_version=v1,
    )
    release_v2 = SkillRelease(
        id=402,
        skill_name="probe-skill",
        release_version="rel-v2",
        package_version=None,
        description="Probe v2",
        release_notes="publish v2",
        status="published",
        artifact_path=v2_uri,
        publisher_user_id=11,
        published_skill_id=301,
        skill_version_id=v2.id,
        skill_version=v2,
    )
    install = SkillInstall(
        id=201,
        user_id=22,
        skill_definition_id=definition.id,
        installed_version_id=v1.id,
        current_version_id=v1.id,
        definition=definition,
        installed_version=v1,
        current_version=v1,
    )
    public_latest_same_name_v2 = Skill(id=301, user_id=None, name="probe-skill", file_path=public_latest_uri)
    agent = _bound_agent_with_install(install, legacy_skill=public_latest_same_name_v2)
    agent_skill = agent.agent_skills[0]

    manifest_session = _FakeManifestSession()
    before_update_skills = AgentRepository._active_runtime_skills(agent)
    before_update_manifest = asyncio.run(
        AgentRepository._create_runtime_manifest(
            manifest_session,
            user_id=22,
            agent=agent,
            skills=before_update_skills,
        )
    )

    before_update_runtime = _runtime_for_manifest(tmp_path, before_update_manifest)
    before_update_load = _load_skill(before_update_runtime, skills_root, "/mnt/skills/probe-skill/SKILL.md")
    public_latest_denied = _load_skill(before_update_runtime, skills_root, "/mnt/skills/public/probe-skill/SKILL.md")
    legacy_custom_denied = _load_skill(before_update_runtime, skills_root, "/mnt/skills/22/probe-skill/SKILL.md")

    assert v1.version_number == 1
    assert v2.version_number == 2
    assert v1.artifact_uri == v1_uri
    assert v2.artifact_uri == v2_uri
    assert release_v1.skill_version_id == v1.id
    assert release_v2.skill_version_id == v2.id
    assert install.installed_version_id == v1.id
    assert install.current_version_id == v1.id
    assert agent_skill.skill_install_id == install.id
    assert agent_skill.skill_id == public_latest_same_name_v2.id
    assert before_update_skills[0].skill_install_id == install.id
    assert before_update_skills[0].skill_version_id == v1.id
    assert before_update_skills[0].version_number == 1
    assert before_update_skills[0].artifact_uri == v1_uri
    assert before_update_manifest.manifest_json == {
        "version": 1,
        "skills": [
            {
                "name": "probe-skill",
                "description": "Probe v1",
                "file_path": v1_uri,
                "virtual_path": "/mnt/skills/probe-skill/SKILL.md",
                "skill_definition_id": definition.id,
                "skill_version_id": v1.id,
                "skill_install_id": install.id,
                "version_number": 1,
                "content_hash": "hash-v1",
                "artifact_uri": v1_uri,
                "source_package_version": None,
            }
        ],
    }
    assert before_update_load == "SKILL_RUNTIME_OK_V1"
    assert "SKILL_RUNTIME_OK_V2_PUBLIC_LATEST" not in before_update_load
    assert "SKILL_RUNTIME_OK_V2_LEGACY_CUSTOM" not in before_update_load
    assert "SKILL_RUNTIME_OK_V2_SAME_NAME_ROOT" not in before_update_load
    assert "Permission denied" in public_latest_denied
    assert "Permission denied" in legacy_custom_denied

    # User A has published v2, but user B has not accepted an update yet.
    after_publish_skills = AgentRepository._active_runtime_skills(agent)
    assert release_v2.status == "published"
    assert release_v2.skill_version_id == v2.id
    assert install.current_version_id == v1.id
    assert after_publish_skills[0].skill_version_id == v1.id
    assert _load_skill(before_update_runtime, skills_root, "/mnt/skills/probe-skill/SKILL.md") == "SKILL_RUNTIME_OK_V1"

    install.current_version_id = v2.id
    install.current_version = v2

    after_update_skills = AgentRepository._active_runtime_skills(agent)
    after_update_manifest = asyncio.run(
        AgentRepository._create_runtime_manifest(
            manifest_session,
            user_id=22,
            agent=agent,
            skills=after_update_skills,
        )
    )
    after_update_runtime = _runtime_for_manifest(tmp_path, after_update_manifest)

    assert install.current_version_id == v2.id
    assert after_update_skills[0].skill_version_id == v2.id
    assert after_update_skills[0].version_number == 2
    assert after_update_manifest.manifest_json["skills"][0]["artifact_uri"] == v2_uri
    assert after_update_manifest.manifest_json["skills"][0]["skill_install_id"] == install.id
    assert _load_skill(after_update_runtime, skills_root, "/mnt/skills/probe-skill/SKILL.md") == "SKILL_RUNTIME_OK_V2"


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

    definition = SkillDefinition(id=1, name="probe-skill", description="Probe")
    missing = SkillVersion(
        id=101,
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
        skill_definition_id=1,
        installed_version_id=101,
        current_version_id=101,
        definition=definition,
        current_version=missing,
    )

    with pytest.raises(RuntimeManifestResolutionError, match="artifact is missing"):
        AgentRepository._active_runtime_skills(_bound_agent_with_install(install))


def test_runtime_manifest_rejects_missing_current_version(tmp_path, monkeypatch):
    skills_root = tmp_path / "skills"
    monkeypatch.setattr("deerflow.config.get_app_config", lambda: _runtime_config(skills_root))

    definition = SkillDefinition(id=1, name="probe-skill", description="Probe")
    install = SkillInstall(
        id=201,
        user_id=22,
        skill_definition_id=1,
        installed_version_id=101,
        current_version_id=None,
        definition=definition,
        current_version=None,
    )

    with pytest.raises(RuntimeManifestResolutionError, match="has no current version"):
        AgentRepository._active_runtime_skills(_bound_agent_with_install(install))


def test_runtime_manifest_rejects_version_from_another_definition(tmp_path, monkeypatch):
    skills_root = tmp_path / "skills"
    artifact_uri = "artifacts/skills/2/v1-other/probe-skill"
    _write_artifact(skills_root, artifact_uri, "wrong definition")
    monkeypatch.setattr("deerflow.config.get_app_config", lambda: _runtime_config(skills_root))

    install_definition = SkillDefinition(id=1, name="probe-skill", description="Probe")
    version_definition = SkillDefinition(id=2, name="probe-skill", description="Other Probe")
    mismatched_version = SkillVersion(
        id=101,
        skill_definition_id=2,
        version_number=1,
        description="Probe",
        content_hash="hash-v1",
        file_manifest_hash="manifest-v1",
        artifact_uri=artifact_uri,
        definition=version_definition,
    )
    install = SkillInstall(
        id=201,
        user_id=22,
        skill_definition_id=1,
        installed_version_id=101,
        current_version_id=101,
        definition=install_definition,
        current_version=mismatched_version,
    )

    with pytest.raises(RuntimeManifestResolutionError, match="version from another definition"):
        AgentRepository._active_runtime_skills(_bound_agent_with_install(install))


def test_runtime_manifest_rejects_missing_skill_md(tmp_path, monkeypatch):
    skills_root = tmp_path / "skills"
    artifact_uri = "artifacts/skills/1/v1-no-skill-md/probe-skill"
    (skills_root / artifact_uri).mkdir(parents=True)
    monkeypatch.setattr("deerflow.config.get_app_config", lambda: _runtime_config(skills_root))

    definition = SkillDefinition(id=1, name="probe-skill", description="Probe")
    version = SkillVersion(
        id=101,
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
        "public/probe-skill",
        "22/probe-skill",
        "custom/probe-skill",
        "probe-skill",
        "artifacts/../public/probe-skill",
    ],
)
def test_runtime_manifest_rejects_non_artifacts_scope_artifact_uri(tmp_path, monkeypatch, artifact_uri):
    skills_root = tmp_path / "skills"
    _write_artifact(skills_root, artifact_uri, "fallback should never authorize")
    monkeypatch.setattr("deerflow.config.get_app_config", lambda: _runtime_config(skills_root))

    definition = SkillDefinition(id=1, name="probe-skill", description="Probe")
    version = SkillVersion(
        id=101,
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
        skill_definition_id=1,
        installed_version_id=101,
        current_version_id=101,
        definition=definition,
        current_version=version,
    )

    with pytest.raises(RuntimeManifestResolutionError, match="immutable artifacts scope"):
        AgentRepository._active_runtime_skills(_bound_agent_with_install(install))


def test_skill_load_reads_manifest_artifact_and_denies_public_latest_same_name(tmp_path):
    skills_root = tmp_path / "skills"
    v1_uri = "artifacts/skills/1/v1-aaa/probe-skill"
    public_uri = "public/probe-skill"
    _write_artifact(skills_root, v1_uri, "SKILL_RUNTIME_OK_V1")
    _write_artifact(skills_root, public_uri, "SKILL_RUNTIME_OK_V2")

    runtime = SimpleNamespace(
        state={"thread_data": {"thread_id": "thread-1", "workspace_path": str(tmp_path)}},
        context={
            "runtime_agent": {
                "manifest_id": "manifest-1",
                "skills": [
                    {
                        "name": "probe-skill",
                        "artifact_uri": v1_uri,
                        "file_path": v1_uri,
                        "virtual_path": "/mnt/skills/probe-skill/SKILL.md",
                        "skill_version_id": 101,
                        "version_number": 1,
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
            path="/mnt/skills/probe-skill/SKILL.md",
        )
        denied = skill_load_tool.func(
            runtime=runtime,
            description="load public latest",
            path="/mnt/skills/public/probe-skill/SKILL.md",
        )

    assert loaded == "SKILL_RUNTIME_OK_V1"
    assert "Permission denied" in denied
