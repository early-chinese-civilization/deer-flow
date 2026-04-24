import logging
from typing import NotRequired, override

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langgraph.runtime import Runtime

from deerflow.agents.thread_state import SandboxState, ThreadDataState
from deerflow.sandbox import get_sandbox_provider
from deerflow.sandbox.skill_scope import derive_skill_scope_from_runtime

logger = logging.getLogger(__name__)


class SandboxMiddlewareState(AgentState):
    """Compatible with the `ThreadState` schema."""

    sandbox: NotRequired[SandboxState | None]
    thread_data: NotRequired[ThreadDataState | None]


class SandboxMiddleware(AgentMiddleware[SandboxMiddlewareState]):
    """Create a sandbox environment and assign it to an agent.

    Lifecycle Management:
    - With lazy_init=True (default): Sandbox is acquired on first tool call
    - With lazy_init=False: Sandbox is acquired on first agent invocation (before_agent)
    - Sandbox is reused across multiple turns within the same thread
    - Sandbox is NOT released after each agent call to avoid wasteful recreation
    - Cleanup happens at application shutdown via SandboxProvider.shutdown()
    """

    state_schema = SandboxMiddlewareState

    def __init__(self, lazy_init: bool = True):
        """Initialize sandbox middleware.

        Args:
            lazy_init: If True, defer sandbox acquisition until first tool call.
                      If False, acquire sandbox eagerly in before_agent().
                      Default is True for optimal performance.
        """
        super().__init__()
        self._lazy_init = lazy_init

    def _acquire_sandbox(
        self,
        thread_id: str,
        workspace_id: str | None = None,
        skill_scope: str | None = None,
    ) -> str:
        provider = get_sandbox_provider()
        sandbox_id = provider.acquire(thread_id, workspace_id=workspace_id, skill_scope=skill_scope)
        logger.info(f"Acquiring sandbox {sandbox_id} with skill_scope={skill_scope}")
        return sandbox_id

    @override
    def before_agent(self, state: SandboxMiddlewareState, runtime: Runtime) -> dict | None:
        # Skip acquisition if lazy_init is enabled
        if self._lazy_init:
            return super().before_agent(state, runtime)

        thread_id = (runtime.context or {}).get("thread_id")
        if thread_id is None:
            return super().before_agent(state, runtime)

        workspace_id = (runtime.context or {}).get("workspace_id")
        expected_skill_scope = derive_skill_scope_from_runtime(runtime)
        provider = get_sandbox_provider()
        sandbox_state = state.get("sandbox")
        if sandbox_state is not None:
            sandbox_id = sandbox_state.get("sandbox_id")
            stored_skill_scope = sandbox_state.get("skill_scope")
            if sandbox_id is not None and stored_skill_scope == expected_skill_scope:
                if provider.get(sandbox_id) is not None:
                    return super().before_agent(state, runtime)
            elif sandbox_id is not None and provider.get(sandbox_id) is not None:
                logger.info(
                    "Releasing active sandbox %s because skill_scope changed from %s to %s",
                    sandbox_id,
                    stored_skill_scope,
                    expected_skill_scope,
                )
                provider.release(sandbox_id)

        sandbox_id = self._acquire_sandbox(
            str(thread_id),
            str(workspace_id) if workspace_id is not None else None,
            skill_scope=expected_skill_scope,
        )
        logger.info(f"Assigned sandbox {sandbox_id} to thread {thread_id}")
        return {"sandbox": {"sandbox_id": sandbox_id, "skill_scope": expected_skill_scope}}

    @override
    def after_agent(self, state: SandboxMiddlewareState, runtime: Runtime) -> dict | None:
        sandbox = state.get("sandbox")
        if sandbox is not None:
            sandbox_id = sandbox["sandbox_id"]
            logger.info(f"Releasing sandbox {sandbox_id}")
            get_sandbox_provider().release(sandbox_id)
            return None

        if (runtime.context or {}).get("sandbox_id") is not None:
            sandbox_id = runtime.context.get("sandbox_id")
            logger.info(f"Releasing sandbox {sandbox_id} from context")
            get_sandbox_provider().release(sandbox_id)
            return None

        # No sandbox to release
        return super().after_agent(state, runtime)
