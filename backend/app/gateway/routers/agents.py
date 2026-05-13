"""CRUD API for user-owned agents stored in the gateway database."""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.gateway.db.models import Agent, SkillDefinition, User
from app.gateway.db.models import Skill as TerminalSkill
from app.gateway.db.repository import AgentRepository, SkillInstallRepository, SkillReleaseRepository, is_system_owned_skill
from app.gateway.deps import get_current_user, get_db
from deerflow.config.paths import get_paths

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["agents"])

AGENT_NAME_PATTERN = re.compile(r"^[A-Za-z0-9-]+$")


class AgentSkillMetadataResponse(BaseModel):
    """Installed skill binding metadata for Agent display surfaces."""

    name: str = Field(..., description="Skill name resolved from the bound install/current version")
    skill_installation_id: int | None = Field(default=None, description="Agent-bound Skill installation ID")
    skill_id: str | None = Field(default=None, description="Terminal Skill UUID")
    version_number: int | None = Field(default=None, description="Terminal Skill version number")
    current_platform_version: int | None = Field(default=None, description="Current installed platform version")
    source: Literal["system", "skillhub", "my_skills", "unknown"] = Field(default="unknown", description="Installed skill source enum for display")
    source_label: str = Field(default="Unknown source", description="Installed skill source label for display")
    update_available: bool | None = Field(default=None, description="Whether a published platform update is available")
    available: bool = Field(default=False, description="Whether install/current version metadata is complete")
    status: Literal["available", "unavailable"] = Field(default="unavailable", description="Display availability status")


class AgentResponse(BaseModel):
    """Response model for a custom agent."""

    name: str = Field(..., description="Agent name (hyphen-case)")
    description: str = Field(default="", description="Agent description")
    skill_metadata: list[AgentSkillMetadataResponse] | None = Field(default=None, description="Installed skill binding metadata for display")
    soul: str | None = Field(default=None, description="SOUL.md content (included on GET /{name})")


class AgentsListResponse(BaseModel):
    """Response model for listing all custom agents."""

    agents: list[AgentResponse]


class AgentCreateRequest(BaseModel):
    """Request body for creating a custom agent."""

    model_config = ConfigDict(extra="allow")

    name: str = Field(..., description="Agent name (must match ^[A-Za-z0-9-]+$, stored as lowercase)")
    description: str = Field(default="", description="Agent description")
    skill_installation_ids: list[int] | None = Field(default=None, description="Optional install-backed Skill installation IDs")
    soul: str = Field(default="", description="SOUL.md content - agent personality and behavioral guardrails")


class AgentUpdateRequest(BaseModel):
    """Request body for updating a custom agent."""

    model_config = ConfigDict(extra="allow")

    description: str | None = Field(default=None, description="Updated description")
    skill_installation_ids: list[int] | None = Field(default=None, description="Updated install-backed Skill installation IDs")
    soul: str | None = Field(default=None, description="Updated SOUL.md content")


def _validate_agent_name(name: str) -> None:
    """Validate agent name against allowed pattern."""
    if not AGENT_NAME_PATTERN.match(name):
        raise HTTPException(
            status_code=422,
            detail=f"Invalid agent name '{name}'. Must match ^[A-Za-z0-9-]+$ (letters, digits, and hyphens only).",
        )


def _normalize_agent_name(name: str) -> str:
    """Normalize agent name to lowercase for storage."""
    return name.lower()


def _active_skill_names(agent: Agent) -> list[str] | None:
    """Return ordered active skill names for an agent, or None when unrestricted."""
    active_associations = [association for association in agent.agent_skills if association.deleted_at is None and association.enabled and association.skill_install is not None]
    if not active_associations:
        return None

    active_associations.sort(key=lambda association: (association.display_order, association.id))
    names: list[str] = []
    for association in active_associations:
        if association.skill_install is not None and association.skill_install.definition is not None:
            names.append(association.skill_install.definition.name)
        elif association.skill_install is not None and association.skill_install.current_version is not None and association.skill_install.current_version.definition is not None:
            names.append(association.skill_install.current_version.definition.name)
    return names


def _skill_source_for_agent(agent: Agent, definition: SkillDefinition | None, terminal_skill: TerminalSkill | None) -> tuple[Literal["system", "skillhub", "my_skills", "unknown"], str]:
    """Return a display source without consulting public/latest rows."""
    if is_system_owned_skill(terminal_skill):
        return "system", "System"
    if definition is None:
        return "unknown", "Unknown source"
    if definition.owner_user_id is None:
        return "unknown", "Unknown source"
    if agent.user_id is not None and definition.owner_user_id == agent.user_id:
        return "my_skills", "My Skills"
    owner_display_name = definition.owner_user.display_name if definition.owner_user is not None else None
    return "skillhub", owner_display_name or "SkillHub"


