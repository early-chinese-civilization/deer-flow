from __future__ import annotations

from types import SimpleNamespace

import pytest


class _ScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)


class _FakeConnection:
    def __init__(self, tables, revisions=None):
        self._tables = tables
        self._revisions = revisions or []

    async def execute(self, statement):
        sql = str(statement)
        if "information_schema.tables" in sql:
            return _ScalarResult(self._tables)
        if "alembic_version" in sql:
            return _ScalarResult(self._revisions)
        raise AssertionError(f"Unexpected SQL: {sql}")


class _FakeConnectContext:
    def __init__(self, connection):
        self._connection = connection

    async def __aenter__(self):
        return self._connection

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.anyio
async def test_assert_gateway_schema_ready_requires_threads_table():
    from app.gateway.db.schema_preflight import assert_gateway_schema_ready

    engine = SimpleNamespace(
        connect=lambda: _FakeConnectContext(
            _FakeConnection(
                tables=["alembic_version", "users", "workspace_files", "workspaces"],
                revisions=["7b279560c2f2"],
            )
        )
    )

    with pytest.raises(RuntimeError, match="Missing tables: threads"):
        await assert_gateway_schema_ready(engine)
