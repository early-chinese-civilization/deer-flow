from __future__ import annotations

import importlib
import logging
from http.cookies import SimpleCookie
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import jwt
import pytest
from ecc_auth import AuthSessionMiddleware
from ecc_auth.config import KeycloakConfig
from ecc_auth.identity import AuthIdentity
from ecc_auth.routes import _decode_auth_state, _encode_auth_state
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from app.gateway import deps as gateway_deps
from app.gateway.auth import routes as auth_routes


class _SessionContext:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _make_config() -> KeycloakConfig:
    return KeycloakConfig(
        url="https://keycloak.example.com",
        realm="ecc",
        client_id="client-id",
        client_secret="",
        tls_insecure=False,
    )


def _cookie_headers(response) -> list[str]:
    get_cookies = getattr(response.headers, "get_list", None) or response.headers.getlist
    return list(get_cookies("set-cookie"))


def _make_client(*, raise_server_exceptions: bool = True) -> TestClient:
    app = FastAPI()
    app.add_middleware(AuthSessionMiddleware)
    app.include_router(auth_routes.create_gateway_auth_router(_make_config()))
    return TestClient(app, raise_server_exceptions=raise_server_exceptions)


def _cookie_value(response, name: str) -> str:
    cookie = SimpleCookie()
    get_cookies = getattr(response.headers, "get_list", None) or response.headers.getlist
    for header in get_cookies("set-cookie"):
        cookie.load(header)
    return cookie[name].value


def test_login_uses_origin_and_return_to_contract() -> None:
    client = _make_client()
    authorization_mock = AsyncMock(
        return_value={
            "url": "https://keycloak.example.com/authorize",
            "state": "opaque-state",
            "code_verifier": "pkce-verifier",
        }
    )

    with patch("ecc_auth.routes.build_authorization_url", authorization_mock):
        response = client.get(
            "/api/auth/login",
            params={"return_to": "/workspace/thread-1"},
            headers={"origin": "http://frontend.local"},
            follow_redirects=False,
        )

    assert response.status_code == 302
    state = authorization_mock.await_args.kwargs["state"]
    assert _decode_auth_state(state) == {
        "nonce": response.cookies["csrf_nonce"],
        "return_to": "/workspace/thread-1",
        "origin": "http://frontend.local",
    }
    assert response.cookies["pkce_verifier"] == "pkce-verifier"


def test_callback_forwards_ecc_auth_exchange_error_code_and_logs_redacted_detail(
    caplog: pytest.LogCaptureFixture,
) -> None:
    client = _make_client()
    state = _encode_auth_state(
        nonce="csrf-nonce",
        return_to="/workspace",
        origin="http://frontend.local",
    )
    request = httpx.Request("POST", "https://keycloak.example.com/token")
    response = httpx.Response(
        400,
        text='{"error":"invalid_grant","client_secret":"super-secret","refresh_token":"refresh-secret"}',
        request=request,
    )
    exchange_error = httpx.HTTPStatusError(
        "token endpoint rejected callback",
        request=request,
        response=response,
    )
    exchange_mock = AsyncMock(side_effect=exchange_error)

    caplog.set_level(logging.WARNING, logger="ecc_auth.callback_errors")
    with patch("ecc_auth.routes.exchange_code_for_token", exchange_mock):
        client.cookies.set("csrf_nonce", "csrf-nonce")
        client.cookies.set("pkce_verifier", "pkce-verifier")
        callback_response = client.get(
            "/api/auth/callback",
            params={"code": "auth-code", "state": state},
            follow_redirects=False,
        )

    assert callback_response.status_code == 302
    assert callback_response.headers["location"] == "http://frontend.local/?error=token_exchange_failed"
    assert "status_code=400" in caplog.text
    assert "response_body=" in caplog.text
    assert "super-secret" not in caplog.text
    assert "refresh-secret" not in caplog.text
    assert "<redacted>" in caplog.text


