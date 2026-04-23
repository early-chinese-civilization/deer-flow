"""Tests for memory storage providers."""

import threading
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from deerflow.agents.memory.storage import (
    DatabaseMemoryStorage,
    FileMemoryStorage,
    MemoryStorage,
    create_empty_memory,
    get_memory_storage,
)
from deerflow.config.memory_config import MemoryConfig


class TestCreateEmptyMemory:
    """Test create_empty_memory function."""

    def test_returns_valid_structure(self):
        """Should return a valid empty memory structure."""
        memory = create_empty_memory()
        assert isinstance(memory, dict)
        assert memory["version"] == "1.0"
        assert "lastUpdated" in memory
        assert isinstance(memory["user"], dict)
        assert isinstance(memory["history"], dict)
        assert isinstance(memory["facts"], list)


class TestMemoryStorageInterface:
    """Test MemoryStorage abstract base class."""

    def test_abstract_methods(self):
        """Should raise TypeError when trying to instantiate abstract class."""

        class TestStorage(MemoryStorage):
            pass

        with pytest.raises(TypeError):
            TestStorage()


class TestFileMemoryStorage:
    """Test FileMemoryStorage implementation."""

    def test_get_memory_file_path_global(self):
        """Should return global memory file path when agent_name is None."""
        expected_path = Path("C:/memory.json")

        def mock_get_paths():
            mock_paths = MagicMock()
            mock_paths.memory_file = expected_path
            return mock_paths

        with patch("deerflow.agents.memory.storage.get_paths", side_effect=mock_get_paths):
            with patch("deerflow.agents.memory.storage.get_memory_config", return_value=MemoryConfig(storage_path="")):
                storage = FileMemoryStorage()
                path = storage._get_memory_file_path(None)
                assert path == expected_path

    def test_get_memory_file_path_agent(self):
        """Should return per-agent memory file path when agent_name is provided."""
        expected_path = Path("C:/agents/test-agent/memory.json")

        def mock_get_paths():
            mock_paths = MagicMock()
            mock_paths.agent_memory_file.return_value = expected_path
            return mock_paths

        with patch("deerflow.agents.memory.storage.get_paths", side_effect=mock_get_paths):
            storage = FileMemoryStorage()
            path = storage._get_memory_file_path("test-agent")
            assert path == expected_path

    @pytest.mark.parametrize("invalid_name", ["", "../etc/passwd", "agent/name", "agent\\name", "agent name", "agent@123", "agent_name"])
    def test_validate_agent_name_invalid(self, invalid_name):
        """Should raise ValueError for invalid agent names that don't match the pattern."""
        storage = FileMemoryStorage()
        with pytest.raises(ValueError, match="Invalid agent name|Agent name must be a non-empty string"):
            storage._validate_agent_name(invalid_name)

    def test_load_creates_empty_memory(self):
        """Should create empty memory when file doesn't exist."""
        expected_path = Path("C:/non-existent-memory.json")

        def mock_get_paths():
            mock_paths = MagicMock()
            mock_paths.memory_file = expected_path
            return mock_paths

        with patch("deerflow.agents.memory.storage.get_paths", side_effect=mock_get_paths):
            with patch("deerflow.agents.memory.storage.get_memory_config", return_value=MemoryConfig(storage_path="")):
                storage = FileMemoryStorage()
                memory = storage.load()
                assert isinstance(memory, dict)
                assert memory["version"] == "1.0"

    def test_save_writes_to_file(self):
        """Should save memory data to file."""
        memory_file = MagicMock()
        memory_file.parent = MagicMock()
        temp_path = MagicMock()
        memory_file.with_suffix.return_value = temp_path
        memory_file.stat.return_value = MagicMock(st_mtime=123.0)

        with patch.object(FileMemoryStorage, "_get_memory_file_path", return_value=memory_file):
            with patch("builtins.open", MagicMock()):
                storage = FileMemoryStorage()
                test_memory = {"version": "1.0", "facts": [{"content": "test fact"}]}
                result = storage.save(test_memory)
                assert result is True
                memory_file.parent.mkdir.assert_called_once()
                temp_path.replace.assert_called_once_with(memory_file)

    def test_reload_forces_cache_invalidation(self):
        """Should force reload from file and invalidate cache."""
        memory_file = MagicMock()
        memory_file.exists.return_value = True
        memory_file.stat.return_value = MagicMock(st_mtime=123.0)

        with patch.object(FileMemoryStorage, "_get_memory_file_path", return_value=memory_file):
            storage = FileMemoryStorage()
            with patch.object(
                storage,
                "_load_memory_from_file",
                side_effect=[
                    {"version": "1.0", "facts": [{"content": "initial fact"}]},
                    {"version": "1.0", "facts": [{"content": "updated fact"}]},
                ],
            ):
                memory1 = storage.load()
                assert memory1["facts"][0]["content"] == "initial fact"

                memory2 = storage.reload()
                assert memory2["facts"][0]["content"] == "updated fact"


