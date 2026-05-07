from typing import Annotated, NotRequired, TypedDict

from langchain.agents import AgentState


class SandboxState(TypedDict):
    sandbox_id: NotRequired[str | None]
    skill_scope: NotRequired[str | None]


class ThreadDataState(TypedDict):
    thread_id: NotRequired[str | None]
    workspace_id: NotRequired[str | None]
    workspace_path: NotRequired[str | None]
    uploads_path: NotRequired[str | None]
    outputs_path: NotRequired[str | None]


class ViewedImageData(TypedDict):
    base64: str
    mime_type: str
    virtual_path: NotRequired[str]
    oss_uri: NotRequired[str]
    http_uri: NotRequired[str | None]
    object_key: NotRequired[str]


class WorkspaceFileState(TypedDict):
    filename: str
    size: int
    path: str
    virtual_path: str
    oss_uri: str
    http_uri: NotRequired[str | None]
    object_key: str
    extension: NotRequired[str | None]
    modified: NotRequired[int | None]
    original_filename: NotRequired[str]
    markdown_file: NotRequired[str | None]
    markdown_path: NotRequired[str | None]
    markdown_virtual_path: NotRequired[str | None]
    markdown_object_key: NotRequired[str | None]
    markdown_oss_uri: NotRequired[str | None]
    markdown_http_uri: NotRequired[str | None]


def _normalize_artifacts(value: dict[str, str] | list[str] | None) -> dict[str, str]:
    if value is None:
        return {}
    if isinstance(value, list):
        return {path: path for path in value if isinstance(path, str)}
    return {str(key): str(val) for key, val in value.items() if isinstance(key, str) and isinstance(val, str)}


def merge_artifacts(
    existing: dict[str, str] | list[str] | None,
    new: dict[str, str] | list[str] | None,
) -> dict[str, str]:
    """Reducer for artifacts map - merges and deduplicates by virtual path."""
    merged = _normalize_artifacts(existing)
    merged.update(_normalize_artifacts(new))
    return merged


def merge_viewed_images(existing: dict[str, ViewedImageData] | None, new: dict[str, ViewedImageData] | None) -> dict[str, ViewedImageData]:
    """Reducer for viewed_images dict - merges image dictionaries.

    Special case: If new is an empty dict {}, it clears the existing images.
    This allows middlewares to clear the viewed_images state after processing.
    """
    if existing is None:
        return new or {}
    if new is None:
        return existing
    # Special case: empty dict means clear all viewed images
    if len(new) == 0:
        return {}
    # Merge dictionaries, new values override existing ones for same keys
    return {**existing, **new}


class ThreadState(AgentState):
    sandbox: NotRequired[SandboxState | None]
    thread_data: NotRequired[ThreadDataState | None]
    title: NotRequired[str | None]
    artifacts: Annotated[dict[str, str], merge_artifacts]
    todos: NotRequired[list | None]
    uploaded_files: NotRequired[list[WorkspaceFileState] | None]
    viewed_images: Annotated[dict[str, ViewedImageData], merge_viewed_images]  # image_path -> {base64, mime_type}
