from types import SimpleNamespace
from uuid import NAMESPACE_DNS, uuid5

import pytest

from deerflow.agents.lead_agent import prompt as prompt_module
from deerflow.sandbox.exceptions import SandboxRuntimeError


def _skill_id(name: str) -> str:
    return str(uuid5(NAMESPACE_DNS, f"deerflow-prompt-test:{name}"))


def _runtime_skill(name: str, *, version_number: int = 1, file_manifest_hash: str | None = None, virtual_path: str | None = None, **extra) -> dict:
    skill_id = _skill_id(name)
    return {
        "name": name,
        "description": f"{name} description",
        "skill_id": skill_id,
        "version_number": version_number,
        "virtual_path": virtual_path or f"/mnt/skills/{skill_id}/{version_number}/SKILL.md",
        "file_manifest_hash": file_manifest_hash or f"manifest-{name}",
        **extra,
    }


def test_build_custom_mounts_section_returns_empty_when_no_mounts(monkeypatch):
    config = SimpleNamespace(sandbox=SimpleNamespace(mounts=[]))
    monkeypatch.setattr("deerflow.config.get_app_config", lambda: config)

    assert prompt_module._build_custom_mounts_section() == ""


def test_build_custom_mounts_section_lists_configured_mounts(monkeypatch):
    mounts = [
        SimpleNamespace(container_path="/home/user/shared", read_only=False),
        SimpleNamespace(container_path="/mnt/reference", read_only=True),
    ]
    config = SimpleNamespace(sandbox=SimpleNamespace(mounts=mounts))
    monkeypatch.setattr("deerflow.config.get_app_config", lambda: config)

    section = prompt_module._build_custom_mounts_section()

    assert "**Custom Mounted Directories:**" in section
    assert "`/home/user/shared`" in section
    assert "read-write" in section
    assert "`/mnt/reference`" in section
    assert "read-only" in section


def test_apply_prompt_template_includes_custom_mounts(monkeypatch):
    mounts = [SimpleNamespace(container_path="/home/user/shared", read_only=False)]
    config = SimpleNamespace(
        sandbox=SimpleNamespace(mounts=mounts),
        skills=SimpleNamespace(container_path="/mnt/skills"),
    )
    monkeypatch.setattr("deerflow.config.get_app_config", lambda: config)
    monkeypatch.setattr(prompt_module, "get_config", lambda: {"context": {}})
    monkeypatch.setattr(prompt_module, "get_deferred_tools_prompt_section", lambda: "")
    monkeypatch.setattr(prompt_module, "_build_acp_section", lambda: "")
    monkeypatch.setattr(prompt_module, "_get_memory_context", lambda agent_name=None, runtime_agent_context=None: "")
    monkeypatch.setattr(prompt_module, "get_agent_soul", lambda agent_name=None, runtime_agent_context=None: "")

    prompt = prompt_module.apply_prompt_template()

    assert "`/home/user/shared`" in prompt
    assert "Custom Mounted Directories" in prompt


def test_get_agent_soul_uses_runtime_context(monkeypatch):
    monkeypatch.setattr(
        prompt_module,
        "get_config",
        lambda: {"context": {"runtime_agent": {"soul": "You are calm and precise."}}},
    )

    soul = prompt_module.get_agent_soul("ignored-agent")

    assert "<soul>" in soul
    assert "You are calm and precise." in soul


def test_runtime_agent_context_is_empty_outside_runnable_context(monkeypatch):
    monkeypatch.setattr(
        prompt_module,
        "get_config",
        lambda: (_ for _ in ()).throw(RuntimeError("Called get_config outside of a runnable context")),
    )

    assert prompt_module._get_runtime_agent_context() == {}


def test_get_skills_prompt_section_uses_runtime_context(monkeypatch):
    config = SimpleNamespace(skills=SimpleNamespace(container_path="/mnt/skills"))
    monkeypatch.setattr("deerflow.config.get_app_config", lambda: config)
    monkeypatch.setattr(
        prompt_module,
        "get_config",
        lambda: {
            "context": {
                "runtime_agent": {
                    "skills": [
                        _runtime_skill("sql-review", file_manifest_hash="manifest-sql", description="Review SQL changes."),
                        _runtime_skill("api-design", version_number=2, file_manifest_hash="manifest-api", description="Design API contracts."),
                    ]
                }
            }
        },
    )

    section = prompt_module.get_skills_prompt_section()

    assert "sql-review" in section
    assert "Review SQL changes." in section
    assert f"/mnt/skills/{_skill_id('sql-review')}/1/SKILL.md" in section
    assert "api-design" in section
    assert f"<skill_id>{_skill_id('sql-review')}</skill_id>" in section
    assert "<skill_version_id>" not in section
    assert "<version_number>2</version_number>" in section
    assert "<file_manifest_hash>manifest-api</file_manifest_hash>" in section
    assert "skill_load" in section


def test_runtime_skill_prompt_descriptors_require_terminal_descriptor_fields():
    with pytest.raises(SandboxRuntimeError, match="missing skill_id"):
        prompt_module.build_runtime_skill_descriptors(
            [
                {
                    "name": "legacy-name-only",
                    "description": "Should be rejected.",
                    "skill_version_id": 101,
                    "version_number": 1,
                    "file_manifest_hash": "manifest-hash",
                    "virtual_path": "/mnt/skills/legacy-name-only/SKILL.md",
                },
            ],
            container_base_path="/mnt/skills",
        )


def test_runtime_skill_prompt_descriptors_use_terminal_identity():
    descriptors = prompt_module.build_runtime_skill_descriptors(
        [
            _runtime_skill("terminal-skill", version_number=2, file_manifest_hash="manifest-hash", description="Allowed."),
        ],
        container_base_path="/mnt/skills",
    )

    assert descriptors == [
        {
            "name": "terminal-skill",
            "description": "Allowed.",
            "location": f"/mnt/skills/{_skill_id('terminal-skill')}/2/SKILL.md",
            "skill_id": _skill_id("terminal-skill"),
            "version_number": "2",
            "file_manifest_hash": "manifest-hash",
        }
    ]
