import asyncio
import json
import logging
import re
import secrets
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

import yaml
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.background import BackgroundTask

from app.gateway.db.models import Agent, PendingSkillForkClaim, Skill, SkillDefinition, SkillInstall, SkillRelease, SkillVersion, User
from app.gateway.db.repository import (
    PendingSkillForkClaimRepository,
    SkillDefinitionRepository,
    SkillInstallRepository,
    SkillReleaseRepository,
    SkillRepository,
    SkillVersionRepository,
    is_system_skill_definition,
)
from app.gateway.deps import get_current_user, get_db
from app.gateway.path_utils import resolve_thread_virtual_path
from deerflow.config import get_app_config
from deerflow.skills.hashing import hash_skill_directory
from deerflow.skills.installer import SkillAlreadyExistsError, install_skill_from_archive
from deerflow.skills.path_utils import (
    build_private_skill_file_path,
    build_public_skill_file_path,
    normalize_skill_file_path,
    resolve_skill_storage_dir,
)
from deerflow.skills.validation import ALLOWED_FRONTMATTER_PROPERTIES, validate_optional_frontmatter_metadata

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["skills"])

ALLOWED_SKILL_FRONTMATTER_KEYS = ALLOWED_FRONTMATTER_PROPERTIES

SkillSpace = Literal["system", "community", "personal"]
SkillSourceKind = Literal["official", "community", "personal", "fork"]
SkillViewerRelation = Literal[
    "system_available",
    "official_available",
    "community_available",
    "downloaded",
    "authored",
    "authored_published",
    "authored_unpublished_changes",
    "update_available",
    "forked",
]

_FORK_SOURCE_VERSION_KEYS = ("source_version_id", "source_version", "skill_version_id", "skill_version")
_FORK_SOURCE_VERSION_RE = re.compile(r"(?:^|[;,\s|])(?:source[_-]?version(?:[_-]?id)?|skill[_-]?version(?:[_-]?id)?)[:=#](\d+)(?:$|[;,\s|])")
_FORK_METADATA_RELATIVE_PATH = Path(".deerflow") / "fork.json"
_FORK_METADATA_KIND = "deerflow.skill.fork"
_FORK_CLAIM_EXPIRY_DAYS = 90


@dataclass(frozen=True)
class ParsedForkClaim:
    """Fork claim payload carried inside an uploaded package."""

    claim_id: int
    claim_token: str
    source_skill_definition_id: int | None
    source_skill_version_id: int | None


@dataclass(frozen=True)
class ValidatedForkClaim:
    """Server-validated fork claim used to classify uploaded Skill content."""

    claim: PendingSkillForkClaim
    source_version: SkillVersion
    source_identifier: str


class SkillResponse(BaseModel):
    """Response model for skill information."""

    name: str = Field(..., description="Name of the skill")
    description: str = Field(..., description="Description of what the skill does")
    license: str | None = Field(None, description="License information")
    category: str = Field(..., description="Category of the skill (public or custom)")
    space: SkillSpace = Field(..., description="User-facing space for this row")
    source_kind: SkillSourceKind = Field(..., description="User-facing source kind for display")
    viewer_relation: SkillViewerRelation = Field(..., description="Current user's relation to this row")
    enabled: bool = Field(default=True, description="Whether this skill is enabled")
    owner_user_id: int | None = Field(default=None, description="Publisher user ID for public skills")
    owner_display_name: str | None = Field(default=None, description="Publisher display name for public skills")
    version: str | None = Field(default=None, description="Platform-managed version number for the skill")
    platform_version: int | None = Field(default=None, description="Platform-managed immutable content version")
    skill_definition_id: int | None = Field(default=None, description="Stable platform skill definition ID")
    skill_definition_source_type: str | None = Field(default=None, description="Stable skill definition source namespace type")
    skill_definition_source_identifier: str | None = Field(default=None, description="Stable skill definition source namespace identifier")
    skill_version_id: int | None = Field(default=None, description="Immutable platform skill version ID")
    skill_install_id: int | None = Field(default=None, description="Current user's install ID when installed")
    current_platform_version: int | None = Field(default=None, description="Current installed platform version")
    installed_platform_version: int | None = Field(default=None, description="Initially installed platform version")
    latest_platform_version: int | None = Field(default=None, description="Newest published platform version available to this install")
    update_available: bool | None = Field(default=None, description="Whether the current install can be updated")
    source_package_version: str | None = Field(default=None, description="Optional SKILL.md source package version metadata")
    package_version: str | None = Field(default=None, description="Deprecated alias for source_package_version; not platform version")
    release_version: str | None = Field(default=None, description="System-generated publish-event identifier")
    release_status: str | None = Field(default=None, description="Release status")
    release_notes: str | None = Field(default=None, description="Optional notes attached to the publish event")
    published_at: str | None = Field(default=None, description="Release publish timestamp")
    fork_source_skill_name: str | None = Field(default=None, description="Original source Skill name for forked rows")
    fork_source_owner_display_name: str | None = Field(default=None, description="Original source author display name for forked rows")
    fork_source_platform_version: int | None = Field(default=None, description="Original source platform version for forked rows")
    fork_source_skill_version_id: int | None = Field(default=None, description="Original source SkillVersion ID for forked rows")


def _display_name_for_user(user: User | None) -> str | None:
    if user is None:
        return None
    display_name = (user.display_name or "").strip()
    return display_name or user.username


def _display_name_for_source_version(version: SkillVersion | None) -> str | None:
    definition = version.definition if version is not None else None
    if definition is None:
        return None
    owner_display_name = _display_name_for_user(definition.owner_user)
    if owner_display_name is not None:
        return owner_display_name
    if definition.source_type == "legacy" and definition.source_identifier == "legacy":
        return "official"
    return None


def _is_official_skill_source(skill: Skill, definition: SkillDefinition | None) -> bool:
    if definition is not None:
        return is_system_skill_definition(definition)
    return skill.user_id is None and skill.owner_user_id is None


def _is_authored_by_current_user(skill: Skill, definition: SkillDefinition | None, current_user_id: int | None) -> bool:
    if current_user_id is None:
        return False
    if definition is not None:
        return definition.owner_user_id == current_user_id
    if skill.user_id is None:
        return skill.owner_user_id == current_user_id
    return skill.user_id == current_user_id


def _derive_skill_source_kind(
    *,
    skill: Skill,
    definition: SkillDefinition | None,
    space: SkillSpace,
    authored_by_current_user: bool,
) -> SkillSourceKind:
    if _is_official_skill_source(skill, definition):
        return "official"
    if definition is not None and definition.source_type == "fork":
        return "fork"
    if space == "personal" and authored_by_current_user:
        return "personal"
    return "community"


def _derive_skill_viewer_relation(
    *,
    space: SkillSpace,
    source_kind: SkillSourceKind,
    authored_by_current_user: bool,
    release: SkillRelease | None,
    skill_version: SkillVersion | None,
    latest_skill_version: SkillVersion | None,
    update_available: bool | None,
) -> SkillViewerRelation:
    if source_kind == "fork":
        return "forked"

    if space == "system":
        return "system_available"

    if space == "community":
        if authored_by_current_user:
            return "authored_published"
        if update_available is True:
            return "update_available"
        if source_kind == "official":
            return "official_available"
        return "community_available"

    if authored_by_current_user:
        if release is not None and skill_version is not None and latest_skill_version is not None and latest_skill_version.id != skill_version.id:
            return "authored_unpublished_changes"
        if release is not None and release.status == "published":
            return "authored_published"
        return "authored"

    if update_available is True:
        return "update_available"
    return "downloaded"


class SkillsListResponse(BaseModel):
    """Response model for listing all skills."""

    skills: list[SkillResponse]


class SkillUpdateRequest(BaseModel):
    """Request model for updating a skill."""

    enabled: bool = Field(..., description="Whether to enable or disable the skill")


class SkillPublishRequest(BaseModel):
    """Request body for publishing the current installed SkillVersion to SkillHub."""

    release_notes: str | None = Field(
        default=None,
        max_length=4000,
        description="Optional notes for this publish event",
    )


class SkillInstallRequest(BaseModel):
    """Request model for installing a skill from a .skill file."""

    thread_id: str = Field(..., description="The thread ID where the .skill file is located")
    path: str = Field(..., description="Virtual path to the .skill file (e.g., mnt/user-data/outputs/my-skill.skill)")


class SkillInstallResponse(BaseModel):
    """Response model for skill installation."""

    success: bool = Field(..., description="Whether the installation was successful")
    skill_name: str = Field(..., description="Name of the installed skill")
    message: str = Field(..., description="Installation result message")


class SkillUploadCheckResponse(BaseModel):
    """Response model for skill upload conflict checks."""

    filename: str = Field(..., description="Original zip filename")
    skill_name: str = Field(..., description="Parsed skill name from SKILL.md")
    package_version: str | None = Field(default=None, description="Deprecated alias for source_package_version")
    source_package_version: str | None = Field(default=None, description="Source version metadata from the uploaded SKILL.md")
    existing_package_version: str | None = Field(default=None, description="Deprecated alias for existing_source_package_version")
    existing_source_package_version: str | None = Field(default=None, description="Current install source package version metadata")
    platform_version: int | None = Field(default=None, description="Platform version that would be used or created")
    same_version: bool = Field(default=False, description="Whether the uploaded canonical content matches an existing platform version")
    exists: bool = Field(..., description="Whether the current user already has this exact active skill version")
    message: str = Field(..., description="Check result message")
    recognized_as: Literal["fork", "original"] = Field(default="original", description="How the upload will be classified when accepted")
    fork_source_name: str | None = Field(default=None, description="Recognized fork source Skill name")
    fork_source_owner_display_name: str | None = Field(default=None, description="Recognized fork source author display name")
    fork_source_platform_version: int | None = Field(default=None, description="Recognized fork source platform version")
    unchanged_from_source: bool = Field(default=False, description="Whether uploaded canonical content is unchanged from the fork source")


