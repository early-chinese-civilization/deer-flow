"""Unified projection service for syncing runtime state into product tables."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.gateway.db.models import Chat
from app.gateway.db.repository import ChatRepository, MessageRepository
from app.gateway.services.message_mirror import extract_user_visible_messages

logger = logging.getLogger(__name__)

_MISSING = object()


def _checkpoint_part(
    checkpoint_tuple: Any,
    attr: str,
    index: int,
    default: Any = None,
) -> Any:
    """Read checkpoint data from attr-style or tuple-style objects."""
    value = getattr(checkpoint_tuple, attr, _MISSING)
    if value is not _MISSING:
        return value
    if isinstance(checkpoint_tuple, tuple) and len(checkpoint_tuple) > index:
        return checkpoint_tuple[index]
    return default


def _coerce_checkpoint_timestamp(raw_value: Any) -> datetime | None:
    """Parse runtime checkpoint timestamps into aware datetimes."""
    if raw_value is None:
        return None
    if isinstance(raw_value, datetime):
        return raw_value.astimezone(UTC) if raw_value.tzinfo else raw_value.replace(tzinfo=UTC)
    if isinstance(raw_value, (int, float)):
        return datetime.fromtimestamp(raw_value, tz=UTC)
    if isinstance(raw_value, str):
        try:
            return datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


async def _lock_chat(db: AsyncSession, thread_id: UUID) -> Chat | None:
    """Lock and load the chat row that owns a thread projection."""
    await db.execute(
        select(Chat)
        .where(Chat.thread_id == thread_id)
        .with_for_update()
    )
    return await db.get(Chat, thread_id)


class ProjectionService:
    """Unified service for projecting runtime state into PG."""

    @staticmethod
    async def project_from_stream_event(
        db: AsyncSession,
        thread_id: UUID | str,
        event: str,
        data: Any,
        *,
        checkpoint_id: str | None = None,
    ) -> dict[str, Any]:
        """Project a final `values` stream event into product tables."""
        if isinstance(thread_id, str):
            thread_id = UUID(thread_id)
        if event != "values":
            return {"projected": False, "reason": "not_values_event"}
        if not isinstance(data, dict):
            return {"projected": False, "reason": "invalid_values_event"}

        try:
            chat = await _lock_chat(db, thread_id)
            if chat is None:
                return {"projected": False, "reason": "chat_not_found"}

            message_count = 0
            if isinstance(data.get("messages"), list):
                messages = extract_user_visible_messages(event, data)
                message_count = await MessageRepository.sync_visible_messages(
                    db=db,
                    thread_id=thread_id,
                    messages=messages,
                    commit=False,
                )

            now = datetime.now(UTC)
            title = data.get("title")
            if isinstance(title, str) and title.strip():
                chat.title = title
            if checkpoint_id:
                chat.latest_checkpoint_id = checkpoint_id
                chat.latest_checkpoint_at = now
            chat.projection_synced_at = now
            await db.commit()

            return {
                "projected": True,
                "message_count": message_count,
                "checkpoint_id": checkpoint_id,
                "synced_at": now.isoformat(),
            }
        except Exception as exc:
            logger.exception("Projection failed for thread %s: %s", thread_id, exc)
            await db.rollback()
            return {
                "projected": False,
                "reason": "projection_error",
                "error": str(exc),
            }

    @staticmethod
    async def project_from_checkpoint(
        db: AsyncSession,
        thread_id: UUID | str,
        checkpoint_tuple: Any,
    ) -> dict[str, Any]:
        """Project the latest root checkpoint into product tables."""
        if isinstance(thread_id, str):
            thread_id = UUID(thread_id)
        if not checkpoint_tuple:
            return {"projected": False, "reason": "no_checkpoint"}

        config = _checkpoint_part(checkpoint_tuple, "config", 0, {}) or {}
        checkpoint = _checkpoint_part(checkpoint_tuple, "checkpoint", 1, {}) or {}
        metadata = _checkpoint_part(checkpoint_tuple, "metadata", 2, {}) or {}
        checkpoint_id = config.get("configurable", {}).get("checkpoint_id")
        if not checkpoint_id:
            return {"projected": False, "reason": "no_checkpoint_id"}

        try:
            chat = await _lock_chat(db, thread_id)
            if chat is None:
                return {"projected": False, "reason": "chat_not_found"}

            channel_values = checkpoint.get("channel_values", {})
            message_count = 0
            if isinstance(channel_values.get("messages"), list):
                messages = extract_user_visible_messages(
                    "values",
                    {"messages": channel_values.get("messages", [])},
                )
                message_count = await MessageRepository.sync_visible_messages(
                    db=db,
                    thread_id=thread_id,
                    messages=messages,
                    commit=False,
                )

            now = datetime.now(UTC)
            title = channel_values.get("title")
            if isinstance(title, str) and title.strip():
                chat.title = title
            chat.latest_checkpoint_id = checkpoint_id
            chat.latest_checkpoint_at = (
                _coerce_checkpoint_timestamp(checkpoint.get("ts"))
                or _coerce_checkpoint_timestamp(metadata.get("created_at"))
                or now
            )
            chat.projection_synced_at = now
            await db.commit()

            return {
                "projected": True,
                "message_count": message_count,
                "checkpoint_id": checkpoint_id,
                "synced_at": now.isoformat(),
            }
        except Exception as exc:
            logger.exception("Checkpoint projection failed for thread %s: %s", thread_id, exc)
            await db.rollback()
            return {
                "projected": False,
                "reason": "projection_error",
                "error": str(exc),
            }

    @staticmethod
    async def get_projection_status(
        db: AsyncSession,
        thread_id: UUID | str,
    ) -> dict[str, Any]:
        """Get product-layer projection status for a thread."""
        if isinstance(thread_id, str):
            thread_id = UUID(thread_id)

        chat = await db.get(Chat, thread_id)
        if not chat:
            return {"exists": False}

        lag_seconds = None
        if chat.latest_checkpoint_at and chat.projection_synced_at:
            lag_seconds = (chat.projection_synced_at - chat.latest_checkpoint_at).total_seconds()

        return {
            "exists": True,
            "latest_checkpoint_id": chat.latest_checkpoint_id,
            "latest_checkpoint_at": chat.latest_checkpoint_at.isoformat() if chat.latest_checkpoint_at else None,
            "projection_synced_at": chat.projection_synced_at.isoformat() if chat.projection_synced_at else None,
            "lag_seconds": lag_seconds,
            "is_synced": chat.latest_checkpoint_id is not None and chat.projection_synced_at is not None,
        }

    @staticmethod
    async def rebuild_thread_projection(
        db: AsyncSession,
        thread_id: UUID | str,
        checkpoint_tuple: Any,
        *,
        owner_user_id: int | None = None,
        workspace_id: UUID | str | None = None,
        agent_id: str | None = None,
    ) -> dict[str, Any]:
        """Explicitly rebuild a single thread projection from runtime state."""
        if isinstance(thread_id, str):
            thread_id = UUID(thread_id)

        chat = await db.get(Chat, thread_id)
        if chat is None:
            if owner_user_id is None:
                return {"projected": False, "reason": "chat_not_found"}
            await ChatRepository.create_chat(
                db=db,
                thread_id=thread_id,
                owner_user_id=owner_user_id,
                workspace_id=workspace_id,
                agent_id=agent_id,
                status="idle",
            )

        return await ProjectionService.project_from_checkpoint(
            db=db,
            thread_id=thread_id,
            checkpoint_tuple=checkpoint_tuple,
        )

    @staticmethod
    async def reindex_runtime_threads(
        db: AsyncSession,
        checkpointer: Any,
        *,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """Batch-project root checkpoints into product tables."""
        seen_thread_ids: set[str] = set()
        projected = 0
        skipped = 0

        async for checkpoint_tuple in checkpointer.alist(None, limit=limit):
            config = _checkpoint_part(checkpoint_tuple, "config", 0, {}) or {}
            configurable = config.get("configurable", {})
            thread_id = configurable.get("thread_id")
            if not thread_id or thread_id in seen_thread_ids:
                continue
            seen_thread_ids.add(thread_id)
            if configurable.get("checkpoint_ns", ""):
                continue

            try:
                result = await ProjectionService.project_from_checkpoint(
                    db=db,
                    thread_id=thread_id,
                    checkpoint_tuple=checkpoint_tuple,
                )
            except Exception:
                logger.exception("Runtime reindex failed for thread %s", thread_id)
                skipped += 1
                continue

            if result.get("projected"):
                projected += 1
            else:
                skipped += 1

        return {
            "projected": projected,
            "skipped": skipped,
            "seen_threads": len(seen_thread_ids),
        }
