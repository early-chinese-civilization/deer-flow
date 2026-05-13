from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import time
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any, cast

from deerflow.sandbox.exceptions import SandboxRuntimeError
from deerflow.skills.hashing import hash_skill_file_manifest
from deerflow.skills.path_utils import is_terminal_skill_version_relative_path, resolve_skill_storage_dir

_ARTIFACTS_SCOPE_ROOT = "artifacts"
_RUNTIME_BUNDLE_SCOPE_ROOT = ".runtime-skill-bundles"
_BUNDLE_READY_FILE = ".deerflow-runtime-bundle.json"
_RUNTIME_BUNDLE_RETENTION_SECONDS = 7 * 24 * 60 * 60
_RUNTIME_BUNDLE_TMP_RETENTION_SECONDS = 60 * 60

logger = logging.getLogger(__name__)


def _is_immutable_runtime_artifact_uri(normalized_artifact: str) -> bool:
    parts = [part for part in normalized_artifact.split("/") if part]
    if any(part in {".", ".."} for part in parts):
        return False
    if len(parts) >= 3 and parts[0] == _ARTIFACTS_SCOPE_ROOT and parts[1] == "skills":
        return True
    return is_terminal_skill_version_relative_path(normalized_artifact)


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
        raise SandboxRuntimeError("Skills root is not available for runtime skill bundle materialization") from exc


def normalize_runtime_artifact_uri(artifact_uri: Any, *, index: int | None = None) -> str:
    """Normalize and validate a Runtime Manifest SkillVersion artifact URI."""
    label = "Runtime skill"
    if index is not None:
        label = f"Runtime skill at index {index}"

    if not isinstance(artifact_uri, str) or not artifact_uri.strip():
        raise SandboxRuntimeError(f"{label} is missing artifact_uri")

    normalized_artifact = artifact_uri.replace("\\", "/").strip("/")
    if not _is_immutable_runtime_artifact_uri(normalized_artifact):
        raise SandboxRuntimeError(f"{label} artifact_uri must use the immutable version storage scope: {artifact_uri!r}")
    return normalized_artifact


def _runtime_bundle_entry(index: int, skill: Mapping[str, Any], *, container_base_path: str) -> dict[str, Any]:
    normalized_artifact = normalize_runtime_artifact_uri(skill.get("artifact_uri"), index=index)

    if skill.get("skill_version_id") is None:
        raise SandboxRuntimeError(f"Runtime skill at index {index} is missing skill_version_id")

    virtual_path = skill.get("virtual_path")
    if not isinstance(virtual_path, str) or not virtual_path.strip():
        raise SandboxRuntimeError(f"Runtime skill at index {index} is missing virtual_path")
    file_manifest_hash = skill.get("file_manifest_hash")
    if not isinstance(file_manifest_hash, str) or not file_manifest_hash.strip():
        raise SandboxRuntimeError(f"Runtime skill at index {index} is missing file_manifest_hash")

    container_root = PurePosixPath(container_base_path.rstrip("/"))
    virtual_root = PurePosixPath(virtual_path.strip()).parent
    try:
        relative_virtual_root = virtual_root.relative_to(container_root)
    except ValueError as exc:
        raise SandboxRuntimeError(f"Runtime skill virtual_path is outside the skills mount: {virtual_path!r}") from exc

    relative_parts = [part for part in relative_virtual_root.parts if part not in ("", ".")]
    if not relative_parts or any(part == ".." for part in relative_parts):
        raise SandboxRuntimeError(f"Runtime skill virtual_path has invalid root: {virtual_path!r}")

    return {
        "artifact_uri": normalized_artifact,
        "content_hash": skill.get("content_hash"),
        "file_manifest_hash": file_manifest_hash,
        "relative_virtual_root": str(PurePosixPath(*relative_parts)),
        "skill_version_id": skill.get("skill_version_id"),
        "virtual_root": str(virtual_root),
    }


def _copy_authorized_artifact_tree(source: Path, target: Path) -> None:
    """Copy one exact Manifest artifact into the run bundle without following symlinks."""
    for current_root, dir_names, file_names in os.walk(source, followlinks=False):
        current = Path(current_root)
        relative = current.relative_to(source)
        destination = target / relative
        destination.mkdir(parents=True, exist_ok=True)

        for dir_name in list(dir_names):
            source_dir = current / dir_name
            if source_dir.is_symlink():
                raise SandboxRuntimeError(f"Runtime skill artifact contains an unsupported symlink: {source_dir.name}")
            (destination / dir_name).mkdir(exist_ok=True)

        for file_name in file_names:
            source_file = current / file_name
            if source_file.is_symlink():
                raise SandboxRuntimeError(f"Runtime skill artifact contains an unsupported symlink: {source_file.name}")
            shutil.copy2(source_file, destination / file_name)


def _verify_authorized_artifact_tree(skills_root: Path, entry: Mapping[str, Any]) -> Path:
    """Verify one manifest artifact still matches its recorded raw hash."""
    artifact_dir = resolve_skill_storage_dir(skills_root, entry["artifact_uri"])
    if not artifact_dir.exists() or not artifact_dir.is_dir():
        raise SandboxRuntimeError(f"Runtime skill artifact is missing: {entry['artifact_uri']}")
    if not (artifact_dir / "SKILL.md").exists():
        raise SandboxRuntimeError(f"Runtime skill artifact is missing SKILL.md: {entry['artifact_uri']}")

    actual_file_manifest_hash = hash_skill_file_manifest(artifact_dir)
    if actual_file_manifest_hash != entry["file_manifest_hash"]:
        raise SandboxRuntimeError(f"Runtime skill artifact file manifest hash mismatch: {entry['artifact_uri']}")
    return artifact_dir