class SkillUploadResult(BaseModel):
    """Per-file upload result."""

    filename: str = Field(..., description="Original zip filename")
    skill_name: str | None = Field(default=None, description="Parsed skill name from SKILL.md")
    package_version: str | None = Field(default=None, description="Deprecated alias for source_package_version")
    source_package_version: str | None = Field(default=None, description="Source version metadata from the uploaded SKILL.md")
    platform_version: int | None = Field(default=None, description="Platform version created or reused")
    skill_version_id: int | None = Field(default=None, description="Immutable platform SkillVersion ID created or reused")
    action: str | None = Field(default=None, description="Upload action: created, updated, or skipped")
    success: bool = Field(..., description="Whether the upload succeeded")
    message: str = Field(..., description="Upload result message")
    recognized_as: Literal["fork", "original"] | None = Field(default=None, description="How the uploaded skill was classified")


class SkillUploadResponse(BaseModel):
    """Response model for bulk skill uploads."""

    results: list[SkillUploadResult]


class SkillDownloadCheckRequest(BaseModel):
    """Compatibility request body for checking whether a SkillHub install will conflict."""

    owner_user_id: int | None = Field(
        default=None,
        description="Deprecated compatibility field. Public skill lookup now uses only skill_name.",
    )
    skill_definition_id: int | None = Field(
        default=None,
        description="Selected public SkillDefinition ID used to disambiguate same-name Community Skills.",
    )


class SkillDownloadCheckResponse(BaseModel):
    """Response model for SkillHub install conflict checks."""

    skill_name: str = Field(..., description="Target custom skill name")
    exists: bool = Field(..., description="Whether the current user already has a custom skill with that name")
    message: str = Field(..., description="Check result message")


class SkillDownloadRequest(BaseModel):
    """Compatibility request body for installing a SkillHub skill."""

    owner_user_id: int | None = Field(
        default=None,
        description="Deprecated compatibility field. Public skill lookup now uses only skill_name.",
    )
    skill_definition_id: int | None = Field(
        default=None,
        description="Selected public SkillDefinition ID used to disambiguate same-name Community Skills.",
    )
    overwrite: bool = Field(default=False, description="Whether to overwrite an existing same-name custom skill")


class SkillForkPackageRequest(BaseModel):
    """Request body for exporting an editable fork package."""

    owner_user_id: int | None = Field(
        default=None,
        description="Publisher owner used to disambiguate same-name Community Skills.",
    )
    skill_definition_id: int | None = Field(
        default=None,
        description="Selected public SkillDefinition ID used to disambiguate same-name Community Skills.",
    )


class SkillInstallUpdateRequest(BaseModel):
    """Request body for explicitly updating an installed skill."""

    skill_install_id: int | None = Field(default=None, description="Selected SkillInstall ID used to disambiguate same-name installs")
    skill_version_id: int | None = Field(default=None, description="Specific platform SkillVersion ID; latest published version is used when omitted")


class SkillUpdateAffectedAgent(BaseModel):
    """Agent affected by an installed Skill update."""

    id: int = Field(..., description="Agent ID")
    name: str = Field(..., description="Agent name")


class SkillInstallUpdatePreviewResponse(BaseModel):
    """Read-only preview for an installed Skill update."""

    skill_name: str = Field(..., description="Skill name")
    skill_install_id: int = Field(..., description="Install ID that would be updated")
    current_skill_version_id: int = Field(..., description="Current installed SkillVersion ID")
    target_skill_version_id: int | None = Field(default=None, description="Target SkillVersion ID when available")
    current_platform_version: int = Field(..., description="Current installed platform version")
    target_platform_version: int | None = Field(default=None, description="Available platform version when update can proceed")
    update_available: bool = Field(..., description="Whether the target version differs from the install current version")
    status: str = Field(..., description="available, up_to_date, or unavailable")
    message: str = Field(..., description="User-correctable update state")
    release_notes: str | None = Field(default=None, description="Publish notes attached to the target version")
    published_at: str | None = Field(default=None, description="Publish timestamp for the target version")
    publisher: str | None = Field(default=None, description="Publisher display name")
    source: str = Field(..., description="Skill source label")
    affected_agents: list[SkillUpdateAffectedAgent] = Field(default_factory=list, description="Agents bound to this install")


def _skill_to_response(
    skill: Skill,
    release: SkillRelease | None = None,
    package_version: str | None = None,
    skill_version: SkillVersion | None = None,
    skill_install: SkillInstall | None = None,
    latest_skill_version: SkillVersion | None = None,
    current_user_id: int | None = None,
    fork_source_version: SkillVersion | None = None,
) -> SkillResponse:
    """Convert a database skill row to the API response model."""
    release_package_version = getattr(release, "package_version", None) if release is not None else None
    version_source_package = None
    if skill_version is not None:
        version_source_package = skill_version.source_package_version
    response_package_version = version_source_package if skill_version is not None else (release_package_version if release is not None else package_version)
    release_version = getattr(release, "release_version", None) if release is not None else None
    release_status = getattr(release, "status", None) if release is not None else None
    release_created_at = getattr(release, "created_at", None) if release is not None else None
    release_notes = getattr(release, "release_notes", None) if release is not None else None
    published_at = release_created_at.isoformat() if release_created_at is not None else None
    platform_version = skill_version.version_number if skill_version is not None else None
    definition = skill_version.definition if skill_version is not None and skill_version.definition is not None else skill.definition
    definition_id = skill_version.skill_definition_id if skill_version is not None else skill.skill_definition_id
    current_platform_version = skill_install.current_version.version_number if skill_install is not None and skill_install.current_version is not None else None
    installed_platform_version = skill_install.installed_version.version_number if skill_install is not None and skill_install.installed_version is not None else current_platform_version
    latest_platform_version = latest_skill_version.version_number if latest_skill_version is not None else None
    base_space: SkillSpace = "community" if skill.user_id is None else "personal"
    authored_by_current_user = _is_authored_by_current_user(skill, definition, current_user_id)
    update_available = None
    if skill_install is not None and latest_skill_version is not None and not authored_by_current_user:
        update_available = skill_install.current_version_id != latest_skill_version.id
    source_kind = _derive_skill_source_kind(
        skill=skill,
        definition=definition,
        space=base_space,
        authored_by_current_user=authored_by_current_user,
    )
    space: SkillSpace = "system" if source_kind == "official" else base_space
    if source_kind == "official":
        skill_install = None
        current_platform_version = None
        installed_platform_version = None
        update_available = None
    viewer_relation = _derive_skill_viewer_relation(
        space=space,
        source_kind=source_kind,
        authored_by_current_user=authored_by_current_user,
        release=release,
        skill_version=skill_version,
        latest_skill_version=latest_skill_version,
        update_available=update_available,
    )
    owner_display_name = _display_name_for_user(skill.owner_user)
    if owner_display_name is None and release is not None:
        owner_display_name = _display_name_for_user(release.publisher_user)
    if owner_display_name is None and definition is not None:
        owner_display_name = _display_name_for_user(definition.owner_user)
    if source_kind == "official":
        owner_display_name = owner_display_name or "official"

    return SkillResponse(
        name=skill.name,
        description=skill.description or "",
        license=None,
        category="public" if skill.user_id is None else "custom",
        space=space,
        source_kind=source_kind,
        viewer_relation=viewer_relation,
        enabled=True,
        owner_user_id=skill.owner_user_id,
        owner_display_name=owner_display_name,
        version=str(platform_version) if platform_version is not None else None,
        platform_version=platform_version,
        skill_definition_id=definition_id,
        skill_definition_source_type=definition.source_type if definition is not None else None,
        skill_definition_source_identifier=definition.source_identifier if definition is not None else None,
        skill_version_id=skill_version.id if skill_version is not None else None,
        skill_install_id=skill_install.id if skill_install is not None else None,
        current_platform_version=current_platform_version,
        installed_platform_version=installed_platform_version,
        latest_platform_version=latest_platform_version,
        update_available=update_available,
        source_package_version=response_package_version,
        package_version=response_package_version,
        release_version=release_version,
        release_status=release_status,
        release_notes=release_notes,
        published_at=published_at,
        fork_source_skill_name=fork_source_version.definition.name if fork_source_version is not None and fork_source_version.definition is not None else None,
        fork_source_owner_display_name=_display_name_for_source_version(fork_source_version),
        fork_source_platform_version=fork_source_version.version_number if fork_source_version is not None else None,
        fork_source_skill_version_id=fork_source_version.id if fork_source_version is not None else None,
    )


def _extract_package_version_for_skill(skill: Skill) -> str | None:
    """Best-effort source package metadata extraction for legacy custom rows."""
    try:
        skill_dir = _resolve_skill_record_dir(skill)
        return _extract_package_version_from_dir(skill_dir)
    except Exception:
        return None


def _extract_package_version_from_dir(skill_dir: Path) -> str | None:
    """Read the optional source package metadata from a skill directory."""
    frontmatter = _extract_frontmatter(skill_dir / "SKILL.md")
    package_version = frontmatter.get("version")
    return package_version if isinstance(package_version, str) else None


async def _skill_to_response_with_metadata(db: AsyncSession, skill: Skill, *, current_user_id: int | None = None) -> SkillResponse:
    """Convert a skill row to API response with best-effort version metadata."""
    if skill.user_id is None and skill.id is not None:
        release = await SkillReleaseRepository.get_latest_release_for_public_skill(db, published_skill_id=skill.id)
        skill_version = None
        if release is not None and release.skill_version_id is not None:
            skill_version = await SkillVersionRepository.get_by_id(db, skill_version_id=release.skill_version_id)
        install = (
            await SkillInstallRepository.get_by_user_and_definition(
                db,
                user_id=current_user_id,
                skill_definition_id=skill_version.skill_definition_id,
            )
            if current_user_id is not None and skill_version is not None
            else None
        )
        fork_source_version = await _get_recorded_fork_source_version(db, skill_version.definition) if skill_version is not None and skill_version.definition is not None else None
        return _skill_to_response(skill, release=release, skill_version=skill_version, skill_install=install, latest_skill_version=skill_version, current_user_id=current_user_id, fork_source_version=fork_source_version)
    install = None
    if skill.user_id is not None:
        if skill.skill_definition_id is not None:
            install = await SkillInstallRepository.get_by_user_and_definition(
                db,
                user_id=skill.user_id,
                skill_definition_id=skill.skill_definition_id,
            )
        else:
            install = await SkillInstallRepository.get_by_user_and_name(db, user_id=skill.user_id, name=skill.name)
    if install is not None:
        latest_release = await SkillReleaseRepository.get_latest_published_release_for_definition(
            db,
            skill_definition_id=install.skill_definition_id,
        )
        latest_version = latest_release.skill_version if latest_release is not None else None
        definition = install.definition or (install.current_version.definition if install.current_version is not None else None)
        fork_source_version = await _get_recorded_fork_source_version(db, definition) if definition is not None else None
        return _skill_to_response(skill, release=latest_release, skill_version=install.current_version, skill_install=install, latest_skill_version=latest_version, current_user_id=current_user_id, fork_source_version=fork_source_version)
    return _skill_to_response(skill, package_version=_extract_package_version_for_skill(skill), current_user_id=current_user_id)


