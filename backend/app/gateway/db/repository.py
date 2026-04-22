"""Database access helpers for Gateway-owned auth, thread, and workspace tables."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.gateway.db.models import Agent, AgentSkill, Memory, Skill, Thread, User, Workspace


@dataclass(frozen=True)
class RuntimeSkillDescriptor:
    """Resolved skill metadata injected into the runtime prompt."""

    name: str
    description: str


@dataclass(frozen=True)
class RuntimeAgentBundle:
    """Resolved runtime resources for a user + agent combination."""

    user_id: int
    agent_name: str | None
    memory_json: dict[str, Any]
    soul: str | None
    skills: list[RuntimeSkillDescriptor]


def _as_optional_uuid(value: str | uuid.UUID | None) -> uuid.UUID | None:
    """Normalize optional UUID values."""
    if value is None or isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(value)


class UserRepository:
    """Persistence helpers for local user records."""

    @staticmethod
    def _build_user_values(
        *,
        external_auth_id: str,
        username: str,
        display_name: str,
        email: str | None,
        given_name: str | None,
        family_name: str | None,
        email_verified: bool,
    ) -> dict[str, Any]:
        return {
            "external_auth_id": external_auth_id,
            "username": username,
            "display_name": display_name,
            "email": email,
            "given_name": given_name,
            "family_name": family_name,
            "email_verified": email_verified,
        }

    @staticmethod
    async def upsert_user(
        db: AsyncSession,
        external_auth_id: str,
        username: str,
        display_name: str,
        email: str | None = None,
        given_name: str | None = None,
        family_name: str | None = None,
        email_verified: bool = False,
    ) -> User:
        """Insert or update a local user mapped from Keycloak."""
        insert_values = UserRepository._build_user_values(
            external_auth_id=external_auth_id,
            username=username,
            display_name=display_name,
            email=email,
            given_name=given_name,
            family_name=family_name,
            email_verified=email_verified,
        )
        update_values = {
            key: value
            for key, value in insert_values.items()
            if key != "external_auth_id"
        }

        stmt = (
            insert(User)
            .values(**insert_values)
            .on_conflict_do_update(
                index_elements=["external_auth_id"],
                set_=update_values,
            )
            .returning(User)
        )
        result = await db.execute(stmt)
        await db.commit()
        return result.scalar_one()

    @staticmethod
    async def get_user_by_id(db: AsyncSession, user_id: int) -> User | None:
        """Load a user by primary key."""
        result = await db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_user_by_external_auth_id(
        db: AsyncSession,
        external_auth_id: str,
    ) -> User | None:
        """Load a user by external authentication subject."""
        result = await db.execute(
            select(User).where(User.external_auth_id == external_auth_id)
        )
        return result.scalar_one_or_none()


class ThreadRepository:
    """Persistence helpers for canonical thread records."""

    @staticmethod
    async def create_thread(
        db: AsyncSession,
        *,
        thread_id: str,
        user_id: int,
        agent_id: int | None = None,
        workspace_id: str | uuid.UUID | None,
        title: str | None = None,
        status: str = "idle",
        metadata: dict[str, Any] | None = None,
        commit: bool = True,
    ) -> Thread:
        """Create a thread row."""
        thread = Thread(
            thread_id=thread_id,
            user_id=user_id,
            agent_id=agent_id,
            workspace_id=_as_optional_uuid(workspace_id),
            title=title,
            status=status,
            thread_metadata=dict(metadata or {}),
        )
        db.add(thread)
        await db.flush()
        await db.refresh(thread)
        if commit:
            await db.commit()
            await db.refresh(thread)
        return thread

    @staticmethod
    async def get_thread_by_id(
        db: AsyncSession,
        thread_id: str,
    ) -> Thread | None:
        """Load a thread row by thread_id."""
        result = await db.execute(select(Thread).where(Thread.thread_id == thread_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def search_threads(
        db: AsyncSession,
        *,
        user_id: int,
        status: str | None = None,
        metadata: dict[str, Any] | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Thread]:
        """Search threads owned by a user."""
        stmt = select(Thread).where(Thread.user_id == user_id)
        if status is not None:
            stmt = stmt.where(Thread.status == status)
        if metadata:
            stmt = stmt.where(Thread.thread_metadata.contains(metadata))

        stmt = stmt.order_by(Thread.updated_at.desc(), Thread.created_at.desc())
        stmt = stmt.offset(offset).limit(limit)

        result = await db.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def update_thread(
        db: AsyncSession,
        *,
        thread_id: str,
        title: str | None = None,
        status: str | None = None,
        metadata: dict[str, Any] | None = None,
        commit: bool = True,
    ) -> Thread | None:
        """Patch title, status, and metadata for an existing thread."""
        thread = await ThreadRepository.get_thread_by_id(db, thread_id)
        if thread is None:
            return None

        if title is not None:
            thread.title = title
        if status is not None:
            thread.status = status
        if metadata:
            merged_metadata = dict(thread.thread_metadata or {})
            merged_metadata.update(metadata)
            thread.thread_metadata = merged_metadata

        await db.flush()
        await db.refresh(thread)
        if commit:
            await db.commit()
            await db.refresh(thread)
        return thread

    @staticmethod
    async def delete_thread(
        db: AsyncSession,
        *,
        thread_id: str,
        commit: bool = True,
    ) -> bool:
        """Delete a thread row."""
        result = await db.execute(delete(Thread).where(Thread.thread_id == thread_id))
        if commit:
            await db.commit()
        return result.rowcount > 0


class WorkspaceRepository:
    """Persistence helpers for workspace records."""

    @staticmethod
    async def create_workspace(
        db: AsyncSession,
        user_id: int,
        name: str | None = None,
        *,
        commit: bool = True,
    ) -> Workspace:
        """Create a workspace record."""
        workspace = Workspace(
            user_id=user_id,
            name=name,
        )
        db.add(workspace)
        await db.flush()
        if workspace.file_path is None:
            workspace.file_path = f"workspaces/{workspace.id}"
            await db.flush()
        await db.refresh(workspace)
        if commit:
            await db.commit()
            await db.refresh(workspace)
        return workspace

    @staticmethod
    async def get_workspace_by_id(
        db: AsyncSession,
        workspace_id: str | uuid.UUID,
    ) -> Workspace | None:
        """Load a workspace by ID."""
        workspace_uuid = _as_optional_uuid(workspace_id)
        if workspace_uuid is None:
            return None
        result = await db.execute(select(Workspace).where(Workspace.id == workspace_uuid))
        return result.scalar_one_or_none()

    @staticmethod
    async def delete_workspace(
        db: AsyncSession,
        workspace_id: str | uuid.UUID,
        *,
        commit: bool = True,
    ) -> bool:
        """Delete a workspace row."""
        workspace_uuid = _as_optional_uuid(workspace_id)
        if workspace_uuid is None:
            return False
        result = await db.execute(delete(Workspace).where(Workspace.id == workspace_uuid))
        if commit:
            await db.commit()
        return result.rowcount > 0

    @staticmethod
    async def update_workspace_file_path(
        db: AsyncSession,
        *,
        workspace_id: str | uuid.UUID,
        file_path: str,
        commit: bool = True,
    ) -> Workspace | None:
        """Update the canonical OSS root prefix for a workspace."""
        workspace = await WorkspaceRepository.get_workspace_by_id(db, workspace_id)
        if workspace is None:
            return None

        workspace.file_path = file_path
        await db.flush()
        await db.refresh(workspace)
        if commit:
            await db.commit()
            await db.refresh(workspace)
        return workspace


class AgentRepository:
    """Persistence helpers for agent records."""

    @staticmethod
    def _active_agent_stmt():
        return select(Agent).where(Agent.deleted_at.is_(None))

    @staticmethod
    def _with_agent_skills(stmt):
        return stmt.options(selectinload(Agent.agent_skills).selectinload(AgentSkill.skill))

    @staticmethod
    async def create_agent(
        db: AsyncSession,
        *,
        user_id: int,
        name: str,
        description: str | None = None,
        soul: str | None = None,
        mcp_config: dict[str, Any] | None = None,
        commit: bool = True,
    ) -> Agent:
        """Create an agent record."""
        agent = Agent(
            user_id=user_id,
            name=name,
            description=description,
            soul=soul,
            mcp_config=mcp_config,
        )
        db.add(agent)
        await db.flush()
        await db.refresh(agent)
        if commit:
            await db.commit()
            await db.refresh(agent)
        return agent

    @staticmethod
    async def get_agent_by_id(db: AsyncSession, agent_id: int) -> Agent | None:
        """Load an agent by ID."""
        stmt = AgentRepository._with_agent_skills(
            AgentRepository._active_agent_stmt().where(Agent.id == agent_id)
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def list_agents(db: AsyncSession, user_id: int) -> list[Agent]:
        """List all agents for a user."""
        stmt = AgentRepository._with_agent_skills(
            AgentRepository._active_agent_stmt()
            .where(Agent.user_id == user_id)
            .order_by(Agent.created_at.desc())
        )
        result = await db.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def get_agent_by_name(db: AsyncSession, *, user_id: int, name: str) -> Agent | None:
        """Load an active user-owned agent by name."""
        stmt = AgentRepository._with_agent_skills(
            AgentRepository._active_agent_stmt().where(Agent.user_id == user_id, Agent.name == name)
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    def _active_runtime_skills(agent: Agent) -> list[RuntimeSkillDescriptor]:
        """Return ordered active skill descriptors for an agent."""
        active_associations = [
            association
            for association in agent.agent_skills
            if association.deleted_at is None
            and association.enabled
            and association.skill is not None
            and association.skill.deleted_at is None
        ]
        active_associations.sort(key=lambda association: (association.display_order, association.id))
        return [
            RuntimeSkillDescriptor(
                name=association.skill.name,
                description=association.skill.description or "",
            )
            for association in active_associations
        ]

    @staticmethod
    async def _public_runtime_skills(db: AsyncSession) -> list[RuntimeSkillDescriptor]:
        """Return ordered descriptors for all active public skills."""
        result = await db.execute(
            select(Skill)
            .where(
                Skill.user_id.is_(None),
                Skill.deleted_at.is_(None),
            )
            .order_by(Skill.name.asc(), Skill.owner_user_id.asc().nullsfirst(), Skill.created_at.desc())
        )
        return [
            RuntimeSkillDescriptor(
                name=skill.name,
                description=skill.description or "",
            )
            for skill in result.scalars().all()
        ]

    @staticmethod
    async def get_runtime_agent_bundle(
        db: AsyncSession,
        *,
        user_id: int,
        agent_name: str | None,
    ) -> RuntimeAgentBundle:
        """Resolve runtime memory, soul, and skills for the given user and agent."""
        memory_row = await MemoryRepository.get_memory_by_user_id(db, user_id)
        memory_json = dict(memory_row.memory_json or {}) if memory_row is not None else {}

        normalized_agent_name = agent_name.strip().lower() if isinstance(agent_name, str) and agent_name.strip() else None
        if normalized_agent_name is None:
            return RuntimeAgentBundle(
                user_id=user_id,
                agent_name=None,
                memory_json=memory_json,
                soul=None,
                skills=await AgentRepository._public_runtime_skills(db),
            )

        agent = await AgentRepository.get_agent_by_name(db, user_id=user_id, name=normalized_agent_name)
        if agent is None:
            return RuntimeAgentBundle(
                user_id=user_id,
                agent_name=normalized_agent_name,
                memory_json=memory_json,
                soul=None,
                skills=await AgentRepository._public_runtime_skills(db),
            )

        return RuntimeAgentBundle(
            user_id=user_id,
            agent_name=agent.name,
            memory_json=memory_json,
            soul=agent.soul,
            skills=AgentRepository._active_runtime_skills(agent),
        )

    @staticmethod
    async def update_agent(
        db: AsyncSession,
        *,
        agent: Agent,
        description: str | None = None,
        soul: str | None = None,
        commit: bool = True,
    ) -> Agent:
        """Update mutable agent fields."""
        if description is not None:
            agent.description = description
        if soul is not None:
            agent.soul = soul

        agent.updated_at = datetime.now(UTC)
        await db.flush()
        await db.refresh(agent)
        if commit:
            await db.commit()
            await db.refresh(agent)
        return agent

    @staticmethod
    async def soft_delete_agent(
        db: AsyncSession,
        *,
        agent: Agent,
        commit: bool = True,
    ) -> None:
        """Soft-delete an agent and its active skill associations."""
        reloaded_agent = await AgentRepository.get_agent_by_id(db, agent.id)
        if reloaded_agent is None:
            return

        now = datetime.now(UTC)
        reloaded_agent.deleted_at = now
        reloaded_agent.updated_at = now
        for association in reloaded_agent.agent_skills:
            if association.deleted_at is None:
                association.deleted_at = now
        await db.flush()
        if commit:
            await db.commit()

    @staticmethod
    async def replace_agent_skills(
        db: AsyncSession,
        *,
        agent: Agent,
        skill_ids: list[int],
        commit: bool = True,
    ) -> Agent:
        """Replace the agent's active skill associations with the provided skills."""
        reloaded_agent = await AgentRepository.get_agent_by_id(db, agent.id)
        if reloaded_agent is None:
            raise ValueError(f"Agent {agent.id} disappeared before skill replacement")

        now = datetime.now(UTC)
        for association in reloaded_agent.agent_skills:
            if association.deleted_at is None:
                association.deleted_at = now

        for display_order, skill_id in enumerate(skill_ids):
            association = AgentSkill(
                agent_id=reloaded_agent.id,
                skill_id=skill_id,
                display_order=display_order,
                enabled=True,
            )
            db.add(association)

        reloaded_agent.updated_at = now
        await db.flush()
        if commit:
            await db.commit()

        refreshed = await AgentRepository.get_agent_by_id(db, reloaded_agent.id)
        if refreshed is None:
            raise ValueError(f"Agent {reloaded_agent.id} disappeared during skill replacement")
        return refreshed