def _active_skill_metadata(agent: Agent, *, latest_versions_by_skill_id: Mapping[str, int] | None = None) -> list[AgentSkillMetadataResponse] | None:
    """Return ordered display metadata for active agent skill bindings."""
    active_associations = [association for association in agent.agent_skills if association.deleted_at is None and association.enabled and association.skill_install is not None]
    if not active_associations:
        return None

    latest_versions_by_skill_id = latest_versions_by_skill_id or {}
    active_associations.sort(key=lambda association: (association.display_order, association.id))
    metadata: list[AgentSkillMetadataResponse] = []
    for association in active_associations:
        install = association.skill_install
        install_active = install is not None and install.deleted_at is None
        current_version = install.current_version if install is not None else None
        definition = install.definition if install is not None else None
        if definition is None and current_version is not None:
            definition = current_version.definition

        name = None
        if definition is not None:
            name = definition.name
        if name is None:
            name = "unknown"

        current_version_matches_install = install is not None and current_version is not None and current_version.id == install.current_version_id
        current_version_matches_definition = install is not None and current_version is not None and current_version.skill_definition_id == install.skill_definition_id
        current_version_matches_terminal = install is not None and current_version is not None and current_version.skill_id == install.skill_id and current_version.version_number == install.version_number
        available = install_active and definition is not None and current_version_matches_install and current_version_matches_definition and current_version_matches_terminal
        terminal_skill_id = str(install.skill_id) if install is not None and install.skill_id is not None else None
        latest_version_number = latest_versions_by_skill_id.get(terminal_skill_id) if terminal_skill_id is not None else None
        update_available = None
        if available and install is not None and latest_version_number is not None:
            update_available = latest_version_number != install.version_number
        source, source_label = _skill_source_for_agent(agent, definition, install.skill if install is not None else None)

        metadata.append(
            AgentSkillMetadataResponse(
                name=name,
                skill_installation_id=install.id if install is not None else None,
                skill_id=terminal_skill_id,
                version_number=install.version_number if install is not None else None,
                current_platform_version=current_version.version_number if current_version is not None else None,
                source=source,
                source_label=source_label,
                update_available=update_available,
                available=available,
                status="available" if available else "unavailable",
            )
        )
    return metadata


def _collect_bound_skill_ids(agents: list[Agent]) -> set[str]:
    """Collect terminal Skill IDs from active install-backed bindings."""
    skill_ids: set[str] = set()
    for agent in agents:
        for association in agent.agent_skills:
            if association.deleted_at is not None or not association.enabled or association.skill_install is None:
                continue
            install = association.skill_install
            if install.deleted_at is not None:
                continue
            if install.skill_id is not None:
                skill_ids.add(str(install.skill_id))
    return skill_ids


async def _load_latest_version_numbers_by_skill(db: AsyncSession, skill_ids: set[str]) -> dict[str, int]:
    """Load latest published platform version numbers for update badges only."""
    latest_versions_by_skill_id: dict[str, int] = {}
    for skill_id in skill_ids:
        release = await SkillReleaseRepository.get_latest_published_release_for_skill(db, skill_id=skill_id)
        if release is not None:
            latest_versions_by_skill_id[skill_id] = release.version_number
    return latest_versions_by_skill_id


def _agent_to_response(
    agent: Agent,
    *,
    include_soul: bool = False,
    latest_versions_by_skill_id: Mapping[str, int] | None = None,
) -> AgentResponse:
    """Convert a database agent row to the API response model."""
    return AgentResponse(
        name=agent.name,
        description=agent.description or "",
        skill_metadata=_active_skill_metadata(agent, latest_versions_by_skill_id=latest_versions_by_skill_id),
        soul=agent.soul if include_soul else None,
    )


async def _resolve_skill_installation_ids_for_request(
    db: AsyncSession,
    *,
    user_id: int,
    skill_installation_ids: list[int] | None,
    skill_names: list[str] | None,
) -> list[int]:
    """Resolve install IDs for terminal custom Agent bindings."""
    if skill_names is not None:
        raise HTTPException(status_code=400, detail="Agent skill name bindings are removed. Submit skill_installation_ids.")
    if skill_installation_ids is not None:
        resolved: list[int] = []
        seen_install_ids: set[int] = set()
        for skill_installation_id in skill_installation_ids:
            if skill_installation_id in seen_install_ids:
                raise HTTPException(status_code=400, detail=f"Duplicate skill installation '{skill_installation_id}'")
            seen_install_ids.add(skill_installation_id)
            install = await SkillInstallRepository.get_by_id_for_user(db, user_id=user_id, skill_installation_id=skill_installation_id)
            if install is None:
                raise HTTPException(status_code=400, detail=f"Skill installation '{skill_installation_id}' not found")
            resolved.append(install.id)
        return resolved
    return []


