import asyncio
import logging
import shutil
import tempfile
import zipfile
from pathlib import Path

import yaml
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.gateway.db.models import Skill, User
from app.gateway.db.repository import SkillRepository
from app.gateway.deps import get_current_user, get_db
from app.gateway.path_utils import resolve_thread_virtual_path
from deerflow.config import get_app_config
from deerflow.skills.installer import SkillAlreadyExistsError, install_skill_from_archive
from deerflow.skills.path_utils import (
    build_private_skill_file_path,
    build_public_skill_file_path,
    normalize_skill_file_path,
    resolve_skill_storage_dir,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["skills"])

ALLOWED_SKILL_FRONTMATTER_KEYS = {
    "name",
    "description",
    "license",
    "allowed-tools",
    "metadata",
    "compatibility",
}


class SkillResponse(BaseModel):
    """Response model for skill information."""

    name: str = Field(..., description="Name of the skill")
    description: str = Field(..., description="Description of what the skill does")
    license: str | None = Field(None, description="License information")
    category: str = Field(..., description="Category of the skill (public or custom)")
    enabled: bool = Field(default=True, description="Whether this skill is enabled")
    owner_user_id: int | None = Field(default=None, description="Publisher user ID for public skills")
    owner_display_name: str | None = Field(default=None, description="Publisher display name for public skills")


class SkillsListResponse(BaseModel):
    """Response model for listing all skills."""

    skills: list[SkillResponse]


class SkillUpdateRequest(BaseModel):
    """Request model for updating a skill."""

    enabled: bool = Field(..., description="Whether to enable or disable the skill")


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
    skill_name: str = Field(..., description="Parsed skill folder name")
    exists: bool = Field(..., description="Whether the current user already has an active skill with this name")
    message: str = Field(..., description="Check result message")


class SkillUploadResult(BaseModel):
    """Per-file upload result."""

    filename: str = Field(..., description="Original zip filename")
    skill_name: str | None = Field(default=None, description="Parsed skill folder name")
    success: bool = Field(..., description="Whether the upload succeeded")
    message: str = Field(..., description="Upload result message")


class SkillUploadResponse(BaseModel):
    """Response model for bulk skill uploads."""

    results: list[SkillUploadResult]


class SkillDownloadCheckRequest(BaseModel):
    """Request body for checking whether a public skill download will conflict."""

    owner_user_id: int | None = Field(
        default=None,
        description="Deprecated compatibility field. Public skill lookup now uses only skill_name.",
    )


class SkillDownloadCheckResponse(BaseModel):
    """Response model for skill download conflict checks."""

    skill_name: str = Field(..., description="Target custom skill name")
    exists: bool = Field(..., description="Whether the current user already has a custom skill with that name")
    message: str = Field(..., description="Check result message")


class SkillDownloadRequest(BaseModel):
    """Request body for downloading a public skill."""

    owner_user_id: int | None = Field(
        default=None,
        description="Deprecated compatibility field. Public skill lookup now uses only skill_name.",
    )
    overwrite: bool = Field(default=False, description="Whether to overwrite an existing same-name custom skill")


def _skill_to_response(skill: Skill) -> SkillResponse:
    """Convert a database skill row to the API response model."""
    owner_display_name = None
    if skill.user_id is None and skill.owner_user_id is not None and skill.owner_user is not None:
        display_name = (skill.owner_user.display_name or "").strip()
        owner_display_name = display_name or skill.owner_user.username

    return SkillResponse(
        name=skill.name,
        description=skill.description or "",
        license=None,
        category="public" if skill.user_id is None else "custom",
        enabled=True,
        owner_user_id=skill.owner_user_id,
        owner_display_name=owner_display_name,
    )


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


def _replace_skill_directory(source_dir: Path, target_dir: Path) -> None:
    """Replace a target skill directory with the contents of source_dir."""
    if not source_dir.exists() or not source_dir.is_dir():
        raise ValueError(f"Skill directory '{source_dir}' does not exist")
    if target_dir.exists():
        shutil.rmtree(target_dir)
    target_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_dir, target_dir)


