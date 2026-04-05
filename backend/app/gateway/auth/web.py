"""认证 Web 辅助函数。"""

from __future__ import annotations

import time
from urllib.parse import urlparse

from fastapi import Request, Response
from pydantic import ValidationError

from app.gateway.auth.schemas import AuthStatePayload

DEFAULT_RETURN_TO = "/workspace"
COOKIE_SAMESITE = "lax"


def set_token_cookies(
    response: Response,
    *,
    access_token: str,
    refresh_token: str,
    id_token: str,
    expires_in: int,
    refresh_expires_in: int,
    secure: bool,
) -> None:
    """把 Keycloak token 集合写入浏览器 cookie。"""
    response.set_cookie(
        "kc_access_token",
        access_token,
        max_age=expires_in,
        httponly=True,
        secure=secure,
        samesite=COOKIE_SAMESITE,
        path="/",
    )
    response.set_cookie(
        "kc_refresh_token",
        refresh_token,
        max_age=refresh_expires_in,
        httponly=True,
        secure=secure,
        samesite=COOKIE_SAMESITE,
        path="/",
    )
    response.set_cookie(
        "kc_id_token",
        id_token,
        max_age=refresh_expires_in,
        httponly=True,
        secure=secure,
        samesite=COOKIE_SAMESITE,
        path="/",
    )
    response.set_cookie(
        "kc_expires_at",
        str(int(time.time() * 1000) + expires_in * 1000),
        max_age=expires_in,
        httponly=False,
        secure=secure,
        samesite=COOKIE_SAMESITE,
        path="/",
    )


def clear_token_cookies(response: Response, *, secure: bool) -> None:
    """清理 Gateway 持有的所有 Keycloak 登录态 cookie。"""
    for cookie_name, is_http_only in (
        ("kc_access_token", True),
        ("kc_refresh_token", True),
        ("kc_id_token", True),
        ("kc_expires_at", False),
    ):
        response.delete_cookie(
            cookie_name,
            path="/",
            secure=secure,
            httponly=is_http_only,
            samesite=COOKIE_SAMESITE,
        )


def set_temporary_auth_cookies(
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
        samesite=COOKIE_SAMESITE,
        path="/",
    )
    response.set_cookie(
        "csrf_nonce",
        csrf_nonce,
        max_age=600,
        httponly=True,
        secure=secure,
        samesite=COOKIE_SAMESITE,
        path="/",
    )


def clear_temporary_auth_cookies(response: Response, *, secure: bool) -> None:
    """清理登录阶段使用的短期上下文 cookie。"""
    for cookie_name in ("pkce_verifier", "csrf_nonce"):
        response.delete_cookie(
            cookie_name,
            path="/",
            secure=secure,
            httponly=True,
            samesite=COOKIE_SAMESITE,
        )


def get_public_origin(request: Request) -> str:
    """推导公开访问的 origin，优先信任代理头。"""
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
    """从 Referer 头提取 origin。"""
    referer = request.headers.get("referer")
    if not referer:
        return None

    parsed = urlparse(referer)
    if not parsed.scheme or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


def get_login_origin(request: Request) -> str:
    """登录入口优先沿用来源页 origin，缺失时回退到请求自身。"""
    return get_referer_origin(request) or get_public_origin(request)


def is_valid_return_to(return_to: str) -> bool:
    """仅允许站内相对路径，阻止开放重定向。"""
    return return_to.startswith("/") and not return_to.startswith("//")


def normalize_return_to(return_to: str | None) -> str:
    """把回跳路径标准化到安全的站内地址。"""
    if not return_to:
        return DEFAULT_RETURN_TO
    return return_to if is_valid_return_to(return_to) else DEFAULT_RETURN_TO


def is_https(request: Request) -> bool:
    """判断请求在公开侧是否为 HTTPS。"""
    proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip()
    if proto:
        return proto == "https"
    return request.url.scheme == "https"


def encode_auth_state(*, nonce: str, return_to: str) -> str:
    """生成回调所需的状态载荷。"""
    return AuthStatePayload(
        nonce=nonce,
        returnTo=normalize_return_to(return_to),
    ).model_dump_json()


def decode_auth_state(state: str) -> AuthStatePayload | None:
    """解析认证状态；对旧字段保持宽容，但只消费白名单字段。"""
    try:
        return AuthStatePayload.model_validate_json(state)
    except ValidationError:
        return None