class SkillRepository:
    """Persistence helpers for skill records."""

    @staticmethod
    def _active_skill_stmt():
        return select(Skill).where(Skill.deleted_at.is_(None))

    @staticmethod
    def _with_owner_user(stmt):
        return stmt.options(selectinload(Skill.owner_user))

    @staticmethod
    async def create_skill(
        db: AsyncSession,
        *,
        user_id: int | None,
        owner_user_id: int | None = None,
        name: str,
        display_name: str | None,
        description: str | None,
        file_path: str,
        commit: bool = True,
    ) -> Skill:
        """Create a skill record."""
        skill = Skill(
            user_id=user_id,
            owner_user_id=owner_user_id,
            name=name,
            display_name=display_name,
            description=description,
            file_path=file_path,
        )
        db.add(skill)
        await db.flush()
        await db.refresh(skill)
        if commit:
            await db.commit()
            await db.refresh(skill)
        return skill

    @staticmethod
    async def get_skill_by_id(db: AsyncSession, skill_id: int) -> Skill | None:
        """Load a skill by ID."""
        stmt = SkillRepository._with_owner_user(
            select(Skill).where(Skill.id == skill_id, Skill.deleted_at.is_(None))
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def list_skills(db: AsyncSession, user_id: int | None = None) -> list[Skill]:
        """List skills (public only if user_id is None, else public plus current user's custom skills)."""
        stmt = SkillRepository._with_owner_user(SkillRepository._active_skill_stmt())
        if user_id is not None:
            stmt = stmt.where((Skill.user_id == user_id) | (Skill.user_id.is_(None)))
        else:
            stmt = stmt.where(Skill.user_id.is_(None))
        result = await db.execute(stmt.order_by(Skill.created_at.desc()))
        return result.scalars().all()

    @staticmethod
    async def list_visible_skills(db: AsyncSession, *, user_id: int) -> list[Skill]:
        """List public skills plus the current user's skills."""
        stmt = SkillRepository._with_owner_user(
            SkillRepository._active_skill_stmt()
            .where((Skill.user_id == user_id) | (Skill.user_id.is_(None)))
            .order_by(
                Skill.user_id.is_(None).desc(),
                Skill.name.asc(),
                Skill.owner_user_id.asc().nullsfirst(),
                Skill.created_at.desc(),
            )
        )
        result = await db.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def list_public_skills(db: AsyncSession) -> list[Skill]:
        """List all active public skills, including seeded and user-published entries."""
        stmt = SkillRepository._with_owner_user(
            SkillRepository._active_skill_stmt()
            .where(Skill.user_id.is_(None))
            .order_by(Skill.name.asc(), Skill.owner_user_id.asc().nullsfirst(), Skill.created_at.desc())
        )
        result = await db.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def list_custom_skills(db: AsyncSession, *, user_id: int) -> list[Skill]:
        """List all active custom skills owned by the current user."""
        stmt = SkillRepository._with_owner_user(
            SkillRepository._active_skill_stmt()
            .where(Skill.user_id == user_id)
            .order_by(Skill.name.asc(), Skill.created_at.desc())
        )
        result = await db.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def get_user_skill_by_name(db: AsyncSession, *, user_id: int, name: str) -> Skill | None:
        """Load the current user's active skill by name."""
        stmt = SkillRepository._with_owner_user(
            SkillRepository._active_skill_stmt().where(Skill.user_id == user_id, Skill.name == name)
        )
        result = await db.execute(
            stmt
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_public_skill_by_name_and_owner(
        db: AsyncSession,
        *,
        name: str,
        owner_user_id: int | None,
    ) -> Skill | None:
        """Load an active public skill by name and publisher."""
        stmt = SkillRepository._with_owner_user(
            SkillRepository._active_skill_stmt().where(
                Skill.user_id.is_(None),
                Skill.name == name,
                Skill.owner_user_id.is_(owner_user_id) if owner_user_id is None else Skill.owner_user_id == owner_user_id,
            )
        )
        result = await db.execute(
            stmt
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_system_public_skill_by_name(db: AsyncSession, *, name: str) -> Skill | None:
        """Load an active seeded public skill by name."""
        return await SkillRepository.get_public_skill_by_name_and_owner(db, name=name, owner_user_id=None)

    @staticmethod
    async def get_public_skill_by_name(db: AsyncSession, *, name: str) -> Skill | None:
        """Load any active public skill by name, preferring seeded public entries."""
        system_skill = await SkillRepository.get_system_public_skill_by_name(db, name=name)
        if system_skill is not None:
            return system_skill

        result = await db.execute(
            SkillRepository._with_owner_user(
                SkillRepository._active_skill_stmt()
            .where(
                Skill.user_id.is_(None),
                Skill.name == name,
                Skill.owner_user_id.is_not(None),
            )
            .order_by(Skill.created_at.desc())
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_visible_skill_by_name(db: AsyncSession, *, user_id: int, name: str) -> Skill | None:
        """Load a visible skill, preferring the current user's copy over the public one."""
        user_skill = await SkillRepository.get_user_skill_by_name(db, user_id=user_id, name=name)
        if user_skill is not None:
            return user_skill
        return await SkillRepository.get_public_skill_by_name(db, name=name)

    @staticmethod
    async def list_bound_agent_names_for_skill(
        db: AsyncSession,
        *,
        user_id: int,
        skill_id: int,
    ) -> list[str]:
        """List active user-owned agent names currently bound to a skill."""
        result = await db.execute(
            select(Agent.name)
            .join(AgentSkill, AgentSkill.agent_id == Agent.id)
            .where(
                Agent.user_id == user_id,
                Agent.deleted_at.is_(None),
                AgentSkill.skill_id == skill_id,
                AgentSkill.deleted_at.is_(None),
            )
            .order_by(Agent.name.asc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def rebind_agent_skills(
        db: AsyncSession,
        *,
        user_id: int,
        old_skill_id: int,
        new_skill_id: int,
    ) -> None:
        """Rebind active user-owned agent skill associations to a new skill row."""
        user_agent_ids = (
            select(Agent.id)
            .where(
                Agent.user_id == user_id,
                Agent.deleted_at.is_(None),
            )
            .scalar_subquery()
        )
        await db.execute(
            update(AgentSkill)
            .where(
                AgentSkill.skill_id == old_skill_id,
                AgentSkill.deleted_at.is_(None),
                AgentSkill.agent_id.in_(user_agent_ids),
            )
            .values(skill_id=new_skill_id)
        )

    @staticmethod
    async def soft_delete_skill(
        db: AsyncSession,
        *,
        skill: Skill,
        commit: bool = True,
    ) -> None:
        """Soft-delete a specific skill row."""
        now = datetime.now(UTC)
        skill.deleted_at = now
        skill.updated_at = now
        await db.flush()
        if commit:
            await db.commit()

    @staticmethod
    async def touch_user_skill(db: AsyncSession, *, user_id: int, name: str, commit: bool = True) -> Skill | None:
        """Refresh updated_at for the current user's skill without changing business fields."""
        skill = await SkillRepository.get_user_skill_by_name(db, user_id=user_id, name=name)
        if skill is None:
            return None

        skill.updated_at = datetime.now(UTC)
        await db.flush()
        await db.refresh(skill)
        if commit:
            await db.commit()
            await db.refresh(skill)
        return skill

    @staticmethod
    async def soft_delete_user_skill(db: AsyncSession, *, user_id: int, name: str, commit: bool = True) -> bool:
        """Soft-delete the current user's skill by name."""
        skill = await SkillRepository.get_user_skill_by_name(db, user_id=user_id, name=name)
        if skill is None:
            return False
        await SkillRepository.soft_delete_skill(db, skill=skill, commit=commit)
        return True


class MemoryRepository:
    """Persistence helpers for memory records."""

    @staticmethod
    async def get_memory_by_user_id(db: AsyncSession, user_id: int) -> Memory | None:
        """Load memory for a user."""
        result = await db.execute(select(Memory).where(Memory.user_id == user_id, Memory.deleted_at.is_(None)))
        return result.scalar_one_or_none()

    @staticmethod
    async def upsert_memory(
        db: AsyncSession,
        user_id: int,
        memory_json: dict[str, Any],
        commit: bool = True,
    ) -> Memory:
        """Create or update the active memory row for a user."""
        stmt = (
            insert(Memory)
            .values(user_id=user_id, memory_json=memory_json)
            .on_conflict_do_update(
                index_elements=["user_id"],
                index_where=Memory.deleted_at.is_(None),
                set_={
                    "memory_json": memory_json,
                    "updated_at": func.now(),
                },
            )
            .returning(Memory)
        )
        result = await db.execute(stmt)
        if commit:
            await db.commit()
        return result.scalar_one()
