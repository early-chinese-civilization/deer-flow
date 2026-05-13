"""Tests for app.gateway.services — run lifecycle service layer."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest


def test_format_sse_basic():
    from app.gateway.services import format_sse

    frame = format_sse("metadata", {"run_id": "abc"})
    assert frame.startswith("event: metadata\n")
    assert "data: " in frame
    parsed = json.loads(frame.split("data: ")[1].split("\n")[0])
    assert parsed["run_id"] == "abc"


def test_format_sse_with_event_id():
    from app.gateway.services import format_sse

    frame = format_sse("metadata", {"run_id": "abc"}, event_id="123-0")
    assert "id: 123-0" in frame


def test_format_sse_end_event_null():
    from app.gateway.services import format_sse

    frame = format_sse("end", None)
    assert "data: null" in frame


def test_format_sse_no_event_id():
    from app.gateway.services import format_sse

    frame = format_sse("values", {"x": 1})
    assert "id:" not in frame


def test_normalize_stream_modes_none():
    from app.gateway.services import normalize_stream_modes

    assert normalize_stream_modes(None) == ["values"]


def test_normalize_stream_modes_string():
    from app.gateway.services import normalize_stream_modes

    assert normalize_stream_modes("messages-tuple") == ["messages-tuple"]


def test_normalize_stream_modes_list():
    from app.gateway.services import normalize_stream_modes

    assert normalize_stream_modes(["values", "messages-tuple"]) == ["values", "messages-tuple"]


def test_normalize_stream_modes_empty_list():
    from app.gateway.services import normalize_stream_modes

    assert normalize_stream_modes([]) == ["values"]


def test_normalize_input_none():
    from app.gateway.services import normalize_input

    assert normalize_input(None) == {}


def test_normalize_input_with_messages():
    from app.gateway.services import normalize_input

    result = normalize_input({"messages": [{"role": "user", "content": "hi"}]})
    assert len(result["messages"]) == 1
    assert result["messages"][0].content == "hi"


def test_normalize_input_passthrough():
    from app.gateway.services import normalize_input

    result = normalize_input({"custom_key": "value"})
    assert result == {"custom_key": "value"}


def test_build_run_config_basic():
    from app.gateway.services import build_run_config

    config = build_run_config("thread-1", None, None)
    assert config["configurable"]["thread_id"] == "thread-1"
    assert config["recursion_limit"] == 100


def test_build_run_config_with_overrides():
    from app.gateway.services import build_run_config

    config = build_run_config(
        "thread-1",
        {"configurable": {"model_name": "gpt-4"}, "tags": ["test"]},
        {"user": "alice"},
    )
    assert config["configurable"]["model_name"] == "gpt-4"
    assert config["tags"] == ["test"]
    assert config["metadata"]["user"] == "alice"


# ---------------------------------------------------------------------------
# Regression tests for issue #1644:
# assistant_id not mapped to agent_name → custom agent SOUL.md never loaded
# ---------------------------------------------------------------------------


def test_build_run_config_custom_agent_injects_agent_name():
    """Custom assistant_id must be forwarded as configurable['agent_name']."""
    from app.gateway.services import build_run_config

    config = build_run_config("thread-1", None, None, assistant_id="finalis")
    assert config["configurable"]["agent_name"] == "finalis"


def test_build_run_config_lead_agent_no_agent_name():
    """'lead_agent' assistant_id must NOT inject configurable['agent_name']."""
    from app.gateway.services import build_run_config

    config = build_run_config("thread-1", None, None, assistant_id="lead_agent")
    assert "agent_name" not in config["configurable"]


def test_build_run_config_none_assistant_id_no_agent_name():
    """None assistant_id must NOT inject configurable['agent_name']."""
    from app.gateway.services import build_run_config

    config = build_run_config("thread-1", None, None, assistant_id=None)
    assert "agent_name" not in config["configurable"]


def test_build_run_config_explicit_agent_name_not_overwritten():
    """An explicit configurable['agent_name'] in the request must take precedence."""
    from app.gateway.services import build_run_config

    config = build_run_config(
        "thread-1",
        {"configurable": {"agent_name": "explicit-agent"}},
        None,
        assistant_id="other-agent",
    )
    assert config["configurable"]["agent_name"] == "explicit-agent"


def test_build_run_config_injects_agent_name_even_when_request_uses_context():
    """Custom assistant selection must survive LangGraph's context-first request shape."""
    from app.gateway.services import build_run_config

    config = build_run_config(
        "thread-1",
        {"context": {"model_name": "gpt-4"}},
        None,
        assistant_id="trusted-agent",
    )

    assert config["context"]["model_name"] == "gpt-4"
    assert config["configurable"]["agent_name"] == "trusted-agent"


def test_build_run_config_promotes_context_agent_name_for_lead_agent_requests():
    """Frontend custom-agent chats still send lead_agent plus context.agent_name."""
    from app.gateway.services import build_run_config

    config = build_run_config(
        "thread-1",
        {"context": {"model_name": "gpt-4", "agent_name": "VIP_AGENT"}},
        None,
        assistant_id="lead_agent",
    )

    assert config["context"]["agent_name"] == "VIP_AGENT"
    assert config["configurable"]["agent_name"] == "vip-agent"


def test_build_run_config_blocks_runtime_only_configurable_keys():
    """Gateway callers must not inject runtime-only configurable flags."""
    from app.gateway.services import build_run_config

    config = build_run_config(
        "thread-1",
        {
            "configurable": {
                "is_bootstrap": True,
                "__pregel_runtime": "spoofed",
                "model_name": "gpt-4",
            }
        },
        None,
    )

    assert config["configurable"]["model_name"] == "gpt-4"
    assert "is_bootstrap" not in config["configurable"]
    assert "__pregel_runtime" not in config["configurable"]


def test_resolve_agent_factory_returns_make_lead_agent():
    """resolve_agent_factory always returns make_lead_agent regardless of assistant_id."""
    from app.gateway.services import resolve_agent_factory
    from deerflow.agents.lead_agent.agent import make_lead_agent

    assert resolve_agent_factory(None) is make_lead_agent
    assert resolve_agent_factory("lead_agent") is make_lead_agent
    assert resolve_agent_factory("finalis") is make_lead_agent
    assert resolve_agent_factory("custom-agent-123") is make_lead_agent


# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Regression tests for issue #1699:
# context field in langgraph-compat requests not merged into configurable
# ---------------------------------------------------------------------------


def test_run_create_request_accepts_context():
    """RunCreateRequest must accept the ``context`` field without dropping it."""
    from app.gateway.routers.thread_runs import RunCreateRequest

    body = RunCreateRequest(
        input={"messages": [{"role": "user", "content": "hi"}]},
        context={
            "model_name": "deepseek-v3",
            "thinking_enabled": True,
            "is_plan_mode": True,
            "subagent_enabled": True,
            "thread_id": "some-thread-id",
        },
    )
    assert body.context is not None
    assert body.context["model_name"] == "deepseek-v3"
    assert body.context["is_plan_mode"] is True
    assert body.context["subagent_enabled"] is True


def test_run_create_request_context_defaults_to_none():
    """RunCreateRequest without context should default to None (backward compat)."""
    from app.gateway.routers.thread_runs import RunCreateRequest

    body = RunCreateRequest(input=None)
    assert body.context is None


def test_context_merges_into_configurable():
    """Context values must be merged into config['configurable'] by start_run.

    Since start_run is async and requires many dependencies, we test the
    merging logic directly by simulating what start_run does.
    """
    from app.gateway.services import build_run_config

    # Simulate the context merging logic from start_run
    config = build_run_config("thread-1", None, None)

    context = {
        "model_name": "deepseek-v3",
        "mode": "ultra",
        "reasoning_effort": "high",
        "thinking_enabled": True,
        "is_plan_mode": True,
        "subagent_enabled": True,
        "max_concurrent_subagents": 5,
        "thread_id": "should-be-ignored",
    }

    _CONTEXT_CONFIGURABLE_KEYS = {
        "model_name",
        "mode",
        "thinking_enabled",
        "reasoning_effort",
        "is_plan_mode",
        "subagent_enabled",
        "max_concurrent_subagents",
    }
    configurable = config.setdefault("configurable", {})
    for key in _CONTEXT_CONFIGURABLE_KEYS:
        if key in context:
            configurable.setdefault(key, context[key])

    assert config["configurable"]["model_name"] == "deepseek-v3"
    assert config["configurable"]["thinking_enabled"] is True
    assert config["configurable"]["is_plan_mode"] is True
    assert config["configurable"]["subagent_enabled"] is True
    assert config["configurable"]["max_concurrent_subagents"] == 5
    assert config["configurable"]["reasoning_effort"] == "high"
    assert config["configurable"]["mode"] == "ultra"
    # thread_id from context should NOT override the one from build_run_config
    assert config["configurable"]["thread_id"] == "thread-1"
    # Non-allowlisted keys should not appear
    assert "thread_id" not in {k for k in context if k in _CONTEXT_CONFIGURABLE_KEYS}


def test_context_does_not_override_existing_configurable():
    """Values already in config.configurable must NOT be overridden by context."""
    from app.gateway.services import build_run_config

    config = build_run_config(
        "thread-1",
        {"configurable": {"model_name": "gpt-4", "is_plan_mode": False}},
        None,
    )

    context = {
        "model_name": "deepseek-v3",
        "is_plan_mode": True,
        "subagent_enabled": True,
    }

    _CONTEXT_CONFIGURABLE_KEYS = {
        "model_name",
        "mode",
        "thinking_enabled",
        "reasoning_effort",
        "is_plan_mode",
        "subagent_enabled",
        "max_concurrent_subagents",
    }
    configurable = config.setdefault("configurable", {})
    for key in _CONTEXT_CONFIGURABLE_KEYS:
        if key in context:
            configurable.setdefault(key, context[key])

    # Existing values must NOT be overridden
    assert config["configurable"]["model_name"] == "gpt-4"
    assert config["configurable"]["is_plan_mode"] is False
    # New values should be added
    assert config["configurable"]["subagent_enabled"] is True


# ---------------------------------------------------------------------------
# build_run_config — context / configurable precedence (LangGraph >= 0.6.0)
# ---------------------------------------------------------------------------


def test_build_run_config_with_context():
    """When caller sends 'context', prefer it over 'configurable'."""
    from app.gateway.services import build_run_config

    config = build_run_config(
        "thread-1",
        {"context": {"user_id": "u-42", "thread_id": "thread-1"}},
        None,
    )
    assert "context" in config
    assert config["context"]["user_id"] == "u-42"
    assert "configurable" not in config
    assert config["recursion_limit"] == 100


def test_build_run_config_context_plus_configurable_warns(caplog):
    """When caller sends both 'context' and 'configurable', prefer 'context' and log a warning."""
    import logging

    from app.gateway.services import build_run_config

    with caplog.at_level(logging.WARNING, logger="app.gateway.services"):
        config = build_run_config(
            "thread-1",
            {
                "context": {"user_id": "u-42"},
                "configurable": {"model_name": "gpt-4"},
            },
            None,
        )
    assert "context" in config
    assert config["context"]["user_id"] == "u-42"
    assert "configurable" not in config
    assert any("both 'context' and 'configurable'" in r.message for r in caplog.records)


def test_build_run_config_context_passthrough_other_keys():
    """Non-conflicting keys from request_config are still passed through when context is used."""
    from app.gateway.services import build_run_config

    config = build_run_config(
        "thread-1",
        {"context": {"thread_id": "thread-1"}, "tags": ["prod"]},
        None,
    )
    assert config["context"]["thread_id"] == "thread-1"
    assert "configurable" not in config
    assert config["tags"] == ["prod"]


def test_build_run_config_no_request_config():
    """When request_config is None, fall back to basic configurable with thread_id."""
    from app.gateway.services import build_run_config

    config = build_run_config("thread-abc", None, None)
    assert config["configurable"] == {"thread_id": "thread-abc"}
    assert "context" not in config


def test_resolve_requested_agent_name_prefers_context():
    from app.gateway.services.runtime import _resolve_requested_agent_name

    body = SimpleNamespace(
        context={"agent_name": "Planner-Agent"},
        config={"configurable": {"agent_name": "fallback-agent"}},
    )

    assert _resolve_requested_agent_name(body) == "planner-agent"