def _extract_frontmatter(skill_md_path: Path) -> dict:
    """Parse YAML front matter from SKILL.md."""
    content = skill_md_path.read_text(encoding="utf-8")
    if not content.startswith("---"):
        raise ValueError("No YAML frontmatter found")

    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("No YAML frontmatter found")

    end_index = None
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end_index = index
            break

    if end_index is None:
        raise ValueError("Invalid frontmatter format")

    frontmatter_text = "\n".join(lines[1:end_index])
    try:
        frontmatter = yaml.safe_load(frontmatter_text)
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML in frontmatter: {exc}") from exc

    if not isinstance(frontmatter, dict):
        raise ValueError("Frontmatter must be a YAML dictionary")

    unexpected_keys = set(frontmatter.keys()) - ALLOWED_SKILL_FRONTMATTER_KEYS
    if unexpected_keys:
        raise ValueError(f"Unexpected key(s) in SKILL.md frontmatter: {', '.join(sorted(unexpected_keys))}. Allowed properties are: {', '.join(sorted(ALLOWED_SKILL_FRONTMATTER_KEYS))}")

    metadata_error = validate_optional_frontmatter_metadata(frontmatter)
    if metadata_error:
        raise ValueError(metadata_error)

    return frontmatter


def _validate_skill_directory(skill_dir: Path) -> tuple[str, str]:
    """Validate a skill directory using the same rules as quick_validate.py."""
    skill_md_path = skill_dir / "SKILL.md"
    if not skill_md_path.exists():
        raise ValueError("SKILL.md not found")

    frontmatter = _extract_frontmatter(skill_md_path)

    if "name" not in frontmatter:
        raise ValueError("Missing 'name' in frontmatter")
    if "description" not in frontmatter:
        raise ValueError("Missing 'description' in frontmatter")

    name = frontmatter.get("name", "")
    if not isinstance(name, str):
        raise ValueError(f"Name must be a string, got {type(name).__name__}")
    name = name.strip()
    if not name:
        raise ValueError("Missing 'name' in frontmatter")
    if not __import__("re").match(r"^[a-z0-9-]+$", name):
        raise ValueError(f"Name '{name}' should be kebab-case (lowercase letters, digits, and hyphens only)")
    if name.startswith("-") or name.endswith("-") or "--" in name:
        raise ValueError(f"Name '{name}' cannot start/end with hyphen or contain consecutive hyphens")
    if len(name) > 64:
        raise ValueError(f"Name is too long ({len(name)} characters). Maximum is 64 characters.")

    description = frontmatter.get("description", "")
    if not isinstance(description, str):
        raise ValueError(f"Description must be a string, got {type(description).__name__}")
    description = description.strip()
    if "<" in description or ">" in description:
        raise ValueError("Description cannot contain angle brackets (< or >)")
    if len(description) > 1024:
        raise ValueError(f"Description is too long ({len(description)} characters). Maximum is 1024 characters.")

    compatibility = frontmatter.get("compatibility", "")
    if compatibility:
        if not isinstance(compatibility, str):
            raise ValueError(f"Compatibility must be a string, got {type(compatibility).__name__}")
        if len(compatibility) > 500:
            raise ValueError(f"Compatibility is too long ({len(compatibility)} characters). Maximum is 500 characters.")

    return name, description


def _extract_publish_metadata(skill_dir: Path, *, expected_name: str) -> dict[str, str | None]:
    """Validate publish metadata and return fields captured for a SkillHub release."""
    name, description = _validate_skill_directory(skill_dir)
    if name != expected_name:
        raise ValueError(f"Skill metadata name '{name}' does not match requested skill '{expected_name}'")

    frontmatter = _extract_frontmatter(skill_dir / "SKILL.md")
    package_version = frontmatter.get("version")
    if package_version is not None and not isinstance(package_version, str):
        raise ValueError(f"Version must be a string, got {type(package_version).__name__}")
    return {
        "name": name,
        "description": description,
        "package_version": package_version,
    }


def _normalize_release_notes(release_notes: str | None) -> str | None:
    """Normalize and validate optional publish-event release notes."""
    if release_notes is None:
        return None
    normalized = release_notes.strip()
    if not normalized:
        return None
    if len(normalized) > 4000:
        raise ValueError("Release notes are too long. Maximum is 4000 characters.")
    return normalized


def _safe_extract_archive(archive_path: Path, destination_dir: Path) -> None:
    """Safely extract a zip archive into a destination directory."""
    with zipfile.ZipFile(archive_path, "r") as zip_ref:
        for member in zip_ref.infolist():
            member_path = Path(member.filename)
            if member_path.is_absolute() or ".." in member_path.parts:
                raise ValueError("Archive contains unsafe paths")
            zip_ref.extract(member, destination_dir)


def _resolve_skill_root_dir(extracted_root: Path) -> Path:
    """Resolve the single skill root directory from an extracted zip archive."""
    top_level_dirs: set[str] = set()
    root_level_files: list[str] = []

    for entry in extracted_root.rglob("*"):
        if entry.is_dir():
            continue

        relative_path = entry.relative_to(extracted_root)
        if not relative_path.parts:
            continue
        if relative_path.parts[0] == "__MACOSX":
            continue

        if len(relative_path.parts) == 1:
            root_level_files.append(relative_path.as_posix())
            continue

        top_level_dirs.add(relative_path.parts[0])

    if root_level_files:
        raise ValueError("Zip root must contain exactly one skill folder")
    if len(top_level_dirs) != 1:
        raise ValueError("Zip must contain exactly one skill folder")

    skill_dir = extracted_root / next(iter(top_level_dirs))
    if not skill_dir.is_dir():
        raise ValueError("Skill folder not found after extraction")
    return skill_dir


def _get_skills_root_dir() -> Path:
    """Return the shared skills root used by gateway and sandbox."""
    return get_app_config().skills.get_skills_path()


def _resolve_skill_dir(file_path: str) -> Path:
    """Resolve a stored skill path to a concrete directory."""
    return resolve_skill_storage_dir(_get_skills_root_dir(), file_path)


def _resolve_skill_record_dir(skill: Skill) -> Path:
    """Resolve a DB-backed skill record to its concrete directory."""
    raw_path = Path(skill.file_path)
    if raw_path.is_absolute():
        return raw_path.resolve()
    return _resolve_skill_dir(
        normalize_skill_file_path(
            skill.file_path,
            user_id=skill.user_id,
            skill_name=skill.name,
        )
    )


def _is_skill_version_artifact_available(version: SkillVersion) -> bool:
    """Return whether an immutable SkillVersion artifact can be used exactly."""
    try:
        artifact_dir = _resolve_skill_dir(version.artifact_uri)
    except Exception:
        return False
    return artifact_dir.is_dir() and (artifact_dir / "SKILL.md").is_file()


def _format_publisher(release: SkillRelease | None) -> str | None:
    publisher = release.publisher_user if release is not None else None
    if publisher is None:
        return None
    display_name = (publisher.display_name or "").strip()
    return display_name or publisher.username


async def _get_user_skill_by_definition_or_legacy(
    db: AsyncSession,
    *,
    user_id: int,
    skill_name: str,
    skill_definition_id: int,
) -> Skill | None:
    """Resolve a user skill by concrete definition, falling back only to legacy name-only rows."""
    skill = await SkillRepository.get_user_skill_by_definition(
        db,
        user_id=user_id,
        skill_definition_id=skill_definition_id,
    )
    if skill is not None:
        return skill

    for candidate in await SkillRepository.list_user_skills_by_name(db, user_id=user_id, name=skill_name):
        if candidate.skill_definition_id is None:
            return candidate
    return None


async def _get_single_install_by_name(
    db: AsyncSession,
    *,
    user_id: int,
    skill_name: str,
) -> SkillInstall:
    installs = await SkillInstallRepository.list_by_user_and_name(db, user_id=user_id, name=skill_name)
    if not installs:
        raise HTTPException(status_code=404, detail=f"Skill install '{skill_name}' not found")
    if len(installs) > 1:
        raise HTTPException(status_code=400, detail=f"Skill install '{skill_name}' is ambiguous; submit a skill_install_id-aware request")
    install = installs[0]
    if install.current_version is None:
        raise HTTPException(status_code=409, detail=f"Skill install '{skill_name}' has no current version")
    return install


async def _get_update_install(
    db: AsyncSession,
    *,
    user_id: int,
    skill_name: str,
    skill_install_id: int | None,
) -> SkillInstall:
    """Resolve an installed Skill for update, preferring stable install identity."""
    if skill_install_id is None:
        return await _get_single_install_by_name(db, user_id=user_id, skill_name=skill_name)

    install = await SkillInstallRepository.get_by_id_for_user(db, user_id=user_id, skill_install_id=skill_install_id)
    if install is None:
        raise HTTPException(status_code=404, detail=f"Skill install '{skill_install_id}' not found")
    definition = install.definition or (install.current_version.definition if install.current_version is not None else None)
    if definition is None or definition.name != skill_name:
        raise HTTPException(status_code=404, detail=f"Skill install '{skill_install_id}' not found for '{skill_name}'")
    if install.current_version is None:
        raise HTTPException(status_code=409, detail=f"Skill install '{skill_name}' has no current version")
    return install


