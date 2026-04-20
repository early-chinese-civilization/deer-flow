"""CRUD API for user-owned agents stored in the gateway database."""

from __future__ import annotations

import logging
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.gateway.db.models import Agent, User
from app.gateway.db.repository import AgentRepository, SkillRepository
from app.gateway.deps import get_current_user, get_db
from deerflow.config.paths import get_paths

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["agents"])

AGENT_NAME_PATTERN = re.compile(r"^[A-Za-z0-9-]+$")


class AgentResponse(BaseModel):
    """Response model for a custom agent."""

    name: str = Field(..., description="Agent name (hyphen-case)")
    description: str = Field(default="", description="Agent description")
    skills: list[str] | None = Field(default=None, description="Optional skills whitelist")
    soul: str | None = Field(default=None, description="SOUL.md content (included on GET /{name})")


class AgentsListResponse(BaseModel):
    """Response model for listing all custom agents."""

    agents: list[AgentResponse]


class AgentCreateRequest(BaseModel):
    """Request body for creating a custom agent."""

    name: str = Field(..., description="Agent name (must match ^[A-Za-z0-9-]+$, stored as lowercase)")
    description: str = Field(default="", description="Agent description")
    skills: list[str] | None = Field(default=None, description="Optional skills whitelist")
    soul: str = Field(default="", description="SOUL.md content - agent personality and behavioral guardrails")


class AgentUpdateRequest(BaseModel):
    """Request body for updating a custom agent."""

    description: str | None = Field(default=None, description="Updated description")
    skills: list[str] | None = Field(default=None, description="Updated skills whitelist")
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
    active_associations = [
        association
        for association in agent.agent_skills
        if association.deleted_at is None and association.skill is not None
    ]
    if not active_associations:
        return None

    active_associations.sort(key=lambda association: (association.display_order, association.id))
    return [association.skill.name for association in active_associations]


def _agent_to_response(agent: Agent, *, include_soul: bool = False) -> AgentResponse:
    """Convert a database agent row to the API response model."""
    return AgentResponse(
        name=agent.name,
        description=agent.description or "",
        skills=_active_skill_names(agent),
        soul=agent.soul if include_soul else None,
    )


async def _resolve_skill_ids(
    db: AsyncSession,
    *,
    user_id: int,
    skill_names: list[str],
) -> list[int]:
    """Resolve request skill names to current-user custom skill IDs."""
    skill_ids: list[int] = []
    seen_skill_names: set[str] = set()
    for skill_name in skill_names:
        if skill_name in seen_skill_names:
            raise HTTPException(status_code=400, detail=f"Duplicate skill '{skill_name}'")
        seen_skill_names.add(skill_name)
        skill = await SkillRepository.get_user_skill_by_name(db, user_id=user_id, name=skill_name)
        if skill is None:
            raise HTTPException(status_code=400, detail=f"Skill '{skill_name}' not found")
        skill_ids.append(skill.id)
    return skill_ids


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
        return AgentsListResponse(agents=[_agent_to_response(agent) for agent in agents])
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
        return _agent_to_response(agent, include_soul=True)
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

        if request.skills is not None:
            skill_ids = await _resolve_skill_ids(db, user_id=current_user.id, skill_names=request.skills)
            agent = await AgentRepository.replace_agent_skills(db, agent=agent, skill_ids=skill_ids, commit=True)
        else:
            await db.commit()
            refreshed = await AgentRepository.get_agent_by_id(db, agent.id)
            if refreshed is None:
                raise HTTPException(status_code=500, detail=f"Failed to reload agent '{normalized_name}'")
            agent = refreshed

        logger.info(f"Created agent '{normalized_name}' for user {current_user.id}")
        return _agent_to_response(agent, include_soul=True)
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

        if "skills" in request.model_fields_set:
            requested_skills = request.skills or []
            skill_ids = await _resolve_skill_ids(db, user_id=current_user.id, skill_names=requested_skills)
            agent = await AgentRepository.replace_agent_skills(db, agent=agent, skill_ids=skill_ids, commit=True)
        else:
            await db.commit()
            refreshed = await AgentRepository.get_agent_by_id(db, agent.id)
            if refreshed is None:
                raise HTTPException(status_code=500, detail=f"Failed to reload agent '{normalized_name}'")
            agent = refreshed

        logger.info(f"Updated agent '{normalized_name}' for user {current_user.id}")
        return _agent_to_response(agent, include_soul=True)
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
