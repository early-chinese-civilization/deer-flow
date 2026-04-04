"""认证路由。

实现 DeerFlow v1 的 Gateway + Keycloak + HttpOnly `kc_*` cookie 流程。
"""
from __future__ import annotations

import json
import logging
import time

from fastapi import APIRouter, Cookie, HTTPException, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel

from app.gateway.auth.keycloak import KeycloakError, get_keycloak_client
from app.gateway.auth.schemas import AuthErrorResponse, CurrentUserResponse, LogoutResponse, RefreshResponse
from app.gateway.auth.security import generate_pkce_pair, generate_state_nonce
from app.gateway.auth.service import (
    build_current_user_response,
    build_logout_response,
    build_refresh_response,
    sync_user_from_access_token,
    upsert_local_user_from_userinfo,
)
from app.gateway.db.engine import get_db_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _set_token_cookies(
    response: Response,
    *,
    access_token: str,
    refresh_token: str,
    id_token: str,
    expires_in: int,
    refresh_expires_in: int,
    secure: bool,
) -> None:
    """把 Keycloak token 集合写入浏览器 HttpOnly cookie。"""
    response.set_cookie(
        "kc_access_token",
        access_token,
        max_age=expires_in,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        "kc_refresh_token",
        refresh_token,
        max_age=refresh_expires_in,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        "kc_id_token",
        id_token,
        max_age=refresh_expires_in,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        "kc_expires_at",
        str(int(time.time() * 1000) + expires_in * 1000),
        max_age=expires_in,
        httponly=False,
        secure=secure,
        samesite="lax",
        path="/",
    )


def _clear_token_cookies(response: Response, *, secure: bool) -> None:
    """清理 Gateway 持有的所有 Keycloak 登录态 cookie。"""
    for cookie_name in ("kc_access_token", "kc_refresh_token", "kc_id_token"):
        response.delete_cookie(
            cookie_name,
            path="/",
            secure=secure,
            httponly=True,
            samesite="lax",
        )
    response.delete_cookie(
        "kc_expires_at",
        path="/",
        secure=secure,
        httponly=False,
        samesite="lax",
    )


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
        _clear_token_cookies(response, secure=secure)
    return response


def _raise_upstream_unavailable(detail: str, *, log_message: str) -> None:
    """统一抛出 Keycloak 上游不可用错误。"""
    logger.exception(log_message)
    raise HTTPException(status_code=503, detail=detail)


def _set_temporary_auth_cookies(
    response: Response,
    *,
    code_verifier: str,
    csrf_nonce: str,
    secure: bool,
) -> None:
    """写入 callback 校验所需的短期 cookie。"""
    response.set_cookie(
        "pkce_verifier",
        code_verifier,
        max_age=600,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        "csrf_nonce",
        csrf_nonce,
        max_age=600,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )


def _clear_temporary_auth_cookies(response: Response, *, secure: bool) -> None:
    """清理登录阶段使用的短期上下文 cookie。"""
    response.delete_cookie("pkce_verifier", path="/", secure=secure, httponly=True, samesite="lax")
    response.delete_cookie("csrf_nonce", path="/", secure=secure, httponly=True, samesite="lax")


async def _load_current_user_response(
    *,
    access_token: str,
    keycloak_client,
):
    """用 access token 获取并同步当前用户，然后构造响应模型。"""
    async with get_db_session() as db:
        user = await sync_user_from_access_token(
            db=db,
            access_token=access_token,
            keycloak_client=keycloak_client,
        )
    return build_current_user_response(user)


def get_public_origin(request: Request) -> str:
    """推导公开访问的 origin（处理反向代理）

    优先使用 x-forwarded-proto 和 x-forwarded-host。

    Args:
        request: FastAPI Request 对象

    Returns:
        公开 origin（如 https://example.com）
    """
    # 反向代理可能传递逗号分隔的 forwarded 值，这里始终取第一跳。
    proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip()
    forwarded_host = request.headers.get("x-forwarded-host", "").split(",")[0].strip()
    host = request.headers.get("host", "").split(",")[0].strip()

    if proto and forwarded_host:
        return f"{proto}://{forwarded_host}"

    if proto and host:
        return f"{proto}://{host}"

    if host:
        scheme = "https" if request.url.scheme == "https" else "http"
        return f"{scheme}://{host}"

    return str(request.base_url).rstrip("/")


