from __future__ import annotations

import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal

from deerflow.skills.hashing import hash_skill_directory
from deerflow.skills.path_utils import build_terminal_skill_version_relative_path, resolve_skill_storage_dir


class SkillStorageMigrationError(RuntimeError):
    """Raised when legacy Skill storage cannot be copied or verified."""


@dataclass(frozen=True)
class SkillVersionStorageMigrationItem:
    """One legacy SkillVersion storage location to copy into terminal layout."""

    skill_id: str | uuid.UUID
    version_number: int
    source_path: str
    content_hash: str
    file_manifest_hash: str


@dataclass(frozen=True)
class SkillVersionStorageMigrationResult:
    """Result for one idempotent storage migration item."""

    source_path: str
    terminal_path: str
    action: Literal["copied", "verified"]


def _normalize_relative_path(raw_path: str) -> str:
    normalized = str(raw_path).replace("\\", "/").strip("/")
    parts = PurePosixPath(normalized).parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise SkillStorageMigrationError(f"Unsupported legacy Skill source path: {raw_path}")
    return PurePosixPath(*parts).as_posix()


def _is_legacy_skill_source_path(relative_path: str) -> bool:
    parts = PurePosixPath(relative_path).parts
    if len(parts) >= 3 and parts[0] == "artifacts" and parts[1] in {"skills", "legacy"}:
        return True
    if len(parts) >= 2 and parts[0] in {"public", "custom", "local"}:
        return True
    return len(parts) >= 2 and parts[0].isdigit()


def _verify_skill_directory(
    skill_dir: Path,
    *,
    expected_content_hash: str,
    expected_file_manifest_hash: str,
) -> None:
    if not skill_dir.is_dir():
        raise SkillStorageMigrationError("Skill storage path is not a directory")
    if not (skill_dir / "SKILL.md").is_file():
        raise SkillStorageMigrationError("Skill storage path is missing SKILL.md")
    if not expected_content_hash:
        raise SkillStorageMigrationError("SkillVersion is missing content_hash")
    if not expected_file_manifest_hash:
        raise SkillStorageMigrationError("SkillVersion is missing file_manifest_hash")

    actual_content_hash, actual_file_manifest_hash = hash_skill_directory(skill_dir)
    if actual_content_hash != expected_content_hash:
        raise SkillStorageMigrationError("Skill storage content_hash mismatch")
    if actual_file_manifest_hash != expected_file_manifest_hash:
        raise SkillStorageMigrationError("Skill storage file_manifest_hash mismatch")


def migrate_skill_version_storage_item(
    skills_root: Path,
    item: SkillVersionStorageMigrationItem,
) -> SkillVersionStorageMigrationResult:
    """Copy or verify one legacy SkillVersion directory into terminal storage."""
    source_relative_path = _normalize_relative_path(item.source_path)
    terminal_relative_path = build_terminal_skill_version_relative_path(item.skill_id, item.version_number)

    if source_relative_path != terminal_relative_path and not _is_legacy_skill_source_path(source_relative_path):
        raise SkillStorageMigrationError(f"Unsupported legacy Skill source path: {item.source_path}")

    source_dir = resolve_skill_storage_dir(skills_root, source_relative_path)
    terminal_dir = resolve_skill_storage_dir(skills_root, terminal_relative_path)

    if terminal_dir.exists():
        _verify_skill_directory(
            terminal_dir,
            expected_content_hash=item.content_hash,
            expected_file_manifest_hash=item.file_manifest_hash,
        )
        return SkillVersionStorageMigrationResult(source_path=source_relative_path, terminal_path=terminal_relative_path, action="verified")

    if not source_dir.exists():
        raise SkillStorageMigrationError(f"Legacy Skill source path is missing: {source_relative_path}")
    _verify_skill_directory(
        source_dir,
        expected_content_hash=item.content_hash,
        expected_file_manifest_hash=item.file_manifest_hash,
    )

    terminal_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_dir, terminal_dir)
    try:
        _verify_skill_directory(
            terminal_dir,
            expected_content_hash=item.content_hash,
            expected_file_manifest_hash=item.file_manifest_hash,
        )
    except Exception:
        shutil.rmtree(terminal_dir, ignore_errors=True)
        raise
    return SkillVersionStorageMigrationResult(source_path=source_relative_path, terminal_path=terminal_relative_path, action="copied")


def migrate_skill_version_storage(
    skills_root: Path,
    items: list[SkillVersionStorageMigrationItem],
) -> list[SkillVersionStorageMigrationResult]:
    """Copy or verify legacy SkillVersion directories into terminal storage."""
    return [migrate_skill_version_storage_item(skills_root, item) for item in items]
