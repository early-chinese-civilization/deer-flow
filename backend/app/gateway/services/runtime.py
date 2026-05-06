"""Run lifecycle service layer for the Gateway-backed LangGraph runtime."""

from __future__ import annotations

import asyncio
import copy
import json
import logging
import re
from typing import Any

from fastapi import HTTPException, Request
from langchain_core.messages import convert_to_messages

from app.gateway.db.engine import get_db_session
from app.gateway.db.models import User
from app.gateway.db.repository import AgentRepository, RuntimeManifestResolutionError, ThreadRepository
from app.gateway.deps import get_checkpointer, get_run_manager, get_store, get_stream_bridge
from app.gateway.services.ownership import ThreadAccessRecord
from app.gateway.services.thread_store import upsert_thread_record
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
_REQUEST_CONFIGURABLE_BLOCKLIST = {
    "__pregel_runtime",
    "is_bootstrap",
}
_TRUSTED_CONTEXT_KEYS = {
    "thread_id",
    "user_id",
    "external_auth_id",
    "username",
    "display_name",
    "email",
    "agent_name",
    "runtime_agent",
}


def _resolve_requested_agent_name(body: Any) -> str | None:
    """Resolve the effective agent_name from request context/configurable payloads."""

    def _normalize(raw: str) -> str:
        return raw.strip().lower().replace("_", "-")

    context = getattr(body, "context", None)
    if isinstance(context, dict):
        raw_agent_name = context.get("agent_name")
        if isinstance(raw_agent_name, str) and raw_agent_name.strip():
            return _normalize(raw_agent_name)

    request_config = getattr(body, "config", None)
    if isinstance(request_config, dict):
        request_context = request_config.get("context", {})
        if isinstance(request_context, dict):
            raw_agent_name = request_context.get("agent_name")
            if isinstance(raw_agent_name, str) and raw_agent_name.strip():
                return _normalize(raw_agent_name)
        configurable = request_config.get("configurable", {})
        if isinstance(configurable, dict):
            raw_agent_name = configurable.get("agent_name")
            if isinstance(raw_agent_name, str) and raw_agent_name.strip():
                return _normalize(raw_agent_name)

    return None


async def _load_runtime_agent_payload(*, user_id: int, agent_name: str | None) -> dict[str, Any]:
    """Load the runtime agent payload injected into config.context."""
    try:
        async with get_db_session() as db:
            bundle = await AgentRepository.get_runtime_agent_bundle(
                db,
                user_id=user_id,
                agent_name=agent_name,
            )
            await db.commit()
    except RuntimeManifestResolutionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return {
        "user_id": bundle.user_id,
        "agent_name": bundle.agent_name,
        "manifest_id": bundle.manifest_id,
        "memory": bundle.memory_json,
        "soul": bundle.soul,
        "skills": [
            {
                "name": skill.name,
                "description": skill.description,
                "file_path": skill.file_path,
                "virtual_path": skill.virtual_path,
                "skill_definition_id": skill.skill_definition_id,
                "skill_version_id": skill.skill_version_id,
                "skill_install_id": skill.skill_install_id,
                "version_number": skill.version_number,
                "content_hash": skill.content_hash,
                "artifact_uri": skill.artifact_uri,
                "source_package_version": skill.source_package_version,
            }
            for skill in bundle.skills
        ],
    }


def _get_thread_workspace_id(thread_record: Any | None) -> str | None:
    """Extract a bound workspace identifier from a DB-backed thread object."""
    if thread_record is None:
        return None
    if isinstance(thread_record, ThreadAccessRecord):
        thread_record = thread_record.thread
    if isinstance(thread_record, dict):
        raw_workspace_id = thread_record.get("workspace_id")
    else:
        raw_workspace_id = getattr(thread_record, "workspace_id", None)
    if raw_workspace_id is None:
        return None
    return str(raw_workspace_id)


async def _sync_bound_workspace_to_thread(
    *,
    thread_id: str,
    workspace_id: str | None,
) -> None:
    """No-op: workspace uploads are no longer mirrored into thread-local storage."""
    return None


