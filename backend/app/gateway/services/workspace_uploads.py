"""Helpers for canonical workspace files backed by the configured uploads backend."""

from __future__ import annotations

import asyncio
import datetime as dt
import mimetypes
import shutil
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import quote

from sqlalchemy.ext.asyncio import AsyncSession

from app.gateway.db.models import Workspace
from app.gateway.db.repository import WorkspaceRepository
from deerflow.config import get_app_config
from deerflow.config.paths import get_paths
from deerflow.uploads import OSSStorageBackend, oss_root_path, workspace_object_key, workspace_root_prefix


@dataclass(frozen=True)
class WorkspaceObjectInfo:
    """Normalized metadata returned from the configured workspace uploads backend."""

    key: str
    size: int
    last_modified: dt.datetime | None
    content_type: str | None = None


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

    if parts[0] == "workspace":
        return str(PurePosixPath("/mnt/user-data/workspace", *parts[1:]))
    if parts[0] == "uploads":
        return str(PurePosixPath("/mnt/user-data/uploads", *parts[1:]))
    if parts[0] == "outputs":
        return str(PurePosixPath("/mnt/user-data/outputs", *parts[1:]))
    return str(PurePosixPath("/mnt/user-data/workspace", *parts))


def _build_markdown_relative_path(*, relative_path: str, markdown_file: str) -> str:
    """Place markdown companions next to their source file in the virtual tree."""
    return PurePosixPath(relative_path).with_name(markdown_file).as_posix()


def _workspace_root_dir(workspace_id: str) -> Path:
    """Return the shared `user-data` root directory for a workspace."""
    return get_paths().workspace_user_data_dir(workspace_id)


def uses_oss_workspace_uploads() -> bool:
    """Return whether canonical workspace uploads are stored in OSS."""
    try:
        return get_app_config().uploads.backend == "oss"
    except Exception:
        return False


def _get_oss_storage_backend() -> OSSStorageBackend:
    """Build the configured OSS storage backend."""
    return OSSStorageBackend.from_app_config()


def _workspace_path_from_relative(*, workspace_id: str, relative_path: str) -> Path:
    """Resolve a workspace-relative path inside the shared filesystem."""
    relative = PurePosixPath(relative_path.strip("/"))
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise ValueError(f"Invalid workspace relative path: {relative_path!r}")

    root_dir = _workspace_root_dir(workspace_id).resolve()
    actual = (root_dir / relative.as_posix()).resolve()
    try:
        actual.relative_to(root_dir)
    except ValueError:
        raise ValueError("Invalid workspace relative path") from None
    return actual


def _relative_path_from_object_key(*, root_prefix: str, object_key: str) -> str:
    """Translate a workspace object key into a relative path below the workspace root."""
    normalized_root = PurePosixPath(root_prefix.strip("/"))
    normalized_key = PurePosixPath(object_key.strip("/"))
    try:
        relative = normalized_key.relative_to(normalized_root)
    except ValueError:
        raise ValueError("Object key does not belong to this workspace") from None
    return relative.as_posix()


def workspace_object_path(*, root_prefix: str, workspace_id: str, object_key: str) -> Path:
    """Resolve a workspace object key to the backing shared-filesystem path."""
    relative_path = _relative_path_from_object_key(root_prefix=root_prefix, object_key=object_key)
    return _workspace_path_from_relative(workspace_id=workspace_id, relative_path=relative_path)


async def ensure_workspace_prefix(
    db: AsyncSession,
    workspace: Workspace,
) -> str:
    """Ensure a workspace has a canonical root prefix and return it."""
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


def build_workspace_root_path(root_prefix: str) -> str:
    """Build a display root path for workspace files."""
    uploads_config = get_app_config().uploads
    if uploads_config.backend == "oss" and uploads_config.oss.bucket:
        return oss_root_path(uploads_config.oss.bucket, root_prefix)
    return str((get_paths().shared_fs_root / root_prefix / "user-data").resolve())


def build_workspace_object_key(root_prefix: str, filename: str, subdir: str | None = None) -> str:
    """Build the canonical object key for a workspace file."""
    return workspace_object_key(root_prefix, filename, subdir=subdir)


