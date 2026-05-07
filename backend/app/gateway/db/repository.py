"""Database access helpers for Gateway-owned auth, thread, and workspace tables."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.gateway.db.models import (
    Agent,
    AgentSkill,
    Memory,
    RuntimeManifest,
    Skill,
    SkillDefinition,
    SkillInstall,
    SkillRelease,
    SkillVersion,
    Thread,
    User,
    Workspace,
)
from deerflow.skills.hashing import hash_skill_file_manifest
from deerflow.skills.path_utils import build_skill_virtual_path, resolve_skill_storage_dir


@dataclass(frozen=True)
class RuntimeSkillDescriptor:
    """Resolved skill metadata injected into the runtime prompt."""

    name: str
    description: str
    file_path: str
    virtual_path: str
    skill_definition_id: int
    skill_version_id: int
    skill_install_id: int
    version_number: int
    content_hash: str
    file_manifest_hash: str
    artifact_uri: str
    source_package_version: str | None


@dataclass(frozen=True)
class RuntimeAgentBundle:
    """Resolved runtime resources for a user + agent combination."""

    user_id: int
    agent_name: str | None
    memory_json: dict[str, Any]
    soul: str | None
    skills: list[RuntimeSkillDescriptor]
    manifest_id: str | None = None
    manifest_hash: str | None = None


class RuntimeManifestResolutionError(RuntimeError):
    """Raised when an agent runtime manifest cannot be resolved exactly."""


def _as_optional_uuid(value: str | uuid.UUID | None) -> uuid.UUID | None:
    """Normalize optional UUID values."""
    if value is None or isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(value)


def _get_skills_container_path() -> str:
    """Return the configured skills container path with a stable fallback."""
    try:
        from deerflow.config import get_app_config

        return get_app_config().skills.container_path
    except Exception:
        return "/mnt/skills"


def build_runtime_manifest_hash(manifest_json: dict[str, Any]) -> str:
    """Return the deterministic audit hash for a Runtime Manifest payload."""
    canonical_payload = json.dumps(manifest_json, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()


def _ensure_artifact_integrity(artifact_uri: str, *, skill_name: str, expected_file_manifest_hash: str) -> None:
    """Fail manifest resolution if an immutable artifact is missing or drifted."""
    normalized_artifact = artifact_uri.replace("\\", "/").strip("/")
    parts = [part for part in normalized_artifact.split("/") if part]
    if len(parts) < 2 or parts[0] != "artifacts" or any(part in {".", ".."} for part in parts):
        raise RuntimeManifestResolutionError(f"Skill '{skill_name}' artifact must use immutable artifacts scope: {artifact_uri}")
    if not expected_file_manifest_hash:
        raise RuntimeManifestResolutionError(f"Skill '{skill_name}' artifact is missing file manifest hash")
    try:
        from deerflow.config import get_app_config

        skills_root = get_app_config().skills.get_skills_path()
        artifact_dir = resolve_skill_storage_dir(skills_root, normalized_artifact)
    except Exception as exc:
        raise RuntimeManifestResolutionError(f"Skill '{skill_name}' artifact cannot be resolved") from exc
    if not artifact_dir.exists() or not artifact_dir.is_dir():
        raise RuntimeManifestResolutionError(f"Skill '{skill_name}' artifact is missing: {artifact_uri}")
    if not (artifact_dir / "SKILL.md").exists():
        raise RuntimeManifestResolutionError(f"Skill '{skill_name}' artifact is missing SKILL.md: {artifact_uri}")
    actual_file_manifest_hash = hash_skill_file_manifest(artifact_dir)
    if actual_file_manifest_hash != expected_file_manifest_hash:
        raise RuntimeManifestResolutionError(f"Skill '{skill_name}' artifact file manifest hash mismatch")


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
        update_values = {key: value for key, value in insert_values.items() if key != "external_auth_id"}

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
        result = await db.execute(select(User).where(User.external_auth_id == external_auth_id))
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
        agent_id: int | None = None,
        metadata: dict[str, Any] | None = None,
        commit: bool = True,
    ) -> Thread | None:
        """Patch title, status, agent binding, and metadata for an existing thread."""
        thread = await ThreadRepository.get_thread_by_id(db, thread_id)
        if thread is None:
            return None

        if title is not None:
            thread.title = title
        if status is not None:
            thread.status = status
        if agent_id is not None:
            thread.agent_id = agent_id
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
        id: str | uuid.UUID | None = None,  # 支持前端传入草稿 workspace_id
        *,
        commit: bool = True,
    ) -> Workspace:
        """创建 workspace 记录，支持显式指定 ID（用于草稿场景）"""
        workspace = Workspace(
            id=_as_optional_uuid(id) or uuid.uuid4(),  # 使用传入的 ID 或生成新 ID
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
        return stmt.options(
            selectinload(Agent.agent_skills).selectinload(AgentSkill.skill),
            selectinload(Agent.agent_skills).selectinload(AgentSkill.skill_install).selectinload(SkillInstall.definition),
            selectinload(Agent.agent_skills).selectinload(AgentSkill.skill_install).selectinload(SkillInstall.current_version).selectinload(SkillVersion.definition),
        )

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
        stmt = AgentRepository._with_agent_skills(AgentRepository._active_agent_stmt().where(Agent.id == agent_id))
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def list_agents(db: AsyncSession, user_id: int) -> list[Agent]:
        """List all agents for a user."""
        stmt = AgentRepository._with_agent_skills(AgentRepository._active_agent_stmt().where(Agent.user_id == user_id).order_by(Agent.created_at.desc()))
        result = await db.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def get_agent_by_name(db: AsyncSession, *, user_id: int, name: str) -> Agent | None:
        """Load an active user-owned agent by name."""
        stmt = AgentRepository._with_agent_skills(AgentRepository._active_agent_stmt().where(Agent.user_id == user_id, Agent.name == name))
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    def _build_runtime_skill_descriptor(install: SkillInstall) -> RuntimeSkillDescriptor:
        """Project an install/current version into runtime manifest metadata."""
        version = install.current_version
        definition = install.definition or (version.definition if version is not None else None)
        if version is None:
            raise RuntimeManifestResolutionError(f"Skill install {install.id} has no current version")
        if definition is None:
            raise RuntimeManifestResolutionError(f"Skill install {install.id} has no definition")
        if version.skill_definition_id != install.skill_definition_id:
            raise RuntimeManifestResolutionError(f"Skill install {install.id} points to a version from another definition")
        file_path = version.artifact_uri
        _ensure_artifact_integrity(file_path, skill_name=definition.name, expected_file_manifest_hash=version.file_manifest_hash)
        return RuntimeSkillDescriptor(
            name=definition.name,
            description=version.description or definition.description or "",
            file_path=file_path,
            virtual_path=build_skill_virtual_path(definition.name, container_base_path=_get_skills_container_path()),
            skill_definition_id=definition.id,
            skill_version_id=version.id,
            skill_install_id=install.id,
            version_number=version.version_number,
            content_hash=version.content_hash,
            file_manifest_hash=version.file_manifest_hash,
            artifact_uri=version.artifact_uri,
            source_package_version=version.source_package_version,
        )

    @staticmethod
    def _active_runtime_skills(agent: Agent) -> list[RuntimeSkillDescriptor]:
        """Return ordered active skill descriptors for an agent."""
        active_associations = [association for association in agent.agent_skills if association.deleted_at is None and association.enabled]
        active_associations.sort(key=lambda association: (association.display_order, association.id))
        descriptors: list[RuntimeSkillDescriptor] = []
        for association in active_associations:
            if association.skill_install is None or association.skill_install.deleted_at is not None:
                raise RuntimeManifestResolutionError(f"Agent '{agent.name}' has a skill binding without an active install")
            descriptors.append(AgentRepository._build_runtime_skill_descriptor(association.skill_install))
        return descriptors

    @staticmethod
    async def _create_runtime_manifest(
        db: AsyncSession,
        *,
        user_id: int,
        agent: Agent,
        skills: list[RuntimeSkillDescriptor],
    ) -> RuntimeManifest:
        """Persist the resolved manifest snapshot used by prompt and skill_load."""
        entries = [
            {
                "name": skill.name,
                "description": skill.description,
                "file_path": skill.file_path,
                "virtual_path": skill.virtual_path,
                "skill_definition_id": skill.skill_definition_id,
                "skill_version_id": skill.skill_version_id,
                "skill_install_id": skill.skill_install_id,
                "version_number": skill.version_number,
                "content_hash": skill.content_hash,
                "file_manifest_hash": skill.file_manifest_hash,
                "artifact_uri": skill.artifact_uri,
                "source_package_version": skill.source_package_version,
            }
            for skill in skills
        ]
        manifest_json = {"version": 1, "skills": entries}
        manifest = RuntimeManifest(
            user_id=user_id,
            agent_id=agent.id,
            agent_name=agent.name,
            manifest_json=manifest_json,
            manifest_hash=build_runtime_manifest_hash(manifest_json),
        )
        db.add(manifest)
        await db.flush()
        await db.refresh(manifest)
        return manifest

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
                skills=[],
            )

        agent = await AgentRepository.get_agent_by_name(db, user_id=user_id, name=normalized_agent_name)
        if agent is None:
            raise RuntimeManifestResolutionError(f"Agent '{normalized_agent_name}' not found")

        skills = AgentRepository._active_runtime_skills(agent)
        manifest = await AgentRepository._create_runtime_manifest(db, user_id=user_id, agent=agent, skills=skills)

        return RuntimeAgentBundle(
            user_id=user_id,
            agent_name=agent.name,
            memory_json=memory_json,
            soul=agent.soul,
            skills=skills,
            manifest_id=str(manifest.id),
            manifest_hash=manifest.manifest_hash,
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
        skill_install_ids: list[int] | None = None,
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

        install_ids = skill_install_ids if skill_install_ids is not None else []
        if skill_install_ids is None:
            install_ids = []

        for display_order, skill_id in enumerate(skill_ids):
            association = AgentSkill(
                agent_id=reloaded_agent.id,
                skill_id=skill_id,
                display_order=display_order,
                enabled=True,
            )
            db.add(association)

        for display_order, install_id in enumerate(install_ids):
            association = AgentSkill(
                agent_id=reloaded_agent.id,
                skill_id=None,
                skill_install_id=install_id,
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


class SkillDefinitionRepository:
    """Persistence helpers for stable skill definitions."""

    @staticmethod
    async def get_by_name(db: AsyncSession, *, name: str) -> SkillDefinition | None:
        result = await db.execute(
            select(SkillDefinition).where(
                SkillDefinition.name == name,
                SkillDefinition.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_or_create(
        db: AsyncSession,
        *,
        name: str,
        display_name: str | None,
        description: str | None,
        owner_user_id: int | None,
    ) -> SkillDefinition:
        definition = await SkillDefinitionRepository.get_by_name(db, name=name)
        if definition is not None:
            definition.display_name = display_name or definition.display_name
            definition.description = description or definition.description
            definition.updated_at = datetime.now(UTC)
            await db.flush()
            await db.refresh(definition)
            return definition

        definition = SkillDefinition(
            name=name,
            display_name=display_name,
            description=description,
            owner_user_id=owner_user_id,
        )
        db.add(definition)
        await db.flush()
        await db.refresh(definition)
        return definition


class SkillVersionRepository:
    """Persistence helpers for immutable platform skill versions."""

    @staticmethod
    async def get_by_id(db: AsyncSession, *, skill_version_id: int) -> SkillVersion | None:
        result = await db.execute(select(SkillVersion).options(selectinload(SkillVersion.definition)).where(SkillVersion.id == skill_version_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_definition_and_hash(
        db: AsyncSession,
        *,
        skill_definition_id: int,
        content_hash: str,
    ) -> SkillVersion | None:
        result = await db.execute(
            select(SkillVersion)
            .options(selectinload(SkillVersion.definition))
            .where(
                SkillVersion.skill_definition_id == skill_definition_id,
                SkillVersion.content_hash == content_hash,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_latest_for_definition(
        db: AsyncSession,
        *,
        skill_definition_id: int,
    ) -> SkillVersion | None:
        result = await db.execute(select(SkillVersion).options(selectinload(SkillVersion.definition)).where(SkillVersion.skill_definition_id == skill_definition_id).order_by(SkillVersion.version_number.desc()).limit(1))
        return result.scalar_one_or_none()

    @staticmethod
    async def create_version(
        db: AsyncSession,
        *,
        definition: SkillDefinition,
        source_package_version: str | None,
        description: str | None,
        content_hash: str,
        file_manifest_hash: str,
        artifact_uri: str,
        created_by_user_id: int | None,
    ) -> SkillVersion:
        latest = await SkillVersionRepository.get_latest_for_definition(db, skill_definition_id=definition.id)
        next_number = 1 if latest is None else latest.version_number + 1
        version = SkillVersion(
            skill_definition_id=definition.id,
            version_number=next_number,
            source_package_version=source_package_version,
            description=description,
            content_hash=content_hash,
            file_manifest_hash=file_manifest_hash,
            artifact_uri=artifact_uri,
            created_by_user_id=created_by_user_id,
        )
        db.add(version)
        await db.flush()
        await db.refresh(version)
        return version


class SkillInstallRepository:
    """Persistence helpers for user skill install state."""

    @staticmethod
    async def get_by_user_and_definition(
        db: AsyncSession,
        *,
        user_id: int,
        skill_definition_id: int,
    ) -> SkillInstall | None:
        result = await db.execute(
            select(SkillInstall)
            .options(
                selectinload(SkillInstall.definition),
                selectinload(SkillInstall.installed_version),
                selectinload(SkillInstall.current_version).selectinload(SkillVersion.definition),
            )
            .where(
                SkillInstall.user_id == user_id,
                SkillInstall.skill_definition_id == skill_definition_id,
                SkillInstall.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_user_and_name(
        db: AsyncSession,
        *,
        user_id: int,
        name: str,
    ) -> SkillInstall | None:
        result = await db.execute(
            select(SkillInstall)
            .join(SkillDefinition, SkillDefinition.id == SkillInstall.skill_definition_id)
            .options(
                selectinload(SkillInstall.definition),
                selectinload(SkillInstall.installed_version),
                selectinload(SkillInstall.current_version).selectinload(SkillVersion.definition),
            )
            .where(
                SkillInstall.user_id == user_id,
                SkillDefinition.name == name,
                SkillDefinition.deleted_at.is_(None),
                SkillInstall.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def upsert_install(
        db: AsyncSession,
        *,
        user_id: int,
        definition: SkillDefinition,
        version: SkillVersion,
    ) -> SkillInstall:
        install = await SkillInstallRepository.get_by_user_and_definition(
            db,
            user_id=user_id,
            skill_definition_id=definition.id,
        )
        now = datetime.now(UTC)
        if install is None:
            install = SkillInstall(
                user_id=user_id,
                skill_definition_id=definition.id,
                installed_version_id=version.id,
                current_version_id=version.id,
            )
            db.add(install)
        else:
            install.current_version_id = version.id
            install.updated_at = now
        await db.flush()
        await db.refresh(install)
        return install

    @staticmethod
    async def update_current_version(
        db: AsyncSession,
        *,
        install: SkillInstall,
        version: SkillVersion,
    ) -> SkillInstall:
        """Update only the runtime-selected version for an existing install."""
        install.current_version_id = version.id
        install.updated_at = datetime.now(UTC)
        await db.flush()
        await db.refresh(install)
        return install


class SkillReleaseRepository:
    """Persistence helpers for immutable skill release records."""

    @staticmethod
    def generate_release_version() -> str:
        """Generate a system-owned immutable release identifier."""
        return f"rel_{uuid.uuid4().hex}"

    @staticmethod
    async def create_release(
        db: AsyncSession,
        *,
        skill_name: str,
        package_version: str | None,
        description: str | None,
        release_notes: str | None = None,
        artifact_path: str,
        publisher_user_id: int | None,
        source_skill_id: int | None,
        published_skill_id: int | None,
        skill_version_id: int | None = None,
        status: str = "published",
        release_version: str | None = None,
        commit: bool = True,
    ) -> SkillRelease:
        """Create an immutable skill release record."""
        release = SkillRelease(
            skill_name=skill_name,
            release_version=release_version or SkillReleaseRepository.generate_release_version(),
            package_version=package_version,
            description=description,
            release_notes=release_notes,
            status=status,
            artifact_path=artifact_path,
            publisher_user_id=publisher_user_id,
            source_skill_id=source_skill_id,
            published_skill_id=published_skill_id,
            skill_version_id=skill_version_id,
        )
        db.add(release)
        await db.flush()
        await db.refresh(release)
        if commit:
            await db.commit()
            await db.refresh(release)
        return release

    @staticmethod
    async def get_latest_published_version_by_name(
        db: AsyncSession,
        *,
        skill_name: str,
    ) -> SkillVersion | None:
        """Load the latest published platform version for a SkillHub skill name."""
        result = await db.execute(
            select(SkillVersion)
            .join(SkillRelease, SkillRelease.skill_version_id == SkillVersion.id)
            .options(selectinload(SkillVersion.definition))
            .where(
                SkillRelease.skill_name == skill_name,
                SkillRelease.status == "published",
                SkillRelease.skill_version_id.is_not(None),
            )
            .order_by(SkillVersion.version_number.desc(), SkillRelease.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_latest_published_release_by_name(
        db: AsyncSession,
        *,
        skill_name: str,
    ) -> SkillRelease | None:
        """Load the latest published release with version and publisher metadata."""
        result = await db.execute(
            select(SkillRelease)
            .join(SkillVersion, SkillVersion.id == SkillRelease.skill_version_id)
            .options(
                selectinload(SkillRelease.skill_version).selectinload(SkillVersion.definition),
                selectinload(SkillRelease.publisher_user),
            )
            .where(
                SkillRelease.skill_name == skill_name,
                SkillRelease.status == "published",
                SkillRelease.skill_version_id.is_not(None),
            )
            .order_by(SkillVersion.version_number.desc(), SkillRelease.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_latest_published_release_for_definition(
        db: AsyncSession,
        *,
        skill_definition_id: int,
    ) -> SkillRelease | None:
        """Load the latest published release for a concrete skill definition."""
        result = await db.execute(
            select(SkillRelease)
            .join(SkillVersion, SkillVersion.id == SkillRelease.skill_version_id)
            .options(
                selectinload(SkillRelease.skill_version).selectinload(SkillVersion.definition),
                selectinload(SkillRelease.publisher_user),
            )
            .where(
                SkillVersion.skill_definition_id == skill_definition_id,
                SkillRelease.status == "published",
                SkillRelease.skill_version_id.is_not(None),
            )
            .order_by(SkillVersion.version_number.desc(), SkillRelease.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_published_release_by_version_id(
        db: AsyncSession,
        *,
        skill_version_id: int,
    ) -> SkillRelease | None:
        """Load a published release for a selected immutable skill version."""
        result = await db.execute(
            select(SkillRelease)
            .options(
                selectinload(SkillRelease.skill_version).selectinload(SkillVersion.definition),
                selectinload(SkillRelease.publisher_user),
            )
            .where(
                SkillRelease.skill_version_id == skill_version_id,
                SkillRelease.status == "published",
            )
            .order_by(SkillRelease.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_latest_release_for_public_skill(
        db: AsyncSession,
        *,
        published_skill_id: int,
    ) -> SkillRelease | None:
        """Load the latest published release that produced a public skill row, if any."""
        result = await db.execute(
            select(SkillRelease)
            .options(selectinload(SkillRelease.skill_version).selectinload(SkillVersion.definition))
            .where(
                SkillRelease.published_skill_id == published_skill_id,
                SkillRelease.status == "published",
            )
            .order_by(SkillRelease.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()


class SkillRepository:
    """Persistence helpers for skill records."""

    @staticmethod
    def _active_skill_stmt():
        return select(Skill).where(Skill.deleted_at.is_(None))

    @staticmethod
    def _with_owner_user(stmt):
        return stmt.options(selectinload(Skill.owner_user))

    @staticmethod
    def _dedupe_public_skills(skills: list[Skill]) -> list[Skill]:
        """Collapse legacy duplicate public rows down to the preferred row per name."""
        deduped: list[Skill] = []
        seen_public_names: set[str] = set()
        for skill in skills:
            if skill.user_id is not None:
                deduped.append(skill)
                continue
            if skill.name in seen_public_names:
                continue
            seen_public_names.add(skill.name)
            deduped.append(skill)
        return deduped

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
        stmt = SkillRepository._with_owner_user(select(Skill).where(Skill.id == skill_id, Skill.deleted_at.is_(None)))
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
                Skill.updated_at.desc(),
                Skill.created_at.desc(),
            )
        )
        result = await db.execute(stmt)
        return SkillRepository._dedupe_public_skills(list(result.scalars().all()))

    @staticmethod
    async def list_public_skills(db: AsyncSession) -> list[Skill]:
        """List all active public skills, preferring the newest row per name."""
        stmt = SkillRepository._with_owner_user(SkillRepository._active_skill_stmt().where(Skill.user_id.is_(None)).order_by(Skill.name.asc(), Skill.updated_at.desc(), Skill.created_at.desc()))
        result = await db.execute(stmt)
        return SkillRepository._dedupe_public_skills(list(result.scalars().all()))

    @staticmethod
    async def list_custom_skills(db: AsyncSession, *, user_id: int) -> list[Skill]:
        """List all active custom skills owned by the current user."""
        stmt = SkillRepository._with_owner_user(SkillRepository._active_skill_stmt().where(Skill.user_id == user_id).order_by(Skill.name.asc(), Skill.created_at.desc()))
        result = await db.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def get_user_skill_by_name(db: AsyncSession, *, user_id: int, name: str) -> Skill | None:
        """Load the current user's active skill by name."""
        stmt = SkillRepository._with_owner_user(SkillRepository._active_skill_stmt().where(Skill.user_id == user_id, Skill.name == name))
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_public_skill_by_name_and_owner(
        db: AsyncSession,
        *,
        name: str,
        owner_user_id: int | None,
    ) -> Skill | None:
        """Load an active public skill by name.

        ``owner_user_id`` is ignored for business logic compatibility.
        """
        del owner_user_id
        return await SkillRepository.get_public_skill_by_name(db, name=name)

    @staticmethod
    async def get_system_public_skill_by_name(db: AsyncSession, *, name: str) -> Skill | None:
        """Load an active public skill by name."""
        return await SkillRepository.get_public_skill_by_name(db, name=name)

    @staticmethod
    async def get_public_skill_by_name(db: AsyncSession, *, name: str) -> Skill | None:
        """Load the active public skill for ``name``, preferring the newest row."""
        result = await db.execute(
            SkillRepository._with_owner_user(
                SkillRepository._active_skill_stmt()
                .where(
                    Skill.user_id.is_(None),
                    Skill.name == name,
                )
                .order_by(Skill.updated_at.desc(), Skill.created_at.desc())
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_public_skills_by_name(db: AsyncSession, *, name: str) -> list[Skill]:
        """List all active public rows for a given skill name."""
        result = await db.execute(
            SkillRepository._with_owner_user(
                SkillRepository._active_skill_stmt()
                .where(
                    Skill.user_id.is_(None),
                    Skill.name == name,
                )
                .order_by(Skill.updated_at.desc(), Skill.created_at.desc())
            )
        )
        return list(result.scalars().all())

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
    async def list_bound_agents_for_install(
        db: AsyncSession,
        *,
        user_id: int,
        skill_install_id: int,
    ) -> list[Agent]:
        """List active user-owned agents currently bound to an install."""
        result = await db.execute(
            select(Agent)
            .join(AgentSkill, AgentSkill.agent_id == Agent.id)
            .where(
                Agent.user_id == user_id,
                Agent.deleted_at.is_(None),
                AgentSkill.skill_install_id == skill_install_id,
                AgentSkill.deleted_at.is_(None),
                AgentSkill.enabled.is_(True),
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
