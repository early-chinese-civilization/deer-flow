"""Middleware for preserving canonical OSS references before the model call."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, override

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import BaseMessage
from langgraph.runtime import Runtime

_OSS_URI_RE = re.compile(r"oss://[^\s<>'\")]+")


class FileReferenceMiddlewareState(AgentState):
    """Compatible with the `ThreadState` schema."""


def _presign_oss_uri(oss_uri: str) -> str:
    return oss_uri


def _strip_trailing_punctuation(uri: str) -> tuple[str, str]:
    suffix = ""
    while uri and uri[-1] in ".,;:!?)]}":
        suffix = uri[-1] + suffix
        uri = uri[:-1]
    return uri, suffix


def _rewrite_text(text: str) -> str:
    def _replace(match: re.Match[str]) -> str:
        uri, suffix = _strip_trailing_punctuation(match.group(0))
        return _presign_oss_uri(uri) + suffix

    return _OSS_URI_RE.sub(_replace, text)


def _rewrite_content(content: Any) -> Any:
    if isinstance(content, str):
        return _rewrite_text(content)
    if isinstance(content, list):
        return [_rewrite_content(item) for item in content]
    if isinstance(content, dict):
        return {key: _rewrite_content(value) for key, value in content.items()}
    return content


def _rewrite_text_with_artifacts(text: str, artifacts: Mapping[str, str]) -> str:
    rewritten = text
    for virtual_path, oss_uri in sorted(artifacts.items(), key=lambda item: len(item[0]), reverse=True):
        if isinstance(virtual_path, str) and isinstance(oss_uri, str) and virtual_path and oss_uri:
            rewritten = rewritten.replace(virtual_path, oss_uri)
    return rewritten


def _rewrite_content_with_artifacts(content: Any, artifacts: Mapping[str, str]) -> Any:
    if isinstance(content, str):
        return _rewrite_text_with_artifacts(content, artifacts)
    if isinstance(content, list):
        return [_rewrite_content_with_artifacts(item, artifacts) for item in content]
    if isinstance(content, dict):
        return {key: _rewrite_content_with_artifacts(value, artifacts) for key, value in content.items()}
    return content


class FileReferenceMiddleware(AgentMiddleware[FileReferenceMiddlewareState]):
    """Keep oss:// references intact for downstream runtime resolution."""

    state_schema = FileReferenceMiddlewareState

    def _rewrite_messages(self, state: FileReferenceMiddlewareState) -> dict[str, list[BaseMessage]] | None:
        messages = list(state.get("messages", []))
        if not messages:
            return None

        rewritten: list[BaseMessage] = []
        changed = False
        for message in messages:
            new_content = _rewrite_content(message.content)
            if new_content != message.content:
                changed = True
                message = message.model_copy(update={"content": new_content})
            rewritten.append(message)

        if not changed:
            return None

        return {"messages": rewritten}

    def _rewrite_messages_with_artifacts(self, state: FileReferenceMiddlewareState) -> dict[str, list[BaseMessage]] | None:
        artifacts = state.get("artifacts")
        if not isinstance(artifacts, Mapping) or not artifacts:
            return None

        messages = list(state.get("messages", []))
        if not messages:
            return None

        rewritten: list[BaseMessage] = []
        changed = False
        for message in messages:
            if getattr(message, "type", None) != "ai":
                rewritten.append(message)
                continue

            new_content = _rewrite_content_with_artifacts(message.content, artifacts)
            if new_content != message.content:
                changed = True
                message = message.model_copy(update={"content": new_content})
            rewritten.append(message)

        if not changed:
            return None

        return {"messages": rewritten}

    @override
    def before_model(self, state: FileReferenceMiddlewareState, runtime: Runtime) -> dict[str, list[BaseMessage]] | None:
        return self._rewrite_messages(state)

    @override
    async def abefore_model(self, state: FileReferenceMiddlewareState, runtime: Runtime) -> dict[str, list[BaseMessage]] | None:
        return self._rewrite_messages(state)

    @override
    def after_model(self, state: FileReferenceMiddlewareState, runtime: Runtime) -> dict[str, list[BaseMessage]] | None:
        return self._rewrite_messages_with_artifacts(state)

    @override
    async def aafter_model(self, state: FileReferenceMiddlewareState, runtime: Runtime) -> dict[str, list[BaseMessage]] | None:
        return self._rewrite_messages_with_artifacts(state)
