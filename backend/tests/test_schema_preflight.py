from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.gateway.db.schema_preflight import (
    REQUIRED_GATEWAY_COLUMN_SIGNATURES,
    REQUIRED_GATEWAY_COLUMNS,
    REQUIRED_GATEWAY_CONSTRAINTS,
    REQUIRED_GATEWAY_INDEXES,
    REQUIRED_GATEWAY_TABLES,
)


class _ScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)

    def scalar_one(self):
        return self._rows[0]


class _RowsResult:
    def __init__(self, rows):
        self._rows = rows

    def __iter__(self):
        return iter(self._rows)


class _FakeConnection:
    def __init__(self, tables, revisions=None, columns=None, column_signatures=None, indexes=None, constraints=None, system_user_count=1):
        self._tables = tables
        self._revisions = revisions or []
        self._columns = columns or {}
        self._column_signatures = column_signatures or _complete_column_signatures()
        self._indexes = indexes if indexes is not None else _complete_indexes()
        self._constraints = constraints if constraints is not None else _complete_constraints()
        self._system_user_count = system_user_count

    async def execute(self, statement, parameters=None):
        sql = str(statement)
        if "information_schema.tables" in sql:
            return _ScalarResult(self._tables)
        if "alembic_version" in sql:
            return _ScalarResult(self._revisions)
        if "information_schema.columns" in sql:
            requested_tables = (parameters or {}).get("tables", [])
            rows = []
            for table in requested_tables:
                for column in self._columns.get(table, ()):
                    signature = self._column_signatures.get((table, column))
                    if signature is None:
                        rows.append((table, column))
                    else:
                        rows.append((table, column, signature.get("udt_name"), signature.get("is_nullable")))
            return _RowsResult(rows)
        if "pg_indexes" in sql:
            requested_tables = (parameters or {}).get("tables", [])
            rows = [(table, index_name) for table in requested_tables for index_name in self._indexes.get(table, ())]
            return _RowsResult(rows)
        if "information_schema.table_constraints" in sql:
            requested_tables = (parameters or {}).get("tables", [])
            rows = [(table, constraint_name) for table in requested_tables for constraint_name in self._constraints.get(table, ())]
            return _RowsResult(rows)
        if "external_auth_id" in sql:
            return _ScalarResult([self._system_user_count])
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


def _complete_column_signatures() -> dict[tuple[str, str], dict[str, str]]:
    return {(table, column): dict(signature) for (table, column), signature in REQUIRED_GATEWAY_COLUMN_SIGNATURES.items()}


def _complete_indexes() -> dict[str, tuple[str, ...]]:
    return {table: tuple(indexes) for table, indexes in REQUIRED_GATEWAY_INDEXES.items()}


def _complete_constraints() -> dict[str, tuple[str, ...]]:
    return {table: tuple(constraints) for table, constraints in REQUIRED_GATEWAY_CONSTRAINTS.items()}


def _all_required_tables() -> list[str]:
    return ["alembic_version", *sorted(REQUIRED_GATEWAY_TABLES)]


@pytest.mark.anyio
async def test_assert_gateway_schema_ready_requires_threads_table():
    from app.gateway.db.schema_preflight import assert_gateway_schema_ready

    existing_tables = [table for table in _all_required_tables() if table != "threads"]
    engine = SimpleNamespace(
        connect=lambda: _FakeConnectContext(
            _FakeConnection(
                tables=existing_tables,
                revisions=["7b279560c2f2"],
                columns=_complete_columns(*(table for table in REQUIRED_GATEWAY_TABLES if table != "threads")),
            )
        )
    )

    with pytest.raises(RuntimeError, match="Missing tables: threads"):
        await assert_gateway_schema_ready(engine)


@pytest.mark.anyio
async def test_assert_gateway_schema_ready_requires_skill_releases_table():
    from app.gateway.db.schema_preflight import assert_gateway_schema_ready

    existing_tables = [table for table in _all_required_tables() if table != "skill_releases"]
    engine = SimpleNamespace(
        connect=lambda: _FakeConnectContext(
            _FakeConnection(
                tables=existing_tables,
                revisions=["b8f3d0a1c2e4"],
                columns=_complete_columns(*(table for table in REQUIRED_GATEWAY_TABLES if table != "skill_releases")),
            )
        )
    )

    with pytest.raises(RuntimeError, match="skill_releases"):
        await assert_gateway_schema_ready(engine)


