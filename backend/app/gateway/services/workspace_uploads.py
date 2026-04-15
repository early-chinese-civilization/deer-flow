"""Helpers for canonical workspace uploads backed by OSS."""

from __future__ import annotations

import asyncio
import logging
import os
import stat
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.gateway.db.models import Thread, Workspace
from app.gateway.db.repository import WorkspaceRepository
from deerflow.config import get_app_config
from deerflow.sandbox.sandbox_provider import get_sandbox_provider
from deerflow.uploads import (
    OSSObjectInfo,
    OSSStorageBackend,
    ensure_uploads_dir,
    oss_root_path,
    upload_artifact_url,
    upload_virtual_path,
    workspace_object_key,
    workspace_root_prefix,
)

logger = logging.getLogger(__name__)


def _make_file_sandbox_writable(file_path: os.PathLike[str] | str) -> None:
    """Ensure files written on the host remain writable inside sandboxes."""
    file_stat = os.lstat(file_path)
    if stat.S_ISLNK(file_stat.st_mode):
        logger.warning("Skipping sandbox chmod for symlinked upload path: %s", file_path)
        return

    writable_mode = stat.S_IMODE(file_stat.st_mode) | stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH
    chmod_kwargs = {"follow_symlinks": False} if os.chmod in os.supports_follow_symlinks else {}
    os.chmod(file_path, writable_mode, **chmod_kwargs)


def _uses_remote_sandbox_sync() -> bool:
    """Return whether uploads must also be copied into a remote sandbox."""
    provisioner_url = getattr(get_app_config().sandbox, "provisioner_url", None)
    return bool(provisioner_url)


def _resolve_thread_sandbox(thread_id: str, *, create_if_missing: bool) -> object | None:
    """Return the thread sandbox when remote sync is required."""
    if not _uses_remote_sandbox_sync():
        return None

    provider = get_sandbox_provider()

    try:
        sandbox_id: str | None
        if create_if_missing:
            sandbox_id = provider.acquire(thread_id)
        else:
            deterministic_id = getattr(provider, "_deterministic_sandbox_id", None)
            if not callable(deterministic_id):
                return None
            sandbox_id = deterministic_id(thread_id)
    except Exception:
        logger.warning("Failed to resolve sandbox for thread %s", thread_id, exc_info=True)
        return None

    if not sandbox_id:
        return None

    try:
        sandbox = provider.get(sandbox_id)
    except Exception:
        logger.warning("Failed to fetch sandbox %s for thread %s", sandbox_id, thread_id, exc_info=True)
        return None

    if sandbox is None and create_if_missing:
        logger.warning("Sandbox %s for thread %s was acquired but not available", sandbox_id, thread_id)
    return sandbox


def _sync_file_to_remote_sandbox(
    *,
    thread_id: str,
    filename: str,
    content: bytes,
    create_if_missing: bool,
) -> None:
    """Write a mirrored upload into the remote sandbox when needed."""
    sandbox = _resolve_thread_sandbox(thread_id, create_if_missing=create_if_missing)
    if sandbox is None:
        return

    sandbox.execute_command("mkdir -p /mnt/user-data/uploads")
    sandbox.update_file(upload_virtual_path(filename), content)


def _reset_remote_thread_uploads_dir(thread_id: str) -> None:
    """Clear the remote sandbox uploads dir before a full workspace sync."""
    sandbox = _resolve_thread_sandbox(thread_id, create_if_missing=True)
    if sandbox is None:
        return

    sandbox.execute_command(
        "mkdir -p /mnt/user-data/uploads && "
        "find /mnt/user-data/uploads -mindepth 1 -maxdepth 1 -type f -delete"
    )


async def ensure_workspace_prefix(
    db: AsyncSession,
    workspace: Workspace,
) -> str:
    """Ensure a workspace has a canonical OSS root prefix and return it."""
    if workspace.file_path:
        return workspace.file_path

    file_path = workspace_root_prefix(str(workspace.id))
    updated = await WorkspaceRepository.update_workspace_file_path(
        db,
        workspace_id=workspace.id,
        file_path=file_path,
        commit=True,
    )
    if updated is not None:
        workspace.file_path = updated.file_path
    return workspace.file_path or file_path


def build_workspace_root_path(storage: OSSStorageBackend, root_prefix: str) -> str:
    """Build a display root path for workspace files."""
    return oss_root_path(storage.bucket, root_prefix)


def build_workspace_object_key(root_prefix: str, filename: str) -> str:
    """Build the canonical object key for a workspace file."""
    return workspace_object_key(root_prefix, filename)