def test_callback_forwards_ecc_auth_user_sync_error_code() -> None:
    client = _make_client()
    state = _encode_auth_state(
        nonce="csrf-nonce",
        return_to="/workspace",
        origin="http://frontend.local",
    )
    exchange_mock = AsyncMock(
        return_value={
            "access_token": "access-token",
            "refresh_token": "refresh-token",
            "id_token": "id-token",
            "expires_in": 300,
            "refresh_expires_in": 1800,
        }
    )
    userinfo_mock = AsyncMock(
        return_value={
            "sub": "kc-sub",
            "name": "Alice",
            "preferred_username": "alice",
            "email": "alice@example.com",
            "email_verified": True,
        }
    )
    sync_mock = AsyncMock(side_effect=RuntimeError("local user projection failed"))

    with (
        patch("ecc_auth.routes.exchange_code_for_token", exchange_mock),
        patch("ecc_auth.routes.fetch_user_info", userinfo_mock),
        patch(
            "app.gateway.auth.routes.get_db_session",
            return_value=_SessionContext(object()),
        ),
        patch("app.gateway.auth.routes.sync_local_user_from_identity", sync_mock),
    ):
        client.cookies.set("csrf_nonce", "csrf-nonce")
        client.cookies.set("pkce_verifier", "pkce-verifier")
        callback_response = client.get(
            "/api/auth/callback",
            params={"code": "auth-code", "state": state},
            follow_redirects=False,
        )

    assert callback_response.status_code == 302
    assert callback_response.headers["location"] == "http://frontend.local/?error=user_sync_failed"
    sync_mock.assert_awaited_once()


def test_me_hydrates_deerflow_payload_via_shared_refresh_flow() -> None:
    client = _make_client()
    verify_mock = AsyncMock(
        side_effect=[
            jwt.ExpiredSignatureError("expired"),
            {
                "sub": "kc-sub",
                "name": "Alice",
                "preferred_username": "alice",
                "email": "alice@example.com",
                "email_verified": True,
            },
        ]
    )
    refresh_mock = AsyncMock(
        return_value={
            "access_token": "new-access-token",
            "refresh_token": "new-refresh-token",
            "id_token": "id-token",
            "expires_in": 300,
            "refresh_expires_in": 1800,
        }
    )
    payload_mock = AsyncMock(
        return_value={
            "id": 123,
            "externalAuthId": "kc-sub",
            "username": "alice",
            "displayName": "Alice",
            "email": "alice@example.com",
            "emailVerified": True,
        }
    )

    with (
        patch("ecc_auth.session.verify_access_token", verify_mock),
        patch("ecc_auth.session.refresh_token_request", refresh_mock),
        patch("app.gateway.auth.routes.get_db_session", return_value=_SessionContext(object())),
        patch("app.gateway.auth.routes.build_current_user_payload", payload_mock),
    ):
        client.cookies.set("kc_access_token", "expired-access-token")
        client.cookies.set("kc_refresh_token", "refresh-token")
        response = client.get("/api/auth/me")

    assert response.status_code == 200
    assert response.json()["user"]["externalAuthId"] == "kc-sub"
    refresh_mock.assert_awaited_once()
    payload_mock.assert_awaited_once()


def test_me_persists_rotated_cookies_when_payload_hydration_fails() -> None:
    client = _make_client(raise_server_exceptions=False)
    verify_mock = AsyncMock(
        side_effect=[
            jwt.ExpiredSignatureError("expired"),
            {
                "sub": "kc-sub",
                "name": "Alice",
                "preferred_username": "alice",
                "email": "alice@example.com",
                "email_verified": True,
            },
        ]
    )
    refresh_mock = AsyncMock(
        return_value={
            "access_token": "new-access-token",
            "refresh_token": "new-refresh-token",
            "id_token": "id-token",
            "expires_in": 300,
            "refresh_expires_in": 1800,
        }
    )
    payload_mock = AsyncMock(side_effect=RuntimeError("db down after refresh"))

    with (
        patch("ecc_auth.session.verify_access_token", verify_mock),
        patch("ecc_auth.session.refresh_token_request", refresh_mock),
        patch("app.gateway.auth.routes.get_db_session", return_value=_SessionContext(object())),
        patch("app.gateway.auth.routes.build_current_user_payload", payload_mock),
    ):
        client.cookies.set("kc_access_token", "expired-access-token")
        client.cookies.set("kc_refresh_token", "refresh-token")
        response = client.get("/api/auth/me")

    assert response.status_code == 500
    cookie_headers = _cookie_headers(response)
    assert any(header.startswith("kc_access_token=new-access-token") for header in cookie_headers)
    assert any(header.startswith("kc_refresh_token=new-refresh-token") for header in cookie_headers)


def test_logout_sets_explicit_logout_marker() -> None:
    client = _make_client()
    client.cookies.set("kc_id_token", "id-token")

    response = client.post("/api/auth/logout")

    assert response.status_code == 200
    assert _cookie_value(response, "kc_logout_marker") == "1"
    assert response.json()["logoutUrl"].startswith("https://keycloak.example.com/realms/ecc/protocol/openid-connect/logout")


