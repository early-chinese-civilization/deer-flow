"""Workspace uploads router backed by canonical OSS storage."""

from __future__ import annotations

import asyncio
import logging
import mimetypes
import tempfile
from pathlib import Path, PurePosixPath
from urllib.parse import quote

from alibabacloud_oss_v2.exceptions import ServiceError
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.gateway.db.models import User, Workspace
from app.gateway.db.repository import WorkspaceRepository
from app.gateway.deps import get_current_user, get_db
from app.gateway.services.workspace_uploads import (
    build_workspace_file_response,
    build_workspace_root_path,
    delete_workspace_object,
    ensure_workspace_prefix,
    list_workspace_objects,
    upload_workspace_object,
    upload_workspace_object_stream,
)
from deerflow.uploads import OSSStorageBackend, normalize_filename
from deerflow.utils.file_conversion import CONVERTIBLE_EXTENSIONS, convert_file_to_markdown

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/workspaces/{workspace_id}/uploads", tags=["uploads"])
_WORKSPACE_PROXY_CHUNK_SIZE = 1024 * 1024


class WorkspaceFileResponse(BaseModel):
    """Serialized metadata for a canonical workspace file."""

    filename: str
    size: int
    path: str
    virtual_path: str
    relative_path: str
    artifact_url: str | None = None
    object_key: str
    signed_url: str | None = None
    modified: int | None = None
    extension: str | None = None
    markdown_file: str | None = None
    markdown_path: str | None = None
    markdown_virtual_path: str | None = None
    markdown_artifact_url: str | None = None
    markdown_object_key: str | None = None
    markdown_signed_url: str | None = None


class FileTreeNode(BaseModel):
    """Tree node representing a file or directory."""

    type: str  # "file" or "directory"
    name: str
    path: str  # relative path from workspace root
    size: int | None = None  # only for files
    modified: int | None = None  # only for files
    children: list[FileTreeNode] | None = None  # only for directories
    # File-specific fields
    filename: str | None = None
    virtual_path: str | None = None
    artifact_url: str | None = None
    object_key: str | None = None
    signed_url: str | None = None
    extension: str | None = None
    markdown_file: str | None = None
    markdown_path: str | None = None
    markdown_virtual_path: str | None = None
    markdown_artifact_url: str | None = None
    markdown_object_key: str | None = None
    markdown_signed_url: str | None = None


class UploadResponse(BaseModel):
    """Response model for workspace file upload."""

    success: bool
    files: list[WorkspaceFileResponse]
    message: str


class ListFilesResponse(BaseModel):
    """Response model for listing workspace files."""

    root_label: str = Field(default="workspace")
    root_path: str
    files: list[WorkspaceFileResponse]
    tree: list[FileTreeNode]  # directory tree structure
    count: int


class DeleteUploadedFileRequest(BaseModel):
    """Request body for deleting a workspace file."""

    filename: str = Field(min_length=1)
    object_key: str | None = None


def _require_authenticated_user(current_user: User | None) -> User:
    """Return the current user or raise a 401."""
    if current_user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return current_user


async def _require_workspace_access(
    *,
    db: AsyncSession,
    workspace_id: str,
    current_user: User | None,
) -> Workspace:
    """Validate that the current user owns the workspace."""
    user = _require_authenticated_user(current_user)
    workspace = await WorkspaceRepository.get_workspace_by_id(db, workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail=f"Workspace {workspace_id} not found")
    if workspace.user_id != user.id:
        raise HTTPException(status_code=403, detail=f"Workspace belongs to user {workspace.user_id}")
    return workspace




def _build_workspace_root_label(workspace: Workspace) -> str:
    """Build a friendly root label for the workspace panel."""
    if workspace.name and workspace.name.strip():
        return workspace.name.strip()
    return "workspace"


def _object_key_belongs_to_workspace(*, object_key: str, root_prefix: str) -> bool:
    """Check that an object key stays within the current workspace prefix."""
    normalized_object_key = object_key.strip("/")
    normalized_root_prefix = root_prefix.strip("/")
    if normalized_object_key == normalized_root_prefix:
        return True
    return normalized_object_key.startswith(f"{normalized_root_prefix}/")