async def _sync_thread_workspace_to_bound_workspace(
    *,
    thread_id: str,
    workspace_id: str | None,
) -> None:
    """No-op: workspace sync removed, files stored in OSS."""
    return None


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

    return {**raw_input, "messages": convert_to_messages(messages)}


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
            config["context"] = dict(request_config["context"])
            context_agent_name = request_config["context"].get("agent_name")
            if context_agent_name is not None and (not assistant_id or assistant_id == _DEFAULT_ASSISTANT_ID):
                configurable = config.setdefault("configurable", {})
                if "agent_name" not in configurable:
                    normalized = str(context_agent_name).strip().lower().replace("_", "-")
                    if not normalized or not re.fullmatch(r"[a-z0-9-]+", normalized):
                        raise ValueError(f"Invalid context.agent_name {context_agent_name!r}: must contain only letters, digits, and hyphens after normalization.")
                    configurable["agent_name"] = normalized
        else:
            configurable = {"thread_id": thread_id}
            client_configurable = request_config.get("configurable", {})
            configurable.update({key: value for key, value in client_configurable.items() if key not in _REQUEST_CONFIGURABLE_BLOCKLIST})
            config["configurable"] = configurable
        for key, value in request_config.items():
            if key not in ("configurable", "context"):
                config[key] = value
    else:
        config["configurable"] = {"thread_id": thread_id}

    if assistant_id and assistant_id != _DEFAULT_ASSISTANT_ID:
        configurable = config.setdefault("configurable", {})
        if "agent_name" not in configurable:
            normalized = assistant_id.strip().lower().replace("_", "-")
            if not normalized or not re.fullmatch(r"[a-z0-9-]+", normalized):
                raise ValueError(f"Invalid assistant_id {assistant_id!r}: must contain only letters, digits, and hyphens after normalization.")
            configurable["agent_name"] = normalized

    if metadata:
        config.setdefault("metadata", {}).update(metadata)
    return config


def _normalize_user_value(value: Any) -> Any:
    if value is None:
        return None
    return str(value)


def build_trusted_run_context(
    *,
    thread_id: str,
    current_user: Any | None,
) -> dict[str, Any]:
    """Build server-owned runtime context that client input cannot override."""
    context: dict[str, Any] = {"thread_id": thread_id}

    if current_user is not None:
        user_fields = {
            "user_id": getattr(current_user, "id", None),
            "external_auth_id": getattr(current_user, "external_auth_id", None),
            "username": getattr(current_user, "username", None),
            "display_name": getattr(current_user, "display_name", None),
            "email": getattr(current_user, "email", None),
        }
        context.update({key: _normalize_user_value(value) for key, value in user_fields.items() if value is not None})

    return context


def _apply_trusted_run_context(config: dict[str, Any], trusted_context: dict[str, Any]) -> None:
    """Overwrite protected runtime context keys with server-derived values."""
    context = config.setdefault("context", {})
    if not isinstance(context, dict):
        context = {}
        config["context"] = context

    for key in _TRUSTED_CONTEXT_KEYS:
        if key in trusted_context:
            context[key] = trusted_context[key]
        else:
            context.pop(key, None)

    configurable = config.setdefault("configurable", {})
    configurable["thread_id"] = trusted_context["thread_id"]


