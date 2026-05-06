"""Gateway auth router mounted via the shared ecc-auth SDK."""

from __future__ import annotations

import os

import ecc_auth.routes as ecc_auth_routes
from ecc_auth import create_auth_router, init_dependencies
from ecc_auth.config import KeycloakConfig
from ecc_auth.identity import AuthIdentity
from fastapi import APIRouter
from starlette.requests import Request
from fastapi.responses import RedirectResponse

from app.gateway.auth.dev_synthetic_auth import (
    get_dev_synthetic_auth_identity,
    is_dev_synthetic_auth_enabled,
)
from app.gateway.auth.service import build_current_user_payload, sync_local_user_from_identity
from app.gateway.db.engine import get_db_session


def _is_tls_insecure() -> bool:
    return os.getenv("KEYCLOAK_TLS_INSECURE", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _get_required_env(name: str) -> str:
    value = os.environ[name].strip()
    if not value:
        raise RuntimeError(f"{name} must not be empty")
    return value


def _get_public_base_path() -> str:
    return (
        os.getenv("DEER_FLOW_PUBLIC_BASE_PATH")
        or os.getenv("NEXT_PUBLIC_BASE_PATH")
        or ""
    ).strip().rstrip("/")


def _with_public_base_path(origin: str) -> str:
    base_path = _get_public_base_path()
    if not base_path:
        return origin
    if not base_path.startswith("/"):
        base_path = f"/{base_path}"
    if origin.endswith(base_path):
        return origin
    return f"{origin.rstrip('/')}{base_path}"


def _patch_ecc_auth_public_origin() -> None:
    original_get_public_origin = ecc_auth_routes.get_public_origin
    print("ecc_auth_routes.get_public_origin:", ecc_auth_routes.get_public_origin)
    print("ecc_auth_routes:", ecc_auth_routes)
    def get_public_origin_with_base_path(request: Request) -> str:
        return _with_public_base_path(original_get_public_origin(request))

    ecc_auth_routes.get_public_origin = get_public_origin_with_base_path


def _build_keycloak_config() -> KeycloakConfig:
    """Build ecc-auth config and fail fast when required env is missing."""
    return KeycloakConfig(
        url=_get_required_env("KEYCLOAK_URL"),
        realm=_get_required_env("KEYCLOAK_REALM"),
        client_id=_get_required_env("KEYCLOAK_CLIENT_ID"),
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


def _safe_return_to(return_to: str | None) -> str:
    if not return_to or not return_to.startswith("/") or return_to.startswith("//"):
        return "/workspace"
    return return_to


def _create_dev_synthetic_auth_router() -> APIRouter:
    """Create development-only auth endpoints backed by a synthetic user."""
    router = APIRouter(prefix="/api/auth", tags=["auth"])

    @router.get("/login")
    async def dev_login(return_to: str | None = None) -> RedirectResponse:
        return RedirectResponse(_safe_return_to(return_to))

    @router.get("/callback")
    async def dev_callback(return_to: str | None = None) -> RedirectResponse:
        return RedirectResponse(_safe_return_to(return_to))

    @router.get("/me")
    async def dev_me() -> dict:
        async with get_db_session() as db:
            user = await build_current_user_payload(
                db=db,
                identity=get_dev_synthetic_auth_identity(),
            )
        return {"user": user}

    @router.post("/refresh")
    async def dev_refresh() -> dict:
        return {"ok": True}

    @router.post("/logout")
    async def dev_logout() -> dict:
        return {"logoutUrl": "/signed-out"}

    return router


def create_gateway_auth_router(config: KeycloakConfig | None = None) -> APIRouter:
    """Wrap the shared SDK router under DeerFlow's `/api/auth` prefix."""
    if config is None and is_dev_synthetic_auth_enabled():
        return _create_dev_synthetic_auth_router()

    resolved_config = config or _build_keycloak_config()
    init_dependencies(resolved_config)
    print("resolved_config:", resolved_config)
    _patch_ecc_auth_public_origin()

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