async def list_workspace_objects(root_prefix: str) -> tuple[OSSStorageBackend, list[OSSObjectInfo]]:
    """List all canonical objects under a workspace root prefix."""
    storage = OSSStorageBackend.from_app_config()
    objects = await asyncio.to_thread(storage.list_objects, prefix=root_prefix)
    return storage, objects


async def upload_workspace_object(
    *,
    root_prefix: str,
    filename: str,
    content: bytes,
    content_type: str | None = None,
) -> tuple[OSSStorageBackend, str, str, object | None]:
    """Upload a file to canonical OSS storage and return key plus signed URL."""
    storage = OSSStorageBackend.from_app_config()
    object_key = build_workspace_object_key(root_prefix, filename)
    await asyncio.to_thread(
        storage.put_object,
        key=object_key,
        content=content,
        content_type=content_type,
    )
    signed_url, expiration = await asyncio.to_thread(
        storage.presign_get_object,
        key=object_key,
    )
    return storage, object_key, signed_url, expiration


async def delete_workspace_object(
    *,
    object_key: str,
) -> None:
    """Delete a canonical OSS object."""
    storage = OSSStorageBackend.from_app_config()
    await asyncio.to_thread(storage.delete_object, key=object_key)


async def mirror_uploaded_file_to_thread(
    *,
    thread_id: str,
    filename: str,
    content: bytes,
) -> Path:
    """Mirror a file into the thread-local uploads directory."""
    uploads_dir = ensure_uploads_dir(thread_id)
    file_path = uploads_dir / filename
    file_path.write_bytes(content)

    try:
        _make_file_sandbox_writable(file_path)
    except OSError:
        logger.warning("Failed to adjust upload permissions for %s", file_path, exc_info=True)

    if _uses_remote_sandbox_sync():
        await asyncio.to_thread(
            _sync_file_to_remote_sandbox,
            thread_id=thread_id,
            filename=filename,
            content=content,
            create_if_missing=False,
        )

    return file_path


async def sync_workspace_uploads_to_thread(
    *,
    db: AsyncSession,
    thread: Thread,
) -> None:
    """Mirror the canonical workspace uploads into a thread-local uploads directory."""
    if thread.workspace_id is None:
        return

    workspace = await WorkspaceRepository.get_workspace_by_id(db, thread.workspace_id)
    if workspace is None:
        logger.warning("Skipping workspace uploads sync for missing workspace %s", thread.workspace_id)
        return

    root_prefix = await ensure_workspace_prefix(db, workspace)
    storage, objects = await list_workspace_objects(root_prefix)
    uploads_dir = ensure_uploads_dir(thread.thread_id)

    desired_filenames = {Path(item.key).name for item in objects if item.key}
    for local_file in uploads_dir.iterdir():
        if local_file.is_file() and local_file.name not in desired_filenames:
            local_file.unlink(missing_ok=True)

    if _uses_remote_sandbox_sync():
        await asyncio.to_thread(_reset_remote_thread_uploads_dir, thread.thread_id)

    for item in objects:
        filename = Path(item.key).name
        if not filename:
            continue
        content = await asyncio.to_thread(storage.get_object_bytes, key=item.key)
        await mirror_uploaded_file_to_thread(
            thread_id=thread.thread_id,
            filename=filename,
            content=content,
        )


def build_workspace_file_response(
    *,
    thread_id: str | None,
    filename: str,
    size: int,
    object_key: str,
    signed_url: str | None,
    modified: int | None = None,
    markdown_file: str | None = None,
    markdown_object_key: str | None = None,
    markdown_signed_url: str | None = None,
) -> dict[str, object]:
    """Build the frontend-facing response payload for a workspace file."""
    virtual_path = upload_virtual_path(filename)
    artifact_url = upload_artifact_url(thread_id, filename) if thread_id else None

    response: dict[str, object] = {
        "filename": filename,
        "size": size,
        "path": virtual_path,
        "virtual_path": virtual_path,
        "artifact_url": artifact_url,
        "object_key": object_key,
        "signed_url": signed_url,
        "modified": modified,
        "extension": Path(filename).suffix,
    }
    if markdown_file:
        markdown_virtual_path = upload_virtual_path(markdown_file)
        response["markdown_file"] = markdown_file
        response["markdown_path"] = markdown_virtual_path
        response["markdown_virtual_path"] = markdown_virtual_path
        response["markdown_artifact_url"] = (
            upload_artifact_url(thread_id, markdown_file) if thread_id else None
        )
        response["markdown_object_key"] = markdown_object_key
        response["markdown_signed_url"] = markdown_signed_url
    return response