class TestGetMemoryStorage:
    """Test get_memory_storage function."""

    @pytest.fixture(autouse=True)
    def reset_storage_instance(self):
        """Reset the global storage instance before and after each test."""
        import deerflow.agents.memory.storage as storage_mod

        storage_mod._storage_instance = None
        yield
        storage_mod._storage_instance = None

    def test_returns_file_memory_storage_by_default(self):
        """Should return DatabaseMemoryStorage by default."""
        with patch("deerflow.agents.memory.storage.get_memory_config", return_value=MemoryConfig(storage_class="deerflow.agents.memory.storage.DatabaseMemoryStorage")):
            storage = get_memory_storage()
            assert isinstance(storage, DatabaseMemoryStorage)

    def test_falls_back_to_file_memory_storage_on_error(self):
        """Should fall back to FileMemoryStorage if configured storage fails to load."""
        with patch("deerflow.agents.memory.storage.get_memory_config", return_value=MemoryConfig(storage_class="non.existent.StorageClass")):
            storage = get_memory_storage()
            assert isinstance(storage, FileMemoryStorage)

    def test_returns_singleton_instance(self):
        """Should return the same instance on subsequent calls."""
        with patch("deerflow.agents.memory.storage.get_memory_config", return_value=MemoryConfig(storage_class="deerflow.agents.memory.storage.DatabaseMemoryStorage")):
            storage1 = get_memory_storage()
            storage2 = get_memory_storage()
            assert storage1 is storage2

    def test_get_memory_storage_thread_safety(self):
        """Should safely initialize the singleton even with concurrent calls."""
        results = []

        def get_storage():
            # get_memory_storage is called concurrently from multiple threads while
            # get_memory_config is patched once around thread creation. This verifies
            # that the singleton initialization remains thread-safe.
            results.append(get_memory_storage())

        with patch("deerflow.agents.memory.storage.get_memory_config", return_value=MemoryConfig(storage_class="deerflow.agents.memory.storage.DatabaseMemoryStorage")):
            threads = [threading.Thread(target=get_storage) for _ in range(10)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        # All results should be the exact same instance
        assert len(results) == 10
        assert all(r is results[0] for r in results)

    def test_get_memory_storage_invalid_class_fallback(self):
        """Should fall back to FileMemoryStorage if the configured class is not actually a class."""
        # Using a built-in function instead of a class
        with patch("deerflow.agents.memory.storage.get_memory_config", return_value=MemoryConfig(storage_class="os.path.join")):
            storage = get_memory_storage()
            assert isinstance(storage, FileMemoryStorage)

    def test_get_memory_storage_non_subclass_fallback(self):
        """Should fall back to FileMemoryStorage if the configured class is not a subclass of MemoryStorage."""
        # Using 'dict' as a class that is not a MemoryStorage subclass
        with patch("deerflow.agents.memory.storage.get_memory_config", return_value=MemoryConfig(storage_class="builtins.dict")):
            storage = get_memory_storage()
            assert isinstance(storage, FileMemoryStorage)


class TestDatabaseMemoryStorage:
    def test_load_returns_empty_memory_when_db_row_missing(self, monkeypatch):
        storage = DatabaseMemoryStorage()
        monkeypatch.setattr(
            storage,
            "_load_from_db",
            AsyncMock(return_value=create_empty_memory()),
        )

        memory = storage.load(user_id=42)

        assert memory["version"] == "1.0"
        assert memory["facts"] == []

    def test_save_updates_cache(self, monkeypatch):
        storage = DatabaseMemoryStorage()
        save_mock = AsyncMock(return_value=None)
        monkeypatch.setattr(storage, "_save_to_db", save_mock)
        test_memory = create_empty_memory()
        test_memory["facts"].append({"content": "Remember this"})

        assert storage.save(test_memory, user_id=42) is True
        assert storage.load(user_id=42)["facts"][0]["content"] == "Remember this"