def _build_content_disposition(disposition_type: str, filename: str) -> str:
    """Build an RFC 5987 encoded Content-Disposition header value."""
    return f"{disposition_type}; filename*=UTF-8''{quote(filename)}"


def _is_missing_workspace_object_error(exc: ServiceError) -> bool:
    """Check whether an OSS error maps to a missing workspace object."""
    return exc.status_code == 404 or exc.code == "NoSuchKey"


def _iter_oss_stream_chunks(stream, *, chunk_size: int = _WORKSPACE_PROXY_CHUNK_SIZE):
    """Yield OSS object data in bounded chunks and close the stream when done."""
    try:
        iter_bytes = getattr(stream, "iter_bytes", None)
        if callable(iter_bytes):
            try:
                yield from iter_bytes(block_size=chunk_size)
            except TypeError:
                yield from iter_bytes()
            return

        read = getattr(stream, "read", None)
        if not callable(read):
            raise TypeError("OSS object stream is not readable")

        try:
            while chunk := read(chunk_size):
                yield chunk
        except TypeError:
            while chunk := read():
                yield chunk
    finally:
        close = getattr(stream, "close", None)
        if callable(close):
            close()


def _relative_object_path(root_prefix: str, object_key: str) -> PurePosixPath:
    """Return the object path relative to the workspace root."""
    workspace_root = PurePosixPath(root_prefix.strip("/"))
    normalized_object_key = PurePosixPath(object_key.strip("/"))

    try:
        return normalized_object_key.relative_to(workspace_root)
    except ValueError:
        return normalized_object_key


def _build_file_tree(*, root_prefix: str, files: list[WorkspaceFileResponse]) -> list[FileTreeNode]:
    """Build a nested directory tree structure from a flat list of files.

    Args:
        root_prefix: Workspace root prefix
        files: Flat list of workspace files

    Returns:
        List of root-level tree nodes (directories and files)
    """
    root_nodes: list[FileTreeNode] = []
    directory_nodes: dict[tuple[str, ...], FileTreeNode] = {}

    def ensure_directory(path_parts: tuple[str, ...]) -> FileTreeNode:
        directory_node = directory_nodes.get(path_parts)
        if directory_node is not None:
            return directory_node

        directory_node = FileTreeNode(
            type="directory",
            name=path_parts[-1],
            path="/".join(path_parts),
            children=[],
        )
        directory_nodes[path_parts] = directory_node

        if len(path_parts) == 1:
            root_nodes.append(directory_node)
            return directory_node

        parent_node = ensure_directory(path_parts[:-1])
        if parent_node.children is None:
            parent_node.children = []
        parent_node.children.append(directory_node)
        return directory_node

    def sort_nodes(nodes: list[FileTreeNode]) -> None:
        nodes.sort(key=lambda node: (node.type != "directory", node.name.lower()))
        for node in nodes:
            if node.type == "directory" and node.children:
                sort_nodes(node.children)

    for file in files:
        relative_path = _relative_object_path(root_prefix, file.object_key)
        if not relative_path.parts:
            continue

        file_node = FileTreeNode(
            type="file",
            name=file.filename,
            path=relative_path.as_posix(),
            size=file.size,
            modified=file.modified,
            filename=file.filename,
            virtual_path=file.virtual_path,
            artifact_url=file.artifact_url,
            object_key=file.object_key,
            signed_url=file.signed_url,
            extension=file.extension,
            markdown_file=file.markdown_file,
            markdown_path=file.markdown_path,
            markdown_virtual_path=file.markdown_virtual_path,
            markdown_artifact_url=file.markdown_artifact_url,
            markdown_object_key=file.markdown_object_key,
            markdown_signed_url=file.markdown_signed_url,
        )

        if len(relative_path.parts) == 1:
            root_nodes.append(file_node)
            continue

        parent_node = ensure_directory(relative_path.parts[:-1])
        if parent_node.children is None:
            parent_node.children = []
        parent_node.children.append(file_node)

    sort_nodes(root_nodes)
    return root_nodes


