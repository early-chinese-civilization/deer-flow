import base64
import mimetypes
from pathlib import Path
from typing import Annotated

from langchain.tools import InjectedToolCallId, ToolRuntime, tool
from langchain_core.messages import ToolMessage
from langgraph.types import Command
from langgraph.typing import ContextT

from deerflow.agents.thread_state import ThreadState


def _resolve_uploaded_image_entry(
    runtime: ToolRuntime[ContextT, ThreadState],
    image_path: str,
    actual_path: str,
) -> dict[str, str] | None:
    if runtime.state is None:
        return None

    uploaded_files = runtime.state.get("uploaded_files") or []
    candidates = {image_path, actual_path}

    for file_entry in uploaded_files:
        if not isinstance(file_entry, dict):
            continue

        virtual_path = file_entry.get("virtual_path")
        path = file_entry.get("path")
        oss_uri = file_entry.get("oss_uri")
        object_key = file_entry.get("object_key")

        if virtual_path not in candidates and path not in candidates and oss_uri not in candidates:
            continue

        result: dict[str, str] = {}
        if isinstance(virtual_path, str) and virtual_path:
            result["virtual_path"] = virtual_path
        if isinstance(oss_uri, str) and oss_uri.startswith("oss://"):
            result["oss_uri"] = oss_uri
        if isinstance(object_key, str) and object_key:
            result["object_key"] = object_key
        return result

    return None


@tool("view_image", parse_docstring=True)
def view_image_tool(
    runtime: ToolRuntime[ContextT, ThreadState],
    image_path: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Read an image file.

    Use this tool to read an image file and make it available for display.

    When to use the view_image tool:
    - When you need to view an image file.

    When NOT to use the view_image tool:
    - For non-image files (use present_files instead)
    - For multiple files at once (use present_files instead)

    Args:
        image_path: Absolute path to the image file. Common formats supported: jpg, jpeg, png, webp.
    """
    from deerflow.sandbox.tools import get_thread_data, replace_virtual_path

    # Replace virtual path with actual path
    # /mnt/user-data/* paths are mapped to thread-specific directories
    thread_data = get_thread_data(runtime)
    actual_path = replace_virtual_path(image_path, thread_data)

    # Validate that the path is absolute
    path = Path(actual_path)
    if not path.is_absolute():
        return Command(
            update={"messages": [ToolMessage(f"Error: Path must be absolute, got: {image_path}", tool_call_id=tool_call_id)]},
        )

    # Validate that the file exists
    if not path.exists():
        return Command(
            update={"messages": [ToolMessage(f"Error: Image file not found: {image_path}", tool_call_id=tool_call_id)]},
        )

    # Validate that it's a file (not a directory)
    if not path.is_file():
        return Command(
            update={"messages": [ToolMessage(f"Error: Path is not a file: {image_path}", tool_call_id=tool_call_id)]},
        )

    # Validate image extension
    valid_extensions = {".jpg", ".jpeg", ".png", ".webp"}
    if path.suffix.lower() not in valid_extensions:
        return Command(
            update={"messages": [ToolMessage(f"Error: Unsupported image format: {path.suffix}. Supported formats: {', '.join(valid_extensions)}", tool_call_id=tool_call_id)]},
        )

    # Detect MIME type from file extension
    mime_type, _ = mimetypes.guess_type(actual_path)
    if mime_type is None:
        # Fallback to default MIME types for common image formats
        extension_to_mime = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
        }
        mime_type = extension_to_mime.get(path.suffix.lower(), "application/octet-stream")

    # Read image file and convert to base64
    try:
        with open(actual_path, "rb") as f:
            image_data = f.read()
            image_base64 = base64.b64encode(image_data).decode("utf-8")
    except Exception as e:
        return Command(
            update={"messages": [ToolMessage(f"Error reading image file: {str(e)}", tool_call_id=tool_call_id)]},
        )

    # Update viewed_images in state
    # The merge_viewed_images reducer will handle merging with existing images
    image_source = _resolve_uploaded_image_entry(runtime, image_path, actual_path)
    image_key = (image_source or {}).get("oss_uri") or image_path
    new_viewed_images = {
        image_key: {
            "base64": image_base64,
            "mime_type": mime_type,
            **(image_source or {}),
        }
    }

    return Command(
        update={"viewed_images": new_viewed_images, "messages": [ToolMessage("Successfully read image", tool_call_id=tool_call_id)]},
    )