def test_resolve_requested_agent_name_falls_back_to_configurable():
    from app.gateway.services.runtime import _resolve_requested_agent_name

    body = SimpleNamespace(
        context=None,
        config={"configurable": {"agent_name": "Research-Agent"}},
    )

    assert _resolve_requested_agent_name(body) == "research-agent"


@pytest.mark.anyio
async def test_runtime_agent_bundle_without_agent_name_does_not_fallback_to_public_skills(monkeypatch):
    from app.gateway.db.repository import AgentRepository

    fake_db = object()
    monkeypatch.setattr(
        "app.gateway.db.repository.MemoryRepository.get_memory_by_user_id",
        AsyncMock(return_value=SimpleNamespace(memory_json={"facts": []})),
    )
    monkeypatch.setattr(
        "deerflow.config.get_app_config",
        lambda: SimpleNamespace(default_chat=SimpleNamespace(system_skills=[])),
    )

    bundle = await AgentRepository.get_runtime_agent_bundle(fake_db, user_id=9, agent_name=None)

    assert bundle.user_id == 9
    assert bundle.agent_name is None
    assert bundle.skills == []


@pytest.mark.anyio
async def test_runtime_agent_bundle_without_agent_name_loads_default_chat_system_skills(tmp_path, monkeypatch):
    from app.gateway.db.models import INTERNAL_SYSTEM_EXTERNAL_AUTH_ID, Skill, SkillDefinition, SkillVersion, User
    from app.gateway.db.repository import AgentRepository
    from deerflow.skills.hashing import hash_skill_file_manifest

    skill_id = uuid4()
    terminal_relative_path = f"{skill_id}/1"
    artifact_dir = tmp_path / "skills" / terminal_relative_path
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "SKILL.md").write_text("DEFAULT_CHAT_SYSTEM_SKILL", encoding="utf-8")
    file_manifest_hash = hash_skill_file_manifest(artifact_dir)
    system_user = User(id=1, external_auth_id=INTERNAL_SYSTEM_EXTERNAL_AUTH_ID, username="system", display_name="System")
    terminal_skill = Skill(id=skill_id, owner_user_id=system_user.id, name="system-skill", owner_user=system_user)
    definition = SkillDefinition(
        id=10,
        name="system-skill",
        description="System skill",
        owner_user_id=system_user.id,
        owner_user=system_user,
    )
    version = SkillVersion(
        id=101,
        skill_id=skill_id,
        skill=terminal_skill,
        skill_definition_id=definition.id,
        definition=definition,
        version_number=1,
        description="System skill",
        content_hash="content-hash",
        file_manifest_hash=file_manifest_hash,
        artifact_uri="artifacts/skills/10/v1/system-skill",
    )

    class _FakeDb:
        def add(self, value):
            raise AssertionError(f"default chat must not create rows: {value!r}")

    async def get_by_skill_version(_db, *, skill_id: str, version_number: int):
        assert skill_id == version.skill_id
        assert version_number == version.version_number
        return version

    monkeypatch.setattr(
        "app.gateway.db.repository.MemoryRepository.get_memory_by_user_id",
        AsyncMock(return_value=SimpleNamespace(memory_json={"facts": []})),
    )
    monkeypatch.setattr(
        "app.gateway.db.repository.SkillVersionRepository.get_by_skill_version",
        get_by_skill_version,
    )
    monkeypatch.setattr(
        "deerflow.config.get_app_config",
        lambda: SimpleNamespace(
            default_chat=SimpleNamespace(system_skills=[SimpleNamespace(skill_id=skill_id, version_number=1)]),
            skills=SimpleNamespace(container_path="/mnt/skills", get_skills_path=lambda: tmp_path / "skills"),
        ),
    )

    bundle = await AgentRepository.get_runtime_agent_bundle(_FakeDb(), user_id=9, agent_name=None)

    assert bundle.agent_name is None
    assert bundle.manifest_id is None
    assert bundle.skills[0].name == "system-skill"
    assert bundle.skills[0].skill_id == str(skill_id)
    assert bundle.skills[0].version_number == 1
    assert bundle.skills[0].file_manifest_hash == file_manifest_hash
    assert bundle.skills[0].virtual_path == f"/mnt/skills/system-skill--{skill_id}-v1/SKILL.md"
    assert not hasattr(bundle.skills[0], "artifact_uri")
    assert not hasattr(bundle.skills[0], "file_path")
    assert not hasattr(bundle.skills[0], "skill_version_id")


@pytest.mark.anyio
async def test_runtime_agent_payload_serializes_terminal_skill_descriptor(monkeypatch):
    from app.gateway.db.repository import RuntimeAgentBundle, RuntimeSkillDescriptor
    from app.gateway.services.runtime import _load_runtime_agent_payload

    skill_id = str(uuid4())
    descriptor = RuntimeSkillDescriptor(
        name="probe-skill",
        description="Probe description",
        skill_id=skill_id,
        version_number=2,
        file_manifest_hash="manifest-hash",
        virtual_path=f"/mnt/skills/probe-skill--{skill_id}-v2/SKILL.md",
    )
    bundle = RuntimeAgentBundle(
        user_id=9,
        agent_name="probe-agent",
        memory_json={"facts": []},
        soul="Probe soul",
        skills=[descriptor],
        manifest_id="manifest-id",
        manifest_hash="manifest-hash",
    )
    db = SimpleNamespace(commit=AsyncMock())

    class _Session:
        async def __aenter__(self):
            return db

        async def __aexit__(self, exc_type, exc, tb):
            return None

    monkeypatch.setattr("app.gateway.services.runtime.get_db_session", lambda: _Session())
    monkeypatch.setattr("app.gateway.services.runtime.AgentRepository.get_runtime_agent_bundle", AsyncMock(return_value=bundle))

    payload = await _load_runtime_agent_payload(user_id=9, agent_name="probe-agent")

    assert payload["skills"] == [
        {
            "name": "probe-skill",
            "description": "Probe description",
            "skill_id": skill_id,
            "version_number": 2,
            "file_manifest_hash": "manifest-hash",
            "virtual_path": f"/mnt/skills/probe-skill--{skill_id}-v2/SKILL.md",
        }
    ]
    assert "manifest_id" in payload
    assert "artifact_uri" not in payload["skills"][0]
    assert "file_path" not in payload["skills"][0]
    assert "skill_version_id" not in payload["skills"][0]


