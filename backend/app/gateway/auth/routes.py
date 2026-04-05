"""认证路由。"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Cookie, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel

from app.gateway.auth.keycloak import KeycloakClient, KeycloakError, get_keycloak_client
from app.gateway.auth.schemas import (
    AuthErrorResponse,
    CurrentUserResponse,
    LogoutResponse,
    RefreshResponse,
)
from app.gateway.auth.security import generate_pkce_pair, generate_state_nonce
from app.gateway.auth.service import (
    build_current_user_response,
    build_logout_response,
    build_refresh_response,
    sync_user_from_access_token,
)
from app.gateway.auth.web import (
    clear_temporary_auth_cookies,
    clear_token_cookies,
    decode_auth_state,
    encode_auth_state,
    get_login_origin,
    get_public_origin,
    is_https,
    normalize_return_to,
    set_temporary_auth_cookies,
    set_token_cookies,
)
from app.gateway.db.engine import get_db_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _build_json_response(payload: BaseModel) -> JSONResponse:
    """把 Pydantic 模型统一转换成 JSON 响应。"""
    return JSONResponse(payload.model_dump())


def _build_auth_error_response(
    detail: str,
    *,
    status_code: int,
    secure: bool,
    should_clear_tokens: bool = False,
) -> JSONResponse:
    """构造认证错误响应，并在需要时清理 token cookie。"""
    response = JSONResponse(AuthErrorResponse(detail=detail).model_dump(), status_code=status_code)
    if should_clear_tokens:
        clear_token_cookies(response, secure=secure)
    return response


def _raise_upstream_unavailable(detail: str, *, log_message: str) -> None:
    """统一抛出 Keycloak 上游不可用错误。"""
    logger.exception(log_message)
    raise HTTPException(status_code=503, detail=detail)


async def _load_current_user_response(
    *,
    access_token: str,
    keycloak_client: KeycloakClient,
) -> CurrentUserResponse:
    """同步当前用户并构造 `/api/auth/me` 成功响应。"""
    async with get_db_session() as db:
        user = await sync_user_from_access_token(
            db=db,
            access_token=access_token,
            keycloak_client=keycloak_client,
        )
    return build_current_user_response(user)


async def _exchange_callback_tokens(
    *,
    request: Request,
    code: str,
    pkce_verifier: str,
    keycloak_client: KeycloakClient,
) -> tuple[CurrentUserResponse, str, str, str, int, int]:
    """完成 callback 的 token 交换与用户同步。"""
    redirect_uri = f"{get_public_origin(request)}/api/auth/callback"
    token_response = await keycloak_client.exchange_code_for_tokens(
        code=code,
        redirect_uri=redirect_uri,
        code_verifier=pkce_verifier,
    )
    current_user = await _load_current_user_response(
        access_token=token_response.access_token,
        keycloak_client=keycloak_client,
    )
    return (
        current_user,
        token_response.access_token,
        token_response.refresh_token,
        token_response.id_token,
        token_response.expires_in,
        token_response.refresh_expires_in,
    )


async def _refresh_current_user_response(
    *,
    request: Request,
    refresh_token: str,
    keycloak_client: KeycloakClient,
) -> JSONResponse:
    """使用 refresh token 恢复登录态并回写 cookie。"""
    secure = is_https(request)

    try:
        token_response = await keycloak_client.refresh_access_token(refresh_token)
    except KeycloakError as exc:
        if exc.status >= 500:
            _raise_upstream_unavailable(
                "Authentication service unavailable",
                log_message="Keycloak refresh failed",
            )
        return _build_auth_error_response(
            "Session expired",
            status_code=401,
            secure=secure,
            should_clear_tokens=True,
        )

    try:
        payload = await _load_current_user_response(
            access_token=token_response.access_token,
            keycloak_client=keycloak_client,
        )
    except KeycloakError as exc:
        if exc.status >= 500:
            _raise_upstream_unavailable(
                "Authentication service unavailable",
                log_message="Keycloak userinfo after refresh failed",
            )
        return _build_auth_error_response(
            "Session expired",
            status_code=401,
            secure=secure,
            should_clear_tokens=True,
        )

    response = _build_json_response(payload)
    set_token_cookies(
        response,
        access_token=token_response.access_token,
        refresh_token=token_response.refresh_token,
        id_token=token_response.id_token,
        expires_in=token_response.expires_in,
        refresh_expires_in=token_response.refresh_expires_in,
        secure=secure,
    )
    return response


@router.get("/login")
async def login(
    request: Request,
    return_to: str = "/workspace",
) -> RedirectResponse:
    """发起登录流程。"""
    try:
        public_origin = get_login_origin(request)
        code_verifier, code_challenge = generate_pkce_pair()
        _, nonce = generate_state_nonce()
        state = encode_auth_state(nonce=nonce, return_to=return_to)

        auth_url = get_keycloak_client().build_auth_url(
            redirect_uri=f"{public_origin}/api/auth/callback",
            state=state,
            code_challenge=code_challenge,
        )
        logger.info("Login initiated, redirecting to Keycloak")

        redirect_response = RedirectResponse(url=auth_url, status_code=302)
        set_temporary_auth_cookies(
            redirect_response,
            code_verifier=code_verifier,
            csrf_nonce=nonce,
            secure=is_https(request),
        )
        return redirect_response
    except Exception:
        logger.exception("Login failed")
        return RedirectResponse(url="/?error=login_failed", status_code=302)


@router.get("/callback")
async def callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    pkce_verifier: str | None = Cookie(default=None),
    csrf_nonce: str | None = Cookie(default=None),
) -> RedirectResponse:
    """处理 Keycloak 回调。"""
    try:
        if not state:
            logger.error("Callback failed: missing state")
            return RedirectResponse(url="/?error=missing_state", status_code=302)

        state_payload = decode_auth_state(state)
        if state_payload is None:
            logger.error("Callback failed: invalid state JSON")
            return RedirectResponse(url="/?error=invalid_state", status_code=302)

        if not code:
            logger.error("Callback failed: missing code")
            return RedirectResponse(url="/?error=missing_code", status_code=302)

        if not csrf_nonce or csrf_nonce != state_payload.nonce:
            logger.error("Callback failed: CSRF check failed")
            return RedirectResponse(url="/?error=csrf_mismatch", status_code=302)

        if not pkce_verifier:
            logger.error("Callback failed: missing PKCE verifier")
            return RedirectResponse(url="/?error=missing_pkce", status_code=302)

        (
            current_user,
            access_token,
            refresh_token,
            id_token,
            expires_in,
            refresh_expires_in,
        ) = await _exchange_callback_tokens(
            request=request,
            code=code,
            pkce_verifier=pkce_verifier,
            keycloak_client=get_keycloak_client(),
        )

        response = RedirectResponse(
            url=normalize_return_to(state_payload.returnTo),
            status_code=302,
        )
        set_token_cookies(
            response,
            access_token=access_token,
            refresh_token=refresh_token,
            id_token=id_token,
            expires_in=expires_in,
            refresh_expires_in=refresh_expires_in,
            secure=is_https(request),
        )
        clear_temporary_auth_cookies(response, secure=is_https(request))

        logger.info("Login successful for user: %s", current_user.user.username)
        return response
    except KeycloakError as exc:
        logger.exception("Keycloak error during callback: %s", exc.detail)
        return RedirectResponse(url="/?error=keycloak_error", status_code=302)
    except Exception:
        logger.exception("Callback failed")
        return RedirectResponse(url="/?error=callback_failed", status_code=302)


@router.get(
    "/me",
    response_model=CurrentUserResponse,
    responses={
        401: {"model": AuthErrorResponse},
        503: {"model": AuthErrorResponse},
    },
)
async def me(
    request: Request,
    kc_access_token: str | None = Cookie(default=None),
    kc_refresh_token: str | None = Cookie(default=None),
) -> CurrentUserResponse | JSONResponse:
    """获取当前用户信息。"""
    if not kc_access_token and not kc_refresh_token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        keycloak_client = get_keycloak_client()
        if kc_access_token:
            try:
                return await _load_current_user_response(
                    access_token=kc_access_token,
                    keycloak_client=keycloak_client,
                )
            except KeycloakError as exc:
                if exc.status >= 500:
                    _raise_upstream_unavailable(
                        "Authentication service unavailable",
                        log_message="Keycloak userinfo failed",
                    )

        if not kc_refresh_token:
            return _build_auth_error_response(
                "Session expired",
                status_code=401,
                secure=is_https(request),
                should_clear_tokens=True,
            )

        return await _refresh_current_user_response(
            request=request,
            refresh_token=kc_refresh_token,
            keycloak_client=keycloak_client,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to get current user")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/logout", response_model=LogoutResponse)
async def logout(
    request: Request,
    kc_id_token: str | None = Cookie(default=None),
) -> JSONResponse:
    """登出。"""
    logout_url = f"{get_public_origin(request)}/"
    try:
        logout_url = get_keycloak_client().build_logout_url(
            id_token_hint=kc_id_token,
            post_logout_redirect_uri=logout_url,
        )
    except Exception:
        logger.exception("Logout failed")

    response = _build_json_response(build_logout_response(logout_url))
    clear_token_cookies(response, secure=is_https(request))
    logger.info("Logout successful")
    return response


@router.post(
    "/refresh",
    response_model=RefreshResponse,
    responses={
        401: {"model": AuthErrorResponse},
        503: {"model": AuthErrorResponse},
    },
)
async def refresh(
    request: Request,
    kc_refresh_token: str | None = Cookie(default=None),
) -> JSONResponse:
    """主动刷新 token。"""
    if not kc_refresh_token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        keycloak_client = get_keycloak_client()
        response = _build_json_response(build_refresh_response())
        token_response = await keycloak_client.refresh_access_token(kc_refresh_token)
        set_token_cookies(
            response,
            access_token=token_response.access_token,
            refresh_token=token_response.refresh_token,
            id_token=token_response.id_token,
            expires_in=token_response.expires_in,
            refresh_expires_in=token_response.refresh_expires_in,
            secure=is_https(request),
        )
        logger.info("Token refreshed successfully")
        return response
    except KeycloakError as exc:
        if exc.status >= 500:
            _raise_upstream_unavailable(
                "Authentication service unavailable",
                log_message="Refresh failed",
            )
        return _build_auth_error_response(
            "Refresh failed",
            status_code=401,
            secure=is_https(request),
            should_clear_tokens=True,
        )
    except Exception:
        logger.exception("Refresh failed")
        raise HTTPException(status_code=500, detail="Internal server error")
