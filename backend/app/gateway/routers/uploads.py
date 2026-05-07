"""Workspace uploads router backed by canonical OSS storage."""

from __future__ import annotations

import asyncio
import logging
import mimetypes
import uuid
from pathlib import Path, PurePosixPath
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse, Response
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
    get_workspace_object_bytes,
    list_workspace_objects,
    upload_workspace_object_stream,
    uses_oss_workspace_uploads,
    workspace_object_path,
)
from deerflow.uploads import (
    OSSStorageBackend,
    claim_unique_filename,
    normalize_filename,
    oss_object_uri,
    workspace_object_key,
    workspace_root_prefix,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/workspaces/{workspace_id}/uploads", tags=["uploads"])


class WorkspaceFileResponse(BaseModel):
    """Serialized metadata for a canonical workspace file."""

    filename: str
    size: int
    path: str
    virtual_path: str
    relative_path: str
    artifact_url: str | None = None
    http_uri: str | None = None
    object_key: str
    signed_url: str | None = None
    oss_uri: str | None = None
    modified: int | None = None
    extension: str | None = None
    markdown_file: str | None = None
    markdown_path: str | None = None
    markdown_virtual_path: str | None = None
    markdown_artifact_url: str | None = None
    markdown_http_uri: str | None = None
    markdown_object_key: str | None = None
    markdown_signed_url: str | None = None
    markdown_oss_uri: str | None = None


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
    http_uri: str | None = None
    object_key: str | None = None
    signed_url: str | None = None
    oss_uri: str | None = None
    extension: str | None = None
    markdown_file: str | None = None
    markdown_path: str | None = None
    markdown_virtual_path: str | None = None
    markdown_artifact_url: str | None = None
    markdown_http_uri: str | None = None
    markdown_object_key: str | None = None
    markdown_signed_url: str | None = None
    markdown_oss_uri: str | None = None


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


class UploadPrepareRequest(BaseModel):
    """Request body for preparing a workspace upload."""

    filename: str = Field(min_length=1)
    content_type: str | None = None
    size: int | None = Field(default=None, ge=0)


class UploadPrepareResponse(BaseModel):
    """Prepared upload metadata returned to the frontend."""

    mode: Literal["direct", "multipart"]
    method: Literal["PUT"] | None = None
    upload_url: str | None = None
    upload_headers: dict[str, str] = Field(default_factory=dict)
    file: WorkspaceFileResponse


class UploadFinalizeRequest(BaseModel):
    """Request body for finalizing a workspace upload."""

    filename: str = Field(min_length=1)
    object_key: str = Field(min_length=1)
    size: int | None = Field(default=None, ge=0)


class DownloadUrlResponse(BaseModel):
    """Presigned workspace download target."""

    download_url: str
    oss_uri: str


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


def _normalize_workspace_id(workspace_id: str) -> str:
    """Normalize and validate a workspace UUID string."""
    try:
        return str(uuid.UUID(workspace_id))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid workspace_id") from exc


async def _resolve_workspace_upload_root(
    *,
    db: AsyncSession,
    workspace_id: str,
    current_user: User | None,
    allow_draft: bool = False,
) -> tuple[Workspace | None, str]:
    """Resolve a workspace upload root, optionally allowing draft workspace IDs."""
    user = _require_authenticated_user(current_user)
    normalized_workspace_id = _normalize_workspace_id(workspace_id)
    workspace = await WorkspaceRepository.get_workspace_by_id(db, normalized_workspace_id)

    if workspace is None:
        if not allow_draft:
            raise HTTPException(status_code=404, detail=f"Workspace {workspace_id} not found")
        return None, workspace_root_prefix(normalized_workspace_id)

    if workspace.user_id != user.id:
        raise HTTPException(status_code=403, detail=f"Workspace belongs to user {workspace.user_id}")

    return workspace, await ensure_workspace_prefix(db, workspace)


def _build_workspace_root_label(workspace: Workspace) -> str:
    """Build a friendly root label for the workspace panel."""
    if workspace.name and workspace.name.strip():
        return workspace.name.strip()
    return "workspace"


def _build_content_disposition(disposition_type: str, filename: str) -> str:
    """Build an RFC 5987 encoded Content-Disposition header."""
    return f"{disposition_type}; filename*=UTF-8''{quote(filename)}"


async def _claim_upload_filenames(
    *,
    root_prefix: str,
    workspace_id: str,
    filenames: list[str],
) -> list[str]:
    """Claim unique upload filenames against the current workspace uploads prefix."""
    existing_objects = await list_workspace_objects(root_prefix=root_prefix, workspace_id=workspace_id)
    seen_names: set[str] = set()

    for item in existing_objects:
        relative_path = _relative_object_path(root_prefix, item.key)
        if not relative_path.parts or relative_path.parts[0] != "uploads":
            continue
        seen_names.add(relative_path.name)

    return [claim_unique_filename(filename, seen_names) for filename in filenames]


def _is_direct_workspace_upload_enabled() -> bool:
    """Return whether direct browser uploads should use OSS presigned PUT."""
    try:
        from deerflow.config import get_app_config

        uploads_config = get_app_config().uploads
    except Exception:
        return False

    if uploads_config.backend != "oss":
        return False

    return bool(uploads_config.oss.endpoint and uploads_config.oss.bucket and uploads_config.oss.access_key_id and uploads_config.oss.access_key_secret)


def _presign_workspace_put_upload(
    *,
    object_key: str,
    content_type: str | None,
    content_length: int | None,
) -> tuple[str, str, dict[str, str]]:
    """Build a presigned PUT upload target for a workspace object."""
    storage = OSSStorageBackend.from_app_config()
    upload_url, _expiration, signed_headers = storage.presign_put_object(
        key=object_key,
        content_type=content_type,
        content_length=content_length,
    )
    return "PUT", upload_url, signed_headers


def _object_key_belongs_to_workspace(*, object_key: str, root_prefix: str) -> bool:
    """Check that an object key stays within the current workspace prefix."""
    normalized_object_key = object_key.strip("/")
    normalized_root_prefix = root_prefix.strip("/")
    if normalized_object_key == normalized_root_prefix:
        return True
    return normalized_object_key.startswith(f"{normalized_root_prefix}/")


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
            markdown_oss_uri=file.markdown_oss_uri,
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


async def _process_single_file(
    *,
    file: UploadFile,
    target_filename: str,
    root_prefix: str,
    workspace_id: str,
) -> WorkspaceFileResponse | None:
    """Process a single file upload into the shared workspace filesystem."""
    if not file.filename:
        return None

    logger.info(
        "Start processing upload for workspace %s: filename=%s content_type=%s",
        workspace_id,
        file.filename,
        file.content_type,
    )

    try:
        file_size = _get_upload_file_size(file) or 0
        logger.info(
            "Streaming upload for workspace %s: filename=%s size=%s",
            workspace_id,
            target_filename,
            file_size,
        )

        await file.seek(0)
        _, object_key, signed_url, _ = await upload_workspace_object_stream(
            root_prefix=root_prefix,
            workspace_id=workspace_id,
            filename=target_filename,
            stream=file.file,
            content_length=_get_upload_file_size(file),
            content_type=file.content_type or mimetypes.guess_type(target_filename)[0],
            subdir="uploads",
        )
        logger.info(
            "Stored streamed upload for workspace %s: filename=%s object_key=%s",
            workspace_id,
            target_filename,
            object_key,
        )

        relative_path = _relative_object_path(root_prefix, object_key).as_posix()
        logger.info(
            "Building upload response for workspace %s: filename=%s object_key=%s relative_path=%s",
            workspace_id,
            target_filename,
            object_key,
            relative_path,
        )
        return WorkspaceFileResponse.model_validate(
            build_workspace_file_response(
                workspace_id=workspace_id,
                filename=target_filename,
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
    """Upload multiple files into the shared workspace directory."""
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    logger.info(
        "Received workspace upload request: workspace_id=%s file_count=%s filenames=%s",
        workspace_id,
        len(files),
        [file.filename for file in files],
    )

    _workspace, root_prefix = await _resolve_workspace_upload_root(
        db=db,
        workspace_id=workspace_id,
        current_user=current_user,
        allow_draft=True,
    )
    normalized_files: list[tuple[UploadFile, str]] = []
    for file in files:
        if not file.filename:
            continue
        try:
            normalized_files.append((file, normalize_filename(file.filename)))
        except ValueError:
            logger.warning("Skipping file with unsafe filename: %r", file.filename)

    claimed_filenames = await _claim_upload_filenames(
        root_prefix=root_prefix,
        workspace_id=workspace_id,
        filenames=[filename for _, filename in normalized_files],
    )

    task_inputs = [((file, normalized_filename), claimed_filename) for (file, normalized_filename), claimed_filename in zip(normalized_files, claimed_filenames, strict=False)]

    tasks = [
        _process_single_file(
            file=file,
            target_filename=claimed_filename,
            root_prefix=root_prefix,
            workspace_id=workspace_id,
        )
        for (file, _), claimed_filename in task_inputs
    ]
    logger.info(
        "Starting parallel upload processing for workspace %s: task_count=%s",
        workspace_id,
        len(tasks),
    )
    results = await asyncio.gather(*tasks, return_exceptions=True)
    logger.info(
        "Parallel upload processing finished for workspace %s: result_count=%s",
        workspace_id,
        len(results),
    )

    uploaded_files: list[WorkspaceFileResponse] = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            if isinstance(result, HTTPException):
                raise result
            (_file, normalized_filename), claimed_filename = task_inputs[i]
            logger.error(
                "Failed to process file %s (claimed=%s): %s",
                normalized_filename,
                claimed_filename,
                result,
            )
            raise HTTPException(
                status_code=500,
                detail=f"Failed to upload {claimed_filename}: {str(result)}",
            )
        if result is not None:
            uploaded_files.append(result)
            logger.info(
                "Upload result ready for workspace %s: filename=%s object_key=%s",
                workspace_id,
                result.filename,
                result.object_key,
            )

    logger.info(
        "Workspace upload request completed: workspace_id=%s uploaded_count=%s",
        workspace_id,
        len(uploaded_files),
    )
    return UploadResponse(
        success=True,
        files=uploaded_files,
        message=f"Successfully uploaded {len(uploaded_files)} file(s)",
    )


@router.post("/prepare", response_model=UploadPrepareResponse)
async def prepare_upload(
    workspace_id: str,
    payload: UploadPrepareRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UploadPrepareResponse:
    """Prepare upload metadata and an optional presigned direct-upload target."""
    _workspace, root_prefix = await _resolve_workspace_upload_root(
        db=db,
        workspace_id=workspace_id,
        current_user=current_user,
        allow_draft=True,
    )

    try:
        safe_filename = normalize_filename(payload.filename)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid filename") from None

    [final_filename] = await _claim_upload_filenames(
        root_prefix=root_prefix,
        workspace_id=workspace_id,
        filenames=[safe_filename],
    )
    object_key = workspace_object_key(root_prefix, final_filename, subdir="uploads")
    relative_path = _relative_object_path(root_prefix, object_key).as_posix()
    file_response = WorkspaceFileResponse.model_validate(
        build_workspace_file_response(
            workspace_id=workspace_id,
            filename=final_filename,
            relative_path=relative_path,
            size=payload.size or 0,
            object_key=object_key,
            signed_url=None,
        )
    )

    if not _is_direct_workspace_upload_enabled():
        return UploadPrepareResponse(
            mode="multipart",
            file=file_response,
        )

    try:
        method, upload_url, upload_headers = _presign_workspace_put_upload(
            object_key=object_key,
            content_type=payload.content_type,
            content_length=payload.size,
        )
    except Exception:
        logger.exception("Failed to presign direct upload for workspace %s", workspace_id)
        return UploadPrepareResponse(
            mode="multipart",
            file=file_response,
        )

    return UploadPrepareResponse(
        mode="direct",
        method=method,
        upload_url=upload_url,
        upload_headers=upload_headers,
        file=file_response,
    )


@router.post("/finalize", response_model=WorkspaceFileResponse)
async def finalize_upload(
    workspace_id: str,
    payload: UploadFinalizeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WorkspaceFileResponse:
    """Finalize an uploaded workspace object and return canonical metadata."""
    _workspace, root_prefix = await _resolve_workspace_upload_root(
        db=db,
        workspace_id=workspace_id,
        current_user=current_user,
        allow_draft=True,
    )

    try:
        safe_filename = normalize_filename(payload.filename)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid filename") from None

    normalized_object_key = payload.object_key.strip("/")
    if not _object_key_belongs_to_workspace(
        object_key=normalized_object_key,
        root_prefix=root_prefix,
    ):
        raise HTTPException(status_code=403, detail="Object key does not belong to this workspace")

    if Path(normalized_object_key).name != safe_filename:
        raise HTTPException(status_code=400, detail="Filename does not match object key")

    objects = await list_workspace_objects(root_prefix=root_prefix, workspace_id=workspace_id)
    uploaded_object = next((item for item in objects if item.key == normalized_object_key), None)
    if uploaded_object is None:
        raise HTTPException(status_code=404, detail="Uploaded file not found")

    relative_path = _relative_object_path(root_prefix, uploaded_object.key).as_posix()
    return WorkspaceFileResponse.model_validate(
        build_workspace_file_response(
            workspace_id=workspace_id,
            filename=safe_filename,
            relative_path=relative_path,
            size=uploaded_object.size,
            object_key=uploaded_object.key,
            signed_url=None,
            modified=int(uploaded_object.last_modified.timestamp()) if uploaded_object.last_modified else None,
        )
    )


@router.get("/list", response_model=ListFilesResponse)
async def list_uploaded_files(
    workspace_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ListFilesResponse:
    """List canonical workspace files from the shared workspace directory."""
    workspace = await _require_workspace_access(
        db=db,
        workspace_id=workspace_id,
        current_user=current_user,
    )

    root_prefix = await ensure_workspace_prefix(db, workspace)
    objects = await list_workspace_objects(root_prefix=root_prefix, workspace_id=workspace_id)

    files: list[WorkspaceFileResponse] = []
    processed_paths: set[str] = set()

    for item in sorted(
        objects,
        key=lambda value: _relative_object_path(root_prefix, value.key).as_posix().lower(),
    ):
        relative_path = _relative_object_path(root_prefix, item.key).as_posix()
        filename = PurePosixPath(relative_path).name

        # Skip if already processed
        if relative_path in processed_paths:
            continue
        processed_paths.add(relative_path)

        signed_url = None

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
                )
            )
        )

    return ListFilesResponse(
        root_label=_build_workspace_root_label(workspace),
        root_path=build_workspace_root_path(root_prefix),
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

    This endpoint provides a stable URL for workspace files. It validates
    workspace ownership and serves the file content directly from the shared filesystem.

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

    filename = Path(normalized_object_key).name
    active_content_types = {
        "text/html",
        "application/xhtml+xml",
        "image/svg+xml",
    }

    if uses_oss_workspace_uploads():
        objects = await list_workspace_objects(root_prefix=root_prefix, workspace_id=workspace_id)
        file_object = next((item for item in objects if item.key == normalized_object_key), None)
        if file_object is None:
            raise HTTPException(status_code=404, detail="Workspace file not found")

        content_type = file_object.content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
        force_download = download or content_type in active_content_types

        try:
            content = await get_workspace_object_bytes(
                root_prefix=root_prefix,
                workspace_id=workspace_id,
                object_key=normalized_object_key,
            )
        except ValueError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="Workspace file not found") from None
        except Exception as exc:
            logger.exception("Failed to fetch workspace file %s", normalized_object_key)
            raise HTTPException(status_code=500, detail="Failed to fetch workspace file") from exc

        if force_download:
            return Response(
                content=content,
                media_type=content_type,
                headers={"Content-Disposition": _build_content_disposition("attachment", filename)},
            )

        if content_type.startswith("text/"):
            try:
                return PlainTextResponse(content=content.decode("utf-8"), media_type=content_type)
            except UnicodeDecodeError:
                pass

        return Response(
            content=content,
            media_type=content_type,
            headers={"Content-Disposition": _build_content_disposition("inline", filename)},
        )

    try:
        file_path = workspace_object_path(
            root_prefix=root_prefix,
            workspace_id=workspace_id,
            object_key=normalized_object_key,
        )
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to resolve workspace file %s", normalized_object_key)
        raise HTTPException(status_code=500, detail="Failed to fetch workspace file") from exc

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Workspace file not found")

    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    force_download = download or content_type in active_content_types

    disposition = "attachment" if force_download else "inline"
    return FileResponse(
        path=file_path,
        media_type=content_type,
        filename=filename,
        content_disposition_type=disposition,
    )


@router.get("/download-url", response_model=DownloadUrlResponse)
async def get_workspace_download_url(
    workspace_id: str,
    object_key: str = Query(..., description="OSS object key"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DownloadUrlResponse:
    """Return a presigned OSS download URL for a workspace object."""
    if not uses_oss_workspace_uploads():
        raise HTTPException(status_code=400, detail="Presigned download URLs require OSS uploads")

    _workspace, root_prefix = await _resolve_workspace_upload_root(
        db=db,
        workspace_id=workspace_id,
        current_user=current_user,
    )

    normalized_object_key = object_key.strip("/")
    if not _object_key_belongs_to_workspace(
        object_key=normalized_object_key,
        root_prefix=root_prefix,
    ):
        raise HTTPException(status_code=403, detail="Object key does not belong to this workspace")

    try:
        storage = OSSStorageBackend.from_app_config()
        download_url, _expiration = storage.presign_get_object(key=normalized_object_key)
    except Exception:
        logger.exception("Failed to presign download URL for workspace %s", workspace_id)
        raise HTTPException(status_code=500, detail="Failed to generate download URL") from None

    return DownloadUrlResponse(
        download_url=download_url,
        oss_uri=oss_object_uri(storage.bucket, normalized_object_key),
    )


@router.delete("")
async def delete_uploaded_file(
    workspace_id: str,
    payload: DeleteUploadedFileRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Delete a canonical workspace file from OSS."""
    _workspace, root_prefix = await _resolve_workspace_upload_root(
        db=db,
        workspace_id=workspace_id,
        current_user=current_user,
        allow_draft=True,
    )

    try:
        safe_filename = normalize_filename(payload.filename)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid filename") from None

    # Determine which subdirectory the file is in by checking the shared filesystem
    objects = await list_workspace_objects(root_prefix=root_prefix, workspace_id=workspace_id)

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
        await delete_workspace_object(root_prefix=root_prefix, workspace_id=workspace_id, object_key=object_key)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to delete %s from workspace %s", safe_filename, workspace_id)
        raise HTTPException(status_code=500, detail=f"Failed to delete {safe_filename}: {exc}") from exc

    return {"success": True, "message": f"Deleted {safe_filename}"}
