from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import patch


def _load_baseline_migration_module():
    versions_dir = Path(__file__).resolve().parents[1] / "alembic" / "versions"
    matches = list(versions_dir.glob("*_initial_baseline.py"))
    assert len(matches) == 1, "Expected exactly one initial_baseline migration"

    migration_path = matches[0]
    spec = importlib.util.spec_from_file_location(migration_path.stem, migration_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_threads_migration_creates_threads_table_and_indexes():
    import sqlalchemy as sa

    migration = _load_baseline_migration_module()

    with (
        patch.object(migration.op, "create_table") as create_table,
        patch.object(migration.op, "create_index") as create_index,
        patch.object(migration.op, "execute"),
    ):
        migration.upgrade()

    table_name, *table_args = next(call.args for call in create_table.call_args_list if call.args[0] == "threads")
    assert table_name == "threads"

    column_names = {column.name for column in table_args if hasattr(column, "name")}
    assert {
        "thread_id",
        "user_id",
        "workspace_id",
        "title",
        "status",
        "metadata",
        "created_at",
        "updated_at",
    }.issubset(column_names)

    workspace_column = next(column for column in table_args if getattr(column, "name", None) == "workspace_id")
    assert workspace_column.nullable is True

    unique_constraints = [constraint for constraint in table_args if isinstance(constraint, sa.UniqueConstraint)]
    assert not any("workspace_id" in constraint.columns.keys() for constraint in unique_constraints)

    foreign_key_constraints = [constraint for constraint in table_args if isinstance(constraint, sa.ForeignKeyConstraint)]
    workspace_fk = next(constraint for constraint in foreign_key_constraints if "workspace_id" in getattr(constraint, "column_keys", []))
    assert workspace_fk.ondelete == "SET NULL"

    index_names = {call.args[0] for call in create_index.call_args_list}
    assert "ix_threads_user_updated" in index_names
    assert "ix_threads_status" in index_names


def test_baseline_uses_user_id_columns_without_legacy_owner_names():
    migration = _load_baseline_migration_module()

    with (
        patch.object(migration.op, "create_table") as create_table,
        patch.object(migration.op, "create_index"),
        patch.object(migration.op, "execute"),
    ):
        migration.upgrade()

    table_columns = {
        call.args[0]: {column.name for column in call.args[1:] if hasattr(column, "name")}
        for call in create_table.call_args_list
    }
    assert "user_id" in table_columns["workspaces"]
    assert "user_id" in table_columns["threads"]
    assert "owner_user_id" not in table_columns["workspaces"]
    assert "owner_user_id" not in table_columns["threads"]


def test_baseline_threads_workspace_binding_is_nullable_and_set_null():
    migration = _load_baseline_migration_module()

    with (
        patch.object(migration.op, "create_table") as create_table,
        patch.object(migration.op, "create_index"),
        patch.object(migration.op, "execute"),
    ):
        migration.upgrade()

    threads_args = next(call.args[1:] for call in create_table.call_args_list if call.args[0] == "threads")
    workspace_column = next(column for column in threads_args if getattr(column, "name", None) == "workspace_id")
    assert workspace_column.nullable is True
    foreign_key_constraints = [constraint for constraint in threads_args if hasattr(constraint, "column_keys")]
    workspace_fk = next(constraint for constraint in foreign_key_constraints if "workspace_id" in getattr(constraint, "column_keys", []))
    assert workspace_fk.ondelete == "SET NULL"
