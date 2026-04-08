"""Run lifecycle service layer for the Gateway-backed LangGraph runtime."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from typing import Any

from fastapi import HTTPException, Request
from langchain_core.messages import HumanMessage

from app.gateway.db.engine import get_db_session
from app.gateway.deps import get_checkpointer, get_run_manager, get_store, get_stream_bridge
from app.gateway.services.thread_store import (
    StoreUnavailableError,
    ThreadRecord,
    get_workspace_id,
    upsert_thread_record,
)
from app.gateway.services.workspace_sync import sync_canonical_to_thread, sync_thread_to_canonical
from deerflow.config.paths import get_paths
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

_DEFAULT_ASSISTANT_ID = "lead_agent"
_CONTEXT_CONFIGURABLE_KEYS = {
    "model_name",
    "mode",
    "thinking_enabled",
    "reasoning_effort",
    "is_plan_mode",
    "subagent_enabled",
    "max_concurrent_subagents",
}


def _coerce_workspace_uuid(workspace_id: str | None) -> uuid.UUID | None:
    """Parse a stored workspace identifier into a UUID."""
    if not workspace_id:
        return None

    try:
        return uuid.UUID(workspace_id)
    except ValueError:
        logger.warning("Skipping invalid workspace_id %s in thread metadata", workspace_id)
        return None


async def _sync_bound_workspace_to_thread(
    *,
    thread_id: str,
    workspace_id: str | None,
) -> None:
    """Project the canonical workspace into the thread workspace before a run."""
    workspace_uuid = _coerce_workspace_uuid(workspace_id)
    if workspace_uuid is None:
        return

    async with get_db_session() as db:
        thread_workspace_path = get_paths().sandbox_work_dir(thread_id)
        await sync_canonical_to_thread(db, workspace_uuid, thread_workspace_path)


async def _sync_thread_workspace_to_bound_workspace(
    *,
    thread_id: str,
    workspace_id: str | None,
) -> None:
    """Persist the thread workspace back into the canonical workspace after a run."""
    workspace_uuid = _coerce_workspace_uuid(workspace_id)
    if workspace_uuid is None:
        return

    async with get_db_session() as db:
        thread_workspace_path = get_paths().sandbox_work_dir(thread_id)
        await sync_thread_to_canonical(db, workspace_uuid, thread_workspace_path)


def format_sse(event: str, data: Any, *, event_id: str | None = None) -> str:
    """Format a single SSE frame in LangGraph-compatible wire format."""
    payload = json.dumps(data, default=str, ensure_ascii=False)
    parts = [f"event: {event}", f"data: {payload}"]
    if event_id:
        parts.append(f"id: {event_id}")
    parts.append("")
    parts.append("")
    return "\n".join(parts)


def normalize_stream_modes(raw: list[str] | str | None) -> list[str]:
    """Normalize the stream_mode parameter to a list."""
    if raw is None:
        return ["values"]
    if isinstance(raw, str):
        return [raw]
    return raw if raw else ["values"]


def normalize_input(raw_input: dict[str, Any] | None) -> dict[str, Any]:
    """Convert LangGraph Platform input format to a LangChain state dict."""
    if raw_input is None:
        return {}

    messages = raw_input.get("messages")
    if not messages or not isinstance(messages, list):
        return raw_input

    converted = []
    for message in messages:
        if isinstance(message, dict):
            role = message.get("role", message.get("type", "user"))
            content = message.get("content", "")
            if role in ("user", "human"):
                converted.append(HumanMessage(content=content))
            else:
                converted.append(HumanMessage(content=content))
            continue
        converted.append(message)

    return {**raw_input, "messages": converted}


def resolve_agent_factory(assistant_id: str | None):
    """Resolve the agent factory callable from config."""
    from deerflow.agents.lead_agent.agent import make_lead_agent

    return make_lead_agent


def build_run_config(
    thread_id: str,
    request_config: dict[str, Any] | None,
    metadata: dict[str, Any] | None,
    *,
    assistant_id: str | None = None,
) -> dict[str, Any]:
    """Build the runnable config passed into the agent graph."""
    config: dict[str, Any] = {"recursion_limit": 100}
    if request_config:
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


def _product_thread_status(run_status: RunStatus) -> str:
    """Map run-manager lifecycle states onto product thread statuses."""
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
    *,
    sync_store_metadata: bool,
    workspace_id: str | None,
) -> None:
    """Update Store metadata and bound workspace after a run completes."""
    await asyncio.wait({run_task})

    thread_id = record.thread_id
    status = _product_thread_status(record.status)
    checkpoint_tuple = None
    title: str | None = None

    try:
        checkpoint_tuple = await checkpointer.aget_tuple(
            {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
        )
    except Exception:
        logger.debug("Failed to load final checkpoint for thread %s", thread_id, exc_info=True)

    if checkpoint_tuple is not None:
        checkpoint = getattr(checkpoint_tuple, "checkpoint", {}) or {}
        channel_values = checkpoint.get("channel_values", {})
        raw_title = channel_values.get("title")
        if isinstance(raw_title, str) and raw_title.strip():
            title = raw_title

    if sync_store_metadata and store is not None:
        try:
            values = {"title": title} if title else None
            await upsert_thread_record(
                store,
                thread_id,
                status=status,
                values=values,
            )
        except StoreUnavailableError:
            logger.warning("Store unavailable while syncing completed thread %s", thread_id)
        except Exception:
            logger.debug("Failed to sync store metadata for thread %s", thread_id, exc_info=True)

    try:
        await _sync_thread_workspace_to_bound_workspace(
            thread_id=thread_id,
            workspace_id=workspace_id,
        )
    except Exception:
        logger.warning("Failed to sync workspace after run for thread %s", thread_id, exc_info=True)


async def start_run(
    body: Any,
    thread_id: str,
    request: Request,
    *,
    thread_record: ThreadRecord | None = None,
) -> RunRecord:
    """Create a RunRecord and launch the background agent task."""
    bridge = get_stream_bridge(request)
    run_mgr = get_run_manager(request)
    checkpointer = get_checkpointer(request)
    store = get_store(request)
    sync_store_metadata = thread_record is not None
    workspace_id = get_workspace_id(thread_record)

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

    if sync_store_metadata and store is not None:
        try:
            await upsert_thread_record(
                store,
                thread_id,
                status="busy",
                metadata=body.metadata,
            )
        except StoreUnavailableError:
            logger.warning("Store unavailable while marking thread %s busy", thread_id)
        except Exception:
            logger.debug("Failed to mark thread %s busy in store", thread_id, exc_info=True)

    try:
        await _sync_bound_workspace_to_thread(
            thread_id=thread_id,
            workspace_id=workspace_id,
        )
        if workspace_id:
            logger.debug("Synced canonical workspace to thread for thread %s", thread_id)
    except Exception:
        logger.warning("Failed to sync workspace before run for thread %s", thread_id, exc_info=True)

    agent_factory = resolve_agent_factory(body.assistant_id)
    graph_input = normalize_input(body.input)
    config = build_run_config(
        thread_id,
        body.config,
        body.metadata,
        assistant_id=body.assistant_id,
    )

    context = getattr(body, "context", None)
    if context:
        configurable = config.setdefault("configurable", {})
        for key in _CONTEXT_CONFIGURABLE_KEYS:
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

    asyncio.create_task(
        _sync_thread_product_state_after_run(
            task,
            record,
            checkpointer,
            store,
            sync_store_metadata=sync_store_metadata,
            workspace_id=workspace_id,
        )
    )
    return record


async def sse_consumer(
    bridge: StreamBridge,
    record: RunRecord,
    request: Request,
    run_mgr: RunManager,
):
    """Yield SSE frames from the bridge until the run completes."""
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

            yield format_sse(entry.event, entry.data, event_id=entry.id or None)
    finally:
        if record.status in (RunStatus.pending, RunStatus.running) and record.on_disconnect == DisconnectMode.cancel:
            await run_mgr.cancel(record.run_id)
