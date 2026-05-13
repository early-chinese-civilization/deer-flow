"""Startup checks for Gateway-owned database schema."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.gateway.db.models import INTERNAL_SYSTEM_EXTERNAL_AUTH_ID
from app.gateway.db.schema_settings import get_gateway_db_schema

REQUIRED_GATEWAY_TABLES = frozenset(
    {
        "users",
        "workspaces",
        "threads",
        "agents",
        "agents_skills",
        "skills",
        "legacy_skills",
        "skill_identity_migration_map",
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
            "system_skill_definition_id",
            "system_skill_version_id",
            "display_order",
            "enabled",
            "created_at",
            "deleted_at",
        }
    ),
    "skills": frozenset(
        {
            "id",
            "owner_user_id",
            "name",
            "display_name",
            "description",
            "created_at",
            "updated_at",
            "deleted_at",
        }
    ),
    "legacy_skills": frozenset(
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
    "skill_identity_migration_map": frozenset(
        {
            "old_skill_definition_id",
            "skill_id",
            "old_skill_id",
            "migration_source",
            "created_at",
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

REQUIRED_GATEWAY_COLUMN_SIGNATURES = {
    ("skills", "id"): {"udt_name": "uuid", "is_nullable": "NO"},
    ("skills", "owner_user_id"): {"udt_name": "int8", "is_nullable": "NO"},
    ("legacy_skills", "id"): {"udt_name": "int8", "is_nullable": "NO"},
    ("skill_identity_migration_map", "old_skill_definition_id"): {"udt_name": "int8", "is_nullable": "NO"},
    ("skill_identity_migration_map", "skill_id"): {"udt_name": "uuid", "is_nullable": "NO"},
    ("skill_identity_migration_map", "migration_source"): {"udt_name": "varchar", "is_nullable": "NO"},
}

REQUIRED_GATEWAY_INDEXES = {
    "users": frozenset({"ix_users_external_auth_id"}),
    "skills": frozenset({"uq_skills_owner_name_active", "ix_skills_owner_user_id", "ix_skills_deleted_at"}),
    "legacy_skills": frozenset({"ix_legacy_skills_skill_definition_id", "ix_legacy_skills_deleted_at"}),
    "skill_identity_migration_map": frozenset({"ix_skill_identity_migration_map_skill_id", "ix_skill_identity_migration_map_old_skill_id"}),
}

REQUIRED_GATEWAY_CONSTRAINTS = {
    "skills": frozenset({"skills_pkey", "fk_skills_owner_user_id_users"}),
    "skill_identity_migration_map": frozenset(
        {
            "skill_identity_migration_map_pkey",
            "fk_skill_identity_migration_map_old_skill_definition_id_skill_definitions",
            "fk_skill_identity_migration_map_skill_id_skills",
            "fk_skill_identity_migration_map_old_skill_id_legacy_skills",
            "uq_skill_identity_migration_map_skill_id",
            "uq_skill_identity_migration_map_migration_source",
        }
    ),
}

_TABLES_SQL = text("select table_name from information_schema.tables where table_schema=:schema order by table_name")
_COLUMNS_SQL = text("select table_name, column_name, udt_name, is_nullable from information_schema.columns where table_schema=:schema and table_name = any(:tables) order by table_name, ordinal_position")
_INDEXES_SQL = text("select tablename, indexname from pg_indexes where schemaname=:schema and tablename = any(:tables) order by tablename, indexname")
_CONSTRAINTS_SQL = text("select table_name, constraint_name from information_schema.table_constraints where table_schema=:schema and table_name = any(:tables) order by table_name, constraint_name")
_ALEMBIC_VERSION_SQL = text("select version_num from alembic_version order by version_num")
_SYSTEM_USER_SQL = text("select count(*) from users where external_auth_id=:external_auth_id")


@dataclass(frozen=True)
class GatewaySchemaStatus:
    """Observed database schema state relevant to Gateway runtime startup."""

    current_revision: str | None
    missing_tables: tuple[str, ...]
    missing_columns: tuple[str, ...]
    missing_indexes: tuple[str, ...]
    missing_constraints: tuple[str, ...]
    failed_checks: tuple[str, ...]


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
        observed_column_signatures: dict[tuple[str, str], dict[str, str]] = {}
        if REQUIRED_GATEWAY_TABLES:
            for row in await connection.execute(
                _COLUMNS_SQL,
                {"schema": schema, "tables": list(REQUIRED_GATEWAY_TABLES)},
            ):
                table_name, column_name = row[0], row[1]
                if table_name in observed_columns:
                    observed_columns[table_name].add(column_name)
                if len(row) >= 4:
                    observed_column_signatures[(table_name, column_name)] = {
                        "udt_name": row[2],
                        "is_nullable": row[3],
                    }

        observed_indexes: dict[str, set[str]] = {table: set() for table in REQUIRED_GATEWAY_TABLES}
        for table_name, index_name in await connection.execute(_INDEXES_SQL, {"schema": schema, "tables": list(REQUIRED_GATEWAY_TABLES)}):
            if table_name in observed_indexes:
                observed_indexes[table_name].add(index_name)

        observed_constraints: dict[str, set[str]] = {table: set() for table in REQUIRED_GATEWAY_TABLES}
        for table_name, constraint_name in await connection.execute(_CONSTRAINTS_SQL, {"schema": schema, "tables": list(REQUIRED_GATEWAY_TABLES)}):
            if table_name in observed_constraints:
                observed_constraints[table_name].add(constraint_name)

        system_user_count: int | None = None
        if "users" in tables and "external_auth_id" in observed_columns.get("users", set()):
            system_user_count = int((await connection.execute(_SYSTEM_USER_SQL, {"external_auth_id": INTERNAL_SYSTEM_EXTERNAL_AUTH_ID})).scalar_one())

    missing_tables = tuple(sorted(REQUIRED_GATEWAY_TABLES - tables))
    missing_columns = tuple(sorted(f"{table}.{column}" for table, required_columns in REQUIRED_GATEWAY_COLUMNS.items() for column in sorted(required_columns - observed_columns.get(table, set()))))
    missing_indexes = tuple(sorted(f"{table}.{index_name}" for table, required_indexes in REQUIRED_GATEWAY_INDEXES.items() for index_name in sorted(required_indexes - observed_indexes.get(table, set()))))
    missing_constraints = tuple(sorted(f"{table}.{constraint_name}" for table, required_constraints in REQUIRED_GATEWAY_CONSTRAINTS.items() for constraint_name in sorted(required_constraints - observed_constraints.get(table, set()))))
    failed_checks = []
    for (table_name, column_name), expected_signature in REQUIRED_GATEWAY_COLUMN_SIGNATURES.items():
        observed_signature = observed_column_signatures.get((table_name, column_name))
        if observed_signature is None:
            continue
        for signature_key, expected_value in expected_signature.items():
            observed_value = observed_signature.get(signature_key)
            if observed_value != expected_value:
                failed_checks.append(f"{table_name}.{column_name} {signature_key} expected {expected_value}, found {observed_value}")
    if system_user_count is not None and system_user_count != 1:
        failed_checks.append(f'users.external_auth_id must contain exactly one "{INTERNAL_SYSTEM_EXTERNAL_AUTH_ID}" row, found {system_user_count}')

    return GatewaySchemaStatus(
        current_revision=current_revision,
        missing_tables=missing_tables,
        missing_columns=missing_columns,
        missing_indexes=missing_indexes,
        missing_constraints=missing_constraints,
        failed_checks=tuple(sorted(failed_checks)),
    )


def _build_schema_error(status: GatewaySchemaStatus) -> str:
    current_revision = status.current_revision or "unknown"
    missing_tables = ", ".join(status.missing_tables)
    missing_columns = ", ".join(status.missing_columns)
    missing_indexes = ", ".join(status.missing_indexes)
    missing_constraints = ", ".join(status.missing_constraints)
    failed_checks = "; ".join(status.failed_checks)
    details: list[str] = []
    if missing_tables:
        details.append(f"Missing tables: {missing_tables}.")
    if missing_columns:
        details.append(f"Missing columns: {missing_columns}.")
    if missing_indexes:
        details.append(f"Missing indexes: {missing_indexes}.")
    if missing_constraints:
        details.append(f"Missing constraints: {missing_constraints}.")
    if failed_checks:
        details.append(f"Failed checks: {failed_checks}.")
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
    if status.missing_tables or status.missing_columns or status.missing_indexes or status.missing_constraints or status.failed_checks:
        raise RuntimeError(_build_schema_error(status))
