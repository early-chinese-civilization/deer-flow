"""认证路由

实现 OAuth 2.0 Authorization Code + PKCE 流程。

路由：
- GET /api/auth/login - 发起登录
- GET /api/auth/callback - 处理回调
- GET /api/auth/me - 获取当前用户
- POST /api/auth/logout - 登出
- POST /api/auth/refresh - 刷新 token
"""
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.gateway.auth.keycloak import KeycloakError, get_keycloak_client
from app.gateway.auth.security import generate_pkce_pair, generate_state_nonce
from app.gateway.auth.session import SessionManager
from app.gateway.db.repository import UserRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


def get_public_origin(request: Request) -> str:
    """推导公开访问的 origin（处理反向代理）

    优先使用 x-forwarded-proto 和 x-forwarded-host。

    Args:
        request: FastAPI Request 对象

    Returns:
        公开 origin（如 https://example.com）
    """
    # 优先使用 x-forwarded-* 头（反向代理场景）
    proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip()
    host = request.headers.get("x-forwarded-host") or request.headers.get("host")

    if proto and host:
        return f"{proto}://{host}"

    if host:
        scheme = "https" if request.url.scheme == "https" else "http"
        return f"{scheme}://{host}"

    return str(request.base_url).rstrip("/")


def get_referer_origin(request: Request) -> Optional[str]:
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
    response: Response,
    return_to: str = "/workspace",
):
    """发起登录流程

    生成 PKCE 参数和 state，设置临时 cookie，重定向到 Keycloak。

    Args:
        request: FastAPI Request
        response: FastAPI Response
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
        state_token, nonce = generate_state_nonce()

        # State 包含 nonce、returnTo 和 publicOrigin
        state_data = {
            "nonce": nonce,
            "returnTo": return_to,
            "publicOrigin": public_origin,
        }
        state = json.dumps(state_data)

        # 设置临时 cookie（10分钟）
        secure = is_https(request)
        response.set_cookie(
            "pkce_verifier",
            code_verifier,
            max_age=600,
            httponly=True,
            secure=secure,
            samesite="lax",
        )
        response.set_cookie(
            "csrf_nonce",
            nonce,
            max_age=600,
            httponly=True,
            secure=secure,
            samesite="lax",
        )

        # 构造 Keycloak 授权 URL
        kc_client = get_keycloak_client()
        redirect_uri = f"{public_origin}/api/auth/callback"
        auth_url = kc_client.build_auth_url(
            redirect_uri=redirect_uri,
            state=state,
            code_challenge=code_challenge,
        )

        logger.info(f"Login initiated, redirecting to Keycloak: {auth_url}")
        return RedirectResponse(url=auth_url, status_code=302)

    except Exception as e:
        logger.exception("Login failed")
        return RedirectResponse(url=f"/?error=login_failed", status_code=302)


@router.get("/callback")
async def callback(
    request: Request,
    response: Response,
    code: Optional[str] = None,
    state: Optional[str] = None,
    pkce_verifier: Optional[str] = Cookie(default=None),
    csrf_nonce: Optional[str] = Cookie(default=None),
):
    """处理 Keycloak 回调

    校验 state、code、CSRF，交换 token，创建用户和会话。

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

        # 6. 获取用户信息
        user_info = await kc_client.fetch_user_info(token_response.access_token)

        # 7. Upsert 用户
        from app.gateway.db.engine import get_db_session
        async with get_db_session() as db:
            user = await UserRepository.upsert_user(
                db=db,
                external_auth_id=user_info.sub,
                username=user_info.preferred_username,
                display_name=user_info.name,
                email=user_info.email,
                given_name=user_info.given_name,
                family_name=user_info.family_name,
                email_verified=user_info.email_verified,
            )

            # 8. 创建会话
            session_id = await SessionManager.create_session(
                db=db,
                user_id=user.id,
                refresh_token=token_response.refresh_token,
                access_token=token_response.access_token,
                id_token=token_response.id_token,
                expires_in=token_response.expires_in,
            )

        # 9. 设置 session cookie
        secure = is_https(request)
        response = RedirectResponse(
            url=state_data.get("returnTo", "/workspace"),
            status_code=302
        )
        response.set_cookie(
            "deer_session",
            session_id,
            max_age=7 * 24 * 3600,  # 7 天
            httponly=True,
            secure=secure,
            samesite="lax",
            path="/",
        )

        # 10. 清除临时 cookie
        response.delete_cookie("pkce_verifier")
        response.delete_cookie("csrf_nonce")

        logger.info(f"Login successful for user: {user.username}")
        return response

    except KeycloakError as e:
        logger.exception(f"Keycloak error: {e.detail}")
        return RedirectResponse(url="/?error=keycloak_error", status_code=302)
    except Exception as e:
        logger.exception("Callback failed")
        return RedirectResponse(url="/?error=callback_failed", status_code=302)


