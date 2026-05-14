from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import UUID

from deerflow.sandbox.exceptions import SandboxRuntimeError
from deerflow.skills.hashing import hash_skill_file_manifest
from deerflow.skills.path_utils import build_terminal_skill_version_relative_path, resolve_terminal_skill_version_dir

CANONICAL_RUNTIME_SKILLS_SCOPE = "."
_REJECTED_RUNTIME_BUNDLE_SCOPE_ROOT = ".runtime-skill-bundles"


@dataclass(frozen=True)
class RuntimeSkillScopeEntry:
    """Terminal runtime Skill descriptor normalized for prompt, mounts, and skill_load."""

    skill_id: str
    version_number: int
    file_manifest_hash: str
    virtual_path: str
    virtual_root: str
    relative_virtual_root: str
    storage_relative_path: str


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


def _get_skills_container_path() -> str:
    try:
        from deerflow.config import get_app_config

        return get_app_config().skills.container_path
    except Exception:
        return "/mnt/skills"


def _get_skills_root_path() -> Path:
    try:
        from deerflow.config import get_app_config

        return get_app_config().skills.get_skills_path()
    except Exception as exc:
        raise SandboxRuntimeError("Skills root is not available for runtime skill scope validation") from exc


def _runtime_skill_label(index: int | None = None) -> str:
    label = "Runtime skill"
    if index is not None:
        label = f"Runtime skill at index {index}"
    return label


def _parse_terminal_version_number(version_number: Any, *, index: int | None = None) -> int:
    label = _runtime_skill_label(index)
    if isinstance(version_number, bool):
        raise SandboxRuntimeError(f"{label} version_number must be a positive integer")
    try:
        terminal_version_number = int(version_number)
    except (TypeError, ValueError) as exc:
        raise SandboxRuntimeError(f"{label} version_number must be a positive integer") from exc
    if terminal_version_number <= 0:
        raise SandboxRuntimeError(f"{label} version_number must be a positive integer")
    return terminal_version_number


def _looks_like_uuid(value: str) -> bool:
    try:
        UUID(value)
    except (TypeError, ValueError, AttributeError):
        return False
    return True


def _reject_legacy_virtual_root(relative_parts: tuple[str, ...], *, virtual_path: str, index: int | None = None) -> None:
    label = _runtime_skill_label(index)
    first = relative_parts[0]
    if first in {"public", "custom", "local"}:
        raise SandboxRuntimeError(f"{label} virtual_path uses a legacy skill root: {virtual_path!r}")
    if first == "artifacts":
        raise SandboxRuntimeError(f"{label} virtual_path uses a legacy artifacts skill root: {virtual_path!r}")
    if first == _REJECTED_RUNTIME_BUNDLE_SCOPE_ROOT:
        raise SandboxRuntimeError(f"{label} virtual_path must not point at runtime bundle cache storage: {virtual_path!r}")
    if first.isdigit():
        raise SandboxRuntimeError(f"{label} virtual_path uses a legacy user or version-id root: {virtual_path!r}")
    if len(relative_parts) == 1 and _looks_like_uuid(first):
        raise SandboxRuntimeError(f"{label} virtual_path uses a legacy standalone version-id root: {virtual_path!r}")


