"""Startup checks for Gateway-owned database schema."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

REQUIRED_GATEWAY_TABLES = frozenset({"users", "workspaces", "workspace_files"})

_TABLES_SQL = text(
    "select table_name from information_schema.tables "
    "where table_schema='public' order by table_name"
)
_ALEMBIC_VERSION_SQL = text("select version_num from alembic_version order by version_num")


@dataclass(frozen=True)
class GatewaySchemaStatus:
    """Observed database schema state relevant to Gateway runtime startup."""

    current_revision: str | None
    missing_tables: tuple[str, ...]


async def inspect_gateway_schema(engine: AsyncEngine) -> GatewaySchemaStatus:
    """Inspect required Gateway schema objects from the configured database."""
    async with engine.connect() as connection:
        tables = set((await connection.execute(_TABLES_SQL)).scalars().all())

        current_revision: str | None = None
        if "alembic_version" in tables:
            revisions = (await connection.execute(_ALEMBIC_VERSION_SQL)).scalars().all()
            if revisions:
                current_revision = ", ".join(revisions)

    missing_tables = tuple(sorted(REQUIRED_GATEWAY_TABLES - tables))
    return GatewaySchemaStatus(current_revision=current_revision, missing_tables=missing_tables)


def _build_schema_error(status: GatewaySchemaStatus) -> str:
    current_revision = status.current_revision or "unknown"
    missing_tables = ", ".join(status.missing_tables)
    return (
        "Gateway database schema is out of date for thread runtime. "
        f"Current alembic revision: {current_revision}. "
        f"Missing tables: {missing_tables}. "
        "Run `make migrate` or `cd backend && uv run alembic upgrade head`, then restart the gateway."
    )


async def assert_gateway_schema_ready(engine: AsyncEngine) -> None:
    """Raise when the database schema is missing tables required by Gateway."""
    status = await inspect_gateway_schema(engine)
    if status.missing_tables:
        raise RuntimeError(_build_schema_error(status))
