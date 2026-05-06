#!/usr/bin/env python3
"""Windows-compatible LangGraph launcher.

Monkey patches asyncio.run() to force SelectorEventLoop on Windows for psycopg compatibility.
"""

import sys

if sys.platform == "win32":
    import asyncio
    import selectors
    from collections.abc import Coroutine
    from typing import Any

    def _patched_run(main: Coroutine, *, debug: bool = False, loop_factory=None) -> Any:  # noqa: ARG001
        """Patched asyncio.run that uses SelectorEventLoop on Windows.

        Ignores loop_factory parameter and always uses SelectorEventLoop for psycopg compatibility.
        """
        # Create a new SelectorEventLoop (ignore loop_factory parameter)
        loop = asyncio.SelectorEventLoop(selectors.SelectSelector())
        asyncio.set_event_loop(loop)

        try:
            return loop.run_until_complete(main)
        finally:
            try:
                _cancel_all_tasks(loop)
                loop.run_until_complete(loop.shutdown_asyncgens())
                loop.run_until_complete(loop.shutdown_default_executor())
            finally:
                asyncio.set_event_loop(None)
                loop.close()

    def _cancel_all_tasks(loop):
        """Cancel all tasks in the loop."""
        tasks = [task for task in asyncio.all_tasks(loop) if not task.done()]
        if not tasks:
            return
        for task in tasks:
            task.cancel()
        loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))

    # Monkey patch asyncio
    asyncio.run = _patched_run
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    print("Patched asyncio.run() to use SelectorEventLoop on Windows for psycopg compatibility", file=sys.stderr)

# Now import and run langgraph CLI
if __name__ == "__main__":
    from langgraph_cli.cli import cli

    cli()