@pytest.mark.anyio
async def test_runtime_agent_bundle_uses_install_composite_identity_not_current_version_id(tmp_path, monkeypatch):
    from app.gateway.db.models import Agent, AgentSkill, Skill, SkillDefinition, SkillInstall, SkillVersion, User
    from app.gateway.db.repository import AgentRepository
    from deerflow.skills.hashing import hash_skill_file_manifest

    skill_id = uuid4()
    terminal_v2_dir = tmp_path / "skills" / str(skill_id) / "2"
    terminal_v2_dir.mkdir(parents=True)
    (terminal_v2_dir / "SKILL.md").write_text("TERMINAL_V2", encoding="utf-8")
    v2_file_manifest_hash = hash_skill_file_manifest(terminal_v2_dir)

    owner = User(id=22, external_auth_id="user-22", username="owner", display_name="Owner")
    terminal_skill = Skill(id=skill_id, owner_user_id=owner.id, name="probe-skill", owner_user=owner)
    definition = SkillDefinition(id=10, name="probe-skill", description="Probe")
    stale_v1 = SkillVersion(
        id=101,
        skill_id=skill_id,
        skill=terminal_skill,
        skill_definition_id=definition.id,
        definition=definition,
        version_number=1,
        description="Probe v1",
        content_hash="hash-v1",
        file_manifest_hash="stale-hash",
        artifact_uri="artifacts/skills/10/v1/probe-skill",
    )
    terminal_v2 = SkillVersion(
        id=102,
        skill_id=skill_id,
        skill=terminal_skill,
        skill_definition_id=definition.id,
        definition=definition,
        version_number=2,
        description="Probe v2",
        content_hash="hash-v2",
        file_manifest_hash=v2_file_manifest_hash,
        artifact_uri="artifacts/skills/10/v2/probe-skill",
    )
    install = SkillInstall(
        id=201,
        user_id=22,
        skill_id=skill_id,
        skill=terminal_skill,
        version_number=2,
        status="active",
        skill_definition_id=definition.id,
        installed_version_id=101,
        current_version_id=101,
        definition=definition,
        current_version=stale_v1,
    )
    agent = Agent(id=501, user_id=22, name="probe-agent", soul="probe")
    agent.agent_skills = [AgentSkill(id=601, agent_id=agent.id, skill_install_id=install.id, skill_install=install, display_order=0, enabled=True)]

    monkeypatch.setattr("app.gateway.db.repository.MemoryRepository.get_memory_by_user_id", AsyncMock(return_value=None))
    monkeypatch.setattr("app.gateway.db.repository.AgentRepository.get_agent_by_name", AsyncMock(return_value=agent))
    monkeypatch.setattr("app.gateway.db.repository.SkillVersionRepository.get_by_skill_version", AsyncMock(return_value=terminal_v2))
    monkeypatch.setattr(
        "deerflow.config.get_app_config",
        lambda: SimpleNamespace(skills=SimpleNamespace(container_path="/mnt/skills", get_skills_path=lambda: tmp_path / "skills")),
    )

    class _FakeDb:
        def __init__(self):
            self.added = []

        def add(self, value):
            self.added.append(value)

        async def flush(self):
            for value in self.added:
                value.id = uuid4()

        async def refresh(self, value):
            return None

    bundle = await AgentRepository.get_runtime_agent_bundle(_FakeDb(), user_id=22, agent_name="probe-agent")

    assert bundle.skills[0].skill_id == str(skill_id)
    assert bundle.skills[0].version_number == 2
    assert bundle.skills[0].file_manifest_hash == v2_file_manifest_hash
    assert bundle.skills[0].description == "Probe v2"


@pytest.mark.anyio
async def test_runtime_agent_bundle_rejects_legacy_artifacts_root_when_terminal_root_missing(tmp_path, monkeypatch):
    from app.gateway.db.models import Agent, AgentSkill, Skill, SkillDefinition, SkillInstall, SkillVersion, User
    from app.gateway.db.repository import AgentRepository, RuntimeManifestResolutionError
    from deerflow.skills.hashing import hash_skill_file_manifest

    skill_id = uuid4()
    legacy_artifact_dir = tmp_path / "skills" / "artifacts" / "skills" / "10" / "v1" / "probe-skill"
    legacy_artifact_dir.mkdir(parents=True)
    (legacy_artifact_dir / "SKILL.md").write_text("LEGACY_ONLY", encoding="utf-8")
    legacy_hash = hash_skill_file_manifest(legacy_artifact_dir)

    owner = User(id=22, external_auth_id="user-22", username="owner", display_name="Owner")
    terminal_skill = Skill(id=skill_id, owner_user_id=owner.id, name="probe-skill", owner_user=owner)
    definition = SkillDefinition(id=10, name="probe-skill", description="Probe")
    version = SkillVersion(
        id=101,
        skill_id=skill_id,
        skill=terminal_skill,
        skill_definition_id=definition.id,
        definition=definition,
        version_number=1,
        description="Probe v1",
        content_hash="hash-v1",
        file_manifest_hash=legacy_hash,
        artifact_uri="artifacts/skills/10/v1/probe-skill",
    )
    install = SkillInstall(
        id=201,
        user_id=22,
        skill_id=skill_id,
        skill=terminal_skill,
        version_number=1,
        status="active",
        skill_definition_id=definition.id,
        installed_version_id=101,
        current_version_id=101,
        definition=definition,
        current_version=version,
    )
    agent = Agent(id=501, user_id=22, name="probe-agent", soul="probe")
    agent.agent_skills = [AgentSkill(id=601, agent_id=agent.id, skill_install_id=install.id, skill_install=install, display_order=0, enabled=True)]

    monkeypatch.setattr("app.gateway.db.repository.MemoryRepository.get_memory_by_user_id", AsyncMock(return_value=None))
    monkeypatch.setattr("app.gateway.db.repository.AgentRepository.get_agent_by_name", AsyncMock(return_value=agent))
    monkeypatch.setattr("app.gateway.db.repository.SkillVersionRepository.get_by_skill_version", AsyncMock(return_value=version))
    monkeypatch.setattr(
        "deerflow.config.get_app_config",
        lambda: SimpleNamespace(skills=SimpleNamespace(container_path="/mnt/skills", get_skills_path=lambda: tmp_path / "skills")),
    )

    with pytest.raises(RuntimeManifestResolutionError, match="terminal storage root is missing"):
        await AgentRepository.get_runtime_agent_bundle(SimpleNamespace(), user_id=22, agent_name="probe-agent")


