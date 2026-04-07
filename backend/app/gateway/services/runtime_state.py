"""Helpers for runtime-state backend availability handling."""

from __future__ import annotations

from fastapi import HTTPException
from psycopg import OperationalError

RUNTIME_STATE_UNAVAILABLE_DETAIL = "Runtime state service unavailable"


def is_runtime_state_unavailable(exc: Exception) -> bool:
    """Return whether an error indicates the checkpointer backend is unavailable."""
    if isinstance(exc, OperationalError):
        return True

    message = str(exc).lower()
    return (
        "connection is closed" in message
        or "closed connection" in message
        or "connection closed" in message
    )


def to_runtime_state_http_exception(exc: Exception) -> HTTPException:
    """Map backend availability failures to a stable API-facing 503."""
    if not is_runtime_state_unavailable(exc):
        raise ValueError("Exception is not a runtime-state availability error")
    return HTTPException(status_code=503, detail=RUNTIME_STATE_UNAVAILABLE_DETAIL)