@pytest.mark.anyio
async def test_assert_gateway_schema_ready_requires_skill_release_columns():
    from app.gateway.db.schema_preflight import assert_gateway_schema_ready

    columns = _complete_columns(
        *REQUIRED_GATEWAY_TABLES,
    )
    columns["skill_releases"] = tuple(column for column in columns["skill_releases"] if column != "release_version")
    engine = SimpleNamespace(
        connect=lambda: _FakeConnectContext(
            _FakeConnection(
                tables=_all_required_tables(),
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

    tables = _all_required_tables()
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


@pytest.mark.anyio
async def test_assert_gateway_schema_ready_requires_agent_system_skill_columns():
    from app.gateway.db.schema_preflight import assert_gateway_schema_ready

    tables = _all_required_tables()
    columns = _complete_columns(*(table for table in tables if table != "alembic_version"))
    columns["agents_skills"] = tuple(column for column in columns["agents_skills"] if column != "system_skill_version_id")
    engine = SimpleNamespace(
        connect=lambda: _FakeConnectContext(
            _FakeConnection(
                tables=tables,
                revisions=["7d3a2b1c0e9f"],
                columns=columns,
            )
        )
    )

    with pytest.raises(RuntimeError, match="Missing columns: agents_skills.system_skill_version_id"):
        await assert_gateway_schema_ready(engine)


@pytest.mark.anyio
async def test_assert_gateway_schema_ready_requires_terminal_skill_uuid():
    from app.gateway.db.schema_preflight import assert_gateway_schema_ready

    column_signatures = _complete_column_signatures()
    column_signatures[("skills", "id")] = {"udt_name": "int8", "is_nullable": "NO"}
    engine = SimpleNamespace(
        connect=lambda: _FakeConnectContext(
            _FakeConnection(
                tables=_all_required_tables(),
                revisions=["8a6f1b2c3d4e"],
                columns=_complete_columns(*REQUIRED_GATEWAY_TABLES),
                column_signatures=column_signatures,
            )
        )
    )

    with pytest.raises(RuntimeError, match="skills.id udt_name expected uuid"):
        await assert_gateway_schema_ready(engine)


@pytest.mark.anyio
async def test_assert_gateway_schema_ready_requires_identity_map_constraints():
    from app.gateway.db.schema_preflight import assert_gateway_schema_ready

    constraints = _complete_constraints()
    constraints["skill_identity_migration_map"] = tuple(constraint for constraint in constraints["skill_identity_migration_map"] if constraint != "uq_skill_identity_migration_map_skill_id")
    engine = SimpleNamespace(
        connect=lambda: _FakeConnectContext(
            _FakeConnection(
                tables=_all_required_tables(),
                revisions=["8a6f1b2c3d4e"],
                columns=_complete_columns(*REQUIRED_GATEWAY_TABLES),
                constraints=constraints,
            )
        )
    )

    with pytest.raises(RuntimeError, match="skill_identity_migration_map.uq_skill_identity_migration_map_skill_id"):
        await assert_gateway_schema_ready(engine)


@pytest.mark.anyio
async def test_assert_gateway_schema_ready_requires_internal_system_user():
    from app.gateway.db.schema_preflight import assert_gateway_schema_ready

    engine = SimpleNamespace(
        connect=lambda: _FakeConnectContext(
            _FakeConnection(
                tables=_all_required_tables(),
                revisions=["8a6f1b2c3d4e"],
                columns=_complete_columns(*REQUIRED_GATEWAY_TABLES),
                system_user_count=0,
            )
        )
    )

    with pytest.raises(RuntimeError, match="system:deerflow"):
        await assert_gateway_schema_ready(engine)


@pytest.mark.anyio
async def test_assert_gateway_schema_ready_accepts_terminal_skill_identity_foundation():
    from app.gateway.db.schema_preflight import assert_gateway_schema_ready

    engine = SimpleNamespace(
        connect=lambda: _FakeConnectContext(
            _FakeConnection(
                tables=_all_required_tables(),
                revisions=["8a6f1b2c3d4e"],
                columns=_complete_columns(*REQUIRED_GATEWAY_TABLES),
            )
        )
    )

    await assert_gateway_schema_ready(engine)
