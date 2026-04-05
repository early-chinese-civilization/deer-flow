"""Helpers for synchronizing final user-visible messages into PostgreSQL."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.gateway.db.repository import MessageRepository, VisibleMessagePayload

logger = logging.getLogger(__name__)

_VISIBLE_ROLES = {"user", "assistant", "system"}


def _normalize_role(raw_role: str | None) -> str | None:
    """Map LangChain/LangGraph message types onto product-facing roles."""
    if not raw_role:
        return None

    role = raw_role.replace("Message", "").lower()
    if role in {"human", "user"}:
        return "user"
    if role in {"ai", "assistant"}:
        return "assistant"
    if role == "system":
        return "system"
    return None


def _normalize_content(raw_content: Any) -> str:
    """Flatten LangChain message content into a stable text representation."""
    if isinstance(raw_content, str):
        return raw_content
    if isinstance(raw_content, list):
        text_parts = [
            block.get("text", "")
            for block in raw_content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        if text_parts:
            return "".join(text_parts)
    if raw_content is None:
        return ""
    return json.dumps(raw_content, ensure_ascii=False, sort_keys=True)


def _build_fallback_source_message_id(*, seq: int, role: str, content: str) -> str:
    """Build a stable fallback identifier when LangGraph omits ``message.id``."""
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
    return f"fallback:{seq}:{role}:{content_hash}"


def extract_user_visible_messages(event: str, data: Any) -> list[VisibleMessagePayload]:
    """Extract final user-visible messages from a stream event.

    Phase 2 now treats ``values.messages`` as the only source of truth. Partial
    ``messages-tuple`` chunks are intentionally ignored for database writes.
    """
    if event != "values" or not isinstance(data, dict):
        return []

    raw_messages = data.get("messages")
    if not isinstance(raw_messages, list):
        return []

    visible_messages: list[VisibleMessagePayload] = []
    for raw_message in raw_messages:
        if not isinstance(raw_message, dict):
            continue

        role = _normalize_role(raw_message.get("type") or raw_message.get("role"))
        if role not in _VISIBLE_ROLES:
            continue

        content = _normalize_content(raw_message.get("content"))
        if not content:
            continue

        seq = len(visible_messages) + 1
        source_message_id = raw_message.get("id")
        if not source_message_id:
            source_message_id = _build_fallback_source_message_id(
                seq=seq,
                role=role,
                content=content,
            )

        visible_messages.append(
            {
                "source_message_id": str(source_message_id),
                "role": role,
                "content": content,
                "seq": seq,
            }
        )

    return visible_messages


async def mirror_messages_from_stream(
    db: AsyncSession,
    thread_id: str,
    event: str,
    data: Any,
) -> int:
    """Synchronize final user-visible messages for a stream event."""
    messages = extract_user_visible_messages(event, data)
    if not messages:
        return 0

    try:
        return await MessageRepository.sync_visible_messages(
            db=db,
            thread_id=thread_id,
            messages=messages,
        )
    except Exception:
        logger.debug("Failed to sync visible messages for thread %s", thread_id, exc_info=True)
        raise