def test_create_app_builds_auth_router_after_loading_config() -> None:
    call_order: list[str] = []
    gateway_app_module = importlib.import_module("app.gateway.app")

    def _load_config():
        call_order.append("config")
        return SimpleNamespace()

    def _create_auth_router():
        call_order.append("router")
        return APIRouter()

    with (
        patch("app.gateway.app.get_app_config", side_effect=_load_config),
        patch("app.gateway.app.auth_routes.create_gateway_auth_router", side_effect=_create_auth_router),
    ):
        gateway_app_module.create_app()

    assert call_order[:2] == ["config", "router"]


def test_create_gateway_auth_router_fails_fast_without_required_keycloak_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("KEYCLOAK_URL", raising=False)
    monkeypatch.setenv("KEYCLOAK_REALM", "ecc")
    monkeypatch.setenv("KEYCLOAK_CLIENT_ID", "client-id")

    with pytest.raises(KeyError):
        auth_routes.create_gateway_auth_router()


def test_create_gateway_auth_router_rejects_empty_required_keycloak_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("KEYCLOAK_URL", " ")
    monkeypatch.setenv("KEYCLOAK_REALM", "ecc")
    monkeypatch.setenv("KEYCLOAK_CLIENT_ID", "client-id")

    with pytest.raises(RuntimeError, match="KEYCLOAK_URL must not be empty"):
        auth_routes.create_gateway_auth_router()


def test_dev_synthetic_auth_router_does_not_require_keycloak_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEER_FLOW_DEV_SYNTHETIC_AUTH", "1")
    monkeypatch.setenv("DEER_FLOW_SERVER_MODE", "dev")
    monkeypatch.delenv("KEYCLOAK_URL", raising=False)
    monkeypatch.delenv("KEYCLOAK_REALM", raising=False)
    monkeypatch.delenv("KEYCLOAK_CLIENT_ID", raising=False)

    app = FastAPI()
    app.include_router(auth_routes.create_gateway_auth_router())
    payload_mock = AsyncMock(
        return_value={
            "id": 1,
            "externalAuthId": "dev-local-user",
            "username": "dev",
            "displayName": "DeerFlow Dev",
            "email": "dev@localhost",
            "emailVerified": True,
        }
    )

    with (
        patch(
            "app.gateway.auth.routes.get_db_session",
            return_value=_SessionContext(object()),
        ),
        patch("app.gateway.auth.routes.build_current_user_payload", payload_mock),
    ):
        response = TestClient(app).get("/api/auth/me")

    assert response.status_code == 200
    assert response.json()["user"]["externalAuthId"] == "dev-local-user"
    payload_mock.assert_awaited_once()


def test_dev_synthetic_auth_rejects_production_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEER_FLOW_DEV_SYNTHETIC_AUTH", "1")
    monkeypatch.setenv("DEER_FLOW_SERVER_MODE", "prod")

    with pytest.raises(RuntimeError, match="cannot be enabled in production mode"):
        auth_routes.create_gateway_auth_router()


@pytest.mark.anyio
async def test_gateway_dependency_projects_auth_identity_to_local_user() -> None:
    identity = AuthIdentity(
        external_auth_id="kc-sub",
        email="alice@example.com",
        display_name="Alice",
        username="alice",
        email_verified=True,
    )
    user = SimpleNamespace(id=7, external_auth_id="kc-sub")

    with patch(
        "app.gateway.deps.sync_local_user_from_identity",
        AsyncMock(return_value=user),
    ) as sync_mock:
        result = await gateway_deps.get_current_user(db=object(), identity=identity)

    assert result is user
    sync_mock.assert_awaited_once()


@pytest.mark.anyio
async def test_gateway_dependency_uses_dev_synthetic_user_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEER_FLOW_DEV_SYNTHETIC_AUTH", "1")
    monkeypatch.setenv("DEER_FLOW_SERVER_MODE", "dev")
    auth_mock = AsyncMock()

    with patch("app.gateway.deps.get_current_auth_identity", auth_mock):
        identity = await gateway_deps.get_gateway_auth_identity(request=object())

    assert identity.external_auth_id == "dev-local-user"
    auth_mock.assert_not_called()


@pytest.mark.anyio
async def test_current_user_projects_dev_synthetic_identity_to_local_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEER_FLOW_DEV_SYNTHETIC_AUTH", "1")
    monkeypatch.setenv("DEER_FLOW_SERVER_MODE", "dev")
    user = SimpleNamespace(id=42, external_auth_id="dev-local-user")

    identity = await gateway_deps.get_gateway_auth_identity(request=object())
    with patch(
        "app.gateway.deps.sync_local_user_from_identity",
        AsyncMock(return_value=user),
    ) as sync_mock:
        result = await gateway_deps.get_current_user(db=object(), identity=identity)

    assert result is user
    synced_identity = sync_mock.await_args.kwargs["identity"]
    assert synced_identity.external_auth_id == "dev-local-user"
