import logging
from typing import NotRequired, override

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langgraph.config import get_config
from langgraph.runtime import Runtime

from deerflow.agents.thread_state import ThreadDataState
from deerflow.config.paths import Paths, get_paths

logger = logging.getLogger(__name__)


class ThreadDataMiddlewareState(AgentState):
    """Compatible with the `ThreadState` schema."""

    thread_data: NotRequired[ThreadDataState | None]


class ThreadDataMiddleware(AgentMiddleware[ThreadDataMiddlewareState]):
    """Create workspace-backed thread data directories for each execution.

    Creates the following directory structure:
    - {shared_fs_root}/workspaces/{workspace_id}/user-data/workspace
    - {shared_fs_root}/workspaces/{workspace_id}/user-data/uploads
    - {shared_fs_root}/workspaces/{workspace_id}/user-data/outputs
    """

    state_schema = ThreadDataMiddlewareState

    def __init__(self, base_dir: str | None = None, lazy_init: bool = False):
        """Initialize the middleware.

        Args:
            base_dir: Base directory for legacy thread data. Defaults to Paths resolution.
            lazy_init: Deprecated and ignored. Workspace directories are always created eagerly.
        """
        super().__init__()
        self._paths = Paths(base_dir) if base_dir else get_paths()
        self._lazy_init = lazy_init

    def _get_workspace_paths(self, workspace_id: str) -> dict[str, str]:
        """Get the paths for a workspace's shared user-data directories.

        Args:
            workspace_id: The workspace ID.

        Returns:
            Dictionary with workspace_path, uploads_path, and outputs_path.
        """
        return {
            "workspace_id": workspace_id,
            "workspace_path": str(self._paths.workspace_work_dir(workspace_id)),
            "uploads_path": str(self._paths.workspace_uploads_dir(workspace_id)),
            "outputs_path": str(self._paths.workspace_outputs_dir(workspace_id)),
        }

    def _create_workspace_directories(self, workspace_id: str) -> dict[str, str]:
        """Create the workspace-backed shared user-data directories.

        Args:
            workspace_id: The workspace ID.

        Returns:
            Dictionary with the created directory paths.
        """
        self._paths.ensure_workspace_dirs(workspace_id)
        return self._get_workspace_paths(workspace_id)

    @override
    def before_agent(self, state: ThreadDataMiddlewareState, runtime: Runtime) -> dict | None:
        context = runtime.context or {}
        thread_id = context.get("thread_id")
        workspace_id = context.get("workspace_id")
        if workspace_id is None and thread_id is not None:
            workspace_id = thread_id

        if workspace_id is None or thread_id is None:
            config = get_config()
            configurable = config.get("configurable", {})
            if workspace_id is None:
                workspace_id = configurable.get("workspace_id")
            if thread_id is None:
                thread_id = configurable.get("thread_id")

        if workspace_id is None and thread_id is not None:
            workspace_id = thread_id

        if workspace_id is None:
            raise ValueError("Workspace ID is required in runtime context or config.configurable")

        paths = self._create_workspace_directories(str(workspace_id))
        logger.debug("Created shared workspace directories for workspace %s", workspace_id)

        thread_data = {**paths}
        if thread_id is not None:
            thread_data["thread_id"] = str(thread_id)

        return {
            "thread_data": thread_data,
        }
