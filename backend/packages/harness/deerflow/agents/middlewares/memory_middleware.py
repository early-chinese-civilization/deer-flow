"""Middleware for memory mechanism."""

import logging
import re
from typing import Any, override

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langgraph.config import get_config
from langgraph.runtime import Runtime

from deerflow.agents.memory.queue import get_memory_queue
from deerflow.config.memory_config import get_memory_config

logger = logging.getLogger(__name__)

_UPLOAD_BLOCK_RE = re.compile(r"<uploaded_files>[\s\S]*?</uploaded_files>\n*", re.IGNORECASE)
_CORRECTION_PATTERNS = (
    re.compile(r"\bthat(?:'s| is) (?:wrong|incorrect)\b", re.IGNORECASE),
    re.compile(r"\byou misunderstood\b", re.IGNORECASE),
    re.compile(r"\btry again\b", re.IGNORECASE),
    re.compile(r"\bredo\b", re.IGNORECASE),
    re.compile(r"不对"),
    re.compile(r"你理解错了"),
    re.compile(r"你理解有误"),
    re.compile(r"重试"),
    re.compile(r"重新来"),
    re.compile(r"换一种"),
    re.compile(r"改用"),
)


class MemoryMiddlewareState(AgentState):
    """Compatible with the `ThreadState` schema."""

    pass


def _get_runtime_context(config_data: dict[str, Any]) -> dict[str, Any]:
    """Resolve runtime context from LangGraph config shapes.

    Depending on the execution path, LangGraph may expose injected context either
    at the top level (`config["context"]`) or nested under
    `config["configurable"]["context"]`.
    """
    top_level_context = config_data.get("context", {})
    if isinstance(top_level_context, dict) and top_level_context:
        return top_level_context

    configurable = config_data.get("configurable", {})
    if not isinstance(configurable, dict):
        return {}

    nested_context = configurable.get("context", {})
    return nested_context if isinstance(nested_context, dict) else {}


def _extract_message_text(message: Any) -> str:
    """Extract plain text from message content for filtering and signal detection."""
    content = getattr(message, "content", "")
    if isinstance(content, list):
        text_parts: list[str] = []
        for part in content:
            if isinstance(part, str):
                text_parts.append(part)
            elif isinstance(part, dict):
                text_val = part.get("text")
                if isinstance(text_val, str):
                    text_parts.append(text_val)
        return " ".join(text_parts)
    return str(content)


def _filter_messages_for_memory(messages: list[Any]) -> list[Any]:
    """Filter messages to keep only user inputs and final assistant responses.

    This filters out:
    - Tool messages (intermediate tool call results)
    - AI messages with tool_calls (intermediate steps, not final responses)
    - The <uploaded_files> block injected by UploadsMiddleware into human messages
      (file paths are session-scoped and must not persist in long-term memory).
      The user's actual question is preserved; only turns whose content is entirely
      the upload block (nothing remains after stripping) are dropped along with
      their paired assistant response.

    Only keeps:
    - Human messages (with the ephemeral upload block removed)
    - AI messages without tool_calls (final assistant responses), unless the
      paired human turn was upload-only and had no real user text.

    Args:
        messages: List of all conversation messages.

    Returns:
        Filtered list containing only user inputs and final assistant responses.
    """
    filtered = []
    skip_next_ai = False
    for msg in messages:
        msg_type = getattr(msg, "type", None)

        if msg_type == "human":
            content_str = _extract_message_text(msg)
            if "<uploaded_files>" in content_str:
                # Strip the ephemeral upload block; keep the user's real question.
                stripped = _UPLOAD_BLOCK_RE.sub("", content_str).strip()
                if not stripped:
                    # Nothing left — the entire turn was upload bookkeeping;
                    # skip it and the paired assistant response.
                    skip_next_ai = True
                    continue
                # Rebuild the message with cleaned content so the user's question
                # is still available for memory summarisation.
                from copy import copy

                clean_msg = copy(msg)
                clean_msg.content = stripped
                filtered.append(clean_msg)
                skip_next_ai = False
            else:
                filtered.append(msg)
                skip_next_ai = False
        elif msg_type == "ai":
            tool_calls = getattr(msg, "tool_calls", None)
            if not tool_calls:
                if skip_next_ai:
                    skip_next_ai = False
                    continue
                filtered.append(msg)
        # Skip tool messages and AI messages with tool_calls

    return filtered


