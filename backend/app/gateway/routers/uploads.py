"""Workspace uploads router backed by canonical OSS storage."""

from __future__ import annotations

import asyncio
import logging
import mimetypes
import tempfile
from pathlib import Path

from alibabacloud_oss_v2.exceptions import ServiceError
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.gateway.db.models import Thread, User, Workspace
from app.gateway.db.repository import ThreadRepository, WorkspaceRepository
from app.gateway.deps import get_current_user, get_db
from app.gateway.services.workspace_uploads import (
    build_workspace_file_response,
    build_workspace_object_key,
    build_workspace_root_path,
    delete_workspace_object,
    ensure_workspace_prefix,
    list_workspace_objects,
    mirror_uploaded_file_to_thread,
    upload_workspace_object,
)
from deerflow.uploads import delete_file_safe, get_uploads_dir, normalize_filename
from deerflow.utils.file_conversion import CONVERTIBLE_EXTENSIONS, convert_file_to_markdown

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/workspaces/{workspace_id}/uploads", tags=["uploads"])


class WorkspaceFileResponse(BaseModel):
    """Serialized metadata for a canonical workspace file."""

    filename: str
    size: int
    path: str
    virtual_path: str
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
    count: int


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


async def _require_thread_context(
    *,
    db: AsyncSession,
    thread_id: str,
    workspace_id: str,
    current_user: User | None,
) -> Thread:
    """Validate that a thread belongs to the current user and bound workspace."""
    user = _require_authenticated_user(current_user)
    thread = await ThreadRepository.get_thread_by_id(db, thread_id)
    if thread is None:
        raise HTTPException(status_code=404, detail=f"Thread {thread_id} not found")
    if thread.user_id != user.id:
        raise HTTPException(status_code=403, detail=f"Thread belongs to user {thread.user_id}")
    if thread.workspace_id is None:
        raise HTTPException(status_code=409, detail=f"Thread {thread_id} is not bound to a workspace")
    if str(thread.workspace_id) != workspace_id:
        raise HTTPException(
            status_code=400,
            detail=f"Thread {thread_id} is not bound to workspace {workspace_id}",
        )
    return thread


async def _load_thread_context(
    *,
    db: AsyncSession,
    workspace_id: str,
    thread_id: str | None,
    current_user: User | None,
) -> Thread | None:
    """Load the optional thread runtime context for upload mirroring."""
    if not thread_id:
        return None

    return await _require_thread_context(
        db=db,
        thread_id=thread_id,
        workspace_id=workspace_id,
        current_user=current_user,
    )


def _build_workspace_root_label(workspace: Workspace) -> str:
    """Build a friendly root label for the workspace panel."""
    if workspace.name and workspace.name.strip():
        return workspace.name.strip()
    return "workspace"


async def _upload_markdown_companion(
    *,
    root_prefix: str,
    markdown_path: Path,
) -> tuple[str, str | None]:
    """Upload an auto-generated markdown companion file to OSS."""
    markdown_content = markdown_path.read_bytes()
    _, markdown_object_key, markdown_signed_url, _ = await upload_workspace_object(
        root_prefix=root_prefix,
        filename=markdown_path.name,
        content=markdown_content,
        content_type="text/markdown; charset=utf-8",
    )
    return markdown_object_key, markdown_signed_url