def _reject_removed_agent_binding_fields(request: AgentCreateRequest | AgentUpdateRequest) -> None:
    """Reject legacy Agent binding fields while preserving explicit 400 errors."""
    extra_fields = set(request.model_extra or {})
    if "skills" in extra_fields:
        raise HTTPException(status_code=400, detail="Agent skill name bindings are removed. Submit skill_installation_ids.")
    if "skill_install_ids" in extra_fields:
        raise HTTPException(status_code=400, detail="skill_install_ids is removed. Submit skill_installation_ids.")
    if "system_skill_version_ids" in extra_fields or "system_skill_definition_ids" in extra_fields:
        raise HTTPException(status_code=400, detail="Direct system Skill bindings are removed from custom Agents. Configure default_chat.system_skills or bind a skill_installation_id.")


@router.get(
    "/agents",
    response_model=AgentsListResponse,
    response_model_exclude_none=True,
    summary="List Custom Agents",
    description="List all custom agents owned by the current user.",
)
async def list_agents(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgentsListResponse:
    try:
        agents = await AgentRepository.list_agents(db, current_user.id)
        latest_versions_by_skill_id = await _load_latest_version_numbers_by_skill(db, _collect_bound_skill_ids(agents))
        return AgentsListResponse(agents=[_agent_to_response(agent, latest_versions_by_skill_id=latest_versions_by_skill_id) for agent in agents])
    except Exception as e:
        logger.error(f"Failed to list agents: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list agents: {str(e)}")


@router.get(
    "/agents/check",
    summary="Check Agent Name",
    description="Validate an agent name and check if it is available (case-insensitive).",
)
async def check_agent_name(
    name: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    _validate_agent_name(name)
    normalized = _normalize_agent_name(name)
    available = await AgentRepository.get_agent_by_name(db, user_id=current_user.id, name=normalized) is None
    return {"available": available, "name": normalized}


@router.get(
    "/agents/{name}",
    response_model=AgentResponse,
    response_model_exclude_none=True,
    summary="Get Custom Agent",
    description="Retrieve details and SOUL.md content for a specific custom agent.",
)
async def get_agent(
    name: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgentResponse:
    _validate_agent_name(name)
    normalized_name = _normalize_agent_name(name)

    try:
        agent = await AgentRepository.get_agent_by_name(db, user_id=current_user.id, name=normalized_name)
        if agent is None:
            raise HTTPException(status_code=404, detail=f"Agent '{normalized_name}' not found")
        latest_versions_by_skill_id = await _load_latest_version_numbers_by_skill(db, _collect_bound_skill_ids([agent]))
        return _agent_to_response(agent, include_soul=True, latest_versions_by_skill_id=latest_versions_by_skill_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get agent '{normalized_name}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get agent: {str(e)}")


@router.post(
    "/agents",
    response_model=AgentResponse,
    response_model_exclude_none=True,
    status_code=201,
    summary="Create Custom Agent",
    description="Create a new custom agent in the database.",
)
async def create_agent_endpoint(
    request: AgentCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgentResponse:
    _validate_agent_name(request.name)
    normalized_name = _normalize_agent_name(request.name)

    try:
        _reject_removed_agent_binding_fields(request)
        existing_agent = await AgentRepository.get_agent_by_name(db, user_id=current_user.id, name=normalized_name)
        if existing_agent is not None:
            raise HTTPException(status_code=409, detail=f"Agent '{normalized_name}' already exists")

        agent = await AgentRepository.create_agent(
            db,
            user_id=current_user.id,
            name=normalized_name,
            description=request.description or "",
            soul=request.soul or "",
            mcp_config=None,
            commit=False,
        )

        if request.skill_installation_ids is not None:
            skill_installation_ids = await _resolve_skill_installation_ids_for_request(
                db,
                user_id=current_user.id,
                skill_installation_ids=request.skill_installation_ids,
                skill_names=None,
            )
            agent = await AgentRepository.replace_agent_skills(db, agent=agent, skill_ids=[], skill_installation_ids=skill_installation_ids, commit=True)
        else:
            await db.commit()
            refreshed = await AgentRepository.get_agent_by_id(db, agent.id)
            if refreshed is None:
                raise HTTPException(status_code=500, detail=f"Failed to reload agent '{normalized_name}'")
            agent = refreshed

        logger.info(f"Created agent '{normalized_name}' for user {current_user.id}")
        latest_versions_by_skill_id = await _load_latest_version_numbers_by_skill(db, _collect_bound_skill_ids([agent]))
        return _agent_to_response(agent, include_soul=True, latest_versions_by_skill_id=latest_versions_by_skill_id)
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to create agent '{request.name}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create agent: {str(e)}")


@router.put(
    "/agents/{name}",
    response_model=AgentResponse,
    response_model_exclude_none=True,
    summary="Update Custom Agent",
    description="Update an existing custom agent in the database.",
)
async def update_agent(
    name: str,
    request: AgentUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgentResponse:
    _validate_agent_name(name)
    normalized_name = _normalize_agent_name(name)

    try:
        _reject_removed_agent_binding_fields(request)
        agent = await AgentRepository.get_agent_by_name(db, user_id=current_user.id, name=normalized_name)
        if agent is None:
            raise HTTPException(status_code=404, detail=f"Agent '{normalized_name}' not found")

        agent = await AgentRepository.update_agent(
            db,
            agent=agent,
            description=request.description,
            soul=request.soul,
            commit=False,
        )

        if "skill_installation_ids" in request.model_fields_set:
            skill_installation_ids = await _resolve_skill_installation_ids_for_request(
                db,
                user_id=current_user.id,
                skill_installation_ids=request.skill_installation_ids,
                skill_names=None,
            )
            agent = await AgentRepository.replace_agent_skills(db, agent=agent, skill_ids=[], skill_installation_ids=skill_installation_ids, commit=True)
        else:
            await db.commit()
            refreshed = await AgentRepository.get_agent_by_id(db, agent.id)
            if refreshed is None:
                raise HTTPException(status_code=500, detail=f"Failed to reload agent '{normalized_name}'")
            agent = refreshed

        logger.info(f"Updated agent '{normalized_name}' for user {current_user.id}")
        latest_versions_by_skill_id = await _load_latest_version_numbers_by_skill(db, _collect_bound_skill_ids([agent]))
        return _agent_to_response(agent, include_soul=True, latest_versions_by_skill_id=latest_versions_by_skill_id)
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to update agent '{normalized_name}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update agent: {str(e)}")


class UserProfileResponse(BaseModel):
    """Response model for the global user profile (USER.md)."""

    content: str | None = Field(default=None, description="USER.md content, or null if not yet created")


class UserProfileUpdateRequest(BaseModel):
    """Request body for setting the global user profile."""

    content: str = Field(default="", description="USER.md content - describes the user's background and preferences")


@router.get(
    "/user-profile",
    response_model=UserProfileResponse,
    summary="Get User Profile",
    description="Read the global USER.md file that is injected into all custom agents.",
)
async def get_user_profile() -> UserProfileResponse:
    try:
        user_md_path = get_paths().user_md_file
        if not user_md_path.exists():
            return UserProfileResponse(content=None)
        raw = user_md_path.read_text(encoding="utf-8").strip()
        return UserProfileResponse(content=raw or None)
    except Exception as e:
        logger.error(f"Failed to read user profile: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to read user profile: {str(e)}")


@router.put(
    "/user-profile",
    response_model=UserProfileResponse,
    summary="Update User Profile",
    description="Write the global USER.md file that is injected into all custom agents.",
)
async def update_user_profile(request: UserProfileUpdateRequest) -> UserProfileResponse:
    try:
        paths = get_paths()
        paths.base_dir.mkdir(parents=True, exist_ok=True)
        paths.user_md_file.write_text(request.content, encoding="utf-8")
        logger.info(f"Updated USER.md at {paths.user_md_file}")
        return UserProfileResponse(content=request.content or None)
    except Exception as e:
        logger.error(f"Failed to update user profile: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update user profile: {str(e)}")


@router.delete(
    "/agents/{name}",
    status_code=204,
    summary="Delete Custom Agent",
    description="Soft-delete a custom agent and its active skill bindings.",
)
async def delete_agent(
    name: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    _validate_agent_name(name)
    normalized_name = _normalize_agent_name(name)

    try:
        agent = await AgentRepository.get_agent_by_name(db, user_id=current_user.id, name=normalized_name)
        if agent is None:
            raise HTTPException(status_code=404, detail=f"Agent '{normalized_name}' not found")

        await AgentRepository.soft_delete_agent(db, agent=agent, commit=True)
        logger.info(f"Deleted agent '{normalized_name}' for user {current_user.id}")
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to delete agent '{normalized_name}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to delete agent: {str(e)}")
