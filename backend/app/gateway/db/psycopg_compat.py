"""Helpers for running psycopg-backed async code on Windows."""

from __future__ import annotations

import asyncio
import selectors
import sys
from collections.abc import Coroutine
from typing import Any


def ensure_windows_selector_event_loop_policy() -> None:
    """Switch Windows to SelectorEventLoopPolicy when psycopg needs it."""
    if sys.platform != "win32":
        return

    proactor_policy = getattr(asyncio, "WindowsProactorEventLoopPolicy", None)
    selector_policy = getattr(asyncio, "WindowsSelectorEventLoopPolicy", None)
    if proactor_policy is None or selector_policy is None:
        return

    if isinstance(asyncio.get_event_loop_policy(), proactor_policy):
        asyncio.set_event_loop_policy(selector_policy())


def _selector_loop_factory():
    """Create a selector-based loop compatible with psycopg on Windows."""
    return asyncio.SelectorEventLoop(selectors.SelectSelector())


def run_async_with_psycopg_compatible_loop(main: Coroutine[Any, Any, Any]) -> Any:
    """Run async work using a SelectorEventLoop on Windows.

    Alembic and other short-lived async entrypoints create their own event loop,
    so they do not benefit from the runtime patches used by the long-lived app.
    """
    if sys.platform != "win32":
        return asyncio.run(main)

    ensure_windows_selector_event_loop_policy()
    return asyncio.run(main, loop_factory=_selector_loop_factory)