def build_public_run_config(config: dict[str, Any]) -> dict[str, Any]:
    """Strip server-owned bindings before exposing run config back to clients."""
    public_config = copy.deepcopy(config)

    context = public_config.get("context")
    if isinstance(context, dict):
        for key in _TRUSTED_CONTEXT_KEYS:
            context.pop(key, None)
        if not context:
            public_config.pop("context", None)

    configurable = public_config.get("configurable")
    if isinstance(configurable, dict):
        configurable.pop("thread_id", None)
        if not configurable:
            public_config.pop("configurable", None)

    return public_config


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
    sync_thread_metadata: bool,
    workspace_id: str | None,
) -> None:
    """Update Store-first thread metadata and the bound workspace after a run completes."""
    await asyncio.wait({run_task})

    thread_id = record.thread_id
    status = _product_thread_status(record.status)
    checkpoint_tuple = None
    title: str | None = None

    try:
        checkpoint_tuple = await checkpointer.aget_tuple({"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}})
    except Exception:
        logger.debug("Failed to load final checkpoint for thread %s", thread_id, exc_info=True)

    if checkpoint_tuple is not None:
        checkpoint = getattr(checkpoint_tuple, "checkpoint", {}) or {}
        channel_values = checkpoint.get("channel_values", {})
        raw_title = channel_values.get("title")
        if isinstance(raw_title, str) and raw_title.strip():
            title = raw_title

    if store is not None:
        try:
            update_kwargs: dict[str, Any] = {
                "thread_id": thread_id,
                "status": status,
            }
            if title is not None:
                update_kwargs["values"] = {"title": title}
                await upsert_thread_record(store=store, **update_kwargs)
        except Exception:
            logger.warning("Failed to sync Store thread metadata for %s", thread_id, exc_info=True)

    if sync_thread_metadata:
        try:
            async with get_db_session() as db:
                update_kwargs: dict[str, Any] = {
                    "db": db,
                    "thread_id": thread_id,
                    "status": status,
                }
                if title is not None:
                    update_kwargs["title"] = title
                await ThreadRepository.update_thread(**update_kwargs)
        except Exception:
            logger.warning("Failed to sync DB thread metadata for %s", thread_id, exc_info=True)

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
    thread_record: Any | None = None,
    current_user: User | None = None,
) -> RunRecord:
    """Create a RunRecord and launch the background agent task."""
    bridge = get_stream_bridge(request)
    run_mgr = get_run_manager(request)
    checkpointer = get_checkpointer(request)
    store = get_store(request)
    sync_thread_metadata = thread_record is not None
    workspace_id = _get_thread_workspace_id(thread_record)

    disconnect = DisconnectMode.cancel if body.on_disconnect == "cancel" else DisconnectMode.continue_

    try:
        config = build_run_config(
            thread_id,
            body.config,
            body.metadata,
            assistant_id=body.assistant_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    context = getattr(body, "context", None)
    if context:
        configurable = config.setdefault("configurable", {})
        for key in _CONTEXT_CONFIGURABLE_KEYS:
            if key in context:
                configurable.setdefault(key, context[key])
        context_agent_name = context.get("agent_name")
        if context_agent_name is not None and (not body.assistant_id or body.assistant_id == _DEFAULT_ASSISTANT_ID):
            if "agent_name" not in configurable:
                normalized = str(context_agent_name).strip().lower().replace("_", "-")
                if not normalized or not re.fullmatch(r"[a-z0-9-]+", normalized):
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid context.agent_name {context_agent_name!r}: must contain only letters, digits, and hyphens after normalization.",
                    )
                configurable["agent_name"] = normalized

    trusted_context = build_trusted_run_context(
        thread_id=thread_id,
        current_user=current_user,
    )
    _apply_trusted_run_context(config, trusted_context)
    public_config = build_public_run_config(config)
    resolved_agent_name = config.get("configurable", {}).get("agent_name")
    thread_metadata = dict(body.metadata or {})
    if isinstance(resolved_agent_name, str) and resolved_agent_name.strip():
        thread_metadata.setdefault("agent_name", resolved_agent_name)

    try:
        record = await run_mgr.create_or_reject(
            thread_id,
            body.assistant_id,
            on_disconnect=disconnect,
            metadata=body.metadata or {},
            kwargs={"input": body.input, "config": public_config},
            multitask_strategy=body.multitask_strategy,
        )
    except ConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except UnsupportedStrategyError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc

    if sync_thread_metadata:
        if store is not None:
            try:
                await upsert_thread_record(
                    store=store,
                    thread_id=thread_id,
                    status="busy",
                    metadata=thread_metadata or None,
                )
            except Exception:
                logger.warning("Failed to mark Store thread %s busy", thread_id, exc_info=True)
        try:
            async with get_db_session() as db:
                resolved_agent_id: int | None = None
                if isinstance(resolved_agent_name, str) and resolved_agent_name.strip() and current_user is not None and getattr(current_user, "id", None) is not None:
                    agent = await AgentRepository.get_agent_by_name(
                        db,
                        user_id=current_user.id,
                        name=resolved_agent_name,
                    )
                    if agent is not None:
                        resolved_agent_id = agent.id

                update_kwargs: dict[str, Any] = {
                    "db": db,
                    "thread_id": thread_id,
                    "status": "busy",
                }
                if resolved_agent_id is not None:
                    update_kwargs["agent_id"] = resolved_agent_id
                if thread_metadata:
                    update_kwargs["metadata"] = thread_metadata
                await ThreadRepository.update_thread(**update_kwargs)
        except Exception:
            logger.warning("Failed to mark DB thread %s busy", thread_id, exc_info=True)

    try:
        await _sync_bound_workspace_to_thread(
            thread_id=thread_id,
            workspace_id=workspace_id,
        )
        if workspace_id:
            logger.debug("Workspace pre-run sync is a no-op for thread %s", thread_id)
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

    resolved_agent_name = _resolve_requested_agent_name(body)
    configurable = config.setdefault("configurable", {})
    configurable.setdefault("thread_id", thread_id)
    if resolved_agent_name:
        configurable.setdefault("agent_name", resolved_agent_name)
    if workspace_id is not None:
        configurable.setdefault("workspace_id", workspace_id)

    _apply_trusted_run_context(config, trusted_context)
    runtime_context = config.setdefault("context", {})
    runtime_context.setdefault("thread_id", thread_id)
    if workspace_id is not None:
        runtime_context.setdefault("workspace_id", workspace_id)
    runtime_context["runtime_agent"] = await _load_runtime_agent_payload(
        user_id=current_user.id,
        agent_name=resolved_agent_name,
    )

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
            sync_thread_metadata=sync_thread_metadata,
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
