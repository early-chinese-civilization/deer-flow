"""Database access helpers for Gateway-owned auth and workspace tables."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.gateway.db.models import User, Workspace, WorkspaceFile


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


class WorkspaceRepository:
    """Persistence helpers for workspace records."""

    @staticmethod
    async def create_workspace(
        db: AsyncSession,
        owner_user_id: int,
        name: str | None = None,
        *,
        commit: bool = True,
    ) -> Workspace:
        """Create a workspace record."""
        workspace = Workspace(
            owner_user_id=owner_user_id,
            name=name,
        )
        db.add(workspace)
        await db.flush()
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
        """Sync workspace files (upsert files, delete missing).

        Args:
            db: Database session
            workspace_id: Workspace ID
            files: List of dicts with keys: file_path, content, file_size

        Returns:
            Number of files synced
        """
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
                "file_path": f["file_path"],
                "content": f["content"],
                "file_size": f["file_size"],
            }
            for f in files
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

        file_paths = [f["file_path"] for f in files]
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
