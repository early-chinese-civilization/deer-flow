"""Workspace synchronization service for Phase 3.

Syncs between canonical workspace (PostgreSQL) and thread workspace (filesystem).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from pathlib import Path
from typing import TypedDict

from sqlalchemy.ext.asyncio import AsyncSession

from app.gateway.db.repository import WorkspaceRepository

logger = logging.getLogger(__name__)

# File size limit: 10MB per file
MAX_FILE_SIZE = 10 * 1024 * 1024

# Maximum number of files to sync
MAX_FILE_COUNT = 1000


class WorkspaceFilePayload(TypedDict):
    """Serialized workspace file payload used for PG sync."""

    file_path: str
    content: bytes
    file_size: int


def _resolve_thread_workspace_path(
    *,
    thread_workspace_path: Path,
    relative_path: str,
) -> Path | None:
    """Resolve a canonical workspace file path inside the thread workspace root."""
    if not relative_path:
        logger.warning("Skipping workspace file with empty path")
        return None

    candidate = (thread_workspace_path / relative_path).resolve()
    workspace_root = thread_workspace_path.resolve()

    try:
        candidate.relative_to(workspace_root)
    except ValueError:
        logger.warning("Skipping unsafe workspace file path outside thread workspace: %s", relative_path)
        return None

    return candidate


def _sync_canonical_to_thread_sync(
    *,
    files: list,
    thread_workspace_path: Path,
) -> int:
    """Mirror canonical workspace files into the thread workspace on disk."""
    thread_workspace_path.mkdir(parents=True, exist_ok=True)
    canonical_paths: set[str] = set()
    synced_count = 0

    for file in files:
        file_path = _resolve_thread_workspace_path(
            thread_workspace_path=thread_workspace_path,
            relative_path=file.file_path,
        )
        if file_path is None:
            continue

        canonical_paths.add(str(file_path.relative_to(thread_workspace_path)).replace("\\", "/"))
        file_path.parent.mkdir(parents=True, exist_ok=True)
        if file_path.is_symlink():
            logger.warning("Replacing symlinked workspace file during sync: %s", file_path)
            file_path.unlink()
        file_path.write_bytes(file.content)
        synced_count += 1

    for file_path in thread_workspace_path.rglob("*"):
        if not file_path.is_file():
            continue

        relative_path = file_path.relative_to(thread_workspace_path)
        relative_str = str(relative_path).replace("\\", "/")
        if relative_str in canonical_paths:
            continue

        file_path.unlink()

    return synced_count


def _collect_thread_workspace_files_sync(thread_workspace_path: Path) -> list[WorkspaceFilePayload]:
    """Collect serializable file payloads from the thread workspace on disk."""
    files: list[WorkspaceFilePayload] = []
    file_count = 0

    for file_path in thread_workspace_path.rglob("*"):
        if not file_path.is_file():
            continue
        if file_path.is_symlink():
            logger.warning("Skipping symlinked workspace file during canonical sync: %s", file_path)
            continue

        file_count += 1
        if file_count > MAX_FILE_COUNT:
            logger.warning("Exceeded max file count (%d), stopping sync", MAX_FILE_COUNT)
            break

        file_size = file_path.stat().st_size
        if file_size > MAX_FILE_SIZE:
            logger.warning("Skipping file %s (size %d exceeds limit %d)", file_path, file_size, MAX_FILE_SIZE)
            continue

        relative_path = file_path.relative_to(thread_workspace_path)
        relative_str = str(relative_path).replace("\\", "/")
        files.append(
            {
                "file_path": relative_str,
                "content": file_path.read_bytes(),
                "file_size": file_size,
            }
        )

    return files


async def sync_canonical_to_thread(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    thread_workspace_path: Path,
) -> None:
    """Sync canonical workspace (PG) to thread workspace (filesystem).

    - Read all files from workspace_files table
    - Write to thread workspace directory
    - Delete files in thread workspace not in canonical

    Args:
        db: Database session
        workspace_id: Workspace ID
        thread_workspace_path: Path to thread workspace directory
    """
    logger.debug("Syncing canonical workspace %s to thread workspace %s", workspace_id, thread_workspace_path)
    files = await WorkspaceRepository.list_workspace_files(db, workspace_id)
    synced_count = await asyncio.to_thread(
        _sync_canonical_to_thread_sync,
        files=files,
        thread_workspace_path=thread_workspace_path,
    )
    logger.info("Synced %d files from canonical to thread workspace", synced_count)


async def sync_thread_to_canonical(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    thread_workspace_path: Path,
) -> None:
    """Sync thread workspace (filesystem) back to canonical (PG).

    - Scan thread workspace directory
    - Upsert files to workspace_files table
    - Delete DB records for files not in filesystem
    - Conflict strategy: last write wins

    Args:
        db: Database session
        workspace_id: Workspace ID
        thread_workspace_path: Path to thread workspace directory
    """
    logger.debug("Syncing thread workspace %s to canonical workspace %s", thread_workspace_path, workspace_id)

    if not thread_workspace_path.exists():
        logger.debug("Thread workspace does not exist, clearing canonical workspace")
        await WorkspaceRepository.sync_workspace_files(db, workspace_id, [])
        return

    files = await asyncio.to_thread(_collect_thread_workspace_files_sync, thread_workspace_path)
    synced_count = await WorkspaceRepository.sync_workspace_files(db, workspace_id, files)
    logger.info("Synced %d files from thread to canonical workspace", synced_count)
