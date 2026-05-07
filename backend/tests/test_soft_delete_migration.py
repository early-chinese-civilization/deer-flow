from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import patch


def _load_soft_delete_migration_module():
    versions_dir = Path(__file__).resolve().parents[1] / "alembic" / "versions"
    matches = list(versions_dir.glob("*_add_soft_delete_to_users_workspaces_threads.py"))
    assert len(matches) == 1, "Expected exactly one core soft-delete migration"

    migration_path = matches[0]
    spec = importlib.util.spec_from_file_location(migration_path.stem, migration_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_core_soft_delete_migration_adds_deleted_at_columns_and_indexes():
    migration = _load_soft_delete_migration_module()

    with (
        patch.object(migration, "_has_column", return_value=False),
        patch.object(migration, "_has_index", return_value=False),
        patch.object(migration.op, "add_column") as add_column,
        patch.object(migration.op, "create_index") as create_index,
    ):
        migration.upgrade()

    added_columns = [(call.args[0], call.args[1].name) for call in add_column.call_args_list]
    assert ("users", "deleted_at") in added_columns
    assert ("workspaces", "deleted_at") in added_columns
    assert ("threads", "deleted_at") in added_columns

    index_names = {call.args[0] for call in create_index.call_args_list}
    assert "ix_users_deleted_at" in index_names
    assert "ix_workspaces_deleted_at" in index_names
    assert "ix_threads_deleted_at" in index_names