@pytest.mark.anyio
async def test_runtime_agent_bundle_missing_agent_hard_fails(monkeypatch):
    from app.gateway.db.repository import AgentRepository, RuntimeManifestResolutionError

    fake_db = object()
    monkeypatch.setattr(
        "app.gateway.db.repository.MemoryRepository.get_memory_by_user_id",
        AsyncMock(return_value=SimpleNamespace(memory_json={"facts": []})),
    )
    monkeypatch.setattr(
        AgentRepository,
        "get_agent_by_name",
        AsyncMock(return_value=None),
    )
    with pytest.raises(RuntimeManifestResolutionError, match="ghost-agent"):
        await AgentRepository.get_runtime_agent_bundle(fake_db, user_id=9, agent_name="ghost-agent")


@pytest.mark.anyio
async def test_sync_thread_product_state_after_run_updates_store_and_db_thread_status_and_title(monkeypatch):
    from app.gateway.services.runtime import _sync_thread_product_state_after_run
    from deerflow.runtime import RunStatus

    thread_id = str(uuid4())
    workspace_id = str(uuid4())
    completed_task = asyncio.get_running_loop().create_future()
    completed_task.set_result(None)
    record = SimpleNamespace(thread_id=thread_id, status=RunStatus.success)
    checkpoint_tuple = SimpleNamespace(
        config={"configurable": {"thread_id": thread_id, "checkpoint_id": "ckpt-3"}},
        checkpoint={"channel_values": {"title": "Projected title", "messages": []}},
        metadata={},
        parent_config=None,
        pending_writes=[],
    )

    class _SessionContext:
        async def __aenter__(self):
            return SimpleNamespace()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr("app.gateway.services.runtime.get_db_session", lambda: _SessionContext())
    upsert_thread_record_mock = AsyncMock()
    update_thread_mock = AsyncMock()
    sync_workspace_mock = AsyncMock()
    monkeypatch.setattr("app.gateway.services.runtime.upsert_thread_record", upsert_thread_record_mock)
    monkeypatch.setattr("app.gateway.services.runtime.ThreadRepository.update_thread", update_thread_mock)
    monkeypatch.setattr("app.gateway.services.runtime._sync_thread_workspace_to_bound_workspace", sync_workspace_mock)

    await _sync_thread_product_state_after_run(
        completed_task,
        record,
        SimpleNamespace(aget_tuple=AsyncMock(return_value=checkpoint_tuple)),
        SimpleNamespace(),
        sync_thread_metadata=True,
        workspace_id=workspace_id,
    )

    upsert_thread_record_mock.assert_awaited_once()
    assert upsert_thread_record_mock.await_args.kwargs["thread_id"] == thread_id
    assert upsert_thread_record_mock.await_args.kwargs["status"] == "idle"
    assert upsert_thread_record_mock.await_args.kwargs["values"] == {"title": "Projected title"}
    update_thread_mock.assert_awaited_once()
    assert update_thread_mock.await_args.kwargs["thread_id"] == thread_id
    assert update_thread_mock.await_args.kwargs["status"] == "idle"
    assert update_thread_mock.await_args.kwargs["title"] == "Projected title"
    sync_workspace_mock.assert_awaited_once_with(thread_id=thread_id, workspace_id=workspace_id)


@pytest.mark.anyio
async def test_start_run_marks_store_busy_before_db_mirror(monkeypatch):
    from app.gateway.services.runtime import start_run
    from deerflow.runtime import DisconnectMode, RunStatus

    thread = SimpleNamespace(
        thread_id="thread-1",
        workspace_id=uuid4(),
    )
    body = SimpleNamespace(
        on_disconnect="cancel",
        assistant_id=None,
        metadata={"source": "ui"},
        input={"messages": [{"role": "user", "content": "hi"}]},
        config=None,
        multitask_strategy="reject",
        stream_mode=None,
        stream_subgraphs=False,
        interrupt_before=None,
        interrupt_after=None,
    )
    bridge = SimpleNamespace()
    checkpointer = SimpleNamespace()
    store = SimpleNamespace()
    record = SimpleNamespace(
        run_id="run-1",
        thread_id="thread-1",
        assistant_id=None,
        status=RunStatus.pending,
        metadata={},
        kwargs={},
        multitask_strategy="reject",
        created_at="",
        updated_at="",
        on_disconnect=DisconnectMode.cancel,
        task=None,
    )
    run_mgr = SimpleNamespace(create_or_reject=AsyncMock(return_value=record))
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                stream_bridge=bridge,
                run_manager=run_mgr,
                checkpointer=checkpointer,
                store=store,
            )
        )
    )

    async def _run_agent(*args, **kwargs):
        return None

    sync_after_run_mock = AsyncMock(return_value=None)
    sync_workspace_mock = AsyncMock(return_value=None)
    upsert_thread_record_mock = AsyncMock(return_value=None)
    update_thread_mock = AsyncMock(return_value=None)

    monkeypatch.setattr("app.gateway.services.runtime.run_agent", _run_agent)
    monkeypatch.setattr("app.gateway.services.runtime._sync_thread_product_state_after_run", sync_after_run_mock)
    monkeypatch.setattr("app.gateway.services.runtime._sync_bound_workspace_to_thread", sync_workspace_mock)
    monkeypatch.setattr("app.gateway.services.runtime.upsert_thread_record", upsert_thread_record_mock)
    monkeypatch.setattr("app.gateway.services.runtime.ThreadRepository.update_thread", update_thread_mock)
    monkeypatch.setattr(
        "app.gateway.services.runtime._load_runtime_agent_payload",
        AsyncMock(return_value={"user_id": 7, "agent_name": None, "memory": {}, "soul": None, "skills": []}),
    )

    await start_run(
        body,
        "thread-1",
        request,
        current_user=SimpleNamespace(id=7),
        thread_record=thread,
    )
    await asyncio.sleep(0)

    upsert_thread_record_mock.assert_awaited_once()
    assert upsert_thread_record_mock.await_args.kwargs["thread_id"] == "thread-1"
    assert upsert_thread_record_mock.await_args.kwargs["status"] == "busy"
    assert upsert_thread_record_mock.await_args.kwargs["metadata"] == {"source": "ui"}
    update_thread_mock.assert_awaited_once()
    assert update_thread_mock.await_args.kwargs["thread_id"] == "thread-1"
    assert update_thread_mock.await_args.kwargs["status"] == "busy"
    assert update_thread_mock.await_args.kwargs["metadata"] == {"source": "ui"}
    sync_workspace_mock.assert_awaited_once_with(
        thread_id="thread-1",
        workspace_id=str(thread.workspace_id),
    )


