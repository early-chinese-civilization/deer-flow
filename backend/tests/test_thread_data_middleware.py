import pytest
from langgraph.runtime import Runtime

from deerflow.agents.middlewares.thread_data_middleware import ThreadDataMiddleware


def _as_posix(path: str) -> str:
    return path.replace("\\", "/")


class TestThreadDataMiddleware:
    def test_before_agent_returns_paths_when_workspace_id_present_in_context(self, tmp_path):
        middleware = ThreadDataMiddleware(base_dir=str(tmp_path), lazy_init=True)

        result = middleware.before_agent(
            state={},
            runtime=Runtime(context={"thread_id": "thread-123", "workspace_id": "workspace-123"}),
        )

        assert result is not None
        assert result["thread_data"]["thread_id"] == "thread-123"
        assert result["thread_data"]["workspace_id"] == "workspace-123"
        assert _as_posix(result["thread_data"]["workspace_path"]).endswith(
            "workspaces/workspace-123/user-data/workspace"
        )
        assert _as_posix(result["thread_data"]["uploads_path"]).endswith(
            "workspaces/workspace-123/user-data/uploads"
        )
        assert _as_posix(result["thread_data"]["outputs_path"]).endswith(
            "workspaces/workspace-123/user-data/outputs"
        )

    def test_before_agent_falls_back_to_thread_id_as_workspace_id(self, tmp_path):
        middleware = ThreadDataMiddleware(base_dir=str(tmp_path), lazy_init=True)

        result = middleware.before_agent(state={}, runtime=Runtime(context={"thread_id": "thread-123"}))

        assert result is not None
        assert result["thread_data"]["thread_id"] == "thread-123"
        assert result["thread_data"]["workspace_id"] == "thread-123"
        assert _as_posix(result["thread_data"]["workspace_path"]).endswith(
            "workspaces/thread-123/user-data/workspace"
        )

    def test_before_agent_uses_workspace_id_from_configurable_when_context_is_none(self, tmp_path, monkeypatch):
        middleware = ThreadDataMiddleware(base_dir=str(tmp_path), lazy_init=True)
        runtime = Runtime(context=None)
        monkeypatch.setattr(
            "deerflow.agents.middlewares.thread_data_middleware.get_config",
            lambda: {"configurable": {"thread_id": "thread-from-config", "workspace_id": "workspace-from-config"}},
        )

        result = middleware.before_agent(state={}, runtime=runtime)

        assert result is not None
        assert result["thread_data"]["thread_id"] == "thread-from-config"
        assert _as_posix(result["thread_data"]["workspace_path"]).endswith(
            "workspaces/workspace-from-config/user-data/workspace"
        )
        assert runtime.context is None

    def test_before_agent_falls_back_to_configured_thread_id_when_workspace_missing(self, tmp_path, monkeypatch):
        middleware = ThreadDataMiddleware(base_dir=str(tmp_path), lazy_init=True)
        runtime = Runtime(context={})
        monkeypatch.setattr(
            "deerflow.agents.middlewares.thread_data_middleware.get_config",
            lambda: {"configurable": {"thread_id": "thread-from-config"}},
        )

        result = middleware.before_agent(state={}, runtime=runtime)

        assert result is not None
        assert result["thread_data"]["workspace_id"] == "thread-from-config"
        assert _as_posix(result["thread_data"]["uploads_path"]).endswith(
            "workspaces/thread-from-config/user-data/uploads"
        )
        assert runtime.context == {}

    def test_before_agent_raises_clear_error_when_workspace_and_thread_missing_everywhere(self, tmp_path, monkeypatch):
        middleware = ThreadDataMiddleware(base_dir=str(tmp_path), lazy_init=True)
        monkeypatch.setattr(
            "deerflow.agents.middlewares.thread_data_middleware.get_config",
            lambda: {"configurable": {}},
        )

        with pytest.raises(ValueError, match="Workspace ID is required in runtime context or config.configurable"):
            middleware.before_agent(state={}, runtime=Runtime(context=None))