def build_runtime_skill_scope_entry(skill: Mapping[str, Any], *, index: int | None = None, container_base_path: str) -> RuntimeSkillScopeEntry:
    """Normalize one terminal runtime Skill descriptor.

    The descriptor contract is intentionally narrow: authorization is derived
    only from skill_id + version_number + file_manifest_hash + virtual_path.
    Legacy path fields such as artifact_uri and file_path are ignored.
    """
    label = _runtime_skill_label(index)

    skill_id = skill.get("skill_id")
    if not isinstance(skill_id, str) or not skill_id.strip():
        raise SandboxRuntimeError(f"{label} is missing skill_id")
    version_number = _parse_terminal_version_number(skill.get("version_number"), index=index)
    try:
        storage_relative_path = build_terminal_skill_version_relative_path(skill_id.strip(), version_number)
    except ValueError as exc:
        raise SandboxRuntimeError(f"{label} skill_id must be a valid UUID") from exc
    terminal_skill_id = storage_relative_path.split("/", 1)[0]

    virtual_path = skill.get("virtual_path")
    if not isinstance(virtual_path, str) or not virtual_path.strip():
        raise SandboxRuntimeError(f"{label} is missing virtual_path")
    file_manifest_hash = skill.get("file_manifest_hash")
    if not isinstance(file_manifest_hash, str) or not file_manifest_hash.strip():
        raise SandboxRuntimeError(f"{label} is missing file_manifest_hash")

    container_root = PurePosixPath(container_base_path.rstrip("/"))
    virtual_root = PurePosixPath(virtual_path.strip()).parent
    try:
        relative_virtual_root = virtual_root.relative_to(container_root)
    except ValueError as exc:
        raise SandboxRuntimeError(f"{label} virtual_path is outside the skills mount: {virtual_path!r}") from exc

    relative_parts = tuple(part for part in relative_virtual_root.parts if part not in ("", "."))
    if not relative_parts or any(part == ".." for part in relative_parts):
        raise SandboxRuntimeError(f"{label} virtual_path has invalid root: {virtual_path!r}")
    _reject_legacy_virtual_root(relative_parts, virtual_path=virtual_path, index=index)
    normalized_relative_virtual_root = str(PurePosixPath(*relative_parts))
    if normalized_relative_virtual_root != storage_relative_path:
        raise SandboxRuntimeError(f"{label} virtual_path must use canonical terminal root {container_root}/{storage_relative_path}: {virtual_path!r}")

    return RuntimeSkillScopeEntry(
        skill_id=terminal_skill_id,
        version_number=version_number,
        file_manifest_hash=file_manifest_hash.strip(),
        virtual_path=virtual_path.strip(),
        virtual_root=str(virtual_root),
        relative_virtual_root=normalized_relative_virtual_root,
        storage_relative_path=storage_relative_path,
    )


def _verify_authorized_skill_tree(skills_root: Path, entry: RuntimeSkillScopeEntry) -> Path:
    """Verify one terminal Skill version still matches its recorded raw hash."""
    artifact_dir = resolve_terminal_skill_version_dir(skills_root, entry.skill_id, entry.version_number)
    if not artifact_dir.exists() or not artifact_dir.is_dir():
        raise SandboxRuntimeError(f"Runtime skill storage is missing: {entry.storage_relative_path}")
    if not (artifact_dir / "SKILL.md").exists():
        raise SandboxRuntimeError(f"Runtime skill storage is missing SKILL.md: {entry.storage_relative_path}")

    actual_file_manifest_hash = hash_skill_file_manifest(artifact_dir)
    if actual_file_manifest_hash != entry.file_manifest_hash:
        raise SandboxRuntimeError(f"Runtime skill file manifest hash mismatch: {entry.storage_relative_path}")
    return artifact_dir


def derive_skill_scope_from_runtime_agent(runtime_agent: Mapping[str, Any] | None) -> str | None:
    """Validate runtime Skill descriptors and request the canonical skills root mount."""
    if runtime_agent is None:
        return None

    raw_skills = runtime_agent.get("skills")
    if raw_skills is None:
        return None
    if not isinstance(raw_skills, list):
        raise SandboxRuntimeError("runtime_agent.skills must be a list when provided")
    if len(raw_skills) == 0:
        return None

    entries: list[RuntimeSkillScopeEntry] = []
    seen_virtual_roots: set[str] = set()
    container_base_path = _get_skills_container_path()

    for index, skill in enumerate(raw_skills):
        if not isinstance(skill, Mapping):
            raise SandboxRuntimeError(f"Runtime skill metadata at index {index} is malformed")

        entry = build_runtime_skill_scope_entry(skill, index=index, container_base_path=container_base_path)
        if entry.relative_virtual_root in seen_virtual_roots:
            raise SandboxRuntimeError(f"Duplicate runtime skill virtual root: {entry.virtual_root}")
        seen_virtual_roots.add(entry.relative_virtual_root)
        entries.append(entry)

    if entries:
        skills_root = _get_skills_root_path()
        for entry in entries:
            _verify_authorized_skill_tree(skills_root, entry)
        return CANONICAL_RUNTIME_SKILLS_SCOPE

    return None


def derive_skill_scope_from_runtime(runtime: Any | None = None) -> str | None:
    """Derive the sandbox skill scope from a runtime object."""
    return derive_skill_scope_from_runtime_agent(get_runtime_agent_context(runtime))