def _remove_runtime_bundle_tree(path: Path) -> None:
    try:
        shutil.rmtree(path)
    except OSError:
        logger.warning("Failed to remove stale runtime skill bundle %s", path, exc_info=True)


def _prune_runtime_skill_bundle_cache(skills_root: Path, *, keep_bundle_scope: str) -> None:
    """Remove stale bundle copies while preserving the bundle needed for this run.

    Bundle ids are keyed by the full manifest projection, including virtual roots.
    That safely reuses repeated direct System Skill bindings with the same virtual
    path, but install-specific virtual roots can still create many copies of the
    same artifact over time. Age-based pruning bounds that cache growth without
    changing authorization or artifact integrity semantics.
    """
    bundle_root = resolve_skill_storage_dir(skills_root, _RUNTIME_BUNDLE_SCOPE_ROOT)
    if not bundle_root.exists():
        return

    keep_bundle_name = PurePosixPath(keep_bundle_scope).name
    now = time.time()

    try:
        children = list(bundle_root.iterdir())
    except OSError:
        logger.warning("Failed to inspect runtime skill bundle cache %s", bundle_root, exc_info=True)
        return

    for child in children:
        if child.name == keep_bundle_name:
            continue
        if child.is_symlink() or not child.is_dir():
            continue

        try:
            age_seconds = now - child.stat().st_mtime
        except OSError:
            logger.warning("Failed to stat runtime skill bundle %s", child, exc_info=True)
            continue

        is_tmp_bundle = child.name.startswith(".") and ".tmp-" in child.name
        if is_tmp_bundle and age_seconds >= _RUNTIME_BUNDLE_TMP_RETENTION_SECONDS:
            _remove_runtime_bundle_tree(child)
            continue

        if (child / _BUNDLE_READY_FILE).exists() and age_seconds >= _RUNTIME_BUNDLE_RETENTION_SECONDS:
            _remove_runtime_bundle_tree(child)


def _materialize_runtime_skill_bundle(entries: list[dict[str, Any]]) -> str:
    """Create a deterministic readonly-bundle source for Manifest-authorized skills.

    Physical layout:
    ``<skills_root>/.runtime-skill-bundles/<manifest-hash>/<virtual-skill-name>/...``.
    The bundle is populated only from exact ``SkillVersion.artifact_uri`` roots
    listed in the Runtime Manifest; it never scans the skills root or falls back
    to public/latest/same-name directories. The deterministic bundle id reuses
    repeated identical manifest projections, while stale cache entries are
    pruned by retention window to prevent unbounded copy accumulation.
    """
    skills_root = _get_skills_root_path()
    payload = json.dumps(entries, sort_keys=True, separators=(",", ":"), default=str)
    bundle_id = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]
    bundle_scope = f"{_RUNTIME_BUNDLE_SCOPE_ROOT}/{bundle_id}"
    bundle_dir = resolve_skill_storage_dir(skills_root, bundle_scope)
    ready_file = bundle_dir / _BUNDLE_READY_FILE

    seen_virtual_roots: set[str] = set()
    verified_sources: list[tuple[dict[str, Any], Path]] = []
    for entry in entries:
        relative_virtual_root = entry["relative_virtual_root"]
        if relative_virtual_root in seen_virtual_roots:
            raise SandboxRuntimeError(f"Duplicate runtime skill virtual root: {entry['virtual_root']}")
        seen_virtual_roots.add(relative_virtual_root)
        verified_sources.append((entry, _verify_authorized_artifact_tree(skills_root, entry)))

    if ready_file.exists():
        _prune_runtime_skill_bundle_cache(skills_root, keep_bundle_scope=bundle_scope)
        return bundle_scope
    if bundle_dir.exists():
        shutil.rmtree(bundle_dir)

    tmp_dir = bundle_dir.with_name(f".{bundle_dir.name}.tmp-{os.getpid()}")
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    tmp_dir.mkdir(parents=True)

    try:
        for entry, artifact_dir in verified_sources:
            relative_virtual_root = entry["relative_virtual_root"]
            _copy_authorized_artifact_tree(artifact_dir, tmp_dir / relative_virtual_root)

        ready_file_payload = {"bundle_id": bundle_id, "skills": entries}
        (tmp_dir / _BUNDLE_READY_FILE).write_text(json.dumps(ready_file_payload, sort_keys=True), encoding="utf-8")
        try:
            tmp_dir.replace(bundle_dir)
        except FileExistsError:
            shutil.rmtree(tmp_dir)
        _prune_runtime_skill_bundle_cache(skills_root, keep_bundle_scope=bundle_scope)
        return bundle_scope
    except Exception:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise


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

    artifact_entries: list[dict[str, Any]] = []
    container_base_path = _get_skills_container_path()

    for index, skill in enumerate(raw_skills):
        if not isinstance(skill, Mapping):
            raise SandboxRuntimeError(f"Runtime skill metadata at index {index} is malformed")

        artifact_entries.append(_runtime_bundle_entry(index, cast(Mapping[str, Any], skill), container_base_path=container_base_path))

    if artifact_entries:
        return _materialize_runtime_skill_bundle(artifact_entries)

    return None


def derive_skill_scope_from_runtime(runtime: Any | None = None) -> str | None:
    """Derive the sandbox skill scope from a runtime object."""
    return derive_skill_scope_from_runtime_agent(get_runtime_agent_context(runtime))
