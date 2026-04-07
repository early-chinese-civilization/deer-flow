"""Database access helpers for Gateway-owned product tables."""

from __future__ import annotations

import uuid
from typing import Any, TypedDict

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.gateway.db.models import Chat, Message, User


class VisibleMessagePayload(TypedDict):
    """Normalized user-visible message payload used for idempotent sync."""

    source_message_id: str
    role: str
    content: str
    seq: int


def _as_thread_uuid(thread_id: str | uuid.UUID) -> uuid.UUID:
    """Normalize thread identifiers to UUID objects."""
    if isinstance(thread_id, uuid.UUID):
        return thread_id
    return uuid.UUID(thread_id)


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


class ChatRepository:
    """Persistence helpers for product chat records."""

    @staticmethod
    async def create_chat(
        db: AsyncSession,
        thread_id: str | uuid.UUID,
        owner_user_id: int,
        workspace_id: str | uuid.UUID | None = None,
        agent_id: str | None = None,
        title: str | None = None,
        status: str = "idle",
    ) -> Chat:
        """Create a chat row or return the existing one for the thread.

        The method is conflict-safe so duplicate ``history`` or ``state``
        requests can race without creating more than one ``chats`` row.
        """
        thread_uuid = _as_thread_uuid(thread_id)
        workspace_uuid = _as_optional_uuid(workspace_id)

        stmt = (
            insert(Chat)
            .values(
                thread_id=thread_uuid,
                owner_user_id=owner_user_id,
                workspace_id=workspace_uuid,
                agent_id=agent_id,
                title=title,
                status=status,
            )
            .on_conflict_do_nothing(index_elements=["thread_id"])
            .returning(Chat)
        )
        result = await db.execute(stmt)
        chat = result.scalar_one_or_none()
        await db.commit()
        if chat is not None:
            return chat

        existing_chat = await ChatRepository.get_chat_by_thread_id(db, thread_uuid)
        if existing_chat is None:
            raise RuntimeError(f"Failed to load chat after create conflict for {thread_uuid}")
        return existing_chat

    @staticmethod
    async def get_chat_by_thread_id(
        db: AsyncSession,
        thread_id: str | uuid.UUID,
    ) -> Chat | None:
        """Load a chat by thread identifier.

        Invalid UUID strings are treated as legacy thread ids and therefore
        return ``None`` instead of raising.
        """
        try:
            thread_uuid = _as_thread_uuid(thread_id)
        except ValueError:
            return None

        result = await db.execute(select(Chat).where(Chat.thread_id == thread_uuid))
        return result.scalar_one_or_none()

    @staticmethod
    async def update_chat(
        db: AsyncSession,
        thread_id: str | uuid.UUID,
        **updates: Any,
    ) -> Chat | None:
        """Update mutable chat fields."""
        thread_uuid = _as_thread_uuid(thread_id)
        result = await db.execute(select(Chat).where(Chat.thread_id == thread_uuid))
        chat = result.scalar_one_or_none()
        if chat is None:
            return None

        for key, value in updates.items():
            if hasattr(chat, key):
                setattr(chat, key, value)

        await db.commit()
        await db.refresh(chat)
        return chat

    @staticmethod
    async def list_chats_by_owner(
        db: AsyncSession,
        owner_user_id: int,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Chat]:
        """List chats owned by a user, newest first."""
        stmt = (
            select(Chat)
            .where(Chat.owner_user_id == owner_user_id)
            .order_by(Chat.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def delete_chat(
        db: AsyncSession,
        thread_id: str | uuid.UUID,
    ) -> bool:
        """Delete a chat and its cascaded message rows."""
        try:
            thread_uuid = _as_thread_uuid(thread_id)
        except ValueError:
            return False

        result = await db.execute(delete(Chat).where(Chat.thread_id == thread_uuid))
        await db.commit()
        return result.rowcount > 0


class MessageRepository:
    """Persistence helpers for the user-visible message truth table."""

    @staticmethod
    async def sync_visible_messages(
        db: AsyncSession,
        thread_id: str | uuid.UUID,
        messages: list[VisibleMessagePayload],
        *,
        commit: bool = True,
    ) -> int:
        """Idempotently align a thread's messages with the latest final state."""
        thread_uuid = _as_thread_uuid(thread_id)

        if not messages:
            await db.execute(delete(Message).where(Message.thread_id == thread_uuid))
            if commit:
                await db.commit()
            return 0

        insert_values = [
            {
                "thread_id": thread_uuid,
                "source_message_id": message["source_message_id"],
                "role": message["role"],
                "content": message["content"],
                "seq": message["seq"],
            }
            for message in messages
        ]
        stmt = insert(Message).values(insert_values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["thread_id", "source_message_id"],
            set_={
                "role": stmt.excluded.role,
                "content": stmt.excluded.content,
                "seq": stmt.excluded.seq,
            },
        )
        await db.execute(stmt)

        source_ids = [message["source_message_id"] for message in messages]
        await db.execute(
            delete(Message).where(
                Message.thread_id == thread_uuid,
                Message.source_message_id.notin_(source_ids),
            )
        )
        if commit:
            await db.commit()
        return len(messages)

    @staticmethod
    async def list_messages(
        db: AsyncSession,
        thread_id: str | uuid.UUID,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Message]:
        """List user-visible messages in final display order."""
        thread_uuid = _as_thread_uuid(thread_id)
        stmt = (
            select(Message)
            .where(Message.thread_id == thread_uuid)
            .order_by(Message.seq)
            .offset(offset)
        )
        if limit is not None:
            stmt = stmt.limit(limit)

        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def get_message_count(
        db: AsyncSession,
        thread_id: str | uuid.UUID,
    ) -> int:
        """Count user-visible messages for a thread."""
        thread_uuid = _as_thread_uuid(thread_id)
        result = await db.execute(
            select(func.count(Message.id)).where(Message.thread_id == thread_uuid)
        )
        return result.scalar() or 0