async def list_workspace_objects(*, root_prefix: str, workspace_id: str) -> list[WorkspaceObjectInfo]:
    """List all canonical files under a workspace root."""

    if uses_oss_workspace_uploads():
        storage = _get_oss_storage_backend()

        def _list_oss() -> list[WorkspaceObjectInfo]:
            objects = storage.list_objects(prefix=root_prefix)
            return [
                WorkspaceObjectInfo(
                    key=item.key,
                    size=item.size,
                    last_modified=item.last_modified,
                    content_type=item.content_type or mimetypes.guess_type(item.key)[0],
                )
                for item in sorted(objects, key=lambda value: value.key.lower())
            ]

        return await asyncio.to_thread(_list_oss)

    def _list() -> list[WorkspaceObjectInfo]:
        root_dir = _workspace_root_dir(workspace_id)
        if not root_dir.exists():
            return []

        objects: list[WorkspaceObjectInfo] = []
        for file_path in sorted(root_dir.rglob("*"), key=lambda item: item.as_posix().lower()):
            if not file_path.is_file():
                continue
            relative_path = file_path.relative_to(root_dir).as_posix()
            stat = file_path.stat()
            last_modified = dt.datetime.fromtimestamp(stat.st_mtime, tz=dt.UTC)
            objects.append(
                WorkspaceObjectInfo(
                    key=build_workspace_object_key(root_prefix, relative_path),
                    size=stat.st_size,
                    last_modified=last_modified,
                    content_type=mimetypes.guess_type(file_path.name)[0],
                )
            )
        return objects

    return await asyncio.to_thread(_list)


async def upload_workspace_object(
    *,
    root_prefix: str,
    workspace_id: str,
    filename: str,
    content: bytes,
    content_type: str | None = None,
    subdir: str | None = None,
) -> tuple[None, str, None, None]:
    """Write a file into canonical workspace storage."""
    object_key = build_workspace_object_key(root_prefix, filename, subdir=subdir)

    if uses_oss_workspace_uploads():
        storage = _get_oss_storage_backend()

        def _write_oss() -> None:
            storage.put_object(
                key=object_key,
                content=content,
                content_type=content_type,
            )

        await asyncio.to_thread(_write_oss)
        return None, object_key, None, None

    relative_path = filename if subdir is None else f"{subdir.strip('/')}/{filename}"
    target_path = _workspace_path_from_relative(workspace_id=workspace_id, relative_path=relative_path)

    def _write() -> None:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(content)

    await asyncio.to_thread(_write)
    return None, object_key, None, None


async def upload_workspace_object_stream(
    *,
    root_prefix: str,
    workspace_id: str,
    filename: str,
    stream,
    content_length: int | None = None,
    content_type: str | None = None,
    subdir: str | None = None,
) -> tuple[None, str, None, None]:
    """Write a streamed upload into canonical workspace storage."""
    object_key = build_workspace_object_key(root_prefix, filename, subdir=subdir)

    if uses_oss_workspace_uploads():
        storage = _get_oss_storage_backend()

        def _write_stream_to_oss() -> None:
            if hasattr(stream, "seek"):
                stream.seek(0)
            storage.put_object_stream(
                key=object_key,
                stream=stream,
                content_length=content_length,
                content_type=content_type,
            )

        await asyncio.to_thread(_write_stream_to_oss)
        return None, object_key, None, None

    relative_path = filename if subdir is None else f"{subdir.strip('/')}/{filename}"
    target_path = _workspace_path_from_relative(workspace_id=workspace_id, relative_path=relative_path)

    def _write_stream() -> None:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        if hasattr(stream, "seek"):
            stream.seek(0)
        with target_path.open("wb") as handle:
            shutil.copyfileobj(stream, handle)

    await asyncio.to_thread(_write_stream)
    return None, object_key, None, None


async def delete_workspace_object(
    *,
    root_prefix: str,
    workspace_id: str,
    object_key: str,
) -> None:
    """Delete a canonical workspace file from the configured uploads backend."""
    if uses_oss_workspace_uploads():
        storage = _get_oss_storage_backend()
        await asyncio.to_thread(storage.delete_object, key=object_key)
        return

    target_path = workspace_object_path(root_prefix=root_prefix, workspace_id=workspace_id, object_key=object_key)
    await asyncio.to_thread(target_path.unlink)


async def get_workspace_object_bytes(
    *,
    root_prefix: str,
    workspace_id: str,
    object_key: str,
) -> bytes:
    """Read a canonical workspace file from the configured uploads backend."""
    if uses_oss_workspace_uploads():
        storage = _get_oss_storage_backend()
        return await asyncio.to_thread(storage.get_object_bytes, key=object_key)

    file_path = workspace_object_path(root_prefix=root_prefix, workspace_id=workspace_id, object_key=object_key)
    return await asyncio.to_thread(file_path.read_bytes)


def build_workspace_file_response(
    *,
    workspace_id: str,
    filename: str,
    relative_path: str,
    size: int,
    object_key: str,
    signed_url: str | None = None,
    modified: int | None = None,
    markdown_file: str | None = None,
    markdown_object_key: str | None = None,
    markdown_signed_url: str | None = None,
) -> dict[str, object]:
    """Build the frontend-facing response payload for a workspace file."""
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
