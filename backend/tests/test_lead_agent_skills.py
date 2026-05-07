from deerflow.agents.lead_agent.prompt import get_skills_prompt_section


def _make_runtime_skill(name: str) -> dict:
    return {
        "name": name,
        "description": f"Description for {name}",
        "virtual_path": f"/mnt/skills/{name}/SKILL.md",
        "skill_version_id": f"{name}-version",
        "version_number": 1,
        "file_manifest_hash": f"{name}-hash",
    }


def _runtime_context(*skills: dict) -> dict:
    return {"skills": list(skills)}


def test_get_skills_prompt_section_returns_empty_when_no_skills_match():
    runtime_context = _runtime_context(_make_runtime_skill("skill1"), _make_runtime_skill("skill2"))
    result = get_skills_prompt_section(available_skills={"non_existent_skill"}, runtime_agent_context=runtime_context)
    assert result == ""


def test_get_skills_prompt_section_returns_empty_when_available_skills_empty():
    runtime_context = _runtime_context(_make_runtime_skill("skill1"), _make_runtime_skill("skill2"))
    result = get_skills_prompt_section(available_skills=set(), runtime_agent_context=runtime_context)
    assert result == ""


def test_get_skills_prompt_section_returns_skills():
    runtime_context = _runtime_context(_make_runtime_skill("skill1"), _make_runtime_skill("skill2"))
    result = get_skills_prompt_section(available_skills={"skill1"}, runtime_agent_context=runtime_context)
    assert "skill1" in result
    assert "skill2" not in result


def test_get_skills_prompt_section_returns_all_when_available_skills_is_none():
    runtime_context = _runtime_context(_make_runtime_skill("skill1"), _make_runtime_skill("skill2"))
    result = get_skills_prompt_section(available_skills=None, runtime_agent_context=runtime_context)
    assert "skill1" in result
    assert "skill2" in result


def test_make_lead_agent_empty_skills_passed_correctly(monkeypatch):
    from unittest.mock import MagicMock

    from deerflow.agents.lead_agent import agent as lead_agent_module

    # Mock dependencies
    monkeypatch.setattr(lead_agent_module, "get_app_config", lambda: MagicMock())
    monkeypatch.setattr(lead_agent_module, "_resolve_model_name", lambda x=None: "default-model")
    monkeypatch.setattr(lead_agent_module, "create_chat_model", lambda **kwargs: "model")
    monkeypatch.setattr("deerflow.tools.get_available_tools", lambda **kwargs: [])
    monkeypatch.setattr(lead_agent_module, "_build_middlewares", lambda *args, **kwargs: [])
    monkeypatch.setattr(lead_agent_module, "create_agent", lambda **kwargs: kwargs)

    class MockModelConfig:
        supports_thinking = False

    mock_app_config = MagicMock()
    mock_app_config.get_model_config.return_value = MockModelConfig()
    monkeypatch.setattr(lead_agent_module, "get_app_config", lambda: mock_app_config)

    captured_skills = []

    def mock_apply_prompt_template(**kwargs):
        captured_skills.append(kwargs.get("available_skills"))
        return "mock_prompt"

    monkeypatch.setattr(lead_agent_module, "apply_prompt_template", mock_apply_prompt_template)

    lead_agent_module.make_lead_agent({"configurable": {"agent_name": "test"}, "context": {"runtime_agent": {"skills": []}}})
    assert captured_skills[-1] is None