@pytest.mark.anyio
async def test_start_run_binds_thread_agent_id_from_resolved_agent_name(monkeypatch):
    from app.gateway.services.runtime import start_run
    from deerflow.runtime import DisconnectMode, RunStatus

    thread = SimpleNamespace(
        thread_id="thread-1",
        workspace_id=uuid4(),
    )
    body = SimpleNamespace(
        on_disconnect="cancel",
        assistant_id="lead_agent",
        metadata=None,
        input={"messages": [{"role": "user", "content": "hi"}]},
        config=None,
        context={"agent_name": "shiz"},
        multitask_strategy="reject",
        stream_mode=None,
        stream_subgraphs=False,
        interrupt_before=None,
        interrupt_after=None,
    )
    bridge = SimpleNamespace()
    checkpointer = SimpleNamespace()
    store = SimpleNamespace()
    record = SimpleNamespace(
        run_id="run-1",
        thread_id="thread-1",
        assistant_id=None,
        status=RunStatus.pending,
        metadata={},
        kwargs={},
        multitask_strategy="reject",
        created_at="",
        updated_at="",
        on_disconnect=DisconnectMode.cancel,
        task=None,
    )
    run_mgr = SimpleNamespace(create_or_reject=AsyncMock(return_value=record))
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                stream_bridge=bridge,
                run_manager=run_mgr,
                checkpointer=checkpointer,
                store=store,
            )
        )
    )

    async def _run_agent(*args, **kwargs):
        return None

    monkeypatch.setattr("app.gateway.services.runtime.run_agent", _run_agent)
    monkeypatch.setattr("app.gateway.services.runtime._sync_thread_product_state_after_run", AsyncMock(return_value=None))
    monkeypatch.setattr("app.gateway.services.runtime._sync_bound_workspace_to_thread", AsyncMock(return_value=None))
    monkeypatch.setattr(
        "app.gateway.services.runtime._load_runtime_agent_payload",
        AsyncMock(return_value={"user_id": 7, "agent_name": "vip-agent", "memory": {}, "soul": None, "skills": []}),
    )
    monkeypatch.setattr(
        "app.gateway.services.runtime._load_runtime_agent_payload",
        AsyncMock(return_value={"user_id": 7, "agent_name": "trusted-agent", "memory": {}, "soul": None, "skills": []}),
    )
    monkeypatch.setattr("app.gateway.services.runtime._load_runtime_agent_payload", AsyncMock(return_value={}))
    monkeypatch.setattr("app.gateway.services.runtime.upsert_thread_record", AsyncMock(return_value=None))
    update_thread_mock = AsyncMock(return_value=None)
    monkeypatch.setattr("app.gateway.services.runtime.ThreadRepository.update_thread", update_thread_mock)
    get_agent_by_name_mock = AsyncMock(return_value=SimpleNamespace(id=42, name="shiz"))
    monkeypatch.setattr("app.gateway.services.runtime.AgentRepository.get_agent_by_name", get_agent_by_name_mock)

    await start_run(
        body,
        "thread-1",
        request,
        thread_record=thread,
        current_user=SimpleNamespace(id=7),
    )
    await asyncio.sleep(0)

    get_agent_by_name_mock.assert_awaited_once()
    assert get_agent_by_name_mock.await_args.kwargs["user_id"] == 7
    assert get_agent_by_name_mock.await_args.kwargs["name"] == "shiz"
    assert update_thread_mock.await_args.kwargs["thread_id"] == "thread-1"
    assert update_thread_mock.await_args.kwargs["status"] == "busy"
    assert update_thread_mock.await_args.kwargs["agent_id"] == 42
    assert update_thread_mock.await_args.kwargs["metadata"] == {"agent_name": "shiz"}


