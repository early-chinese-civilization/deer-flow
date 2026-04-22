"""Memory update queue with debounce mechanism."""

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from deerflow.config.memory_config import get_memory_config

logger = logging.getLogger(__name__)


@dataclass
class ConversationContext:
    """Context for a conversation to be processed for memory update."""

    thread_id: str
    user_id: int | None
    messages: list[Any]
    timestamp: datetime = field(default_factory=datetime.utcnow)
    agent_name: str | None = None
    correction_detected: bool = False


class MemoryUpdateQueue:
    """Queue for memory updates with debounce mechanism.

    This queue collects conversation contexts and processes them after
    a configurable debounce period. Multiple conversations received within
    the debounce window are batched together.
    """

    def __init__(self):
        """Initialize the memory update queue."""
        self._queue: list[ConversationContext] = []
        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None
        self._processing = False

    def add(
        self,
        thread_id: str,
        user_id: int | None,
        messages: list[Any],
        agent_name: str | None = None,
        correction_detected: bool = False,
    ) -> None:
        """Add a conversation to the update queue.

        Args:
            thread_id: The thread ID.
            messages: The conversation messages.
            agent_name: If provided, memory is stored per-agent. If None, uses global memory.
            correction_detected: Whether recent turns include an explicit correction signal.
        """
        config = get_memory_config()
        if not config.enabled:
            logger.debug("Skipping queue add for thread %s because memory is disabled", thread_id)
            return

        with self._lock:
            existing_context = next(
                (context for context in self._queue if context.thread_id == thread_id),
                None,
            )
            merged_correction_detected = correction_detected or (existing_context.correction_detected if existing_context is not None else False)
            context = ConversationContext(
                thread_id=thread_id,
                user_id=user_id,
                messages=messages,
                agent_name=agent_name,
                correction_detected=merged_correction_detected,
            )

            # Check if this thread already has a pending update
            # If so, replace it with the newer one
            replaced_existing = existing_context is not None
            self._queue = [c for c in self._queue if c.thread_id != thread_id]
            self._queue.append(context)
            queue_size = len(self._queue)

            # Reset or start the debounce timer
            self._reset_timer()

        logger.info(
            "Memory update queued for thread %s user %s: queue_size=%d replaced_existing=%s messages=%d correction=%s agent=%s",
            thread_id,
            user_id,
            queue_size,
            replaced_existing,
            len(messages),
            merged_correction_detected,
            agent_name or "<default>",
        )

    def _reset_timer(self) -> None:
        """Reset the debounce timer."""
        config = get_memory_config()

        # Cancel existing timer if any
        if self._timer is not None:
            self._timer.cancel()

        # Start new timer
        self._timer = threading.Timer(
            config.debounce_seconds,
            self._process_queue,
        )
        self._timer.daemon = True
        self._timer.start()

        logger.info("Memory update timer reset: debounce=%ss pending=%d", config.debounce_seconds, len(self._queue))

    def _process_queue(self) -> None:
        """Process all queued conversation contexts."""
        # Import here to avoid circular dependency
        from deerflow.agents.memory.updater import MemoryUpdater

        with self._lock:
            if self._processing:
                # Already processing, reschedule
                logger.info("Memory queue already processing; rescheduling pending updates")
                self._reset_timer()
                return

            if not self._queue:
                logger.debug("Memory queue processing skipped because queue is empty")
                return

            self._processing = True
            contexts_to_process = self._queue.copy()
            self._queue.clear()
            self._timer = None

        logger.info("Processing %d queued memory updates", len(contexts_to_process))

        try:
            updater = MemoryUpdater()

            for context in contexts_to_process:
                try:
                    logger.info(
                        "Updating memory for thread %s user %s: messages=%d correction=%s agent=%s",
                        context.thread_id,
                        context.user_id,
                        len(context.messages),
                        context.correction_detected,
                        context.agent_name or "<default>",
                    )
                    success = updater.update_memory(
                        messages=context.messages,
                        thread_id=context.thread_id,
                        user_id=context.user_id,
                        agent_name=context.agent_name,
                        correction_detected=context.correction_detected,
                    )
                    if success:
                        logger.info("Memory updated successfully for thread %s user %s", context.thread_id, context.user_id)
                    else:
                        logger.warning("Memory update skipped or failed for thread %s user %s", context.thread_id, context.user_id)
                except Exception as e:
                    logger.exception("Error updating memory for thread %s user %s: %s", context.thread_id, context.user_id, e)

                # Small delay between updates to avoid rate limiting
                if len(contexts_to_process) > 1:
                    time.sleep(0.5)

        finally:
            with self._lock:
                self._processing = False

    def flush(self) -> None:
        """Force immediate processing of the queue.

        This is useful for testing or graceful shutdown.
        """
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None

        logger.info("Flushing memory update queue")
        self._process_queue()

    def clear(self) -> None:
        """Clear the queue without processing.

        This is useful for testing.
        """
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            self._queue.clear()
            self._processing = False
        logger.info("Cleared memory update queue")

    @property
    def pending_count(self) -> int:
        """Get the number of pending updates."""
        with self._lock:
            return len(self._queue)

    @property
    def is_processing(self) -> bool:
        """Check if the queue is currently being processed."""
        with self._lock:
            return self._processing


# Global singleton instance
_memory_queue: MemoryUpdateQueue | None = None
_queue_lock = threading.Lock()


def get_memory_queue() -> MemoryUpdateQueue:
    """Get the global memory update queue singleton.

    Returns:
        The memory update queue instance.
    """
    global _memory_queue
    with _queue_lock:
        if _memory_queue is None:
            _memory_queue = MemoryUpdateQueue()
        return _memory_queue


def reset_memory_queue() -> None:
    """Reset the global memory queue.

    This is useful for testing.
    """
    global _memory_queue
    with _queue_lock:
        if _memory_queue is not None:
            _memory_queue.clear()
        _memory_queue = None
