from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from deerflow.sandbox.exceptions import SandboxRuntimeError
from deerflow.skills.path_utils import PUBLIC_SKILLS_DIR

_PRIVATE_SCOPE_PATTERN = re.compile(r"^[0-9]+$")


def get_runtime_agent_context(
    runtime: Any | None = None,
    *,
    context: Mapping[str, Any] | None = None,
    config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return runtime_agent metadata injected into runtime context/config."""
    runtime_context = context
    runtime_config = config

    if runtime is not None:
        runtime_context = getattr(runtime, "context", None)
        runtime_config = getattr(runtime, "config", None)

    if isinstance(runtime_context, Mapping):
        runtime_agent = runtime_context.get("runtime_agent")
        if isinstance(runtime_agent, dict):
            return runtime_agent

    if isinstance(runtime_config, Mapping):
        config_context = runtime_config.get("context")
        if isinstance(config_context, Mapping):
            runtime_agent = config_context.get("runtime_agent")
            if isinstance(runtime_agent, dict):
                return runtime_agent

    return {}


def derive_skill_scope_from_runtime_agent(runtime_agent: Mapping[str, Any] | None) -> str | None:
    """Derive the single allowed sandbox skills scope from runtime metadata."""
    if runtime_agent is None:
        return None

    raw_skills = runtime_agent.get("skills")
    if raw_skills is None:
        return None
    if not isinstance(raw_skills, list):
        raise SandboxRuntimeError("runtime_agent.skills must be a list when provided")
    if len(raw_skills) == 0:
        return None

    scopes: set[str] = set()
    private_scopes: set[str] = set()

    for index, skill in enumerate(raw_skills):
        if not isinstance(skill, Mapping):
            raise SandboxRuntimeError(f"Runtime skill metadata at index {index} is malformed")

        file_path = skill.get("file_path")
        if not isinstance(file_path, str) or not file_path.strip():
            raise SandboxRuntimeError(f"Runtime skill at index {index} is missing file_path")

        normalized = file_path.replace("\\", "/").strip("/")
        parts = [part for part in normalized.split("/") if part]
        if len(parts) < 2:
            raise SandboxRuntimeError(f"Runtime skill file_path has invalid scope root: {file_path!r}")

        scope_root = parts[0]
        if scope_root == PUBLIC_SKILLS_DIR:
            scopes.add(PUBLIC_SKILLS_DIR)
            continue

        if not _PRIVATE_SCOPE_PATTERN.fullmatch(scope_root):
            raise SandboxRuntimeError(f"Runtime skill file_path has invalid scope root: {file_path!r}")

        scopes.add(scope_root)
        private_scopes.add(scope_root)

    if not scopes:
        return None

    if PUBLIC_SKILLS_DIR in scopes and len(scopes) > 1:
        raise SandboxRuntimeError("Runtime skills must all come from the same scope")

    if len(private_scopes) > 1:
        raise SandboxRuntimeError("Runtime skills must all come from the same private scope")

    if scopes == {PUBLIC_SKILLS_DIR}:
        return PUBLIC_SKILLS_DIR

    private_scope = next(iter(private_scopes))
    runtime_user_id = runtime_agent.get("user_id")
    if runtime_user_id is None:
        raise SandboxRuntimeError("runtime_agent.user_id is required for private runtime skills")

    if str(runtime_user_id) != private_scope:
        raise SandboxRuntimeError("Private runtime skill scope does not match runtime_agent.user_id")

    return private_scope


def derive_skill_scope_from_runtime(runtime: Any | None = None) -> str | None:
    """Derive the sandbox skill scope from a runtime object."""
    return derive_skill_scope_from_runtime_agent(get_runtime_agent_context(runtime))
