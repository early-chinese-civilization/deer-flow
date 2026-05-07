from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.gateway.db.schema_preflight import REQUIRED_GATEWAY_COLUMNS


class _ScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)


class _RowsResult:
    def __init__(self, rows):
        self._rows = rows

    def __iter__(self):
        return iter(self._rows)


class _FakeConnection:
    def __init__(self, tables, revisions=None, columns=None):
        self._tables = tables
        self._revisions = revisions or []
        self._columns = columns or {}

    async def execute(self, statement, parameters=None):
        sql = str(statement)
        if "information_schema.tables" in sql:
            return _ScalarResult(self._tables)
        if "alembic_version" in sql:
            return _ScalarResult(self._revisions)
        if "information_schema.columns" in sql:
            requested_tables = (parameters or {}).get("tables", [])
            rows = [(table, column) for table in requested_tables for column in self._columns.get(table, ())]
            return _RowsResult(rows)
        raise AssertionError(f"Unexpected SQL: {sql}")


class _FakeConnectContext:
    def __init__(self, connection):
        self._connection = connection

    async def __aenter__(self):
        return self._connection

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _complete_columns(*tables: str) -> dict[str, tuple[str, ...]]:
    return {table: tuple(REQUIRED_GATEWAY_COLUMNS[table]) for table in tables}


@pytest.mark.anyio
async def test_assert_gateway_schema_ready_requires_threads_table():
    from app.gateway.db.schema_preflight import assert_gateway_schema_ready

    existing_tables = [
        "alembic_version",
        "users",
        "workspace_files",
        "workspaces",
        "agents",
        "agents_skills",
        "skills",
        "skill_definitions",
        "skill_versions",
        "skill_installs",
        "skill_releases",
        "pending_skill_fork_claims",
        "runtime_manifests",
    ]
    engine = SimpleNamespace(
        connect=lambda: _FakeConnectContext(
            _FakeConnection(
                tables=existing_tables,
                revisions=["7b279560c2f2"],
                columns=_complete_columns(
                    "users",
                    "workspaces",
                    "agents",
                    "agents_skills",
                    "skills",
                    "skill_definitions",
                    "skill_versions",
                    "skill_installs",
                    "skill_releases",
                    "pending_skill_fork_claims",
                    "runtime_manifests",
                ),
            )
        )
    )

    with pytest.raises(RuntimeError, match="Missing tables: threads"):
        await assert_gateway_schema_ready(engine)


@pytest.mark.anyio
async def test_assert_gateway_schema_ready_requires_skill_releases_table():
    from app.gateway.db.schema_preflight import assert_gateway_schema_ready

    existing_tables = ["alembic_version", "users", "workspaces", "threads", "skills"]
    engine = SimpleNamespace(
        connect=lambda: _FakeConnectContext(
            _FakeConnection(
                tables=existing_tables,
                revisions=["b8f3d0a1c2e4"],
                columns=_complete_columns("users", "workspaces", "threads", "skills"),
            )
        )
    )

    with pytest.raises(RuntimeError, match="skill_releases"):
        await assert_gateway_schema_ready(engine)


@pytest.mark.anyio
async def test_assert_gateway_schema_ready_requires_skill_release_columns():
    from app.gateway.db.schema_preflight import assert_gateway_schema_ready

    columns = _complete_columns(
        "users",
        "workspaces",
        "threads",
        "agents",
        "agents_skills",
        "skills",
        "skill_definitions",
        "skill_versions",
        "skill_installs",
        "skill_releases",
        "pending_skill_fork_claims",
        "runtime_manifests",
    )
    columns["skill_releases"] = tuple(column for column in columns["skill_releases"] if column != "release_version")
    engine = SimpleNamespace(
        connect=lambda: _FakeConnectContext(
            _FakeConnection(
                tables=[
                    "alembic_version",
                    "users",
                    "workspaces",
                    "threads",
                    "agents",
                    "agents_skills",
                    "skills",
                    "skill_definitions",
                    "skill_versions",
                    "skill_installs",
                    "skill_releases",
                    "pending_skill_fork_claims",
                    "runtime_manifests",
                ],
                revisions=["e2a7c9d4f601"],
                columns=columns,
            )
        )
    )

    with pytest.raises(RuntimeError, match="Missing columns: skill_releases.release_version"):
        await assert_gateway_schema_ready(engine)


@pytest.mark.anyio
async def test_assert_gateway_schema_ready_requires_agent_skill_install_column():
    from app.gateway.db.schema_preflight import assert_gateway_schema_ready

    tables = [
        "alembic_version",
        "users",
        "workspaces",
        "threads",
        "agents",
        "agents_skills",
        "skills",
        "skill_definitions",
        "skill_versions",
        "skill_installs",
        "skill_releases",
        "pending_skill_fork_claims",
        "runtime_manifests",
    ]
    columns = _complete_columns(*(table for table in tables if table != "alembic_version"))
    columns["agents_skills"] = tuple(column for column in columns["agents_skills"] if column != "skill_install_id")
    engine = SimpleNamespace(
        connect=lambda: _FakeConnectContext(
            _FakeConnection(
                tables=tables,
                revisions=["a7c9e2d5f604"],
                columns=columns,
            )
        )
    )

    with pytest.raises(RuntimeError, match="Missing columns: agents_skills.skill_install_id"):
        await assert_gateway_schema_ready(engine)
