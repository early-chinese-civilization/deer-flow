"""Shared Gateway database schema settings."""

from __future__ import annotations

import os
import re

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def get_gateway_db_schema() -> str:
    """Return the schema name used for Gateway-owned PostgreSQL objects."""
    return os.getenv("DEER_FLOW_DB_SCHEMA", "public")


def format_search_path(schema: str | None = None) -> str:
    """Format a schema name for PostgreSQL search_path."""
    value = schema or get_gateway_db_schema()
    if _IDENTIFIER_RE.fullmatch(value):
        return value
    return f'"{value.replace('"', '""')}"'


def get_gateway_db_connect_args() -> dict[str, dict[str, str]]:
    """Return psycopg connect args that pin the search_path to the Gateway schema."""
    return {"server_settings": {"search_path": format_search_path()}}
