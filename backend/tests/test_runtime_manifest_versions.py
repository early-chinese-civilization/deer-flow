from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.gateway.db.models import Agent, AgentSkill, Skill, SkillDefinition, SkillInstall, SkillVersion
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


def _bound_agent_with_install(install: SkillInstall) -> Agent:
    agent = Agent(id=10, user_id=22, name="probe-agent", soul="probe")
    agent.agent_skills = [
        AgentSkill(
            id=501,
            agent_id=10,
            skill_install_id=install.id,
            display_order=0,
            enabled=True,
            skill_install=install,
        )
    ]
    return agent


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
