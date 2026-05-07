from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import patch


def _load_threads_migration_module():
    versions_dir = Path(__file__).resolve().parents[1] / "alembic" / "versions"
    matches = list(versions_dir.glob("*_add_threads_table.py"))
    assert len(matches) == 1, "Expected exactly one add_threads_table migration"

    migration_path = matches[0]
    spec = importlib.util.spec_from_file_location(migration_path.stem, migration_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_user_id_migration_module():
    versions_dir = Path(__file__).resolve().parents[1] / "alembic" / "versions"
    matches = list(versions_dir.glob("*_rename_owner_user_id_to_user_id.py"))
    assert len(matches) == 1, "Expected exactly one rename_owner_user_id_to_user_id migration"

    migration_path = matches[0]
    spec = importlib.util.spec_from_file_location(migration_path.stem, migration_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_workspace_decoupling_migration_module():
    versions_dir = Path(__file__).resolve().parents[1] / "alembic" / "versions"
    matches = list(versions_dir.glob("*_decouple_threads_workspace_binding.py"))
    assert len(matches) == 1, "Expected exactly one decouple_threads_workspace_binding migration"

    migration_path = matches[0]
    spec = importlib.util.spec_from_file_location(migration_path.stem, migration_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_threads_migration_creates_threads_table_and_indexes():
    import sqlalchemy as sa

    migration = _load_threads_migration_module()

    with (
        patch.object(migration.op, "create_table") as create_table,
        patch.object(migration.op, "create_index") as create_index,
    ):
        migration.upgrade()

    assert create_table.call_count == 1
    table_name, *table_args = create_table.call_args.args
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


def test_user_id_migration_renames_thread_and_workspace_owner_columns():
    migration = _load_user_id_migration_module()

    with (
        patch.object(migration.op, "execute") as execute,
    ):
        migration.upgrade()

    executed_sql = "\n".join(str(call.args[0]) for call in execute.call_args_list)
    assert "ALTER TABLE workspaces RENAME COLUMN owner_user_id TO user_id" in executed_sql
    assert "ALTER TABLE threads RENAME COLUMN owner_user_id TO user_id" in executed_sql
    assert "ALTER INDEX IF EXISTS ix_workspaces_owner_user_id RENAME TO ix_workspaces_user_id" in executed_sql
    assert "ALTER INDEX IF EXISTS ix_threads_owner_updated RENAME TO ix_threads_user_updated" in executed_sql


def test_workspace_decoupling_migration_drops_workspace_uniqueness_and_sets_null_delete_rule():
    migration = _load_workspace_decoupling_migration_module()

    with patch.object(migration.op, "execute") as execute:
        migration.upgrade()

    executed_sql = "\n".join(str(call.args[0]) for call in execute.call_args_list)
    assert "ALTER TABLE threads ALTER COLUMN workspace_id DROP NOT NULL" in executed_sql
    assert "DROP CONSTRAINT IF EXISTS threads_workspace_id_key" in executed_sql
    assert "DROP CONSTRAINT IF EXISTS threads_workspace_id_fkey" in executed_sql
    assert "ON DELETE SET NULL" in executed_sql