def get_referer_origin(request: Request) -> str | None:
    """从 Referer 头获取 origin

    Args:
        request: FastAPI Request 对象

    Returns:
        Referer origin，如果不存在则返回 None
    """
    referer = request.headers.get("referer")
    if not referer:
        return None

    # 提取 origin（去掉路径）
    from urllib.parse import urlparse
    parsed = urlparse(referer)
    return f"{parsed.scheme}://{parsed.netloc}"


def is_valid_return_to(return_to: str) -> bool:
    """校验 returnTo 参数（防止开放重定向）

    Args:
        return_to: returnTo 参数

    Returns:
        是否有效
    """
    # 必须是相对路径
    if not return_to.startswith("/"):
        return False
    # 防止开放重定向（//example.com）
    if return_to.startswith("//"):
        return False
    return True


def is_https(request: Request) -> bool:
    """判断是否为 HTTPS 请求

    Args:
        request: FastAPI Request 对象

    Returns:
        是否为 HTTPS
    """
    proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip()
    if proto:
        return proto == "https"
    return request.url.scheme == "https"


@router.get("/login")
async def login(
    request: Request,
    return_to: str = "/workspace",
) -> RedirectResponse:
    """发起登录流程

    生成 PKCE 参数和 state，设置临时 cookie，重定向到 Keycloak。

    Args:
        request: FastAPI Request
        return_to: 登录成功后跳转的路径（默认 /workspace）

    Returns:
        重定向到 Keycloak 授权页面
    """
    try:
        # 校验 returnTo
        if not is_valid_return_to(return_to):
            return_to = "/workspace"

        # 推导 public origin
        public_origin = get_referer_origin(request) or get_public_origin(request)

        # 生成 PKCE
        code_verifier, code_challenge = generate_pkce_pair()

        # 生成 state 和 nonce（CSRF 保护）
        _, nonce = generate_state_nonce()

        # State 包含 nonce、returnTo 和 publicOrigin
        state_data = {
            "nonce": nonce,
            "returnTo": return_to,
            "publicOrigin": public_origin,
        }
        state = json.dumps(state_data)

        # 构造 Keycloak 授权 URL
        kc_client = get_keycloak_client()
        redirect_uri = f"{public_origin}/api/auth/callback"
        auth_url = kc_client.build_auth_url(
            redirect_uri=redirect_uri,
            state=state,
            code_challenge=code_challenge,
        )

        logger.info(f"Login initiated, redirecting to Keycloak: {auth_url}")

        # 临时认证 cookie 必须绑定到最终返回的 RedirectResponse，
        # 否则浏览器收不到 CSRF/PKCE 上下文，callback 会直接校验失败。
        redirect_response = RedirectResponse(url=auth_url, status_code=302)
        secure = is_https(request)
        _set_temporary_auth_cookies(
            redirect_response,
            code_verifier=code_verifier,
            csrf_nonce=nonce,
            secure=secure,
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
    """处理 Keycloak 回调

    校验 state、code、CSRF，交换 token，创建用户并写入 `kc_*` cookie。

    Args:
        request: FastAPI Request
        response: FastAPI Response
        code: 授权码
        state: State 参数
        pkce_verifier: PKCE code_verifier（来自 cookie）
        csrf_nonce: CSRF nonce（来自 cookie）

    Returns:
        重定向到 returnTo 或错误页面
    """
    try:
        # 1. 校验 state
        if not state:
            logger.error("Callback failed: missing state")
            return RedirectResponse(url="/?error=missing_state", status_code=302)

        try:
            state_data = json.loads(state)
        except json.JSONDecodeError:
            logger.error("Callback failed: invalid state JSON")
            return RedirectResponse(url="/?error=invalid_state", status_code=302)

        # 2. 校验 code
        if not code:
            logger.error("Callback failed: missing code")
            return RedirectResponse(url="/?error=missing_code", status_code=302)

        # 3. 校验 CSRF
        if not csrf_nonce or csrf_nonce != state_data.get("nonce"):
            logger.error("Callback failed: CSRF check failed")
            return RedirectResponse(url="/?error=csrf_mismatch", status_code=302)

        # 4. 校验 PKCE verifier
        if not pkce_verifier:
            logger.error("Callback failed: missing PKCE verifier")
            return RedirectResponse(url="/?error=missing_pkce", status_code=302)

        # 5. 交换 token
        kc_client = get_keycloak_client()
        public_origin = state_data.get("publicOrigin", get_public_origin(request))
        redirect_uri = f"{public_origin}/api/auth/callback"

        token_response = await kc_client.exchange_code_for_tokens(
            code=code,
            redirect_uri=redirect_uri,
            code_verifier=pkce_verifier,
        )

        # 6. 获取用户信息并同步本地 users 表
        user_info = await kc_client.fetch_user_info(token_response.access_token)
        async with get_db_session() as db:
            user = await upsert_local_user_from_userinfo(db=db, user_info=user_info)

        # 8. 设置 Keycloak token cookie
        secure = is_https(request)
        response = RedirectResponse(
            url=state_data.get("returnTo", "/workspace"),
            status_code=302
        )
        _set_token_cookies(
            response,
            access_token=token_response.access_token,
            refresh_token=token_response.refresh_token,
            id_token=token_response.id_token,
            expires_in=token_response.expires_in,
            refresh_expires_in=token_response.refresh_expires_in,
            secure=secure,
        )

        # 临时认证 cookie 只用于完成 callback 校验，成功后必须立即清理。
        _clear_temporary_auth_cookies(response, secure=secure)

        logger.info(f"Login successful for user: {user.username}")
        return response

    except KeycloakError as e:
        logger.exception(f"Keycloak error: {e.detail}")
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
    """获取当前用户信息

    支持懒刷新：优先 userinfo，失败后自动使用 refresh_token 恢复。

    Args:
        request: FastAPI Request
        kc_access_token: Access token（来自 HttpOnly cookie）
        kc_refresh_token: Refresh token（来自 HttpOnly cookie）

    Returns:
        用户信息 JSON
    """
    if not kc_access_token and not kc_refresh_token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        kc_client = get_keycloak_client()
        secure = is_https(request)

        if kc_access_token:
            try:
                return await _load_current_user_response(
                    access_token=kc_access_token,
                    keycloak_client=kc_client,
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
                secure=secure,
                should_clear_tokens=True,
            )

        # 只有 `/api/auth/me` 和 `/api/auth/refresh` 负责懒刷新并回写 cookie，
        # 普通依赖解析则只消费当前 cookie，避免在无明确响应上下文里隐式改写浏览器状态。
        try:
            token_response = await kc_client.refresh_access_token(kc_refresh_token)
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
                keycloak_client=kc_client,
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
        _set_token_cookies(
            response,
            access_token=token_response.access_token,
            refresh_token=token_response.refresh_token,
            id_token=token_response.id_token,
            expires_in=token_response.expires_in,
            refresh_expires_in=token_response.refresh_expires_in,
            secure=secure,
        )
        return response

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
    """登出

    清理本地 `kc_*` cookie，返回 Keycloak logout URL。

    Args:
        request: FastAPI Request
        kc_id_token: ID token（来自 HttpOnly cookie）

    Returns:
        包含 logoutUrl 的 JSON
    """
    logout_url = f"{get_public_origin(request)}/"

    try:
        kc_client = get_keycloak_client()
        logout_url = kc_client.build_logout_url(
            id_token_hint=kc_id_token,
            post_logout_redirect_uri=f"{get_public_origin(request)}/",
        )
    except Exception:
        logger.exception("Logout failed")

    response = _build_json_response(build_logout_response(logout_url))
    _clear_token_cookies(response, secure=is_https(request))

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
    """主动刷新 token

    Args:
        kc_refresh_token: Refresh token（来自 HttpOnly cookie）

    Returns:
        成功状态 JSON
    """
    if not kc_refresh_token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        kc_client = get_keycloak_client()
        token_response = await kc_client.refresh_access_token(kc_refresh_token)
        response = _build_json_response(build_refresh_response())
        _set_token_cookies(
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

    except KeycloakError as e:
        if e.status >= 500:
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