@router.get("/me")
async def me(
    request: Request,
    deer_session: Optional[str] = Cookie(default=None),
):
    """获取当前用户信息

    支持懒刷新：如果 access_token 过期，自动使用 refresh_token 刷新。

    Args:
        request: FastAPI Request
        deer_session: 会话ID（来自 cookie）

    Returns:
        用户信息 JSON
    """
    if not deer_session:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        from app.gateway.db.engine import get_db_session

        async with get_db_session() as db:
            # 获取会话
            session = await SessionManager.get_session(db, deer_session)
            if not session:
                raise HTTPException(status_code=401, detail="Invalid session")

            # 检查过期
            now = datetime.now(timezone.utc)
            if session.expires_at < now:
                # 尝试刷新
                logger.info("Session expired, attempting refresh")
                try:
                    kc_client = get_keycloak_client()
                    refresh_token = SessionManager.get_refresh_token(session)
                    token_response = await kc_client.refresh_access_token(refresh_token)

                    # 更新会话
                    await SessionManager.update_session_tokens(
                        db=db,
                        session_id=deer_session,
                        refresh_token=token_response.refresh_token,
                        access_token=token_response.access_token,
                        id_token=token_response.id_token,
                        expires_in=token_response.expires_in,
                    )

                    logger.info("Session refreshed successfully")

                except KeycloakError:
                    # 刷新失败，删除会话
                    logger.warning("Refresh failed, deleting session")
                    await SessionManager.delete_session(db, deer_session)
                    raise HTTPException(status_code=401, detail="Session expired and refresh failed")

            # 获取用户
            user = await UserRepository.get_user_by_id(db, session.user_id)
            if not user:
                raise HTTPException(status_code=401, detail="User not found")

            return JSONResponse({
                "user": {
                    "id": user.id,
                    "externalAuthId": user.external_auth_id,
                    "username": user.username,
                    "displayName": user.display_name,
                    "email": user.email,
                    "givenName": user.given_name,
                    "familyName": user.family_name,
                    "emailVerified": user.email_verified,
                }
            })

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to get current user")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    deer_session: Optional[str] = Cookie(default=None),
):
    """登出

    删除本地会话，返回 Keycloak 登出 URL。

    Args:
        request: FastAPI Request
        response: FastAPI Response
        deer_session: 会话ID（来自 cookie）

    Returns:
        包含 logoutUrl 的 JSON
    """
    logout_url = f"{get_public_origin(request)}/"

    if deer_session:
        try:
            from app.gateway.db.engine import get_db_session

            async with get_db_session() as db:
                # 获取会话（用于获取 id_token）
                session = await SessionManager.get_session(db, deer_session)
                id_token = session.id_token if session else None

                # 删除会话
                await SessionManager.delete_session(db, deer_session)

                # 构造 Keycloak 登出 URL
                kc_client = get_keycloak_client()
                logout_url = kc_client.build_logout_url(
                    id_token_hint=id_token,
                    post_logout_redirect_uri=f"{get_public_origin(request)}/",
                )

        except Exception as e:
            logger.exception("Logout failed")

    # 清除 session cookie
    response = JSONResponse({"logoutUrl": logout_url})
    response.delete_cookie("deer_session", path="/")

    logger.info("Logout successful")
    return response


@router.post("/refresh")
async def refresh(
    deer_session: Optional[str] = Cookie(default=None),
):
    """主动刷新 token

    Args:
        deer_session: 会话ID（来自 cookie）

    Returns:
        成功状态 JSON
    """
    if not deer_session:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        from app.gateway.db.engine import get_db_session

        async with get_db_session() as db:
            # 获取会话
            session = await SessionManager.get_session(db, deer_session)
            if not session:
                raise HTTPException(status_code=401, detail="Invalid session")

            # 刷新 token
            kc_client = get_keycloak_client()
            refresh_token = SessionManager.get_refresh_token(session)
            token_response = await kc_client.refresh_access_token(refresh_token)

            # 更新会话
            await SessionManager.update_session_tokens(
                db=db,
                session_id=deer_session,
                refresh_token=token_response.refresh_token,
                access_token=token_response.access_token,
                id_token=token_response.id_token,
                expires_in=token_response.expires_in,
            )

            logger.info("Token refreshed successfully")
            return JSONResponse({"ok": True})

    except KeycloakError as e:
        logger.exception("Refresh failed")
        raise HTTPException(status_code=401, detail="Refresh failed")
    except Exception as e:
        logger.exception("Refresh failed")
        raise HTTPException(status_code=500, detail="Internal server error")
