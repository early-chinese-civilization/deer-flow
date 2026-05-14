from __future__ import annotations

import uuid
from pathlib import Path, PurePosixPath

PUBLIC_SKILLS_DIR = "public"
LEGACY_CUSTOM_SKILLS_DIR = "custom"
LOCAL_CLIENT_SKILLS_DIR = "local"


def build_private_skill_file_path(user_id: int | str, skill_name: str) -> str:
    """Return the canonical shared-filesystem path for a private skill."""
    return f"{user_id}/{skill_name}"


def build_public_skill_file_path(skill_name: str, owner_user_id: int | str | None = None) -> str:
    """Return the canonical shared-filesystem path for a public skill."""
    if owner_user_id is not None:
        return f"{PUBLIC_SKILLS_DIR}/{owner_user_id}/{skill_name}"
    return f"{PUBLIC_SKILLS_DIR}/{skill_name}"


def build_skill_virtual_root(skill_name: str, *, container_base_path: str = "/mnt/skills", identity_suffix: str | int | None = None) -> str:
    """Return the stable virtual root exposed to the model for a skill."""
    root_name = skill_name
    if identity_suffix is not None:
        root_name = f"{skill_name}--{identity_suffix}"
    return f"{container_base_path.rstrip('/')}/{root_name}"


def build_skill_virtual_path(skill_name: str, *, container_base_path: str = "/mnt/skills", identity_suffix: str | int | None = None) -> str:
    """Return the stable virtual SKILL.md path exposed to the model."""
    return f"{build_skill_virtual_root(skill_name, container_base_path=container_base_path, identity_suffix=identity_suffix)}/SKILL.md"


def build_terminal_skill_version_relative_path(skill_id: str | uuid.UUID, version_number: int | str) -> str:
    """Return the terminal relative content path for an immutable Skill version."""
    try:
        terminal_skill_id = str(skill_id) if isinstance(skill_id, uuid.UUID) else str(uuid.UUID(str(skill_id)))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError("skill_id must be a valid UUID") from exc

    if isinstance(version_number, bool):
        raise ValueError("version_number must be a positive integer")
    try:
        terminal_version_number = int(version_number)
    except (TypeError, ValueError) as exc:
        raise ValueError("version_number must be a positive integer") from exc
    if terminal_version_number <= 0:
        raise ValueError("version_number must be a positive integer")

    return f"{terminal_skill_id}/{terminal_version_number}"


def build_terminal_skill_virtual_root(skill_id: str | uuid.UUID, version_number: int | str, *, container_base_path: str = "/mnt/skills") -> str:
    """Return the canonical virtual root for an immutable Skill version."""
    return f"{container_base_path.rstrip('/')}/{build_terminal_skill_version_relative_path(skill_id, version_number)}"


def build_terminal_skill_virtual_path(skill_id: str | uuid.UUID, version_number: int | str, *, container_base_path: str = "/mnt/skills") -> str:
    """Return the canonical virtual SKILL.md path for an immutable Skill version."""
    return f"{build_terminal_skill_virtual_root(skill_id, version_number, container_base_path=container_base_path)}/SKILL.md"


def is_terminal_skill_version_relative_path(file_path: str | None) -> bool:
    """Return whether a relative path is exactly ``{skill_id}/{version_number}``."""
    normalized = str(file_path or "").replace("\\", "/").strip("/")
    parts = [part for part in normalized.split("/") if part]
    if len(parts) != 2 or any(part in {".", ".."} for part in parts):
        return False
    try:
        return build_terminal_skill_version_relative_path(parts[0], parts[1]) == normalized
    except ValueError:
        return False


def resolve_terminal_skill_version_dir(skills_root: Path, skill_id: str | uuid.UUID, version_number: int | str) -> Path:
    """Resolve the terminal immutable Skill version directory under the skills root."""
    return resolve_skill_storage_dir(skills_root, build_terminal_skill_version_relative_path(skill_id, version_number))


def normalize_skill_file_path(
    file_path: str | None,
    *,
    user_id: int | None,
    skill_name: str,
) -> str:
    """Normalize stored skill paths to the shared-filesystem relative layout.

    Compatibility:
    - strips a legacy ``skills/`` prefix
    - rewrites legacy public ``public/<name>/<owner>`` paths to ``public/<name>``
    - rewrites legacy custom ``custom/<name>`` paths to ``<user_id>/<name>``
    """
    canonical = build_public_skill_file_path(skill_name) if user_id is None else build_private_skill_file_path(user_id, skill_name)
    if file_path is None:
        return canonical

    normalized = str(file_path).replace("\\", "/").strip("/")
    if not normalized:
        return canonical

    if normalized.startswith("skills/"):
        normalized = normalized.removeprefix("skills/")

    if user_id is None:
        if normalized == canonical or normalized.startswith(f"{canonical}/"):
            return canonical
        normalized_parts = PurePosixPath(normalized).parts
        if len(normalized_parts) == 3 and normalized_parts[0] == PUBLIC_SKILLS_DIR and normalized_parts[2] == skill_name:
            return normalized
        if normalized.startswith(f"{PUBLIC_SKILLS_DIR}/{skill_name}/"):
            return canonical
        return canonical

    legacy_custom = f"{LEGACY_CUSTOM_SKILLS_DIR}/{skill_name}"
    if normalized == canonical or normalized.startswith(f"{canonical}/"):
        return canonical
    if normalized == legacy_custom or normalized.startswith(f"{legacy_custom}/"):
        return canonical
    return canonical


def resolve_skill_storage_dir(skills_root: Path, file_path: str) -> Path:
    """Resolve a stored skill path into an actual directory on disk.

    Absolute paths are preserved for compatibility with legacy seed/public rows.
    Relative paths are resolved under ``skills_root`` and must stay inside it.
    """
    candidate = Path(file_path)
    if candidate.is_absolute():
        return candidate.resolve()

    normalized = str(file_path).replace("\\", "/").strip("/")
    if not normalized:
        raise ValueError("Skill path cannot be empty")

    resolved = (skills_root / Path(PurePosixPath(normalized))).resolve()
    resolved.relative_to(skills_root.resolve())
    return resolved
