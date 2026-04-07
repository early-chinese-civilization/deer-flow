"""Run lifecycle service layer.

Centralizes the business logic for creating runs, formatting SSE
frames, and consuming stream bridge events.  Router modules
(``thread_runs``, ``runs``) are thin HTTP handlers that delegate here.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any

from fastapi import HTTPException, Request
from langchain_core.messages import HumanMessage

from app.gateway.db.engine import get_db_session
from app.gateway.db.repository import ChatRepository
from app.gateway.deps import get_checkpointer, get_run_manager, get_store, get_stream_bridge
from app.gateway.services.projection import ProjectionService
from deerflow.runtime import (
    END_SENTINEL,
    HEARTBEAT_SENTINEL,
    ConflictError,
    DisconnectMode,
    RunManager,
    RunRecord,
    RunStatus,
    StreamBridge,
    UnsupportedStrategyError,
    run_agent,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SSE formatting
# ---------------------------------------------------------------------------


def format_sse(event: str, data: Any, *, event_id: str | None = None) -> str:
    """Format a single SSE frame.

    Field order: ``event:`` -> ``data:`` -> ``id:`` (optional) -> blank line.
    This matches the LangGraph Platform wire format consumed by the
    ``useStream`` React hook and the Python ``langgraph-sdk`` SSE decoder.
    """
    payload = json.dumps(data, default=str, ensure_ascii=False)
    parts = [f"event: {event}", f"data: {payload}"]
    if event_id:
        parts.append(f"id: {event_id}")
    parts.append("")
    parts.append("")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Input / config helpers
# ---------------------------------------------------------------------------


def normalize_stream_modes(raw: list[str] | str | None) -> list[str]:
    """Normalize the stream_mode parameter to a list."""
    if raw is None:
        return ["values"]
    if isinstance(raw, str):
        return [raw]
    return raw if raw else ["values"]


def normalize_input(raw_input: dict[str, Any] | None) -> dict[str, Any]:
    """Convert LangGraph Platform input format to LangChain state dict."""
    if raw_input is None:
        return {}
    messages = raw_input.get("messages")
    if messages and isinstance(messages, list):
        converted = []
        for msg in messages:
            if isinstance(msg, dict):
                role = msg.get("role", msg.get("type", "user"))
                content = msg.get("content", "")
                if role in ("user", "human"):
                    converted.append(HumanMessage(content=content))
                else:
                    # TODO: handle other message types (system, ai, tool)
                    converted.append(HumanMessage(content=content))
            else:
                converted.append(msg)
        return {**raw_input, "messages": converted}
    return raw_input


_DEFAULT_ASSISTANT_ID = "lead_agent"


def resolve_agent_factory(assistant_id: str | None):
    """Resolve the agent factory callable from config.

    Custom agents are implemented as ``lead_agent`` + an ``agent_name``
    injected into ``configurable`` — see :func:`build_run_config`.  All
    ``assistant_id`` values therefore map to the same factory; the routing
    happens inside ``make_lead_agent`` when it reads ``cfg["agent_name"]``.
    """
    from deerflow.agents.lead_agent.agent import make_lead_agent

    return make_lead_agent


def build_run_config(
    thread_id: str,
    request_config: dict[str, Any] | None,
    metadata: dict[str, Any] | None,
    *,
    assistant_id: str | None = None,
) -> dict[str, Any]:
    """Build a RunnableConfig dict for the agent.

    When *assistant_id* refers to a custom agent (anything other than
    ``"lead_agent"`` / ``None``), the name is forwarded as
    ``configurable["agent_name"]``.  ``make_lead_agent`` reads this key to
    load the matching ``agents/<name>/SOUL.md`` and per-agent config —
    without it the agent silently runs as the default lead agent.

    This mirrors the channel manager's ``_resolve_run_params`` logic so that
    the LangGraph Platform-compatible HTTP API and the IM channel path behave
    identically.
    """
    config: dict[str, Any] = {"recursion_limit": 100}
    if request_config:
        # LangGraph >= 0.6.0 introduced ``context`` as the preferred way to
        # pass thread-level data and rejects requests that include both
        # ``configurable`` and ``context``.  If the caller already sends
        # ``context``, honour it and skip our own ``configurable`` dict.
        if "context" in request_config:
            if "configurable" in request_config:
                logger.warning(
                    "build_run_config: client sent both 'context' and 'configurable'; preferring 'context' (LangGraph >= 0.6.0). thread_id=%s, caller_configurable keys=%s",
                    thread_id,
                    list(request_config.get("configurable", {}).keys()),
                )
            config["context"] = request_config["context"]
        else:
            configurable = {"thread_id": thread_id}
            configurable.update(request_config.get("configurable", {}))
            config["configurable"] = configurable
        for key, value in request_config.items():
            if key not in ("configurable", "context"):
                config[key] = value
    else:
        config["configurable"] = {"thread_id": thread_id}

    # Inject custom agent name when the caller specified a non-default assistant.
    # Honour an explicit configurable["agent_name"] in the request if already set.
    if assistant_id and assistant_id != _DEFAULT_ASSISTANT_ID and "configurable" in config:
        if "agent_name" not in config["configurable"]:
            normalized = assistant_id.strip().lower().replace("_", "-")
            if not normalized or not re.fullmatch(r"[a-z0-9-]+", normalized):
                raise ValueError(
                    f"Invalid assistant_id {assistant_id!r}: must contain only letters, digits, and hyphens after normalization."
                )
            config["configurable"]["agent_name"] = normalized
    if metadata:
        config.setdefault("metadata", {}).update(metadata)
    return config


# ---------------------------------------------------------------------------
# Run lifecycle
# ---------------------------------------------------------------------------


async def _upsert_thread_in_store(store, thread_id: str, metadata: dict | None) -> None:
    """Create or refresh the thread record in the Store.

    Called from :func:`start_run` so that threads created via the stateless
    ``/runs/stream`` endpoint (which never calls ``POST /threads``) still
    appear in ``/threads/search`` results.
    """
    # Deferred import to avoid circular import with the threads router module.
    from app.gateway.routers.threads import _store_upsert

    try:
        await _store_upsert(store, thread_id, metadata=metadata)
    except Exception:
        logger.warning("Failed to upsert thread %s in store (non-fatal)", thread_id)


async def mirror_stream_event_messages(
    *,
    thread_id: str,
    event: str,
    data: Any,
    checkpoint_id: str | None = None,
) -> dict[str, Any]:
    """Project a single SSE event using the unified projection service.

    Each mirror attempt uses its own session so the SSE consumer never shares an
    ``AsyncSession`` across concurrent events or long-lived stream handling.
    """
    if event != "values":
        return {"projected": False, "reason": "not_values_event"}

    async with get_db_session() as db:
        return await ProjectionService.project_from_stream_event(
            db=db,
            thread_id=thread_id,
            event=event,
            data=data,
            checkpoint_id=checkpoint_id,
        )


def _product_thread_status(run_status: RunStatus) -> str:
    """Map run-manager lifecycle states onto product chat statuses."""
    if run_status in (RunStatus.pending, RunStatus.running):
        return "busy"
    if run_status == RunStatus.interrupted:
        return "interrupted"
    if run_status == RunStatus.success:
        return "idle"
    return "error"


async def _sync_thread_product_state_after_run(
    run_task: asyncio.Task,
    record: RunRecord,
    checkpointer: Any,
    store: Any,
) -> None:
    """Project final runtime state into product tables after a run completes."""
    await asyncio.wait({run_task})

    from app.gateway.routers.threads import _store_get, _store_put

    thread_id = record.thread_id
    status = _product_thread_status(record.status)
    checkpoint_tuple = None

    try:
        ckpt_config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
        checkpoint_tuple = await checkpointer.aget_tuple(ckpt_config)
    except Exception:
        logger.debug("Failed to load final checkpoint for thread %s", thread_id, exc_info=True)

    try:
        async with get_db_session() as db:
            if checkpoint_tuple is not None:
                result = await ProjectionService.project_from_checkpoint(
                    db=db,
                    thread_id=thread_id,
                    checkpoint_tuple=checkpoint_tuple,
                )
                if not result.get("projected"):
                    logger.debug(
                        "Post-run projection skipped for thread %s: %s",
                        thread_id,
                        result.get("reason"),
                    )
            await ChatRepository.update_chat(db, thread_id, status=status)
    except Exception:
        logger.debug("Failed to sync product projection for thread %s", thread_id, exc_info=True)

    if store is None:
        return

    try:
        existing = await _store_get(store, thread_id)
        if existing is None:
            return

        updated = dict(existing)
        updated["status"] = status
        updated["updated_at"] = time.time()

        checkpoint = getattr(checkpoint_tuple, "checkpoint", {}) or {}
        channel_values = checkpoint.get("channel_values", {})
        title = channel_values.get("title")
        if isinstance(title, str) and title.strip():
            updated.setdefault("values", {})["title"] = title

        await _store_put(store, updated)
    except Exception:
        logger.debug("Failed to sync store projection for thread %s", thread_id, exc_info=True)


async def start_run(
    body: Any,
    thread_id: str,
    request: Request,
) -> RunRecord:
    """Create a RunRecord and launch the background agent task.

    Parameters
    ----------
    body : RunCreateRequest
        The validated request body (typed as Any to avoid circular import
        with the router module that defines the Pydantic model).
    thread_id : str
        Target thread.
    request : Request
        FastAPI request — used to retrieve singletons from ``app.state``.
    """
    bridge = get_stream_bridge(request)
    run_mgr = get_run_manager(request)
    checkpointer = get_checkpointer(request)
    store = get_store(request)

    disconnect = DisconnectMode.cancel if body.on_disconnect == "cancel" else DisconnectMode.continue_

    try:
        record = await run_mgr.create_or_reject(
            thread_id,
            body.assistant_id,
            on_disconnect=disconnect,
            metadata=body.metadata or {},
            kwargs={"input": body.input, "config": body.config},
            multitask_strategy=body.multitask_strategy,
        )
    except ConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except UnsupportedStrategyError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc

    try:
        async with get_db_session() as db:
            await ChatRepository.update_chat(db, thread_id, status="busy")
    except Exception:
        logger.debug("Failed to mark thread %s as busy", thread_id, exc_info=True)

    # Ensure the thread is visible in /threads/search, even for threads that
    # were never explicitly created via POST /threads (e.g. stateless runs).
    if store is not None:
        await _upsert_thread_in_store(store, thread_id, body.metadata)

    agent_factory = resolve_agent_factory(body.assistant_id)
    graph_input = normalize_input(body.input)
    config = build_run_config(thread_id, body.config, body.metadata, assistant_id=body.assistant_id)

    # Merge DeerFlow-specific context overrides into configurable.
    # The ``context`` field is a custom extension for the langgraph-compat layer
    # that carries agent configuration (model_name, thinking_enabled, etc.).
    # Only agent-relevant keys are forwarded; unknown keys (e.g. thread_id) are ignored.
    context = getattr(body, "context", None)
    if context:
        context_configurable_keys = {
            "model_name",
            "mode",
            "thinking_enabled",
            "reasoning_effort",
            "is_plan_mode",
            "subagent_enabled",
            "max_concurrent_subagents",
        }
        configurable = config.setdefault("configurable", {})
        for key in context_configurable_keys:
            if key in context:
                configurable.setdefault(key, context[key])

    stream_modes = normalize_stream_modes(body.stream_mode)

    task = asyncio.create_task(
        run_agent(
            bridge,
            run_mgr,
            record,
            checkpointer=checkpointer,
            store=store,
            agent_factory=agent_factory,
            graph_input=graph_input,
            config=config,
            stream_modes=stream_modes,
            stream_subgraphs=body.stream_subgraphs,
            interrupt_before=body.interrupt_before,
            interrupt_after=body.interrupt_after,
        )
    )
    record.task = task

    asyncio.create_task(_sync_thread_product_state_after_run(task, record, checkpointer, store))
    return record


async def sse_consumer(
    bridge: StreamBridge,
    record: RunRecord,
    request: Request,
    run_mgr: RunManager,
):
    """Async generator that yields SSE frames from the bridge.

    The ``finally`` block implements ``on_disconnect`` semantics:
    - ``cancel``: abort the background task on client disconnect.
    - ``continue``: let the task run; events are discarded.

    Also mirrors user-visible messages to the database.
    """
    try:
        async for entry in bridge.subscribe(record.run_id):
            if await request.is_disconnected():
                break

            if entry is HEARTBEAT_SENTINEL:
                yield ": heartbeat\n\n"
                continue

            if entry is END_SENTINEL:
                yield format_sse("end", None, event_id=entry.id or None)
                return

            # Mirror only the latest ``values.messages`` snapshot. Partial
            # chunk events are not the product source of truth.
            if entry.event == "values":
                try:
                    checkpoint_id = None
                    if hasattr(entry, "metadata") and isinstance(entry.metadata, dict):
                        checkpoint_id = entry.metadata.get("checkpoint_id")

                    result = await mirror_stream_event_messages(
                        thread_id=record.thread_id,
                        event=entry.event,
                        data=entry.data,
                        checkpoint_id=checkpoint_id,
                    )
                    if not result.get("projected"):
                        logger.debug(
                            "Projection skipped for thread %s: %s",
                            record.thread_id,
                            result.get("reason"),
                        )
                except Exception:
                    logger.debug("Projection failed (non-fatal)", exc_info=True)

            yield format_sse(entry.event, entry.data, event_id=entry.id or None)
    finally:
        if record.status in (RunStatus.pending, RunStatus.running):
            if record.on_disconnect == DisconnectMode.cancel:
                await run_mgr.cancel(record.run_id)