def _definition_is_publishable_by_user(definition: SkillDefinition, *, user_id: int) -> bool:
    """Return whether a definition represents a current-user authored publish target."""
    if definition.owner_user_id != user_id:
        return False
    if definition.source_type == "user":
        return definition.source_identifier == str(user_id)
    return definition.source_type == "fork"


async def _resolve_publish_definition_or_reject_downloaded(
    db: AsyncSession,
    *,
    user_id: int,
    skill_name: str,
) -> SkillDefinition | None:
    """Resolve the current user's publishable definition, or reject downloaded same-name installs."""
    definition = await SkillDefinitionRepository.get_by_name_and_owner(db, name=skill_name, owner_user_id=user_id)
    if definition is not None:
        return definition

    publishable_definitions: list[SkillDefinition] = []
    downloaded_install_found = False
    for install in await SkillInstallRepository.list_by_user_and_name(db, user_id=user_id, name=skill_name):
        definition = install.definition or (install.current_version.definition if install.current_version is not None else None)
        if definition is None:
            continue
        if _definition_is_publishable_by_user(definition, user_id=user_id):
            publishable_definitions.append(definition)
        else:
            downloaded_install_found = True

    unique_publishable = {definition.id: definition for definition in publishable_definitions if definition.id is not None}
    if len(unique_publishable) == 1:
        return next(iter(unique_publishable.values()))
    if len(unique_publishable) > 1:
        raise HTTPException(status_code=400, detail=f"Skill '{skill_name}' has multiple authored definitions; submit a definition-aware publish request")
    if downloaded_install_found:
        raise HTTPException(status_code=403, detail=f"Skill '{skill_name}' was downloaded from Community Space. Create your own version before publishing it.")
    return None


def _parse_recorded_source_version_id(source_identifier: str | None) -> int | None:
    """Extract a recorded source SkillVersion ID from fork attribution when present."""
    if not source_identifier:
        return None
    source_identifier = source_identifier.strip()
    if not source_identifier:
        return None

    try:
        parsed_identifier = json.loads(source_identifier)
    except json.JSONDecodeError:
        parsed_identifier = None
    if isinstance(parsed_identifier, dict):
        for key in _FORK_SOURCE_VERSION_KEYS:
            raw_value = parsed_identifier.get(key)
            if raw_value is None:
                continue
            try:
                source_version_id = int(raw_value)
            except (TypeError, ValueError):
                continue
            return source_version_id if source_version_id > 0 else None

    match = _FORK_SOURCE_VERSION_RE.search(source_identifier)
    if match is None:
        return None
    source_version_id = int(match.group(1))
    return source_version_id if source_version_id > 0 else None


async def _get_recorded_fork_source_version(db: AsyncSession, definition: SkillDefinition) -> SkillVersion | None:
    """Load the source version recorded by a fork definition, if current attribution encodes one."""
    if definition.source_type != "fork":
        return None
    source_version_id = _parse_recorded_source_version_id(definition.source_identifier)
    if source_version_id is None:
        return None
    return await SkillVersionRepository.get_by_id(db, skill_version_id=source_version_id)


async def _reject_unchanged_fork_publish(
    db: AsyncSession,
    *,
    definition: SkillDefinition,
    current_version: SkillVersion,
) -> None:
    """Hard-block an attributed fork whose current content is exactly unchanged from its source."""
    source_version = await _get_recorded_fork_source_version(db, definition)
    if source_version is None:
        return
    same_file_manifest = bool(current_version.file_manifest_hash) and current_version.file_manifest_hash == source_version.file_manifest_hash
    same_content = bool(current_version.content_hash) and current_version.content_hash == source_version.content_hash
    if same_file_manifest or same_content:
        raise HTTPException(status_code=409, detail=f"Skill '{definition.name}' is unchanged from its source version. Modify it before publishing to Community Space.")


def _affected_agent_to_response(agent: Agent) -> SkillUpdateAffectedAgent:
    return SkillUpdateAffectedAgent(id=agent.id, name=agent.name)


async def _build_skill_update_preview(
    db: AsyncSession,
    *,
    skill_name: str,
    current_user: User,
    skill_install_id: int | None = None,
    install: SkillInstall | None = None,
    target_version: SkillVersion | None = None,
    target_release: SkillRelease | None = None,
) -> SkillInstallUpdatePreviewResponse:
    """Build a read-only update preview for the current user's install."""
    if install is None:
        install = await _get_update_install(db, user_id=current_user.id, skill_name=skill_name, skill_install_id=skill_install_id)

    release = target_release
    if target_version is None:
        release = await SkillReleaseRepository.get_latest_published_release_for_definition(
            db,
            skill_definition_id=install.skill_definition_id,
        )
        target_version = release.skill_version if release is not None else None
    elif target_version.skill_definition_id != install.skill_definition_id:
        raise HTTPException(status_code=404, detail=f"Skill version '{target_version.id}' not found for '{skill_name}'")

    affected_agents = [
        _affected_agent_to_response(agent)
        for agent in await SkillRepository.list_bound_agents_for_install(
            db,
            user_id=current_user.id,
            skill_install_id=install.id,
        )
    ]

    current_artifact_available = _is_skill_version_artifact_available(install.current_version)

    if target_version is None:
        if not current_artifact_available:
            return SkillInstallUpdatePreviewResponse(
                skill_name=skill_name,
                skill_install_id=install.id,
                current_skill_version_id=install.current_version.id,
                target_skill_version_id=None,
                current_platform_version=install.current_version.version_number,
                target_platform_version=None,
                update_available=False,
                status="unavailable",
                message=f"Current installed version {install.current_version.version_number} is unavailable.",
                source="SkillHub",
                affected_agents=affected_agents,
            )
        return SkillInstallUpdatePreviewResponse(
            skill_name=skill_name,
            skill_install_id=install.id,
            current_skill_version_id=install.current_version.id,
            target_skill_version_id=None,
            current_platform_version=install.current_version.version_number,
            target_platform_version=None,
            update_available=False,
            status="unavailable",
            message=f"No published update found for '{skill_name}'",
            source="SkillHub",
            affected_agents=affected_agents,
        )

    target_artifact_available = _is_skill_version_artifact_available(target_version)
    update_available = install.current_version_id != target_version.id
    artifact_available = current_artifact_available and target_artifact_available
    status = "available" if update_available and artifact_available else "up_to_date"
    message = f"Version {target_version.version_number} is available."
    if not current_artifact_available:
        status = "unavailable"
        message = f"Current installed version {install.current_version.version_number} is unavailable."
    elif not update_available:
        message = f"Skill '{skill_name}' is already on version {install.current_version.version_number}."
    elif not target_artifact_available:
        status = "unavailable"
        message = f"Version {target_version.version_number} is unavailable."

    return SkillInstallUpdatePreviewResponse(
        skill_name=skill_name,
        skill_install_id=install.id,
        current_skill_version_id=install.current_version.id,
        target_skill_version_id=target_version.id,
        current_platform_version=install.current_version.version_number,
        target_platform_version=target_version.version_number,
        update_available=update_available and artifact_available,
        status=status,
        message=message,
        release_notes=release.release_notes if release is not None else None,
        published_at=release.created_at.isoformat() if release is not None and release.created_at is not None else None,
        publisher=_format_publisher(release),
        source="SkillHub",
        affected_agents=affected_agents,
    )


def _replace_skill_directory(source_dir: Path, target_dir: Path) -> None:
    """Replace a target skill directory with the contents of source_dir."""
    if not source_dir.exists() or not source_dir.is_dir():
        raise ValueError(f"Skill directory '{source_dir}' does not exist")
    if target_dir.exists():
        shutil.rmtree(target_dir)
    target_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_dir, target_dir)


def _hash_skill_directory(skill_dir: Path) -> tuple[str, str]:
    """Compute canonical content and raw file-manifest hashes for a skill dir."""
    return hash_skill_directory(skill_dir)


def _build_version_artifact_uri(*, definition_id: int, version_number: int, content_hash: str, skill_name: str) -> str:
    """Build the immutable artifact path for a platform SkillVersion."""
    return f"artifacts/skills/{definition_id}/v{version_number}-{content_hash[:12]}/{skill_name}"


def _copy_version_artifact(source_dir: Path, artifact_uri: str) -> None:
    """Copy a skill directory into its immutable artifact path."""
    target_dir = _resolve_skill_dir(artifact_uri)
    if target_dir.exists():
        return
    target_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_dir, target_dir)


