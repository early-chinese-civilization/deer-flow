from types import SimpleNamespace

from deerflow.agents.lead_agent import prompt as prompt_module


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
                        {
                            "name": "sql-review",
                            "description": "Review SQL changes.",
                            "file_path": "public/sql-review",
                            "virtual_path": "/mnt/skills/sql-review/SKILL.md",
                        },
                        {
                            "name": "api-design",
                            "description": "Design API contracts.",
                            "file_path": "9/api-design",
                            "virtual_path": "/mnt/skills/api-design/SKILL.md",
                        },
                    ]
                }
            }
        },
    )

    section = prompt_module.get_skills_prompt_section()

    assert "sql-review" in section
    assert "Review SQL changes." in section
    assert "/mnt/skills/sql-review/SKILL.md" in section
    assert "api-design" in section
    assert "skill_load" in section


def test_apply_prompt_template_repeats_identity_rule_in_final_reminders(monkeypatch):
    monkeypatch.setattr(prompt_module, "get_config", lambda: {"context": {}})
    monkeypatch.setattr(prompt_module, "get_deferred_tools_prompt_section", lambda: "")
    monkeypatch.setattr(prompt_module, "_build_acp_section", lambda: "")
    monkeypatch.setattr(prompt_module, "_build_custom_mounts_section", lambda: "")
    monkeypatch.setattr(prompt_module, "_get_memory_context", lambda agent_name=None, runtime_agent_context=None: "")
    monkeypatch.setattr(prompt_module, "get_agent_soul", lambda agent_name=None, runtime_agent_context=None: "")

    prompt = prompt_module.apply_prompt_template(agent_name="default")
    reminders_index = prompt.index("<critical_reminders>")
    identity_index = prompt.index("Identity questions")

    assert identity_index > reminders_index
    assert "炎黄早期中华文明大模型" in prompt[identity_index:]
    assert "Use the same language as the user" in prompt[identity_index:]
