"""Memory storage providers."""

import abc
import asyncio
import json
import logging
import threading
from collections.abc import Awaitable, Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from deerflow.config.agents_config import AGENT_NAME_PATTERN
from deerflow.config.memory_config import get_memory_config
from deerflow.config.paths import get_paths

logger = logging.getLogger(__name__)

DatabaseMemoryLoadHandler = Callable[[int], Awaitable[dict[str, Any]]]
DatabaseMemorySaveHandler = Callable[[int, dict[str, Any]], Awaitable[None]]

_database_memory_load_handler: DatabaseMemoryLoadHandler | None = None
_database_memory_save_handler: DatabaseMemorySaveHandler | None = None


def register_database_memory_handlers(
    *,
    load_handler: DatabaseMemoryLoadHandler,
    save_handler: DatabaseMemorySaveHandler,
) -> None:
    """Register app-owned database handlers for DatabaseMemoryStorage."""
    global _database_memory_load_handler, _database_memory_save_handler
    _database_memory_load_handler = load_handler
    _database_memory_save_handler = save_handler


def clear_database_memory_handlers() -> None:
    """Clear registered database handlers, primarily for isolated tests."""
    global _database_memory_load_handler, _database_memory_save_handler
    _database_memory_load_handler = None
    _database_memory_save_handler = None