@pytest.mark.anyio
async def test_start_run_overwrites_client_identity_context(monkeypatch):
    from app.gateway.services.runtime import start_run
    from deerflow.runtime import DisconnectMode, RunStatus

    body = SimpleNamespace(
        on_disconnect="cancel",
        assistant_id="trusted-agent",
        metadata=None,
        input={"messages": [{"role": "user", "content": "hi"}]},
        config={
            "context": {
                "thread_id": "evil-thread",
                "user_id": "evil-user",
                "external_auth_id": "evil-sub",
                "agent_name": "evil-agent",
            },
        },
        context={
            "model_name": "gpt-4",
            "is_plan_mode": True,
        },
        multitask_strategy="reject",
        stream_mode=None,
        stream_subgraphs=False,
        interrupt_before=None,
        interrupt_after=None,
    )
    record = SimpleNamespace(
        run_id="run-1",
        thread_id="thread-1",
        assistant_id=None,
        status=RunStatus.pending,
        metadata={},
        kwargs={},
        multitask_strategy="reject",
        created_at="",
        updated_at="",
        on_disconnect=DisconnectMode.cancel,
        task=None,
    )
    run_mgr = SimpleNamespace(create_or_reject=AsyncMock(return_value=record))
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                stream_bridge=SimpleNamespace(),
                run_manager=run_mgr,
                checkpointer=SimpleNamespace(),
                store=SimpleNamespace(),
            )
        )
    )
    captured: dict[str, object] = {}

    async def _run_agent(*args, **kwargs):
        captured["config"] = kwargs["config"]

    monkeypatch.setattr("app.gateway.services.runtime.run_agent", _run_agent)
    monkeypatch.setattr("app.gateway.services.runtime._sync_thread_product_state_after_run", AsyncMock(return_value=None))
    monkeypatch.setattr("app.gateway.services.runtime._sync_bound_workspace_to_thread", AsyncMock(return_value=None))
    monkeypatch.setattr(
        "app.gateway.services.runtime._load_runtime_agent_payload",
        AsyncMock(return_value={"user_id": 7, "agent_name": "vip-agent", "memory": {}, "soul": None, "skills": []}),
    )
    monkeypatch.setattr(
        "app.gateway.services.runtime._load_runtime_agent_payload",
        AsyncMock(return_value={"user_id": 7, "agent_name": "vip-agent", "memory": {}, "soul": None, "skills": []}),
    )

    await start_run(
        body,
        "thread-1",
        request,
        thread_record=None,
        current_user=SimpleNamespace(
            id=7,
            external_auth_id="kc-sub",
            username="alice",
            display_name="Alice",
            email="alice@example.com",
        ),
    )
    await asyncio.sleep(0)

    config = captured["config"]
    assert config["context"]["thread_id"] == "thread-1"
    assert config["context"]["user_id"] == "7"
    assert config["context"]["external_auth_id"] == "kc-sub"
    assert config["context"]["username"] == "alice"
    assert "agent_name" not in config["context"]
    assert config["configurable"]["thread_id"] == "thread-1"
    assert config["configurable"]["agent_name"] == "trusted-agent"
    assert config["configurable"]["model_name"] == "gpt-4"
    assert config["configurable"]["is_plan_mode"] is True
    assert "is_bootstrap" not in config["configurable"]


@pytest.mark.anyio
async def test_start_run_stores_sanitized_public_config_in_run_record(monkeypatch):
    from app.gateway.services.runtime import start_run
    from deerflow.runtime import DisconnectMode, RunStatus

    body = SimpleNamespace(
        on_disconnect="cancel",
        assistant_id="trusted-agent",
        metadata={"source": "ui"},
        input={"messages": [{"role": "user", "content": "hi"}]},
        config={
            "context": {
                "thread_id": "evil-thread",
                "user_id": "evil-user",
                "external_auth_id": "evil-sub",
                "model_name": "gpt-4",
            },
        },
        context=None,
        multitask_strategy="reject",
        stream_mode=None,
        stream_subgraphs=False,
        interrupt_before=None,
        interrupt_after=None,
    )
    record = SimpleNamespace(
        run_id="run-1",
        thread_id="thread-1",
        assistant_id=None,
        status=RunStatus.pending,
        metadata={},
        kwargs={},
        multitask_strategy="reject",
        created_at="",
        updated_at="",
        on_disconnect=DisconnectMode.cancel,
        task=None,
    )
    run_mgr = SimpleNamespace(create_or_reject=AsyncMock(return_value=record))
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                stream_bridge=SimpleNamespace(),
                run_manager=run_mgr,
                checkpointer=SimpleNamespace(),
                store=SimpleNamespace(),
            )
        )
    )

    async def _run_agent(*args, **kwargs):
        return None

    monkeypatch.setattr("app.gateway.services.runtime.run_agent", _run_agent)
    monkeypatch.setattr("app.gateway.services.runtime._sync_thread_product_state_after_run", AsyncMock(return_value=None))
    monkeypatch.setattr("app.gateway.services.runtime._sync_bound_workspace_to_thread", AsyncMock(return_value=None))
    monkeypatch.setattr(
        "app.gateway.services.runtime._load_runtime_agent_payload",
        AsyncMock(return_value={"user_id": 7, "agent_name": "vip-agent", "memory": {}, "soul": None, "skills": []}),
    )

    await start_run(
        body,
        "thread-1",
        request,
        current_user=SimpleNamespace(
            id=7,
            external_auth_id="kc-sub",
            username="alice",
            display_name="Alice",
            email="alice@example.com",
        ),
    )
    await asyncio.sleep(0)

    stored_config = run_mgr.create_or_reject.await_args.kwargs["kwargs"]["config"]
    assert stored_config == {
        "context": {"model_name": "gpt-4"},
        "configurable": {"agent_name": "trusted-agent"},
        "metadata": {"source": "ui"},
        "recursion_limit": 100,
    }


@pytest.mark.anyio
async def test_start_run_keeps_custom_agent_selection_from_context(monkeypatch):
    from app.gateway.services.runtime import start_run
    from deerflow.runtime import DisconnectMode, RunStatus

    body = SimpleNamespace(
        on_disconnect="cancel",
        assistant_id="lead_agent",
        metadata=None,
        input={"messages": [{"role": "user", "content": "hi"}]},
        config={"context": {"agent_name": "VIP_AGENT", "model_name": "gpt-4"}},
        context=None,
        multitask_strategy="reject",
        stream_mode=None,
        stream_subgraphs=False,
        interrupt_before=None,
        interrupt_after=None,
    )
    record = SimpleNamespace(
        run_id="run-1",
        thread_id="thread-1",
        assistant_id=None,
        status=RunStatus.pending,
        metadata={},
        kwargs={},
        multitask_strategy="reject",
        created_at="",
        updated_at="",
        on_disconnect=DisconnectMode.cancel,
        task=None,
    )
    run_mgr = SimpleNamespace(create_or_reject=AsyncMock(return_value=record))
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                stream_bridge=SimpleNamespace(),
                run_manager=run_mgr,
                checkpointer=SimpleNamespace(),
                store=SimpleNamespace(),
            )
        )
    )
    captured: dict[str, object] = {}

    async def _run_agent(*args, **kwargs):
        captured["config"] = kwargs["config"]

    monkeypatch.setattr("app.gateway.services.runtime.run_agent", _run_agent)
    monkeypatch.setattr("app.gateway.services.runtime._sync_thread_product_state_after_run", AsyncMock(return_value=None))
    monkeypatch.setattr("app.gateway.services.runtime._sync_bound_workspace_to_thread", AsyncMock(return_value=None))
    monkeypatch.setattr(
        "app.gateway.services.runtime._load_runtime_agent_payload",
        AsyncMock(return_value={"user_id": 7, "agent_name": "vip-agent", "memory": {}, "soul": None, "skills": []}),
    )

    await start_run(
        body,
        "thread-1",
        request,
        thread_record=None,
        current_user=SimpleNamespace(
            id=7,
            external_auth_id="kc-sub",
            username="alice",
            display_name="Alice",
            email="alice@example.com",
        ),
    )
    await asyncio.sleep(0)

    config = captured["config"]
    assert config["context"]["thread_id"] == "thread-1"
    assert "agent_name" not in config["context"]
    assert config["configurable"]["agent_name"] == "vip-agent"

    stored_config = run_mgr.create_or_reject.await_args.kwargs["kwargs"]["config"]
    assert stored_config == {
        "context": {"model_name": "gpt-4"},
        "configurable": {"agent_name": "vip-agent"},
        "recursion_limit": 100,
    }


