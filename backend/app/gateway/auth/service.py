"""认证共享服务。

收敛 routes / deps 中重复的用户同步和响应构造逻辑。
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.gateway.auth.keycloak import KeycloakClient, KeycloakUserInfo, get_keycloak_client
from app.gateway.auth.schemas import AuthUserPayload, CurrentUserResponse, LogoutResponse, RefreshResponse
from app.gateway.db.models import User
from app.gateway.db.repository import UserRepository


async def upsert_local_user_from_userinfo(
    *,
    db: AsyncSession,
    user_info: KeycloakUserInfo,
) -> User:
    """把 Keycloak 用户信息同步到本地 `users` 表。"""
    return await UserRepository.upsert_user(
        db=db,
        external_auth_id=user_info.sub,
        username=user_info.preferred_username,
        display_name=user_info.name or user_info.preferred_username,
        email=user_info.email,
        given_name=user_info.given_name,
        family_name=user_info.family_name,
        email_verified=user_info.email_verified,
    )


async def sync_user_from_access_token(
    *,
    db: AsyncSession,
    access_token: str,
    keycloak_client: KeycloakClient | None = None,
) -> User:
    """用 access token 拉取 userinfo，并同步本地用户。"""
    kc_client = keycloak_client or get_keycloak_client()
    user_info = await kc_client.fetch_user_info(access_token)
    return await upsert_local_user_from_userinfo(db=db, user_info=user_info)


def build_current_user_response(user: User) -> CurrentUserResponse:
    """构造 `/api/auth/me` 成功响应。"""
    return CurrentUserResponse(user=AuthUserPayload.from_user(user))


def build_logout_response(logout_url: str) -> LogoutResponse:
    """构造 `/api/auth/logout` 成功响应。"""
    return LogoutResponse(logoutUrl=logout_url)


def build_refresh_response() -> RefreshResponse:
    """构造 `/api/auth/refresh` 成功响应。"""
    return RefreshResponse(ok=True)