def _load_uploaded_fork_claim(skill_dir: Path) -> ParsedForkClaim | None:
    """Read the optional fork claim sidecar from an extracted Skill package."""
    claim_path = skill_dir / _FORK_METADATA_RELATIVE_PATH
    if not claim_path.exists():
        return None
    try:
        raw_claim = json.loads(claim_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("Invalid fork claim metadata") from exc
    if not isinstance(raw_claim, dict) or raw_claim.get("kind") != _FORK_METADATA_KIND:
        raise ValueError("Invalid fork claim metadata")

    raw_claim_id = raw_claim.get("claim_id")
    raw_token = raw_claim.get("claim_token")
    try:
        claim_id = int(raw_claim_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid fork claim metadata") from exc
    if claim_id <= 0 or not isinstance(raw_token, str) or not raw_token.strip():
        raise ValueError("Invalid fork claim metadata")

    def optional_int(value: object) -> int | None:
        if value is None:
            return None
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None

    return ParsedForkClaim(
        claim_id=claim_id,
        claim_token=raw_token,
        source_skill_definition_id=optional_int(raw_claim.get("source_skill_definition_id")),
        source_skill_version_id=optional_int(raw_claim.get("source_skill_version_id")),
    )


def _build_fork_source_identifier(*, claim: PendingSkillForkClaim, source_version: SkillVersion) -> str:
    """Build the compact, server-authored fork source namespace identifier."""
    payload = {
        "source_version_id": source_version.id,
        "source_definition_id": source_version.skill_definition_id,
        "fork_claim_id": claim.id,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


async def _validate_uploaded_fork_claim(
    db: AsyncSession,
    *,
    parsed_claim: ParsedForkClaim | None,
    user_id: int,
) -> ValidatedForkClaim | None:
    """Validate a package-carried fork claim against server-side state."""
    if parsed_claim is None:
        return None

    now = datetime.now(UTC)
    claim = await PendingSkillForkClaimRepository.get_valid_claim(
        db,
        claim_id=parsed_claim.claim_id,
        user_id=user_id,
        claim_token=parsed_claim.claim_token,
        now=now,
    )
    if claim is None or claim.source_version is None:
        raise ValueError("Fork claim is invalid or expired. Create a new editable copy, then upload again.")

    source_version = claim.source_version
    if parsed_claim.source_skill_version_id is not None and parsed_claim.source_skill_version_id != source_version.id:
        raise ValueError("Fork claim source does not match the exported Skill package")
    if parsed_claim.source_skill_definition_id is not None and parsed_claim.source_skill_definition_id != source_version.skill_definition_id:
        raise ValueError("Fork claim source does not match the exported Skill package")

    return ValidatedForkClaim(
        claim=claim,
        source_version=source_version,
        source_identifier=_build_fork_source_identifier(claim=claim, source_version=source_version),
    )


def _fork_source_message_parts(validated_claim: ValidatedForkClaim | None) -> tuple[str | None, str | None, int | None]:
    if validated_claim is None:
        return None, None, None
    source_version = validated_claim.source_version
    source_definition = source_version.definition
    source_name = source_definition.name if source_definition is not None else None
    source_owner = _display_name_for_source_version(source_version)
    return source_name, source_owner, source_version.version_number


def _delete_skill_directory(target_dir: Path) -> None:
    """Delete a skill directory if it exists."""
    if target_dir.exists():
        shutil.rmtree(target_dir)


def _backup_skill_directory(target_dir: Path) -> tuple[tempfile.TemporaryDirectory[str], Path | None]:
    """Create a temporary backup of a target skill directory before publish replacement."""
    backup_temp = tempfile.TemporaryDirectory(prefix="skill-publish-backup-")
    backup_dir: Path | None = None
    if target_dir.exists():
        backup_dir = Path(backup_temp.name) / "target"
        shutil.copytree(target_dir, backup_dir)
    return backup_temp, backup_dir


def _restore_skill_directory_backup(target_dir: Path, backup_dir: Path | None) -> None:
    """Restore the target skill directory from backup after a failed publish."""
    if target_dir.exists():
        shutil.rmtree(target_dir)
    if backup_dir is not None:
        target_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(backup_dir, target_dir)


def _log_publish_phase(
    *,
    phase: str,
    skill_name: str,
    publisher_user_id: int,
    release_version: str | None = None,
) -> None:
    logger.info(
        "skill_publish phase=%s skill_name=%s publisher_user_id=%s release_version=%s",
        phase,
        skill_name,
        publisher_user_id,
        release_version,
    )


def _log_publish_failure(
    *,
    phase: str,
    skill_name: str,
    publisher_user_id: int,
    exc: Exception,
    release_version: str | None = None,
) -> None:
    logger.error(
        "skill_publish_failed phase=%s skill_name=%s publisher_user_id=%s release_version=%s error_type=%s error=%s",
        phase,
        skill_name,
        publisher_user_id,
        release_version,
        type(exc).__name__,
        str(exc),
        exc_info=True,
    )


async def _ensure_skill_version_from_dir(
    db: AsyncSession,
    *,
    user_id: int,
    skill_name: str,
    description: str,
    source_package_version: str | None,
    skill_dir: Path,
    definition_source_type: str | None = None,
    definition_source_identifier: str | None = None,
) -> tuple[SkillVersion, bool, SkillDefinition]:
    """Create or reuse the platform SkillVersion for canonical skill content."""
    content_hash, file_manifest_hash = _hash_skill_directory(skill_dir)
    definition_kwargs = {}
    if definition_source_type is not None:
        definition_kwargs["source_type"] = definition_source_type
    if definition_source_identifier is not None:
        definition_kwargs["source_identifier"] = definition_source_identifier
    definition = await SkillDefinitionRepository.get_or_create(
        db,
        name=skill_name,
        display_name=skill_name,
        description=description,
        owner_user_id=user_id,
        **definition_kwargs,
    )
    existing_version = await SkillVersionRepository.get_by_definition_and_hash(
        db,
        skill_definition_id=definition.id,
        content_hash=content_hash,
    )
    if existing_version is not None:
        return existing_version, False, definition

    latest = await SkillVersionRepository.get_latest_for_definition(db, skill_definition_id=definition.id)
    next_number = 1 if latest is None else latest.version_number + 1
    artifact_uri = _build_version_artifact_uri(
        definition_id=definition.id,
        version_number=next_number,
        content_hash=content_hash,
        skill_name=skill_name,
    )
    await asyncio.to_thread(_copy_version_artifact, skill_dir, artifact_uri)
    version = await SkillVersionRepository.create_version(
        db,
        definition=definition,
        source_package_version=source_package_version,
        description=description,
        content_hash=content_hash,
        file_manifest_hash=file_manifest_hash,
        artifact_uri=artifact_uri,
        created_by_user_id=user_id,
    )
    return version, True, definition


async def _parse_uploaded_skill_archive(upload_file: UploadFile) -> tuple[str, str, str | None, Path, tempfile.TemporaryDirectory[str], ParsedForkClaim | None]:
    """Persist, extract, and validate an uploaded skill archive."""
    if not upload_file.filename:
        raise ValueError("Uploaded file must have a filename")

    temp_dir = tempfile.TemporaryDirectory(prefix="skill-upload-")
    archive_path = Path(temp_dir.name) / upload_file.filename
    archive_path.write_bytes(await upload_file.read())

    if not zipfile.is_zipfile(archive_path):
        temp_dir.cleanup()
        raise ValueError("Uploaded file must be a valid zip archive")

    extracted_dir = Path(temp_dir.name) / "extracted"
    extracted_dir.mkdir(parents=True, exist_ok=True)

    try:
        _safe_extract_archive(archive_path, extracted_dir)
        skill_dir = _resolve_skill_root_dir(extracted_dir)
        skill_name, _ = _validate_skill_directory(skill_dir)
        package_version = _extract_package_version_from_dir(skill_dir)
        fork_claim = _load_uploaded_fork_claim(skill_dir)
        return upload_file.filename, skill_name, package_version, skill_dir, temp_dir, fork_claim
    except Exception:
        temp_dir.cleanup()
        raise


async def _get_download_source_skill(
    db: AsyncSession,
    *,
    skill_name: str,
    owner_user_id: int | None,
    skill_definition_id: int | None = None,
) -> Skill | None:
    """Resolve the selected public catalog row by source owner when supplied."""
    if skill_definition_id is not None:
        skill = await SkillRepository.get_public_skill_by_definition(
            db,
            skill_definition_id=skill_definition_id,
        )
        if skill is None or skill.name != skill_name:
            return None
        return skill
    return await SkillRepository.get_public_skill_by_name_and_owner(
        db,
        name=skill_name,
        owner_user_id=owner_user_id,
    )


def _source_kind_for_public_skill(source_skill: Skill, source_version: SkillVersion) -> SkillSourceKind:
    definition = source_version.definition
    if _is_official_skill_source(source_skill, definition):
        return "official"
    if definition is not None and definition.source_type == "fork":
        return "fork"
    return "community"


def _reject_system_skill_action(source_skill: Skill, source_version: SkillVersion, *, action: str) -> None:
    """Reject install/export actions that do not apply to directly usable System Skills."""
    if _source_kind_for_public_skill(source_skill, source_version) != "official":
        return
    if action == "install":
        raise HTTPException(status_code=400, detail="System Skills are directly usable and cannot be installed to My Skills")
    if action == "download":
        raise HTTPException(status_code=400, detail="System Skills cannot be downloaded as editable packages")
    raise HTTPException(status_code=400, detail="System Skill action is not supported")


def _build_fork_claim_metadata(
    *,
    claim: PendingSkillForkClaim,
    claim_token: str,
    source_skill: Skill,
    source_version: SkillVersion,
    source_kind: SkillSourceKind,
    expires_at: datetime,
) -> dict[str, object]:
    source_definition = source_version.definition
    source_owner_display_name = _display_name_for_source_version(source_version) or _display_name_for_user(source_skill.owner_user)
    return {
        "schema_version": 1,
        "kind": _FORK_METADATA_KIND,
        "claim_id": claim.id,
        "claim_token": claim_token,
        "source_skill_definition_id": source_version.skill_definition_id,
        "source_skill_version_id": source_version.id,
        "source_name": source_definition.name if source_definition is not None else source_skill.name,
        "source_owner_display_name": source_owner_display_name,
        "source_kind": source_kind,
        "source_platform_version": source_version.version_number,
        "source_content_hash": source_version.content_hash,
        "source_file_manifest_hash": source_version.file_manifest_hash,
        "issued_at": claim.created_at.isoformat(),
        "expires_at": expires_at.isoformat(),
    }


def _write_fork_package_archive(source_dir: Path, destination_zip: Path, *, skill_name: str, fork_metadata: dict[str, object]) -> None:
    """Write an editable source ZIP with a server-verifiable fork claim sidecar."""
    root = skill_name
    sidecar_relative = f"{root}/{_FORK_METADATA_RELATIVE_PATH.as_posix()}"
    with zipfile.ZipFile(destination_zip, "w", compression=zipfile.ZIP_DEFLATED) as zip_ref:
        for path in sorted(item for item in source_dir.rglob("*") if item.is_file()):
            relative = path.relative_to(source_dir).as_posix()
            archive_name = f"{root}/{relative}"
            if archive_name == sidecar_relative:
                continue
            zip_ref.write(path, archive_name)
        zip_ref.writestr(
            sidecar_relative,
            json.dumps(fork_metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )


def _download_filename_for_fork_package(*, skill_name: str, platform_version: int) -> str:
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "-", skill_name).strip("-") or "skill"
    return f"{safe_name}-editable-copy-v{platform_version}.zip"


@router.post(
    "/skills/check-upload",
    response_model=SkillUploadCheckResponse,
    summary="Check Skill Upload",
    description="Parse a skill zip archive and determine whether the current user already has a skill with that folder name.",
)
async def check_skill_upload(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SkillUploadCheckResponse:
    temp_dir: tempfile.TemporaryDirectory[str] | None = None
    try:
        filename, skill_name, package_version, skill_dir, temp_dir, parsed_fork_claim = await _parse_uploaded_skill_archive(file)
        content_hash, _ = _hash_skill_directory(skill_dir)
        validated_claim = await _validate_uploaded_fork_claim(db, parsed_claim=parsed_fork_claim, user_id=current_user.id)
        definition = (
            await SkillDefinitionRepository.get_by_identity(
                db,
                name=skill_name,
                source_type="fork",
                source_identifier=validated_claim.source_identifier,
            )
            if validated_claim is not None
            else await SkillDefinitionRepository.get_by_name_and_owner(db, name=skill_name, owner_user_id=current_user.id)
        )
        existing_version = None
        latest_version = None
        if definition is not None:
            existing_version = await SkillVersionRepository.get_by_definition_and_hash(
                db,
                skill_definition_id=definition.id,
                content_hash=content_hash,
            )
            latest_version = await SkillVersionRepository.get_latest_for_definition(
                db,
                skill_definition_id=definition.id,
            )
        install = (
            await SkillInstallRepository.get_by_user_and_definition(
                db,
                user_id=current_user.id,
                skill_definition_id=definition.id,
            )
            if definition is not None
            else None
        )
        existing_package_version = install.current_version.source_package_version if install is not None and install.current_version is not None else None
        same_version = existing_version is not None
        exists = same_version and install is not None and install.current_version_id == existing_version.id
        platform_version = existing_version.version_number if existing_version is not None else ((latest_version.version_number + 1) if latest_version is not None else 1)
        if same_version:
            message = f"Skill '{skill_name}' platform version {platform_version} already exists"
        elif install is not None:
            message = f"Skill '{skill_name}' will create platform version {platform_version}"
        else:
            message = "Skill content is available as a new platform version"
        if validated_claim is not None:
            source_name, source_owner, source_platform_version = _fork_source_message_parts(validated_claim)
            message = f"Skill '{skill_name}' will be added as a fork of '{source_name or 'source Skill'}'"
        else:
            source_name, source_owner, source_platform_version = None, None, None
        return SkillUploadCheckResponse(
            filename=filename,
            skill_name=skill_name,
            package_version=package_version,
            source_package_version=package_version,
            existing_package_version=existing_package_version,
            existing_source_package_version=existing_package_version,
            platform_version=platform_version,
            same_version=same_version,
            exists=exists,
            message=message,
            recognized_as="fork" if validated_claim is not None else "original",
            fork_source_name=source_name,
            fork_source_owner_display_name=source_owner,
            fork_source_platform_version=source_platform_version,
            unchanged_from_source=bool(validated_claim is not None and content_hash == validated_claim.source_version.content_hash),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("Failed to check skill upload: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to check skill upload: {exc}")
    finally:
        if temp_dir is not None:
            temp_dir.cleanup()


@router.post(
    "/skills/uploads",
    response_model=SkillUploadResponse,
    summary="Upload Skills",
    description="Upload one or more custom skill zip archives for the current user.",
)
async def upload_skills(
    files: list[UploadFile] = File(...),
    overwrite_names: list[str] | None = Form(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SkillUploadResponse:
    overwrite_set = set(overwrite_names or [])
    results: list[SkillUploadResult] = []

    for upload_file in files:
        temp_dir: tempfile.TemporaryDirectory[str] | None = None
        try:
            filename, skill_name, package_version, skill_dir, temp_dir, parsed_fork_claim = await _parse_uploaded_skill_archive(upload_file)
            validated_claim = await _validate_uploaded_fork_claim(db, parsed_claim=parsed_fork_claim, user_id=current_user.id)
            description = _extract_frontmatter(skill_dir / "SKILL.md").get("description", "")
            if not isinstance(description, str):
                description = ""
            description = description.strip()

            target_path = build_private_skill_file_path(current_user.id, skill_name)
            target_dir = _resolve_skill_dir(target_path)
            version, created_version, definition = await _ensure_skill_version_from_dir(
                db,
                user_id=current_user.id,
                skill_name=skill_name,
                description=description,
                source_package_version=package_version,
                skill_dir=skill_dir,
                definition_source_type="fork" if validated_claim is not None else None,
                definition_source_identifier=validated_claim.source_identifier if validated_claim is not None else None,
            )
            existing_install = await SkillInstallRepository.get_by_user_and_definition(
                db,
                user_id=current_user.id,
                skill_definition_id=definition.id,
            )
            existing_skill = await _get_user_skill_by_definition_or_legacy(
                db,
                user_id=current_user.id,
                skill_name=skill_name,
                skill_definition_id=definition.id,
            )
            await SkillInstallRepository.upsert_install(
                db,
                user_id=current_user.id,
                definition=definition,
                version=version,
            )
            orphaned_target_exists = existing_skill is None and target_dir.exists()
            if not created_version and existing_install is not None and existing_install.current_version_id == version.id and skill_name not in overwrite_set:
                results.append(
                    SkillUploadResult(
                        filename=filename,
                        skill_name=skill_name,
                        package_version=package_version,
                        source_package_version=package_version,
                        platform_version=version.version_number,
                        skill_version_id=version.id,
                        action="skipped",
                        success=True,
                        message=f"Skill '{skill_name}' platform version {version.version_number} already exists",
                        recognized_as="fork" if validated_claim is not None else "original",
                    )
                )
                await db.rollback()
                continue

            if orphaned_target_exists and skill_name not in overwrite_set:
                results.append(
                    SkillUploadResult(
                        filename=filename,
                        skill_name=skill_name,
                        package_version=package_version,
                        source_package_version=package_version,
                        platform_version=version.version_number,
                        skill_version_id=version.id,
                        action="skipped",
                        success=False,
                        message=f"Skill '{skill_name}' target directory already exists",
                        recognized_as="fork" if validated_claim is not None else "original",
                    )
                )
                await db.rollback()
                continue

            await asyncio.to_thread(_replace_skill_directory, skill_dir, target_dir)

            if existing_skill is not None:
                existing_skill.display_name = skill_name
                existing_skill.description = description
                existing_skill.file_path = target_path
                existing_skill.skill_definition_id = definition.id
                await db.flush()
                action = "updated"
            else:
                await SkillRepository.create_skill(
                    db,
                    user_id=current_user.id,
                    owner_user_id=None,
                    skill_definition_id=definition.id,
                    name=skill_name,
                    display_name=skill_name,
                    description=description,
                    file_path=target_path,
                    commit=False,
                )
                action = "created"

            if validated_claim is not None:
                await PendingSkillForkClaimRepository.mark_claimed(db, claim=validated_claim.claim, now=datetime.now(UTC))

            await db.commit()
            refreshed_install = await SkillInstallRepository.get_by_user_and_definition(
                db,
                user_id=current_user.id,
                skill_definition_id=version.skill_definition_id,
            )
            results.append(
                SkillUploadResult(
                    filename=filename,
                    skill_name=skill_name,
                    package_version=package_version,
                    source_package_version=package_version,
                    platform_version=version.version_number,
                    skill_version_id=version.id,
                    action=action,
                    success=True,
                    message=(f"Skill installed at platform version {refreshed_install.current_version.version_number}" if refreshed_install is not None and refreshed_install.current_version is not None else "Skill uploaded successfully"),
                    recognized_as="fork" if validated_claim is not None else "original",
                )
            )
        except ValueError as exc:
            await db.rollback()
            results.append(
                SkillUploadResult(
                    filename=upload_file.filename or "unknown.zip",
                    success=False,
                    message=str(exc),
                )
            )
        except Exception as exc:
            await db.rollback()
            logger.error("Failed to upload skill archive %s: %s", upload_file.filename, exc, exc_info=True)
            results.append(
                SkillUploadResult(
                    filename=upload_file.filename or "unknown.zip",
                    success=False,
                    message=f"Failed to upload skill: {exc}",
                )
            )
        finally:
            if temp_dir is not None:
                temp_dir.cleanup()

    return SkillUploadResponse(results=results)


@router.post(
    "/skills/{skill_name}/fork-package",
    response_class=FileResponse,
    summary="Download Editable Fork Package",
    description="Export a published Skill as an editable ZIP with a server-verifiable fork claim.",
)
async def download_skill_fork_package(
    skill_name: str,
    request: SkillForkPackageRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    try:
        source_skill = await _get_download_source_skill(
            db,
            skill_name=skill_name,
            owner_user_id=request.owner_user_id,
            skill_definition_id=request.skill_definition_id,
        )
        if source_skill is None:
            raise HTTPException(status_code=404, detail=f"Community Skill '{skill_name}' not found")

        source_release = await SkillReleaseRepository.get_latest_release_for_public_skill(db, published_skill_id=source_skill.id) if source_skill.id is not None else None
        source_version = source_release.skill_version if source_release is not None else None
        if source_version is None or source_version.definition is None:
            raise HTTPException(status_code=404, detail=f"Published version for skill '{skill_name}' not found")
        _reject_system_skill_action(source_skill, source_version, action="download")
        if not _is_skill_version_artifact_available(source_version):
            raise HTTPException(status_code=409, detail=f"Published version for skill '{skill_name}' is unavailable")

        claim_token = secrets.token_urlsafe(32)
        expires_at = datetime.now(UTC) + timedelta(days=_FORK_CLAIM_EXPIRY_DAYS)
        source_kind = _source_kind_for_public_skill(source_skill, source_version)
        source_snapshot = {
            "source_name": source_version.definition.name,
            "source_owner_display_name": _display_name_for_source_version(source_version) or _display_name_for_user(source_skill.owner_user),
            "source_kind": source_kind,
            "source_platform_version": source_version.version_number,
            "source_content_hash": source_version.content_hash,
            "source_file_manifest_hash": source_version.file_manifest_hash,
        }
        claim = await PendingSkillForkClaimRepository.create_claim(
            db,
            user_id=current_user.id,
            source_version=source_version,
            claim_token_hash=PendingSkillForkClaimRepository.hash_claim_token(claim_token),
            source_snapshot=source_snapshot,
            expires_at=expires_at,
        )
        fork_metadata = _build_fork_claim_metadata(
            claim=claim,
            claim_token=claim_token,
            source_skill=source_skill,
            source_version=source_version,
            source_kind=source_kind,
            expires_at=expires_at,
        )
        temp_dir = tempfile.TemporaryDirectory(prefix="skill-fork-package-")
        archive_path = Path(temp_dir.name) / _download_filename_for_fork_package(skill_name=source_version.definition.name, platform_version=source_version.version_number)
        await asyncio.to_thread(
            _write_fork_package_archive,
            _resolve_skill_dir(source_version.artifact_uri),
            archive_path,
            skill_name=source_version.definition.name,
            fork_metadata=fork_metadata,
        )
        await db.commit()
        return FileResponse(
            archive_path,
            media_type="application/zip",
            filename=archive_path.name,
            background=BackgroundTask(temp_dir.cleanup),
        )
    except HTTPException:
        await db.rollback()
        raise
    except Exception as exc:
        await db.rollback()
        logger.error("Failed to create fork package for %s: %s", skill_name, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create editable copy: {exc}")


@router.post(
    "/skills/{skill_name}/check-download",
    response_model=SkillDownloadCheckResponse,
    summary="Check SkillHub Install",
    description="Check whether installing a SkillHub skill would conflict with the current user's installed skill state.",
)
async def check_skill_download(
    skill_name: str,
    request: SkillDownloadCheckRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SkillDownloadCheckResponse:
    try:
        source_skill = await _get_download_source_skill(
            db,
            skill_name=skill_name,
            owner_user_id=request.owner_user_id,
            skill_definition_id=request.skill_definition_id,
        )
        if source_skill is None:
            raise HTTPException(status_code=404, detail=f"SkillHub skill '{skill_name}' not found")

        source_release = await SkillReleaseRepository.get_latest_release_for_public_skill(db, published_skill_id=source_skill.id) if source_skill.id is not None else None
        version = source_release.skill_version if source_release is not None else None
        if version is not None:
            _reject_system_skill_action(source_skill, version, action="install")
        existing_install = (
            await SkillInstallRepository.get_by_user_and_definition(
                db,
                user_id=current_user.id,
                skill_definition_id=version.skill_definition_id,
            )
            if version is not None
            else None
        )
        existing_skill = (
            await SkillRepository.get_user_skill_by_definition(
                db,
                user_id=current_user.id,
                skill_definition_id=version.skill_definition_id,
            )
            if version is not None
            else await SkillRepository.get_user_skill_by_name(db, user_id=current_user.id, name=skill_name)
        )
        exists = existing_install is not None or existing_skill is not None
        return SkillDownloadCheckResponse(
            skill_name=skill_name,
            exists=exists,
            message="Skill name already exists" if exists else "Skill can be installed",
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to check SkillHub install %s: %s", skill_name, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to check SkillHub install: {exc}")


@router.post(
    "/skills/{skill_name}/download",
    response_model=SkillResponse,
    summary="Install SkillHub Skill",
    description="Install the currently published SkillHub version into the current user's install state.",
)
async def download_skill(
    skill_name: str,
    request: SkillDownloadRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SkillResponse:
    try:
        source_skill = await _get_download_source_skill(
            db,
            skill_name=skill_name,
            owner_user_id=request.owner_user_id,
            skill_definition_id=request.skill_definition_id,
        )
        if source_skill is None:
            raise HTTPException(status_code=404, detail=f"SkillHub skill '{skill_name}' not found")

        source_release = None
        if source_skill.id is not None:
            source_release = await SkillReleaseRepository.get_latest_release_for_public_skill(db, published_skill_id=source_skill.id)
        version = source_release.skill_version if source_release is not None else None
        if version is None or version.definition is None:
            raise HTTPException(status_code=404, detail=f"Published version for skill '{skill_name}' not found")
        _reject_system_skill_action(source_skill, version, action="install")

        existing_install = await SkillInstallRepository.get_by_user_and_definition(
            db,
            user_id=current_user.id,
            skill_definition_id=version.skill_definition_id,
        )
        existing_skill = await SkillRepository.get_user_skill_by_definition(
            db,
            user_id=current_user.id,
            skill_definition_id=version.skill_definition_id,
        )
        target_path = version.artifact_uri
        already_exists = existing_install is not None or existing_skill is not None
        if already_exists and not request.overwrite:
            raise HTTPException(status_code=409, detail=f"Skill '{skill_name}' already exists")
        if existing_install is not None and existing_install.current_version_id != version.id:
            raise HTTPException(status_code=409, detail=f"Skill '{skill_name}' has an installed version change available; use update preview and confirmation before switching versions")

        if existing_skill is not None:
            await SkillRepository.soft_delete_skill(db, skill=existing_skill, commit=False)

        install = await SkillInstallRepository.upsert_install(
            db,
            user_id=current_user.id,
            definition=version.definition,
            version=version,
        )
        created_skill = await SkillRepository.create_skill(
            db,
            user_id=current_user.id,
            owner_user_id=None,
            skill_definition_id=version.skill_definition_id,
            name=skill_name,
            display_name=skill_name,
            description=version.description or source_skill.description,
            file_path=target_path,
            commit=False,
        )

        await db.commit()
        refreshed_skill = await SkillRepository.get_skill_by_id(db, created_skill.id)
        if refreshed_skill is None:
            raise HTTPException(status_code=500, detail=f"Failed to load installed skill '{skill_name}'")
        refreshed_install = await SkillInstallRepository.get_by_user_and_definition(
            db,
            user_id=current_user.id,
            skill_definition_id=version.skill_definition_id,
        )
        return _skill_to_response(refreshed_skill, release=source_release, skill_version=version, skill_install=refreshed_install or install, current_user_id=current_user.id)
    except HTTPException:
        await db.rollback()
        raise
    except Exception as exc:
        await db.rollback()
        logger.error("Failed to install SkillHub skill %s: %s", skill_name, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to install SkillHub skill: {exc}")


@router.post(
    "/skills/{skill_name}/update-install",
    response_model=SkillInstallUpdatePreviewResponse,
    summary="Update Installed Skill",
    description="Explicitly update the current user's install to a platform SkillVersion.",
)
async def update_skill_install(
    skill_name: str,
    request: SkillInstallUpdateRequest | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SkillInstallUpdatePreviewResponse:
    try:
        requested_install_id = request.skill_install_id if request is not None else None
        install = await _get_update_install(db, user_id=current_user.id, skill_name=skill_name, skill_install_id=requested_install_id)

        release: SkillRelease | None = None
        if request is not None and request.skill_version_id is not None:
            release = await SkillReleaseRepository.get_published_release_by_version_id(
                db,
                skill_version_id=request.skill_version_id,
            )
            version = release.skill_version if release is not None else None
            if version is None or version.skill_definition_id != install.skill_definition_id:
                raise HTTPException(status_code=404, detail=f"Skill version '{request.skill_version_id}' not found for '{skill_name}'")
        else:
            release = await SkillReleaseRepository.get_latest_published_release_for_definition(
                db,
                skill_definition_id=install.skill_definition_id,
            )
            version = release.skill_version if release is not None else None
            if version is None:
                raise HTTPException(status_code=404, detail=f"No published update found for '{skill_name}'")

        preview = await _build_skill_update_preview(
            db,
            skill_name=skill_name,
            current_user=current_user,
            install=install,
            target_version=version,
            target_release=release,
        )
        if preview.status == "unavailable":
            raise HTTPException(status_code=409, detail=preview.message)
        if preview.update_available:
            await SkillInstallRepository.update_current_version(
                db,
                install=install,
                version=version,
            )

        await db.commit()
        return preview
    except HTTPException:
        await db.rollback()
        raise
    except Exception as exc:
        await db.rollback()
        logger.error("Failed to update skill install %s: %s", skill_name, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update skill install: {exc}")


@router.get(
    "/skills/{skill_name}/update-install/preview",
    response_model=SkillInstallUpdatePreviewResponse,
    summary="Preview Installed Skill Update",
    description="Read-only preview of an installed Skill update and affected Agents.",
)
async def preview_skill_install_update(
    skill_name: str,
    skill_install_id: int | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SkillInstallUpdatePreviewResponse:
    try:
        return await _build_skill_update_preview(db, skill_name=skill_name, current_user=current_user, skill_install_id=skill_install_id)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to preview skill install update %s: %s", skill_name, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to preview skill install update: {exc}")


@router.post(
    "/skills/{skill_name}/publish",
    response_model=SkillResponse,
    summary="Publish Custom Skill",
    description="Publish the current installed SkillVersion to SkillHub without changing existing user installs.",
)
async def publish_skill(
    skill_name: str,
    request: SkillPublishRequest | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SkillResponse:
    phase = "validate_custom_skill"
    release_version: str | None = None
    target_dir: Path | None = None
    backup_temp: tempfile.TemporaryDirectory[str] | None = None
    backup_dir: Path | None = None
    artifact_committed = False
    try:
        _log_publish_phase(phase=phase, skill_name=skill_name, publisher_user_id=current_user.id)
        definition = await _resolve_publish_definition_or_reject_downloaded(db, user_id=current_user.id, skill_name=skill_name)
        if definition is None:
            raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found")
        custom_skill = await _get_user_skill_by_definition_or_legacy(
            db,
            user_id=current_user.id,
            skill_name=skill_name,
            skill_definition_id=definition.id,
        )
        if custom_skill is None:
            raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found")
        install = await SkillInstallRepository.get_by_user_and_definition(
            db,
            user_id=current_user.id,
            skill_definition_id=definition.id,
        )
        if install is None or install.current_version is None:
            raise HTTPException(status_code=409, detail=f"Skill '{skill_name}' has no installed platform version")
        current_version = install.current_version
        await _reject_unchanged_fork_publish(db, definition=definition, current_version=current_version)

        source_dir = _resolve_skill_dir(current_version.artifact_uri)
        publish_metadata = _extract_publish_metadata(source_dir, expected_name=skill_name)
        release_notes = _normalize_release_notes(request.release_notes if request is not None else None)
        existing_public_skills = await SkillRepository.list_public_skills_by_name_and_owner(db, name=skill_name, owner_user_id=current_user.id)
        target_path = build_public_skill_file_path(skill_name, owner_user_id=current_user.id)
        target_dir = _resolve_skill_dir(target_path)

        phase = "copy_public_artifact"
        _log_publish_phase(phase=phase, skill_name=skill_name, publisher_user_id=current_user.id)
        backup_temp, backup_dir = await asyncio.to_thread(_backup_skill_directory, target_dir)
        await asyncio.to_thread(_replace_skill_directory, source_dir, target_dir)

        phase = "update_skillhub_catalog"
        _log_publish_phase(phase=phase, skill_name=skill_name, publisher_user_id=current_user.id)
        for existing_public_skill in existing_public_skills:
            await SkillRepository.soft_delete_skill(db, skill=existing_public_skill, commit=False)

        published_skill = await SkillRepository.create_skill(
            db,
            user_id=None,
            owner_user_id=current_user.id,
            skill_definition_id=current_version.skill_definition_id,
            name=skill_name,
            display_name=skill_name,
            description=publish_metadata["description"],
            file_path=target_path,
            commit=False,
        )
        phase = "create_release_record"
        _log_publish_phase(phase=phase, skill_name=skill_name, publisher_user_id=current_user.id)
        release = await SkillReleaseRepository.create_release(
            db,
            skill_name=skill_name,
            package_version=current_version.source_package_version,
            description=publish_metadata["description"],
            release_notes=release_notes,
            artifact_path=current_version.artifact_uri,
            publisher_user_id=current_user.id,
            source_skill_id=custom_skill.id,
            published_skill_id=published_skill.id,
            skill_version_id=current_version.id,
            commit=False,
        )
        release_version = release.release_version
        phase = "commit_publish"
        _log_publish_phase(phase=phase, skill_name=skill_name, publisher_user_id=current_user.id, release_version=release_version)
        await db.commit()
        artifact_committed = True
        refreshed_skill = await SkillRepository.get_skill_by_id(db, published_skill.id)
        if refreshed_skill is None:
            raise HTTPException(status_code=500, detail=f"Failed to load published skill '{skill_name}'")
        fork_source_version = await _get_recorded_fork_source_version(db, definition)
        return _skill_to_response(refreshed_skill, release=release, skill_version=current_version, current_user_id=current_user.id, fork_source_version=fork_source_version)
    except HTTPException as exc:
        await db.rollback()
        if not artifact_committed and target_dir is not None and backup_temp is not None:
            await asyncio.to_thread(_restore_skill_directory_backup, target_dir, backup_dir)
        if exc.status_code >= 500:
            _log_publish_failure(phase=phase, skill_name=skill_name, publisher_user_id=current_user.id, release_version=release_version, exc=exc)
        raise
    except ValueError as exc:
        await db.rollback()
        if not artifact_committed and target_dir is not None and backup_temp is not None:
            await asyncio.to_thread(_restore_skill_directory_backup, target_dir, backup_dir)
        _log_publish_failure(phase=phase, skill_name=skill_name, publisher_user_id=current_user.id, release_version=release_version, exc=exc)
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        await db.rollback()
        if not artifact_committed and target_dir is not None and backup_temp is not None:
            await asyncio.to_thread(_restore_skill_directory_backup, target_dir, backup_dir)
        _log_publish_failure(phase=phase, skill_name=skill_name, publisher_user_id=current_user.id, release_version=release_version, exc=exc)
        raise HTTPException(status_code=500, detail="Failed to publish skill")
    finally:
        if backup_temp is not None:
            backup_temp.cleanup()


@router.get(
    "/skills",
    response_model=SkillsListResponse,
    summary="List All Skills",
    description="Retrieve the current user's skills and public skills from the database.",
)
async def list_skills(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SkillsListResponse:
    try:
        skills = await SkillRepository.list_visible_skills(db, user_id=current_user.id)
        return SkillsListResponse(skills=[await _skill_to_response_with_metadata(db, skill, current_user_id=current_user.id) for skill in skills])
    except Exception as exc:
        logger.error("Failed to load skills: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to load skills: {exc}")


@router.get(
    "/skills/{skill_name}",
    response_model=SkillResponse,
    summary="Get Skill Details",
    description="Retrieve details for a visible skill, preferring the current user's copy.",
)
async def get_skill(
    skill_name: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SkillResponse:
    try:
        skill = await SkillRepository.get_visible_skill_by_name(db, user_id=current_user.id, name=skill_name)
        if skill is None:
            raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found")

        return await _skill_to_response_with_metadata(db, skill, current_user_id=current_user.id)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to get skill %s: %s", skill_name, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get skill: {exc}")


@router.put(
    "/skills/{skill_name}",
    response_model=SkillResponse,
    summary="Update Skill",
    description="Update the current user's skill record. Public skills are read-only.",
)
async def update_skill(
    skill_name: str,
    request: SkillUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SkillResponse:
    del request
    try:
        user_skill = await SkillRepository.get_user_skill_by_name(db, user_id=current_user.id, name=skill_name)
        if user_skill is not None:
            updated_skill = await SkillRepository.touch_user_skill(db, user_id=current_user.id, name=skill_name)
            if updated_skill is None:
                raise HTTPException(status_code=500, detail=f"Failed to refresh skill '{skill_name}'")
            return await _skill_to_response_with_metadata(db, updated_skill, current_user_id=current_user.id)

        public_skill = await SkillRepository.get_public_skill_by_name(db, name=skill_name)
        if public_skill is not None:
            raise HTTPException(status_code=403, detail=f"Skill '{skill_name}' is public and cannot be modified")

        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found")
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to update skill %s: %s", skill_name, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update skill: {exc}")


@router.delete(
    "/skills/{skill_name}",
    status_code=204,
    summary="Delete Skill",
    description="Soft-delete the current user's skill record. Public skills cannot be deleted.",
)
async def delete_skill(
    skill_name: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    try:
        user_skill = await SkillRepository.get_user_skill_by_name(db, user_id=current_user.id, name=skill_name)
        if user_skill is not None:
            bound_agent_names = await SkillRepository.list_bound_agent_names_for_skill(
                db,
                user_id=current_user.id,
                skill_id=user_skill.id,
            )
            if user_skill.skill_definition_id is not None:
                install = await SkillInstallRepository.get_by_user_and_definition(
                    db,
                    user_id=current_user.id,
                    skill_definition_id=user_skill.skill_definition_id,
                )
                if install is not None:
                    bound_agent_names.extend(
                        agent.name
                        for agent in await SkillRepository.list_bound_agents_for_install(
                            db,
                            user_id=current_user.id,
                            skill_install_id=install.id,
                        )
                    )
            if bound_agent_names:
                raise HTTPException(
                    status_code=409,
                    detail=f"Skill '{skill_name}' is bound to agent '{bound_agent_names[0]}' and cannot be deleted",
                )

            await asyncio.to_thread(_delete_skill_directory, _resolve_skill_record_dir(user_skill))
            await SkillRepository.soft_delete_skill(db, skill=user_skill, commit=True)
            return

        public_skill = await SkillRepository.get_public_skill_by_name(db, name=skill_name)
        if public_skill is not None:
            raise HTTPException(status_code=403, detail=f"Skill '{skill_name}' is public and cannot be deleted")

        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found")
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to delete skill %s: %s", skill_name, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to delete skill: {exc}")


@router.post(
    "/skills/install",
    response_model=SkillInstallResponse,
    summary="Install Skill",
    description="Install a skill from a .skill file (ZIP archive) located in the thread's user-data directory.",
)
async def install_skill(
    request: SkillInstallRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SkillInstallResponse:
    installed_dir: Path | None = None
    try:
        skill_file_path = resolve_thread_virtual_path(request.thread_id, request.path)
        skills_root = _get_skills_root_dir()
        result = install_skill_from_archive(skill_file_path, skills_root=skills_root, user_id=current_user.id)
        skill_name = result["skill_name"]
        installed_dir = _resolve_skill_dir(build_private_skill_file_path(current_user.id, skill_name))
        existing_definition = await SkillDefinitionRepository.get_by_name_and_owner(db, name=skill_name, owner_user_id=current_user.id)
        if existing_definition is not None:
            existing_install = await SkillInstallRepository.get_by_user_and_definition(
                db,
                user_id=current_user.id,
                skill_definition_id=existing_definition.id,
            )
            existing_skill = await _get_user_skill_by_definition_or_legacy(
                db,
                user_id=current_user.id,
                skill_name=skill_name,
                skill_definition_id=existing_definition.id,
            )
            if existing_install is not None or existing_skill is not None:
                await asyncio.to_thread(_delete_skill_directory, installed_dir)
                raise SkillAlreadyExistsError(f"Skill '{skill_name}' already exists")
        else:
            for candidate in await SkillRepository.list_user_skills_by_name(db, user_id=current_user.id, name=skill_name):
                if candidate.skill_definition_id is None:
                    await asyncio.to_thread(_delete_skill_directory, installed_dir)
                    raise SkillAlreadyExistsError(f"Skill '{skill_name}' already exists")

        description = _extract_frontmatter(installed_dir / "SKILL.md").get("description", "")
        if not isinstance(description, str):
            description = ""
        source_package_version = _extract_package_version_from_dir(installed_dir)
        version, _, definition = await _ensure_skill_version_from_dir(
            db,
            user_id=current_user.id,
            skill_name=skill_name,
            description=description.strip(),
            source_package_version=source_package_version,
            skill_dir=installed_dir,
        )
        await SkillInstallRepository.upsert_install(
            db,
            user_id=current_user.id,
            definition=definition,
            version=version,
        )

        await SkillRepository.create_skill(
            db,
            user_id=current_user.id,
            owner_user_id=None,
            skill_definition_id=definition.id,
            name=skill_name,
            display_name=skill_name,
            description=description.strip(),
            file_path=build_private_skill_file_path(current_user.id, skill_name),
            commit=True,
        )
        return SkillInstallResponse(**result)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except SkillAlreadyExistsError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))
    except HTTPException:
        await db.rollback()
        raise
    except Exception as exc:
        await db.rollback()
        if installed_dir is not None:
            await asyncio.to_thread(_delete_skill_directory, installed_dir)
        logger.error("Failed to install skill: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to install skill: {exc}")