@pytest.mark.anyio
async def test_start_run_keeps_custom_agent_selection_from_top_level_context(monkeypatch):
    from app.gateway.services.runtime import start_run
    from deerflow.runtime import DisconnectMode, RunStatus

    body = SimpleNamespace(
        on_disconnect="cancel",
        assistant_id="lead_agent",
        metadata=None,
        input={"messages": [{"role": "user", "content": "hi"}]},
        config=None,
        context={"agent_name": "VIP_AGENT", "model_name": "gpt-4", "is_plan_mode": True},
        multitask_strategy="reject",
        stream_mode=None,
        stream_subgraphs=False,
        interrupt_before=None,
        interrupt_after=None,
    )
    record = SimpleNamespace(
        run_id="run-1",
        thread_id="thread-1",
        assistant_id=None,
        status=RunStatus.pending,
        metadata={},
        kwargs={},
        multitask_strategy="reject",
        created_at="",
        updated_at="",
        on_disconnect=DisconnectMode.cancel,
        task=None,
    )
    run_mgr = SimpleNamespace(create_or_reject=AsyncMock(return_value=record))
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                stream_bridge=SimpleNamespace(),
                run_manager=run_mgr,
                checkpointer=SimpleNamespace(),
                store=SimpleNamespace(),
            )
        )
    )
    captured: dict[str, object] = {}

    async def _run_agent(*args, **kwargs):
        captured["config"] = kwargs["config"]

    monkeypatch.setattr("app.gateway.services.runtime.run_agent", _run_agent)
    monkeypatch.setattr("app.gateway.services.runtime._sync_thread_product_state_after_run", AsyncMock(return_value=None))
    monkeypatch.setattr("app.gateway.services.runtime._sync_bound_workspace_to_thread", AsyncMock(return_value=None))
    monkeypatch.setattr(
        "app.gateway.services.runtime._load_runtime_agent_payload",
        AsyncMock(return_value={"user_id": 7, "agent_name": "vip-agent", "memory": {}, "soul": None, "skills": []}),
    )

    await start_run(
        body,
        "thread-1",
        request,
        thread_record=None,
        current_user=SimpleNamespace(
            id=7,
            external_auth_id="kc-sub",
            username="alice",
            display_name="Alice",
            email="alice@example.com",
        ),
    )
    await asyncio.sleep(0)

    config = captured["config"]
    assert config["context"]["thread_id"] == "thread-1"
    assert "agent_name" not in config["context"]
    assert config["configurable"]["agent_name"] == "vip-agent"
    assert config["configurable"]["model_name"] == "gpt-4"
    assert config["configurable"]["is_plan_mode"] is True

    stored_config = run_mgr.create_or_reject.await_args.kwargs["kwargs"]["config"]
    assert stored_config == {
        "configurable": {
            "agent_name": "vip-agent",
            "model_name": "gpt-4",
            "is_plan_mode": True,
        },
        "recursion_limit": 100,
    }


@pytest.mark.anyio
async def test_start_run_skips_workspace_sync_when_thread_is_unbound(monkeypatch):
    from app.gateway.services.runtime import start_run
    from deerflow.runtime import DisconnectMode, RunStatus

    body = SimpleNamespace(
        on_disconnect="cancel",
        assistant_id=None,
        metadata=None,
        input={"messages": [{"role": "user", "content": "hi"}]},
        config=None,
        multitask_strategy="reject",
        stream_mode=None,
        stream_subgraphs=False,
        interrupt_before=None,
        interrupt_after=None,
    )
    record = SimpleNamespace(
        run_id="run-1",
        thread_id="thread-1",
        assistant_id=None,
        status=RunStatus.pending,
        metadata={},
        kwargs={},
        multitask_strategy="reject",
        created_at="",
        updated_at="",
        on_disconnect=DisconnectMode.cancel,
        task=None,
    )
    run_mgr = SimpleNamespace(create_or_reject=AsyncMock(return_value=record))
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                stream_bridge=SimpleNamespace(),
                run_manager=run_mgr,
                checkpointer=SimpleNamespace(),
                store=SimpleNamespace(),
            )
        )
    )

    async def _run_agent(*args, **kwargs):
        return None

    monkeypatch.setattr("app.gateway.services.runtime.run_agent", _run_agent)
    monkeypatch.setattr("app.gateway.services.runtime._sync_thread_product_state_after_run", AsyncMock(return_value=None))
    sync_workspace_mock = AsyncMock(return_value=None)
    monkeypatch.setattr("app.gateway.services.runtime._sync_bound_workspace_to_thread", sync_workspace_mock)
    monkeypatch.setattr("app.gateway.services.runtime.upsert_thread_record", AsyncMock(return_value=None))
    monkeypatch.setattr("app.gateway.services.runtime.ThreadRepository.update_thread", AsyncMock(return_value=None))
    monkeypatch.setattr(
        "app.gateway.services.runtime._load_runtime_agent_payload",
        AsyncMock(return_value={"user_id": 7, "agent_name": None, "memory": {}, "soul": None, "skills": []}),
    )

    await start_run(
        body,
        "thread-1",
        request,
        current_user=SimpleNamespace(id=7),
        thread_record=SimpleNamespace(thread_id="thread-1", workspace_id=None),
    )
    await asyncio.sleep(0)

    sync_workspace_mock.assert_awaited_once_with(thread_id="thread-1", workspace_id=None)