def _delete_skill_directory(target_dir: Path) -> None:
    """Delete a skill directory if it exists."""
    if target_dir.exists():
        shutil.rmtree(target_dir)


async def _parse_uploaded_skill_archive(upload_file: UploadFile) -> tuple[str, str, Path, tempfile.TemporaryDirectory[str]]:
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
        _, description = _validate_skill_directory(skill_dir)
        return upload_file.filename, skill_dir.name, skill_dir, temp_dir
    except Exception:
        temp_dir.cleanup()
        raise


async def _get_download_source_skill(
    db: AsyncSession,
    *,
    skill_name: str,
    owner_user_id: int | None,
) -> Skill | None:
    """Resolve the public skill selected for download.

    ``owner_user_id`` is accepted for request compatibility but ignored.
    """
    del owner_user_id
    return await SkillRepository.get_public_skill_by_name(db, name=skill_name)


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
        filename, skill_name, _, temp_dir = await _parse_uploaded_skill_archive(file)
        existing_skill = await SkillRepository.get_user_skill_by_name(db, user_id=current_user.id, name=skill_name)
        target_dir = _resolve_skill_dir(build_private_skill_file_path(current_user.id, skill_name))
        exists = existing_skill is not None or target_dir.exists()
        return SkillUploadCheckResponse(
            filename=filename,
            skill_name=skill_name,
            exists=exists,
            message="Skill name already exists" if exists else "Skill name is available",
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
            filename, skill_name, skill_dir, temp_dir = await _parse_uploaded_skill_archive(upload_file)
            description = _extract_frontmatter(skill_dir / "SKILL.md").get("description", "")
            if not isinstance(description, str):
                description = ""
            description = description.strip()

            existing_skill = await SkillRepository.get_user_skill_by_name(db, user_id=current_user.id, name=skill_name)
            target_path = build_private_skill_file_path(current_user.id, skill_name)
            target_dir = _resolve_skill_dir(target_path)
            already_exists = existing_skill is not None or target_dir.exists()
            if already_exists and skill_name not in overwrite_set:
                results.append(
                    SkillUploadResult(
                        filename=filename,
                        skill_name=skill_name,
                        success=False,
                        message=f"Skill '{skill_name}' already exists",
                    )
                )
                continue

            await asyncio.to_thread(_replace_skill_directory, skill_dir, target_dir)

            if existing_skill is not None:
                await SkillRepository.soft_delete_skill(db, skill=existing_skill, commit=False)

            created_skill = await SkillRepository.create_skill(
                db,
                user_id=current_user.id,
                owner_user_id=None,
                name=skill_name,
                display_name=skill_name,
                description=description,
                file_path=target_path,
                commit=False,
            )

            if existing_skill is not None:
                await SkillRepository.rebind_agent_skills(
                    db,
                    user_id=current_user.id,
                    old_skill_id=existing_skill.id,
                    new_skill_id=created_skill.id,
                )

            await db.commit()
            results.append(
                SkillUploadResult(
                    filename=filename,
                    skill_name=skill_name,
                    success=True,
                    message="Skill uploaded successfully",
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
    "/skills/{skill_name}/check-download",
    response_model=SkillDownloadCheckResponse,
    summary="Check Skill Download",
    description="Check whether downloading a public skill would overwrite one of the current user's custom skills.",
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
        )
        if source_skill is None:
            raise HTTPException(status_code=404, detail=f"Public skill '{skill_name}' not found")

        existing_skill = await SkillRepository.get_user_skill_by_name(db, user_id=current_user.id, name=skill_name)
        target_dir = _resolve_skill_dir(build_private_skill_file_path(current_user.id, skill_name))
        exists = existing_skill is not None or target_dir.exists()
        return SkillDownloadCheckResponse(
            skill_name=skill_name,
            exists=exists,
            message="Skill name already exists" if exists else "Skill can be downloaded",
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to check skill download %s: %s", skill_name, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to check skill download: {exc}")


@router.post(
    "/skills/{skill_name}/download",
    response_model=SkillResponse,
    summary="Download Public Skill",
    description="Copy a public skill into the current user's custom skills, optionally overwriting an existing custom copy.",
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
        )
        if source_skill is None:
            raise HTTPException(status_code=404, detail=f"Public skill '{skill_name}' not found")

        existing_skill = await SkillRepository.get_user_skill_by_name(db, user_id=current_user.id, name=skill_name)
        target_path = build_private_skill_file_path(current_user.id, skill_name)
        target_dir = _resolve_skill_dir(target_path)
        already_exists = existing_skill is not None or target_dir.exists()
        if already_exists and not request.overwrite:
            raise HTTPException(status_code=409, detail=f"Skill '{skill_name}' already exists")

        source_dir = _resolve_skill_record_dir(source_skill)
        await asyncio.to_thread(_replace_skill_directory, source_dir, target_dir)

        if existing_skill is not None:
            await SkillRepository.soft_delete_skill(db, skill=existing_skill, commit=False)

        created_skill = await SkillRepository.create_skill(
            db,
            user_id=current_user.id,
            owner_user_id=None,
            name=skill_name,
            display_name=skill_name,
            description=source_skill.description,
            file_path=target_path,
            commit=False,
        )

        if existing_skill is not None:
            await SkillRepository.rebind_agent_skills(
                db,
                user_id=current_user.id,
                old_skill_id=existing_skill.id,
                new_skill_id=created_skill.id,
            )

        await db.commit()
        refreshed_skill = await SkillRepository.get_skill_by_id(db, created_skill.id)
        if refreshed_skill is None:
            raise HTTPException(status_code=500, detail=f"Failed to load downloaded skill '{skill_name}'")
        return _skill_to_response(refreshed_skill)
    except HTTPException:
        await db.rollback()
        raise
    except Exception as exc:
        await db.rollback()
        logger.error("Failed to download skill %s: %s", skill_name, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to download skill: {exc}")


@router.post(
    "/skills/{skill_name}/publish",
    response_model=SkillResponse,
    summary="Publish Custom Skill",
    description="Copy the current user's custom skill into the public catalog, overwriting any existing public skill with the same skill_name.",
)
async def publish_skill(
    skill_name: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SkillResponse:
    try:
        custom_skill = await SkillRepository.get_user_skill_by_name(db, user_id=current_user.id, name=skill_name)
        if custom_skill is None:
            raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found")

        existing_public_skills = await SkillRepository.list_public_skills_by_name(db, name=skill_name)
        source_dir = _resolve_skill_record_dir(custom_skill)
        target_path = build_public_skill_file_path(skill_name)
        target_dir = _resolve_skill_dir(target_path)

        await asyncio.to_thread(_replace_skill_directory, source_dir, target_dir)

        for existing_public_skill in existing_public_skills:
            await SkillRepository.soft_delete_skill(db, skill=existing_public_skill, commit=False)

        published_skill = await SkillRepository.create_skill(
            db,
            user_id=None,
            owner_user_id=current_user.id,
            name=skill_name,
            display_name=skill_name,
            description=custom_skill.description,
            file_path=target_path,
            commit=False,
        )
        await db.commit()
        refreshed_skill = await SkillRepository.get_skill_by_id(db, published_skill.id)
        if refreshed_skill is None:
            raise HTTPException(status_code=500, detail=f"Failed to load published skill '{skill_name}'")
        return _skill_to_response(refreshed_skill)
    except HTTPException:
        await db.rollback()
        raise
    except Exception as exc:
        await db.rollback()
        logger.error("Failed to publish skill %s: %s", skill_name, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to publish skill: {exc}")


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
        return SkillsListResponse(skills=[_skill_to_response(skill) for skill in skills])
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

        return _skill_to_response(skill)
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
            return _skill_to_response(updated_skill)

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

        existing_skill = await SkillRepository.get_user_skill_by_name(db, user_id=current_user.id, name=skill_name)
        if existing_skill is not None:
            await asyncio.to_thread(_delete_skill_directory, installed_dir)
            raise SkillAlreadyExistsError(f"Skill '{skill_name}' already exists")

        description = _extract_frontmatter(installed_dir / "SKILL.md").get("description", "")
        if not isinstance(description, str):
            description = ""

        await SkillRepository.create_skill(
            db,
            user_id=current_user.id,
            owner_user_id=None,
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
