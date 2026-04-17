"""Helpers for canonical workspace uploads backed by OSS."""

from __future__ import annotations

import asyncio
from pathlib import Path, PurePosixPath
from urllib.parse import quote

from sqlalchemy.ext.asyncio import AsyncSession

from app.gateway.db.models import Workspace
from app.gateway.db.repository import WorkspaceRepository
from deerflow.uploads import (
    OSSObjectInfo,
    OSSStorageBackend,
    oss_root_path,
    workspace_object_key,
    workspace_root_prefix,
)


def _build_workspace_content_url(*, workspace_id: str, object_key: str) -> str:
    """Build a stable proxy URL for a workspace-backed object."""
    encoded_workspace_id = quote(workspace_id, safe="")
    encoded_object_key = quote(object_key, safe="")
    return f"/api/workspaces/{encoded_workspace_id}/uploads/content?object_key={encoded_object_key}"


def _relative_path_to_virtual_path(relative_path: str) -> str:
    """Translate a workspace-relative path into its sandbox virtual path."""
    normalized_path = PurePosixPath(relative_path.strip("/"))
    if normalized_path.is_absolute() or any(part in {"", ".", ".."} for part in normalized_path.parts):
        raise ValueError(f"Invalid workspace relative path: {relative_path!r}")

    parts = normalized_path.parts
    if not parts:
        raise ValueError("Workspace relative path cannot be empty")

    if parts[0] == "uploads":
        return str(PurePosixPath("/mnt/user-data/uploads", *parts[1:]))
    if parts[0] == "outputs":
        return str(PurePosixPath("/mnt/user-data/outputs", *parts[1:]))
    return str(PurePosixPath("/mnt/user-data/workspace", *parts))


def _build_markdown_relative_path(*, relative_path: str, markdown_file: str) -> str:
    """Place markdown companions next to their source file in the virtual tree."""
    return PurePosixPath(relative_path).with_name(markdown_file).as_posix()


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


def build_workspace_object_key(root_prefix: str, filename: str, subdir: str | None = None) -> str:
    """Build the canonical object key for a workspace file.

    Args:
        root_prefix: Workspace root prefix
        filename: File name
        subdir: Optional subdirectory (e.g., "uploads" or "outputs")
    """
    return workspace_object_key(root_prefix, filename, subdir=subdir)


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
    subdir: str | None = None,
) -> tuple[OSSStorageBackend, str, str, object | None]:
    """Upload a file to canonical OSS storage and return key plus signed URL.

    Args:
        root_prefix: Workspace root prefix
        filename: File name
        content: File content
        content_type: MIME type
        subdir: Optional subdirectory (e.g., "uploads" or "outputs")
    """
    storage = OSSStorageBackend.from_app_config()
    object_key = build_workspace_object_key(root_prefix, filename, subdir=subdir)
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


async def upload_workspace_object_stream(
    *,
    root_prefix: str,
    filename: str,
    stream,
    content_length: int | None = None,
    content_type: str | None = None,
    subdir: str | None = None,
) -> tuple[OSSStorageBackend, str, str, object | None]:
    """Upload a file stream to canonical OSS storage and return key plus signed URL.

    Args:
        root_prefix: Workspace root prefix
        filename: File name
        stream: File stream
        content_length: Content length
        content_type: MIME type
        subdir: Optional subdirectory (e.g., "uploads" or "outputs")
    """
    storage = OSSStorageBackend.from_app_config()
    object_key = build_workspace_object_key(root_prefix, filename, subdir=subdir)
    await asyncio.to_thread(
        storage.put_object_stream,
        key=object_key,
        stream=stream,
        content_length=content_length,
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


def build_workspace_file_response(
    *,
    workspace_id: str,
    filename: str,
    relative_path: str,
    size: int,
    object_key: str,
    signed_url: str | None,
    modified: int | None = None,
    markdown_file: str | None = None,
    markdown_object_key: str | None = None,
    markdown_signed_url: str | None = None,
) -> dict[str, object]:
    """Build the frontend-facing response payload for a workspace file.

    Note: artifact_url fields are now workspace-scoped stable proxy URLs,
    not thread-scoped artifact URLs. This ensures files remain accessible
    even after signed URLs expire.
    """
    artifact_url = _build_workspace_content_url(
        workspace_id=workspace_id,
        object_key=object_key,
    )
    virtual_path = _relative_path_to_virtual_path(relative_path)

    response: dict[str, object] = {
        "filename": filename,
        "size": size,
        "path": virtual_path,
        "virtual_path": virtual_path,
        "relative_path": relative_path,
        "artifact_url": artifact_url,
        "object_key": object_key,
        "signed_url": signed_url,
        "modified": modified,
        "extension": Path(filename).suffix,
    }
    if markdown_file:
        markdown_relative_path = _build_markdown_relative_path(
            relative_path=relative_path,
            markdown_file=markdown_file,
        )
        markdown_virtual_path = _relative_path_to_virtual_path(markdown_relative_path)
        response["markdown_file"] = markdown_file
        response["markdown_path"] = markdown_virtual_path
        response["markdown_virtual_path"] = markdown_virtual_path
        response["markdown_artifact_url"] = (
            _build_workspace_content_url(
                workspace_id=workspace_id,
                object_key=markdown_object_key,
            )
            if markdown_object_key
            else None
        )
        response["markdown_object_key"] = markdown_object_key
        response["markdown_signed_url"] = markdown_signed_url
    return response
