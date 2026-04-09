"""Database access helpers for Gateway-owned auth, thread, and workspace tables."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.gateway.db.models import Thread, User, Workspace, WorkspaceFile


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
        return list(result.scalars().all())

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
    async def list_workspace_files(
        db: AsyncSession,
        workspace_id: str | uuid.UUID,
    ) -> list[WorkspaceFile]:
        """List all files in a workspace."""
        workspace_uuid = _as_optional_uuid(workspace_id)
        if workspace_uuid is None:
            return []
        result = await db.execute(
            select(WorkspaceFile)
            .where(WorkspaceFile.workspace_id == workspace_uuid)
            .order_by(WorkspaceFile.file_path)
        )
        return list(result.scalars().all())

    @staticmethod
    async def sync_workspace_files(
        db: AsyncSession,
        workspace_id: str | uuid.UUID,
        files: list[dict[str, Any]],
    ) -> int:
        """Sync workspace files (upsert files, delete missing)."""
        workspace_uuid = _as_optional_uuid(workspace_id)
        if workspace_uuid is None:
            return 0

        if not files:
            await db.execute(delete(WorkspaceFile).where(WorkspaceFile.workspace_id == workspace_uuid))
            await db.commit()
            return 0

        insert_values = [
            {
                "workspace_id": workspace_uuid,
                "file_path": file_info["file_path"],
                "content": file_info["content"],
                "file_size": file_info["file_size"],
            }
            for file_info in files
        ]
        stmt = insert(WorkspaceFile).values(insert_values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["workspace_id", "file_path"],
            set_={
                "content": stmt.excluded.content,
                "file_size": stmt.excluded.file_size,
            },
        )
        await db.execute(stmt)

        file_paths = [file_info["file_path"] for file_info in files]
        await db.execute(
            delete(WorkspaceFile).where(
                WorkspaceFile.workspace_id == workspace_uuid,
                WorkspaceFile.file_path.notin_(file_paths),
            )
        )
        await db.commit()
        return len(files)

    @staticmethod
    async def delete_workspace(
        db: AsyncSession,
        workspace_id: str | uuid.UUID,
        *,
        commit: bool = True,
    ) -> bool:
        """Delete a workspace and its cascaded files."""
        workspace_uuid = _as_optional_uuid(workspace_id)
        if workspace_uuid is None:
            return False
        result = await db.execute(delete(Workspace).where(Workspace.id == workspace_uuid))
        if commit:
            await db.commit()
        return result.rowcount > 0
