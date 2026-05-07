"""Gateway-owned database adapter for harness memory storage."""

from __future__ import annotations

from typing import Any

from app.gateway.db.engine import get_db_session
from app.gateway.db.repository import MemoryRepository
from deerflow.agents.memory.storage import create_empty_memory, register_database_memory_handlers


async def _load_memory_from_gateway_db(user_id: int) -> dict[str, Any]:
    async with get_db_session() as db:
        memory_row = await MemoryRepository.get_memory_by_user_id(db, user_id)
    return dict(memory_row.memory_json or {}) if memory_row is not None else create_empty_memory()


async def _save_memory_to_gateway_db(user_id: int, memory_data: dict[str, Any]) -> None:
    async with get_db_session() as db:
        await MemoryRepository.upsert_memory(db, user_id, memory_data, commit=True)


def register_gateway_memory_storage() -> None:
    """Register Gateway DB handlers with the harness memory storage provider."""
    register_database_memory_handlers(
        load_handler=_load_memory_from_gateway_db,
        save_handler=_save_memory_to_gateway_db,
    )