def detect_correction(messages: list[Any]) -> bool:
    """Detect explicit user corrections in recent conversation turns.

    The queue keeps only one pending context per thread, so callers pass the
    latest filtered message list. Checking only recent user turns keeps signal
    detection conservative while avoiding stale corrections from long histories.
    """
    recent_user_msgs = [msg for msg in messages[-6:] if getattr(msg, "type", None) == "human"]

    for msg in recent_user_msgs:
        content = _extract_message_text(msg).strip()
        if not content:
            continue
        if any(pattern.search(content) for pattern in _CORRECTION_PATTERNS):
            return True

    return False


class MemoryMiddleware(AgentMiddleware[MemoryMiddlewareState]):
    """Middleware that queues conversation for memory update after agent execution.

    This middleware:
    1. After each agent execution, queues the conversation for memory update
    2. Only includes user inputs and final assistant responses (ignores tool calls)
    3. The queue uses debouncing to batch multiple updates together
    4. Memory is updated asynchronously via LLM summarization
    """

    state_schema = MemoryMiddlewareState

    def __init__(self, agent_name: str | None = None):
        """Initialize the MemoryMiddleware.

        Args:
            agent_name: Optional agent name retained for logging and context.
        """
        super().__init__()
        self._agent_name = agent_name

    @override
    def after_agent(self, state: MemoryMiddlewareState, runtime: Runtime) -> dict | None:
        """Queue conversation for memory update after agent completes.

        Args:
            state: The current agent state.
            runtime: The runtime context.

        Returns:
            None (no state changes needed from this middleware).
        """
        config = get_memory_config()
        if not config.enabled:
            logger.debug("Skipping memory update because memory is disabled")
            return None

        # Get thread ID from runtime context first, then fall back to LangGraph's configurable metadata
        thread_id = runtime.context.get("thread_id") if runtime.context else None
        config_data = get_config()
        if thread_id is None:
            thread_id = config_data.get("configurable", {}).get("thread_id")
        if not thread_id:
            logger.debug("Skipping memory update because no thread_id was available in runtime/config context")
            return None

        runtime_context = _get_runtime_context(config_data)
        runtime_agent = runtime_context.get("runtime_agent", {})
        user_id = runtime_agent.get("user_id") if isinstance(runtime_agent, dict) else None
        if not isinstance(user_id, int):
            logger.debug(
                "Skipping memory update for thread %s because runtime_agent.user_id is missing or invalid: %r",
                thread_id,
                user_id,
            )
            return None

        # Get messages from state
        messages = state.get("messages", [])
        if not messages:
            logger.debug("Skipping memory update for thread %s because state.messages is empty", thread_id)
            return None

        # Filter to only keep user inputs and final assistant responses
        filtered_messages = _filter_messages_for_memory(messages)

        # Only queue if there's meaningful conversation
        # At minimum need one user message and one assistant response
        user_messages = [m for m in filtered_messages if getattr(m, "type", None) == "human"]
        assistant_messages = [m for m in filtered_messages if getattr(m, "type", None) == "ai"]

        if not user_messages or not assistant_messages:
            logger.debug(
                "Skipping memory update for thread %s after filtering: total=%d filtered=%d human=%d ai=%d",
                thread_id,
                len(messages),
                len(filtered_messages),
                len(user_messages),
                len(assistant_messages),
            )
            return None

        # Queue the filtered conversation for memory update
        correction_detected = detect_correction(filtered_messages)
        queue = get_memory_queue()
        logger.info(
            "Queueing memory update for thread %s user %s: total_messages=%d filtered_messages=%d human=%d ai=%d correction=%s agent=%s",
            thread_id,
            user_id,
            len(messages),
            len(filtered_messages),
            len(user_messages),
            len(assistant_messages),
            correction_detected,
            self._agent_name or "<default>",
        )
        queue.add(
            thread_id=thread_id,
            user_id=user_id,
            messages=filtered_messages,
            agent_name=self._agent_name,
            correction_detected=correction_detected,
        )

        return None