def _get_upload_file_size(upload_file: UploadFile) -> int | None:
    """Best-effort content length for streamed uploads."""
    if upload_file.size is not None:
        return upload_file.size

    stream = upload_file.file
    if not hasattr(stream, "tell") or not hasattr(stream, "seek"):
        return None

    try:
        current_position = stream.tell()
        stream.seek(0, 2)
        size = stream.tell()
        stream.seek(current_position)
    except (AttributeError, OSError, ValueError):
        return None

    return size


async def _read_upload_content(upload_file: UploadFile) -> bytes:
    """Read an upload from the beginning and reset the stream position."""
    await upload_file.seek(0)
    content = await upload_file.read()
    await upload_file.seek(0)
    return content


async def _upload_markdown_companion(
    *,
    root_prefix: str,
    markdown_path: Path,
    subdir: str | None = None,
) -> tuple[str, str | None]:
    """Upload an auto-generated markdown companion file to OSS."""
    markdown_content = markdown_path.read_bytes()
    _, markdown_object_key, markdown_signed_url, _ = await upload_workspace_object(
        root_prefix=root_prefix,
        filename=markdown_path.name,
        content=markdown_content,
        content_type="text/markdown; charset=utf-8",
        subdir=subdir,
    )
    return markdown_object_key, markdown_signed_url


