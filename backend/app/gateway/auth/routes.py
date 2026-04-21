"""Gateway auth router mounted via the shared ecc-auth SDK."""

from __future__ import annotations

import os

from ecc_auth import create_auth_router, init_dependencies
from ecc_auth.config import KeycloakConfig
from ecc_auth.identity import AuthIdentity
from fastapi import APIRouter

from app.gateway.auth.service import build_current_user_payload, sync_local_user_from_identity
from app.gateway.db.engine import get_db_session


def _is_tls_insecure() -> bool:
    return os.getenv("KEYCLOAK_TLS_INSECURE", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _build_keycloak_config() -> KeycloakConfig:
    """Build ecc-auth config without forcing a confidential-client secret."""
    return KeycloakConfig(
        url=os.getenv("KEYCLOAK_URL", ""),
        realm=os.getenv("KEYCLOAK_REALM", ""),
        client_id=os.getenv("KEYCLOAK_CLIENT_ID", ""),
        client_secret=os.getenv("KEYCLOAK_CLIENT_SECRET", ""),
        tls_insecure=_is_tls_insecure(),
    )


async def _on_user_authenticated(identity: AuthIdentity) -> None:
    """Keep DeerFlow's local user projection warm on successful login."""
    async with get_db_session() as db:
        await sync_local_user_from_identity(db=db, identity=identity)


async def _load_current_user(identity: AuthIdentity) -> dict:
    """Map the shared identity back into DeerFlow's existing `/me` payload."""
    async with get_db_session() as db:
        return await build_current_user_payload(db=db, identity=identity)


def create_gateway_auth_router(config: KeycloakConfig | None = None) -> APIRouter:
    """Wrap the shared SDK router under DeerFlow's `/api/auth` prefix."""
    resolved_config = config or _build_keycloak_config()
    init_dependencies(resolved_config)

    router = APIRouter(prefix="/api/auth", tags=["auth"])
    router.include_router(
        create_auth_router(
            resolved_config,
            on_user_authenticated=_on_user_authenticated,
            load_current_user=_load_current_user,
            default_return_to="/workspace",
        )
    )
    return router