def _run_async(coro):
    """Run async DB helpers from both sync and async call sites."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result: dict[str, Any] = {}
    error: dict[str, BaseException] = {}

    def _runner() -> None:
        try:
            result["value"] = asyncio.run(coro)
        except BaseException as exc:  # pragma: no cover - re-raised on caller thread
            error["value"] = exc

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()
    thread.join()
    if "value" in error:
        raise error["value"]
    return result.get("value")


def create_empty_memory() -> dict[str, Any]:
    """Create an empty memory structure."""
    return {
        "version": "1.0",
        "lastUpdated": datetime.utcnow().isoformat() + "Z",
        "user": {
            "workContext": {"summary": "", "updatedAt": ""},
            "personalContext": {"summary": "", "updatedAt": ""},
            "topOfMind": {"summary": "", "updatedAt": ""},
        },
        "history": {
            "recentMonths": {"summary": "", "updatedAt": ""},
            "earlierContext": {"summary": "", "updatedAt": ""},
            "longTermBackground": {"summary": "", "updatedAt": ""},
        },
        "facts": [],
    }


class MemoryStorage(abc.ABC):
    """Abstract base class for memory storage providers."""

    @abc.abstractmethod
    def load(self, user_id: int | None = None, agent_name: str | None = None) -> dict[str, Any]:
        """Load memory data for the given agent."""
        pass

    @abc.abstractmethod
    def reload(self, user_id: int | None = None, agent_name: str | None = None) -> dict[str, Any]:
        """Force reload memory data for the given agent."""
        pass

    @abc.abstractmethod
    def save(self, memory_data: dict[str, Any], user_id: int | None = None, agent_name: str | None = None) -> bool:
        """Save memory data for the given agent."""
        pass


class FileMemoryStorage(MemoryStorage):
    """File-based memory storage provider."""

    def __init__(self):
        """Initialize the file memory storage."""
        # Per-agent memory cache: keyed by agent_name (None = global)
        # Value: (memory_data, file_mtime)
        self._memory_cache: dict[str | None, tuple[dict[str, Any], float | None]] = {}

    def _validate_agent_name(self, agent_name: str) -> None:
        """Validate that the agent name is safe to use in filesystem paths.

        Uses the repository's established AGENT_NAME_PATTERN to ensure consistency
        across the codebase and prevent path traversal or other problematic characters.
        """
        if not agent_name:
            raise ValueError("Agent name must be a non-empty string.")
        if not AGENT_NAME_PATTERN.match(agent_name):
            raise ValueError(f"Invalid agent name {agent_name!r}: names must match {AGENT_NAME_PATTERN.pattern}")

    def _get_memory_file_path(self, agent_name: str | None = None) -> Path:
        """Get the path to the memory file."""
        if agent_name is not None:
            self._validate_agent_name(agent_name)
            return get_paths().agent_memory_file(agent_name)

        config = get_memory_config()
        if config.storage_path:
            p = Path(config.storage_path)
            return p if p.is_absolute() else get_paths().base_dir / p
        return get_paths().memory_file

    def _load_memory_from_file(self, agent_name: str | None = None) -> dict[str, Any]:
        """Load memory data from file."""
        file_path = self._get_memory_file_path(agent_name)

        if not file_path.exists():
            return create_empty_memory()

        try:
            with open(file_path, encoding="utf-8") as f:
                data = json.load(f)
            return data
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load memory file: %s", e)
            return create_empty_memory()

    def load(self, user_id: int | None = None, agent_name: str | None = None) -> dict[str, Any]:
        """Load memory data (cached with file modification time check)."""
        del user_id
        file_path = self._get_memory_file_path(agent_name)

        try:
            current_mtime = file_path.stat().st_mtime if file_path.exists() else None
        except OSError:
            current_mtime = None

        cached = self._memory_cache.get(agent_name)

        if cached is None or cached[1] != current_mtime:
            memory_data = self._load_memory_from_file(agent_name)
            self._memory_cache[agent_name] = (memory_data, current_mtime)
            return memory_data

        return cached[0]

    def reload(self, user_id: int | None = None, agent_name: str | None = None) -> dict[str, Any]:
        """Reload memory data from file, forcing cache invalidation."""
        del user_id
        file_path = self._get_memory_file_path(agent_name)
        memory_data = self._load_memory_from_file(agent_name)

        try:
            mtime = file_path.stat().st_mtime if file_path.exists() else None
        except OSError:
            mtime = None

        self._memory_cache[agent_name] = (memory_data, mtime)
        return memory_data

    def save(self, memory_data: dict[str, Any], user_id: int | None = None, agent_name: str | None = None) -> bool:
        """Save memory data to file and update cache."""
        del user_id
        file_path = self._get_memory_file_path(agent_name)

        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            memory_data["lastUpdated"] = datetime.utcnow().isoformat() + "Z"

            temp_path = file_path.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(memory_data, f, indent=2, ensure_ascii=False)

            temp_path.replace(file_path)

            try:
                mtime = file_path.stat().st_mtime
            except OSError:
                mtime = None

            self._memory_cache[agent_name] = (memory_data, mtime)
            logger.info("Memory saved to %s", file_path)
            return True
        except OSError as e:
            logger.error("Failed to save memory file: %s", e)
            return False


class DatabaseMemoryStorage(MemoryStorage):
    """Database-backed memory storage provider."""

    def __init__(self):
        self._memory_cache: dict[int, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def _require_user_id(self, user_id: int | None) -> int:
        if user_id is None:
            raise ValueError("user_id")
        return user_id

    @staticmethod
    async def _load_from_db(user_id: int) -> dict[str, Any]:
        if _database_memory_load_handler is None:
            raise RuntimeError("Database memory storage is not registered")
        memory_data = await _database_memory_load_handler(user_id)
        logger.info("Loaded memory from database for user %s: facts=%d", user_id, len(memory_data.get("facts", [])))
        return dict(memory_data)

    @staticmethod
    async def _save_to_db(user_id: int, memory_data: dict[str, Any]) -> None:
        if _database_memory_save_handler is None:
            raise RuntimeError("Database memory storage is not registered")

        logger.info(
            "Persisting memory to database for user %s: facts=%d",
            user_id,
            len(memory_data.get("facts", [])),
        )
        await _database_memory_save_handler(user_id, memory_data)
        logger.info("Persisted memory to database for user %s", user_id)

    def load(self, user_id: int | None = None, agent_name: str | None = None) -> dict[str, Any]:
        del agent_name
        normalized_user_id = self._require_user_id(user_id)
        with self._lock:
            cached = self._memory_cache.get(normalized_user_id)
        if cached is not None:
            logger.debug("Memory cache hit for user %s", normalized_user_id)
            return cached

        logger.info("Memory cache miss for user %s; loading from database", normalized_user_id)
        memory_data = _run_async(self._load_from_db(normalized_user_id))
        with self._lock:
            self._memory_cache[normalized_user_id] = memory_data
        return memory_data

    def reload(self, user_id: int | None = None, agent_name: str | None = None) -> dict[str, Any]:
        del agent_name
        normalized_user_id = self._require_user_id(user_id)
        logger.info("Reloading memory from database for user %s", normalized_user_id)
        memory_data = _run_async(self._load_from_db(normalized_user_id))
        with self._lock:
            self._memory_cache[normalized_user_id] = memory_data
        return memory_data

    def save(self, memory_data: dict[str, Any], user_id: int | None = None, agent_name: str | None = None) -> bool:
        del agent_name
        normalized_user_id = self._require_user_id(user_id)
        memory_data["lastUpdated"] = datetime.utcnow().isoformat() + "Z"
        try:
            logger.info("Saving memory through DatabaseMemoryStorage for user %s", normalized_user_id)
            _run_async(self._save_to_db(normalized_user_id, memory_data))
        except Exception as exc:
            logger.error("Failed to save database memory for user %s: %s", normalized_user_id, exc)
            return False

        with self._lock:
            self._memory_cache[normalized_user_id] = memory_data
        logger.info("Memory cache updated after save for user %s", normalized_user_id)
        return True


_storage_instance: MemoryStorage | None = None
_storage_lock = threading.Lock()


def get_memory_storage() -> MemoryStorage:
    """Get the configured memory storage instance."""
    global _storage_instance
    if _storage_instance is not None:
        return _storage_instance

    with _storage_lock:
        if _storage_instance is not None:
            return _storage_instance

        config = get_memory_config()
        storage_class_path = config.storage_class

        try:
            module_path, class_name = storage_class_path.rsplit(".", 1)
            import importlib

            module = importlib.import_module(module_path)
            storage_class = getattr(module, class_name)

            # Validate that the configured storage is a MemoryStorage implementation
            if not isinstance(storage_class, type):
                raise TypeError(f"Configured memory storage '{storage_class_path}' is not a class: {storage_class!r}")
            if not issubclass(storage_class, MemoryStorage):
                raise TypeError(f"Configured memory storage '{storage_class_path}' is not a subclass of MemoryStorage")

            _storage_instance = storage_class()
        except Exception as e:
            logger.error(
                "Failed to load memory storage %s, falling back to FileMemoryStorage: %s",
                storage_class_path,
                e,
            )
            _storage_instance = FileMemoryStorage()

    return _storage_instance