async def _process_single_file(
    *,
    file: UploadFile,
    root_prefix: str,
    workspace_id: str,
    temp_dir: Path,
) -> WorkspaceFileResponse | None:
    """Process a single file upload (stream to OSS for non-convertible files)."""
    if not file.filename:
        return None

    try:
        safe_filename = normalize_filename(file.filename)
    except ValueError:
        logger.warning("Skipping file with unsafe filename: %r", file.filename)
        return None

    try:
        # Check if file needs conversion
        needs_conversion = Path(safe_filename).suffix.lower() in CONVERTIBLE_EXTENSIONS

        if needs_conversion:
            # For convertible files, read content once for both OSS upload and conversion
            content = await _read_upload_content(file)
            file_size = len(content)

            # Upload to OSS (user uploads go to uploads/ subdirectory)
            _, object_key, signed_url, _ = await upload_workspace_object(
                root_prefix=root_prefix,
                filename=safe_filename,
                content=content,
                content_type=file.content_type or mimetypes.guess_type(safe_filename)[0],
                subdir="uploads",
            )

            # Write to temp directory for document conversion
            convert_source_path = temp_dir / safe_filename
            convert_source_path.write_bytes(content)

            # Convert to markdown
            markdown_path = await convert_file_to_markdown(convert_source_path)
            if markdown_path is not None:
                markdown_object_key, markdown_signed_url = await _upload_markdown_companion(
                    root_prefix=root_prefix,
                    markdown_path=markdown_path,
                    subdir="uploads",
                )
                relative_path = _relative_object_path(root_prefix, object_key).as_posix()
                return WorkspaceFileResponse.model_validate(
                    build_workspace_file_response(
                        workspace_id=workspace_id,
                        filename=safe_filename,
                        relative_path=relative_path,
                        size=file_size,
                        object_key=object_key,
                        signed_url=signed_url,
                        markdown_file=markdown_path.name,
                        markdown_object_key=markdown_object_key,
                        markdown_signed_url=markdown_signed_url,
                    )
                )
        else:
            # For non-convertible files, stream directly to OSS without reading into memory
            file_size = _get_upload_file_size(file) or 0

            # Stream to OSS (user uploads go to uploads/ subdirectory)
            await file.seek(0)
            _, object_key, signed_url, _ = await upload_workspace_object_stream(
                root_prefix=root_prefix,
                filename=safe_filename,
                stream=file.file,
                content_length=_get_upload_file_size(file),
                content_type=file.content_type or mimetypes.guess_type(safe_filename)[0],
                subdir="uploads",
            )

        relative_path = _relative_object_path(root_prefix, object_key).as_posix()
        return WorkspaceFileResponse.model_validate(
            build_workspace_file_response(
                workspace_id=workspace_id,
                filename=safe_filename,
                relative_path=relative_path,
                size=file_size,
                object_key=object_key,
                signed_url=signed_url,
            )
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to upload %s", file.filename)
        raise HTTPException(status_code=500, detail=f"Failed to upload {file.filename}: {exc}") from exc


@router.post("", response_model=UploadResponse)
async def upload_files(
    workspace_id: str,
    files: list[UploadFile] = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UploadResponse:
    """Upload multiple files into a canonical workspace OSS directory (parallel processing)."""
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    workspace = await _require_workspace_access(
        db=db,
        workspace_id=workspace_id,
        current_user=current_user,
    )

    root_prefix = await ensure_workspace_prefix(db, workspace)

    with tempfile.TemporaryDirectory(prefix="workspace-upload-") as temp_dir_str:
        temp_dir = Path(temp_dir_str)

        # Process all files in parallel
        tasks = [
            _process_single_file(
                file=file,
                root_prefix=root_prefix,
                workspace_id=workspace_id,
                temp_dir=temp_dir,
            )
            for file in files
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Collect successful uploads and handle errors
        uploaded_files: list[WorkspaceFileResponse] = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                # Re-raise HTTPException to maintain error handling behavior
                if isinstance(result, HTTPException):
                    raise result
                logger.error("Failed to process file %s: %s", files[i].filename, result)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to upload {files[i].filename}: {str(result)}"
                )
            elif result is not None:
                uploaded_files.append(result)

    return UploadResponse(
        success=True,
        files=uploaded_files,
        message=f"Successfully uploaded {len(uploaded_files)} file(s)",
    )


@router.get("/list", response_model=ListFilesResponse)
async def list_uploaded_files(
    workspace_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ListFilesResponse:
    """List canonical workspace files from OSS."""
    workspace = await _require_workspace_access(
        db=db,
        workspace_id=workspace_id,
        current_user=current_user,
    )

    root_prefix = await ensure_workspace_prefix(db, workspace)
    storage, objects = await list_workspace_objects(root_prefix)

    objects_by_relative_path = {
        _relative_object_path(root_prefix, item.key).as_posix(): item for item in objects
    }

    files: list[WorkspaceFileResponse] = []
    processed_paths: set[str] = set()

    for item in sorted(
        objects,
        key=lambda value: _relative_object_path(root_prefix, value.key).as_posix().lower(),
    ):
        relative_path = _relative_object_path(root_prefix, item.key).as_posix()
        filename = PurePosixPath(relative_path).name

        # Skip markdown companion files (they'll be linked to their source files)
        if filename.endswith(".md"):
            source_stem = str(PurePosixPath(relative_path).with_suffix(""))
            if any(f"{source_stem}{extension}" in objects_by_relative_path for extension in CONVERTIBLE_EXTENSIONS):
                continue

        # Skip if already processed
        if relative_path in processed_paths:
            continue
        processed_paths.add(relative_path)

        signed_url, _ = await asyncio.to_thread(storage.presign_get_object, key=item.key)

        # Check if this file has a markdown companion
        markdown_file = None
        markdown_object_key = None
        markdown_signed_url = None
        if PurePosixPath(relative_path).suffix.lower() in CONVERTIBLE_EXTENSIONS:
            markdown_relative_path = PurePosixPath(relative_path).with_suffix(".md").as_posix()
            if markdown_relative_path in objects_by_relative_path:
                markdown_item = objects_by_relative_path[markdown_relative_path]
                markdown_object_key = markdown_item.key
                markdown_signed_url, _ = await asyncio.to_thread(
                    storage.presign_get_object, key=markdown_object_key
                )
                markdown_file = PurePosixPath(markdown_relative_path).name
                processed_paths.add(markdown_relative_path)

        files.append(
            WorkspaceFileResponse.model_validate(
                build_workspace_file_response(
                    workspace_id=workspace_id,
                    filename=filename,
                    relative_path=relative_path,
                    size=item.size,
                    object_key=item.key,
                    signed_url=signed_url,
                    modified=int(item.last_modified.timestamp()) if item.last_modified is not None else None,
                    markdown_file=markdown_file,
                    markdown_object_key=markdown_object_key,
                    markdown_signed_url=markdown_signed_url,
                )
            )
        )

    return ListFilesResponse(
        root_label=_build_workspace_root_label(workspace),
        root_path=build_workspace_root_path(storage, root_prefix),
        files=files,
        tree=_build_file_tree(root_prefix=root_prefix, files=files),
        count=len(files),
    )


@router.get("/content")
async def get_workspace_file_content(
    workspace_id: str,
    object_key: str = Query(..., description="OSS object key"),
    download: bool = Query(default=False, description="Force download as attachment"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Serve workspace file content via stable backend proxy.

    This endpoint provides a stable URL for workspace files that doesn't expire
    like signed URLs. It validates workspace ownership and serves the file content
    directly from OSS.

    For security, HTML/XHTML/SVG files are always forced as downloads to prevent XSS.
    """
    workspace = await _require_workspace_access(
        db=db,
        workspace_id=workspace_id,
        current_user=current_user,
    )

    root_prefix = await ensure_workspace_prefix(db, workspace)
    normalized_object_key = object_key.strip("/")

    # Validate that the object_key belongs to this workspace
    if not _object_key_belongs_to_workspace(
        object_key=normalized_object_key,
        root_prefix=root_prefix,
    ):
        raise HTTPException(
            status_code=403,
            detail="Object key does not belong to this workspace",
        )

    storage = OSSStorageBackend.from_app_config()
    try:
        object_stream = await asyncio.to_thread(
            storage.open_object,
            key=normalized_object_key,
        )
    except ServiceError as exc:
        if _is_missing_workspace_object_error(exc):
            raise HTTPException(status_code=404, detail="Workspace file not found") from exc
        logger.exception("Failed to fetch object %s from OSS", normalized_object_key)
        raise HTTPException(status_code=502, detail="Failed to fetch workspace file") from exc
    except Exception as exc:
        logger.exception("Failed to fetch object %s from OSS", normalized_object_key)
        raise HTTPException(status_code=500, detail="Failed to fetch workspace file") from exc

    filename = Path(normalized_object_key).name
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"

    active_content_types = {
        "text/html",
        "application/xhtml+xml",
        "image/svg+xml",
    }
    force_download = download or content_type in active_content_types

    headers = {}
    if force_download:
        headers["Content-Disposition"] = _build_content_disposition("attachment", filename)
    else:
        headers["Content-Disposition"] = _build_content_disposition("inline", filename)

    return StreamingResponse(
        _iter_oss_stream_chunks(object_stream),
        media_type=content_type,
        headers=headers,
    )


@router.delete("")
async def delete_uploaded_file(
    workspace_id: str,
    payload: DeleteUploadedFileRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Delete a canonical workspace file from OSS."""
    workspace = await _require_workspace_access(
        db=db,
        workspace_id=workspace_id,
        current_user=current_user,
    )

    try:
        safe_filename = normalize_filename(payload.filename)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid filename") from None

    root_prefix = await ensure_workspace_prefix(db, workspace)

    # Determine which subdirectory the file is in by checking OSS
    storage, objects = await list_workspace_objects(root_prefix)

    file_object = None
    if payload.object_key:
        normalized_object_key = payload.object_key.strip("/")
        file_object = next((obj for obj in objects if obj.key == normalized_object_key), None)
        if file_object is not None and Path(file_object.key).name != safe_filename:
            raise HTTPException(status_code=400, detail="Filename does not match object key")
    else:
        # Fall back to basename lookup for older clients.
        for obj in objects:
            if Path(obj.key).name == safe_filename:
                file_object = obj
                break

    if file_object is None:
        raise HTTPException(status_code=404, detail=f"File {safe_filename} not found")

    object_key = file_object.key

    try:
        await delete_workspace_object(object_key=object_key)
        if Path(safe_filename).suffix.lower() in CONVERTIBLE_EXTENSIONS:
            companion_key = str(PurePosixPath(object_key).with_suffix(".md"))
            try:
                await delete_workspace_object(object_key=companion_key)
            except ServiceError as exc:
                if exc.status_code != 404 and exc.code != "NoSuchKey":
                    raise
                logger.debug("Workspace markdown companion already missing: %s", companion_key)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to delete %s from workspace %s", safe_filename, workspace_id)
        raise HTTPException(status_code=500, detail=f"Failed to delete {safe_filename}: {exc}") from exc

    return {"success": True, "message": f"Deleted {safe_filename}"}
