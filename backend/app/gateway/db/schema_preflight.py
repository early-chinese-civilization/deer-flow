"""Startup checks for Gateway-owned database schema."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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
        "agent_skills",
        "skills",
        "skill_versions",
        "skill_installations",
        "skill_releases",
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
    "agent_skills": frozenset(
        {
            "id",
            "agent_id",
            "skill_installation_id",
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
    "skill_releases": frozenset(
        {
            "skill_id",
            "version_number",
            "skill_name",
            "release_version",
            "package_version",
            "description",
            "release_notes",
            "status",
            "publisher_user_id",
            "published_at",
            "created_at",
            "updated_at",
        }
    ),
    "skill_versions": frozenset(
        {
            "skill_id",
            "version_number",
            "source_package_version",
            "description",
            "content_hash",
            "file_manifest_hash",
            "created_by_user_id",
            "created_at",
        }
    ),
    "skill_installations": frozenset(
        {
            "id",
            "user_id",
            "skill_id",
            "version_number",
            "status",
            "created_at",
            "updated_at",
            "deleted_at",
        }
    ),
}

REQUIRED_GATEWAY_COLUMN_SIGNATURES = {
    ("threads", "agent_id"): {"udt_name": "int8", "is_nullable": "YES"},
    ("skills", "id"): {"udt_name": "uuid", "is_nullable": "NO"},
    ("skills", "owner_user_id"): {"udt_name": "int8", "is_nullable": "NO"},
    ("skill_versions", "skill_id"): {"udt_name": "uuid", "is_nullable": "NO"},
    ("skill_versions", "version_number"): {"udt_name": "int4", "is_nullable": "NO"},
    ("skill_installations", "skill_id"): {"udt_name": "uuid", "is_nullable": "NO"},
    ("skill_installations", "version_number"): {"udt_name": "int4", "is_nullable": "NO"},
    ("skill_installations", "status"): {"udt_name": "varchar", "is_nullable": "NO"},
    ("skill_releases", "skill_id"): {"udt_name": "uuid", "is_nullable": "NO"},
    ("skill_releases", "version_number"): {"udt_name": "int4", "is_nullable": "NO"},
    ("skill_releases", "status"): {"udt_name": "varchar", "is_nullable": "NO"},
    ("agent_skills", "skill_installation_id"): {"udt_name": "int8", "is_nullable": "NO"},
}

REQUIRED_GATEWAY_INDEXES = {
    "users": frozenset({"ix_users_external_auth_id"}),
    "skills": frozenset({"uq_skills_owner_name_active", "ix_skills_owner_user_id", "ix_skills_deleted_at"}),
    "skill_versions": frozenset({"ix_skill_versions_skill_id_created"}),
    "skill_installations": frozenset({"uq_skill_installations_user_skill_active", "ix_skill_installations_skill_version"}),
    "skill_releases": frozenset({"ix_skill_releases_status_skill_version"}),
    "agent_skills": frozenset({"uq_agent_skills_agent_installation_active", "ix_agent_skills_skill_installation_id"}),
}

REQUIRED_GATEWAY_CONSTRAINTS = {
    "skills": frozenset({"skills_pkey", "fk_skills_owner_user_id_users"}),
    "skill_versions": frozenset(
        {
            "fk_skill_versions_skill_id_skills",
            "uq_skill_versions_skill_version_number",
            "uq_skill_versions_skill_content_hash",
        }
    ),
    "skill_installations": frozenset(
        {
            "skill_installations_pkey",
            "fk_skill_installations_skill_version_composite",
        }
    ),
    "skill_releases": frozenset(
        {
            "fk_skill_releases_skill_version_composite",
            "uq_skill_releases_skill_version",
        }
    ),
    "agent_skills": frozenset(
        {
            "agent_skills_pkey",
            "fk_agent_skills_agent_id_agents",
            "fk_agent_skills_skill_installation_id_skill_installations",
        }
    ),
}

_TABLES_SQL = text("select table_name from information_schema.tables where table_schema=:schema order by table_name")
_COLUMNS_SQL = text("select table_name, column_name, udt_name, is_nullable from information_schema.columns where table_schema=:schema and table_name = any(:tables) order by table_name, ordinal_position")
_INDEXES_SQL = text("select tablename, indexname from pg_indexes where schemaname=:schema and tablename = any(:tables) order by tablename, indexname")
_CONSTRAINTS_SQL = text("select table_name, constraint_name from information_schema.table_constraints where table_schema=:schema and table_name = any(:tables) order by table_name, constraint_name")
_ALEMBIC_VERSION_SQL = text("select version_num from alembic_version order by version_num")
_SYSTEM_USER_SQL = text("select count(*) from users where external_auth_id=:external_auth_id")
_DEFAULT_CHAT_SKILL_SQL = text(
    """
    select skills.deleted_at, users.external_auth_id
    from skills
    join users on users.id = skills.owner_user_id
    where skills.id = :skill_id
    """
)
_DEFAULT_CHAT_VERSION_SQL = text(
    """
    select count(*)
    from skill_versions
    where skill_id = :skill_id
      and version_number = :version_number
    """
)


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


async def assert_default_chat_system_skills_ready(engine: AsyncEngine, system_skills: list[Any]) -> None:
    """Validate configured default-chat system Skill versions against terminal DB rows."""
    if not system_skills:
        return

    failed_checks: list[str] = []
    async with engine.connect() as connection:
        for index, entry in enumerate(system_skills):
            skill_id = getattr(entry, "skill_id", None)
            version_number = getattr(entry, "version_number", None)
            if skill_id is None or version_number is None:
                failed_checks.append(f"default_chat.system_skills[{index}] must contain skill_id and version_number")
                continue
            skill_row = (await connection.execute(_DEFAULT_CHAT_SKILL_SQL, {"skill_id": skill_id})).first()
            if skill_row is None:
                failed_checks.append(f"default_chat.system_skills[{index}] skill_id {skill_id} does not exist")
                continue
            deleted_at, external_auth_id = skill_row[0], skill_row[1]
            if deleted_at is not None:
                failed_checks.append(f"default_chat.system_skills[{index}] skill_id {skill_id} is deleted")
                continue
            if external_auth_id != INTERNAL_SYSTEM_EXTERNAL_AUTH_ID:
                failed_checks.append(f'default_chat.system_skills[{index}] skill_id {skill_id} must be owned by "{INTERNAL_SYSTEM_EXTERNAL_AUTH_ID}"')
                continue
            version_count = int((await connection.execute(_DEFAULT_CHAT_VERSION_SQL, {"skill_id": skill_id, "version_number": version_number})).scalar_one())
            if version_count != 1:
                failed_checks.append(f"default_chat.system_skills[{index}] version ({skill_id}, {version_number}) does not exist")

    if failed_checks:
        raise RuntimeError("Default chat system Skill config is invalid. " + "; ".join(failed_checks))
