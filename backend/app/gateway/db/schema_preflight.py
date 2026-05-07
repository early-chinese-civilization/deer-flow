"""Startup checks for Gateway-owned database schema."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.gateway.db.schema_settings import get_gateway_db_schema

REQUIRED_GATEWAY_TABLES = frozenset(
    {
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
    }
)
REQUIRED_GATEWAY_COLUMNS = {
    "users": frozenset(
        {
            "id",
            "external_auth_id",
            "username",
            "display_name",
            "email",
            "given_name",
            "family_name",
            "email_verified",
            "created_at",
            "updated_at",
        }
    ),
    "workspaces": frozenset(
        {
            "id",
            "user_id",
            "name",
            "file_path",
            "created_at",
            "updated_at",
        }
    ),
    "threads": frozenset(
        {
            "thread_id",
            "user_id",
            "agent_id",
            "workspace_id",
            "title",
            "status",
            "metadata",
            "created_at",
            "updated_at",
        }
    ),
    "agents": frozenset(
        {
            "id",
            "user_id",
            "name",
            "description",
            "soul",
            "mcp_config",
            "created_at",
            "updated_at",
            "deleted_at",
        }
    ),
    "agents_skills": frozenset(
        {
            "id",
            "agent_id",
            "skill_id",
            "skill_install_id",
            "display_order",
            "enabled",
            "created_at",
            "deleted_at",
        }
    ),
    "skills": frozenset(
        {
            "id",
            "user_id",
            "owner_user_id",
            "name",
            "display_name",
            "description",
            "file_path",
            "skill_definition_id",
            "created_at",
            "updated_at",
            "deleted_at",
        }
    ),
    "skill_releases": frozenset(
        {
            "id",
            "skill_name",
            "release_version",
            "package_version",
            "description",
            "release_notes",
            "status",
            "artifact_path",
            "publisher_user_id",
            "source_skill_id",
            "published_skill_id",
            "skill_version_id",
            "created_at",
        }
    ),
    "skill_definitions": frozenset(
        {
            "id",
            "name",
            "display_name",
            "description",
            "source_type",
            "source_identifier",
            "owner_user_id",
            "created_at",
            "updated_at",
            "deleted_at",
        }
    ),
    "skill_versions": frozenset(
        {
            "id",
            "skill_definition_id",
            "version_number",
            "source_package_version",
            "description",
            "content_hash",
            "file_manifest_hash",
            "artifact_uri",
            "created_by_user_id",
            "created_at",
        }
    ),
    "skill_installs": frozenset(
        {
            "id",
            "user_id",
            "skill_definition_id",
            "installed_version_id",
            "current_version_id",
            "created_at",
            "updated_at",
            "deleted_at",
        }
    ),
    "pending_skill_fork_claims": frozenset(
        {
            "id",
            "user_id",
            "source_skill_definition_id",
            "source_skill_version_id",
            "claim_token_hash",
            "status",
            "source_snapshot",
            "expires_at",
            "claimed_at",
            "created_at",
            "updated_at",
        }
    ),
    "runtime_manifests": frozenset(
        {
            "id",
            "user_id",
            "agent_id",
            "agent_name",
            "manifest_json",
            "manifest_hash",
            "created_at",
        }
    ),
}

_TABLES_SQL = text("select table_name from information_schema.tables where table_schema=:schema order by table_name")
_COLUMNS_SQL = text("select table_name, column_name from information_schema.columns where table_schema=:schema and table_name = any(:tables) order by table_name, ordinal_position")
_ALEMBIC_VERSION_SQL = text("select version_num from alembic_version order by version_num")


@dataclass(frozen=True)
class GatewaySchemaStatus:
    """Observed database schema state relevant to Gateway runtime startup."""

    current_revision: str | None
    missing_tables: tuple[str, ...]
    missing_columns: tuple[str, ...]


async def inspect_gateway_schema(engine: AsyncEngine) -> GatewaySchemaStatus:
    """Inspect required Gateway schema objects from the configured database."""
    schema = get_gateway_db_schema()
    async with engine.connect() as connection:
        tables = set((await connection.execute(_TABLES_SQL, {"schema": schema})).scalars().all())

        current_revision: str | None = None
        if "alembic_version" in tables:
            revisions = (await connection.execute(_ALEMBIC_VERSION_SQL)).scalars().all()
            if revisions:
                current_revision = ", ".join(revisions)

        observed_columns: dict[str, set[str]] = {table: set() for table in REQUIRED_GATEWAY_TABLES}
        if REQUIRED_GATEWAY_TABLES:
            for table_name, column_name in await connection.execute(
                _COLUMNS_SQL,
                {"schema": schema, "tables": list(REQUIRED_GATEWAY_TABLES)},
            ):
                if table_name in observed_columns:
                    observed_columns[table_name].add(column_name)

    missing_tables = tuple(sorted(REQUIRED_GATEWAY_TABLES - tables))
    missing_columns = tuple(sorted(f"{table}.{column}" for table, required_columns in REQUIRED_GATEWAY_COLUMNS.items() for column in sorted(required_columns - observed_columns.get(table, set()))))
    return GatewaySchemaStatus(
        current_revision=current_revision,
        missing_tables=missing_tables,
        missing_columns=missing_columns,
    )


def _build_schema_error(status: GatewaySchemaStatus) -> str:
    current_revision = status.current_revision or "unknown"
    missing_tables = ", ".join(status.missing_tables)
    missing_columns = ", ".join(status.missing_columns)
    details: list[str] = []
    if missing_tables:
        details.append(f"Missing tables: {missing_tables}.")
    if missing_columns:
        details.append(f"Missing columns: {missing_columns}.")
    return (
        "Gateway database schema is out of date for thread runtime. "
        f"Schema: {get_gateway_db_schema()}. "
        f"Current alembic revision: {current_revision}. "
        f"{' '.join(details)} "
        "Run `make migrate` or `cd backend && uv run alembic upgrade head`, then restart the gateway."
    )


async def assert_gateway_schema_ready(engine: AsyncEngine) -> None:
    """Raise when the database schema is missing tables required by Gateway."""
    status = await inspect_gateway_schema(engine)
    if status.missing_tables or status.missing_columns:
        raise RuntimeError(_build_schema_error(status))