@router.post("", response_model=UploadResponse)
async def upload_files(
    workspace_id: str,
    files: list[UploadFile] = File(...),
    thread_id: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UploadResponse:
    """Upload multiple files into a canonical workspace OSS directory."""
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    workspace = await _require_workspace_access(
        db=db,
        workspace_id=workspace_id,
        current_user=current_user,
    )
    thread = await _load_thread_context(
        db=db,
        workspace_id=workspace_id,
        thread_id=thread_id,
        current_user=current_user,
    )

    root_prefix = await ensure_workspace_prefix(db, workspace)
    uploaded_files: list[WorkspaceFileResponse] = []

    with tempfile.TemporaryDirectory(prefix="workspace-upload-") as temp_dir_str:
        temp_dir = Path(temp_dir_str)
        for file in files:
            if not file.filename:
                continue

            try:
                safe_filename = normalize_filename(file.filename)
            except ValueError:
                logger.warning("Skipping file with unsafe filename: %r", file.filename)
                continue

            try:
                content = await file.read()
                _, object_key, signed_url, _ = await upload_workspace_object(
                    root_prefix=root_prefix,
                    filename=safe_filename,
                    content=content,
                    content_type=file.content_type or mimetypes.guess_type(safe_filename)[0],
                )

                if thread is not None:
                    await mirror_uploaded_file_to_thread(
                        thread_id=thread.thread_id,
                        filename=safe_filename,
                        content=content,
                    )

                convert_source_path = temp_dir / safe_filename
                convert_source_path.write_bytes(content)

                response_payload: dict[str, object] = build_workspace_file_response(
                    thread_id=thread.thread_id if thread is not None else None,
                    filename=safe_filename,
                    size=len(content),
                    object_key=object_key,
                    signed_url=signed_url,
                )

                if convert_source_path.suffix.lower() in CONVERTIBLE_EXTENSIONS:
                    markdown_path = await convert_file_to_markdown(convert_source_path)
                    if markdown_path is not None:
                        markdown_content = markdown_path.read_bytes()
                        markdown_object_key, markdown_signed_url = await _upload_markdown_companion(
                            root_prefix=root_prefix,
                            markdown_path=markdown_path,
                        )
                        if thread is not None:
                            await mirror_uploaded_file_to_thread(
                                thread_id=thread.thread_id,
                                filename=markdown_path.name,
                                content=markdown_content,
                            )
                        response_payload = build_workspace_file_response(
                            thread_id=thread.thread_id if thread is not None else None,
                            filename=safe_filename,
                            size=len(content),
                            object_key=object_key,
                            signed_url=signed_url,
                            markdown_file=markdown_path.name,
                            markdown_object_key=markdown_object_key,
                            markdown_signed_url=markdown_signed_url,
                        )

                uploaded_files.append(WorkspaceFileResponse.model_validate(response_payload))
            except HTTPException:
                raise
            except Exception as exc:
                logger.exception("Failed to upload %s into workspace %s", file.filename, workspace_id)
                raise HTTPException(status_code=500, detail=f"Failed to upload {file.filename}: {exc}") from exc

    return UploadResponse(
        success=True,
        files=uploaded_files,
        message=f"Successfully uploaded {len(uploaded_files)} file(s)",
    )


@router.get("/list", response_model=ListFilesResponse)
async def list_uploaded_files(
    workspace_id: str,
    thread_id: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ListFilesResponse:
    """List canonical workspace files from OSS."""
    workspace = await _require_workspace_access(
        db=db,
        workspace_id=workspace_id,
        current_user=current_user,
    )
    thread = await _load_thread_context(
        db=db,
        workspace_id=workspace_id,
        thread_id=thread_id,
        current_user=current_user,
    )

    root_prefix = await ensure_workspace_prefix(db, workspace)
    storage, objects = await list_workspace_objects(root_prefix)

    files: list[WorkspaceFileResponse] = []
    for item in sorted(objects, key=lambda value: Path(value.key).name.lower()):
        filename = Path(item.key).name
        signed_url, _ = await asyncio.to_thread(storage.presign_get_object, key=item.key)
        files.append(
            WorkspaceFileResponse.model_validate(
                build_workspace_file_response(
                    thread_id=thread.thread_id if thread is not None else None,
                    filename=filename,
                    size=item.size,
                    object_key=item.key,
                    signed_url=signed_url,
                    modified=int(item.last_modified.timestamp()) if item.last_modified is not None else None,
                )
            )
        )

    return ListFilesResponse(
        root_label=_build_workspace_root_label(workspace),
        root_path=build_workspace_root_path(storage, root_prefix),
        files=files,
        count=len(files),
    )


@router.delete("/{filename}")
async def delete_uploaded_file(
    workspace_id: str,
    filename: str,
    thread_id: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Delete a canonical workspace file from OSS."""
    workspace = await _require_workspace_access(
        db=db,
        workspace_id=workspace_id,
        current_user=current_user,
    )
    thread = await _load_thread_context(
        db=db,
        workspace_id=workspace_id,
        thread_id=thread_id,
        current_user=current_user,
    )

    try:
        safe_filename = normalize_filename(filename)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid filename") from None

    root_prefix = await ensure_workspace_prefix(db, workspace)
    object_key = build_workspace_object_key(root_prefix, safe_filename)

    try:
        await delete_workspace_object(object_key=object_key)
        if Path(safe_filename).suffix.lower() in CONVERTIBLE_EXTENSIONS:
            companion_key = build_workspace_object_key(
                root_prefix,
                Path(safe_filename).with_suffix(".md").name,
            )
            try:
                await delete_workspace_object(object_key=companion_key)
            except ServiceError as exc:
                if exc.status_code != 404 and exc.code != "NoSuchKey":
                    raise
                logger.debug("Workspace markdown companion already missing: %s", companion_key)

        if thread is not None:
            try:
                delete_file_safe(
                    get_uploads_dir(thread.thread_id),
                    safe_filename,
                    convertible_extensions=CONVERTIBLE_EXTENSIONS,
                )
            except FileNotFoundError:
                logger.debug(
                    "Thread mirror already missing for %s in thread %s",
                    safe_filename,
                    thread.thread_id,
                )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to delete %s from workspace %s", safe_filename, workspace_id)
        raise HTTPException(status_code=500, detail=f"Failed to delete {safe_filename}: {exc}") from exc

    return {"success": True, "message": f"Deleted {safe_filename}"}
