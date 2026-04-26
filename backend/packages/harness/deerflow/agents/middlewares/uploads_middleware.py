"""Middleware to inject uploaded files information into agent context."""

import logging
from pathlib import Path
from typing import NotRequired, override
from urllib.parse import unquote, urlsplit

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import HumanMessage
from langgraph.runtime import Runtime

from deerflow.agents.thread_state import WorkspaceFileState
from deerflow.config import get_app_config
from deerflow.config.paths import VIRTUAL_PATH_PREFIX
from deerflow.uploads import oss_object_uri

logger = logging.getLogger(__name__)


class UploadsMiddlewareState(AgentState):
    """State schema for uploads middleware."""

    uploaded_files: NotRequired[list[WorkspaceFileState] | None]


class UploadsMiddleware(AgentMiddleware[UploadsMiddlewareState]):
    """Middleware to inject uploaded files information into the agent context.

    Reads file metadata from the current message's additional_kwargs.files
    (set by the frontend after upload) and prepends an <uploaded_files> block
    to the last human message so the model knows which files are available.
    """

    state_schema = UploadsMiddlewareState

    def __init__(self, base_dir: str | None = None):
        """Initialize the middleware.

        Args:
            base_dir: Base directory for thread data. Defaults to Paths resolution.
        """
        super().__init__()

    def _create_files_message(self, new_files: list[WorkspaceFileState], historical_files: list[WorkspaceFileState]) -> str:
        """Create a formatted message listing uploaded files.

        Args:
            new_files: Files uploaded in the current message.
            historical_files: Files uploaded in previous messages.

        Returns:
            Formatted string inside <uploaded_files> tags.
        """
        lines = ["<uploaded_files>"]

        lines.append("The following files were uploaded in this message:")
        lines.append("")
        if new_files:
            for file in new_files:
                size_kb = file["size"] / 1024
                size_str = f"{size_kb:.1f} KB" if size_kb < 1024 else f"{size_kb / 1024:.1f} MB"
                lines.append(f"- {file['filename']} ({size_str})")
                lines.append(f"  virtual_path: {file['virtual_path']}")
                lines.append(f"  oss_uri: {file['oss_uri']}")
                lines.append("")
        else:
            lines.append("(empty)")

        if historical_files:
            lines.append("The following files were uploaded in previous messages and are still available:")
            lines.append("")
            for file in historical_files:
                size_kb = file["size"] / 1024
                size_str = f"{size_kb:.1f} KB" if size_kb < 1024 else f"{size_kb / 1024:.1f} MB"
                lines.append(f"- {file['filename']} ({size_str})")
                lines.append(f"  virtual_path: {file['virtual_path']}")
                lines.append(f"  oss_uri: {file['oss_uri']}")
                lines.append("")

        lines.append("Use the `virtual_path` values with the `read_file` and `view_image` tools.")
        lines.append("</uploaded_files>")

        return "\n".join(lines)

    def _oss_uri_to_object_key(self, oss_uri: str) -> str | None:
        parts = urlsplit(oss_uri)
        if parts.scheme != "oss" or not parts.netloc:
            return None
        return unquote(parts.path.lstrip("/")) or None

    def _object_key_to_oss_uri(self, object_key: str) -> str | None:
        bucket = get_app_config().uploads.oss.bucket
        if not bucket:
            return None
        return oss_object_uri(bucket, object_key)

    def _resolve_virtual_path(self, payload: dict) -> str | None:
        virtual_path = payload.get("virtual_path")
        if isinstance(virtual_path, str) and virtual_path:
            return virtual_path

        path = payload.get("path")
        if isinstance(path, str) and path.startswith(VIRTUAL_PATH_PREFIX):
            return path

        return None

    def _sanitize_uploaded_file_entry(self, payload: dict) -> WorkspaceFileState | None:
        file_entry = self._workspace_file_from_payload(payload)
        if file_entry is None:
            return None

        return file_entry

    def _workspace_file_from_payload(self, payload: dict) -> WorkspaceFileState | None:
        filename = payload.get("filename")
        if not isinstance(filename, str) or not filename or Path(filename).name != filename:
            return None

        virtual_path = self._resolve_virtual_path(payload)
        if virtual_path is None:
            return None

        oss_uri = payload.get("oss_uri") or payload.get("path")
        object_key = payload.get("object_key")
        if isinstance(oss_uri, str) and oss_uri.startswith("oss://"):
            object_key = object_key if isinstance(object_key, str) and object_key else self._oss_uri_to_object_key(oss_uri)
        elif isinstance(object_key, str) and object_key:
            oss_uri = self._object_key_to_oss_uri(object_key)
        else:
            object_key = None

        if not isinstance(oss_uri, str) or not oss_uri.startswith("oss://"):
            return None
        if not isinstance(object_key, str) or not object_key:
            object_key = self._oss_uri_to_object_key(oss_uri)
        if not isinstance(object_key, str) or not object_key:
            return None

        entry: WorkspaceFileState = {
            "filename": filename,
            "size": int(payload.get("size") or 0),
            "path": oss_uri,
            "virtual_path": virtual_path,
            "oss_uri": oss_uri,
            "object_key": object_key,
        }

        for key in (
            "extension",
            "modified",
            "original_filename",
            "markdown_file",
            "markdown_path",
            "markdown_virtual_path",
            "markdown_object_key",
            "markdown_oss_uri",
        ):
            value = payload.get(key)
            if value is not None:
                entry[key] = value

        return entry

    def _files_from_kwargs(self, message: HumanMessage) -> list[WorkspaceFileState] | None:
        """Extract file info from message additional_kwargs.files.

        The frontend sends uploaded file metadata in additional_kwargs.files
        after a successful upload. Each entry includes the canonical OSS URI,
        the sandbox virtual path, and related metadata needed by the model.

        Args:
            message: The human message to inspect.

        Returns:
            List of canonical file dicts, or None if the field is absent or empty.
        """
        kwargs_files = (message.additional_kwargs or {}).get("files")
        if not isinstance(kwargs_files, list) or not kwargs_files:
            return None

        files: list[WorkspaceFileState] = []
        for f in kwargs_files:
            if not isinstance(f, dict):
                continue
            file_entry = self._workspace_file_from_payload(f)
            if file_entry is not None:
                files.append(file_entry)
        return files if files else None

    @override
    def before_agent(self, state: UploadsMiddlewareState, runtime: Runtime) -> dict | None:
        """Inject uploaded files information before agent execution.

        New files come from the current message's additional_kwargs.files.
        Historical files are read from the persisted thread state and merged with
        any uploads in the current message.

        Prepends <uploaded_files> context to the last human message content.
        The original additional_kwargs (including files metadata) is preserved
        on the updated message so the frontend can read it from the stream.

        Args:
            state: Current agent state.
            runtime: Runtime context containing workspace_id.

        Returns:
            State updates including uploaded files list.
        """
        messages = list(state.get("messages", []))
        if not messages:
            return None

        last_message_index = len(messages) - 1
        last_message = messages[last_message_index]

        if not isinstance(last_message, HumanMessage):
            return None

        # Get newly uploaded files from the current message's additional_kwargs.files
        new_files = self._files_from_kwargs(last_message) or []

        existing_files = []
        for file_entry in state.get("uploaded_files") or []:
            if not isinstance(file_entry, dict):
                continue
            sanitized = self._sanitize_uploaded_file_entry(file_entry)
            if sanitized is not None:
                existing_files.append(sanitized)

        seen_keys = {f.get("object_key") or f.get("oss_uri") for f in existing_files if isinstance(f.get("object_key") or f.get("oss_uri"), str)}
        merged_files = list(existing_files)
        for file_entry in new_files:
            key = file_entry.get("object_key") or file_entry.get("oss_uri")
            if isinstance(key, str) and key in seen_keys:
                continue
            merged_files.append(file_entry)
            if isinstance(key, str):
                seen_keys.add(key)

        new_keys = {f.get("object_key") or f.get("oss_uri") for f in new_files if isinstance(f.get("object_key") or f.get("oss_uri"), str)}
        historical_files = [f for f in existing_files if (f.get("object_key") or f.get("oss_uri")) not in new_keys]

        if not new_files and not historical_files:
            return None

        logger.debug(f"New files: {[f['filename'] for f in new_files]}, historical: {[f['filename'] for f in historical_files]}")

        # Create files message and prepend to the last human message content
        files_message = self._create_files_message(new_files, historical_files)

        # Extract original content - handle both string and list formats
        original_content = ""
        if isinstance(last_message.content, str):
            original_content = last_message.content
        elif isinstance(last_message.content, list):
            text_parts = []
            for block in last_message.content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
            original_content = "\n".join(text_parts)

        # Create new message with combined content.
        # Preserve additional_kwargs (including files metadata) so the frontend
        # can read structured file info from the streamed message.
        updated_message = HumanMessage(
            content=f"{files_message}\n\n{original_content}",
            id=last_message.id,
            additional_kwargs=last_message.additional_kwargs,
        )

        messages[last_message_index] = updated_message

        return {
            "uploaded_files": merged_files,
            "messages": messages,
        }
