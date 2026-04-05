"""Keycloak OpenID Connect 客户端。"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class TokenResponse:
    """Token 响应。"""

    access_token: str
    expires_in: int
    refresh_token: str
    refresh_expires_in: int
    token_type: str
    id_token: str
    scope: str


@dataclass(slots=True)
class KeycloakUserInfo:
    """Keycloak 用户信息。"""

    sub: str
    name: str
    preferred_username: str
    given_name: str | None = None
    family_name: str | None = None
    email: str | None = None
    email_verified: bool = False


class KeycloakError(Exception):
    """Keycloak 错误。"""

    def __init__(self, message: str, status: int, detail: str | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.detail = detail


def _is_tls_insecure() -> bool:
    """仅在显式开启时跳过 Keycloak TLS 校验。"""
    return os.getenv("KEYCLOAK_TLS_INSECURE", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _get_httpx_verify() -> bool:
    """生产默认严格校验证书，本地可通过环境变量关闭。"""
    return not _is_tls_insecure()


class KeycloakClient:
    """Keycloak 客户端。"""

    def __init__(self) -> None:
        self.url = os.getenv("KEYCLOAK_URL", "")
        self.realm = os.getenv("KEYCLOAK_REALM", "")
        self.client_id = os.getenv("KEYCLOAK_CLIENT_ID", "")
        self.client_secret = os.getenv("KEYCLOAK_CLIENT_SECRET", "")
        self.auth_url = f"{self.url}/realms/{self.realm}/protocol/openid-connect"

        if not all([self.url, self.realm, self.client_id]):
            raise ValueError(
                "Keycloak configuration incomplete: "
                "KEYCLOAK_URL, KEYCLOAK_REALM, KEYCLOAK_CLIENT_ID are required"
            )

        logger.info(
            "Keycloak client configured: realm=%s client_id=%s has_client_secret=%s tls_insecure=%s",
            self.realm,
            self.client_id,
            bool(self.client_secret),
            _is_tls_insecure(),
        )

    def build_auth_url(
        self,
        *,
        redirect_uri: str,
        state: str,
        code_challenge: str,
        code_challenge_method: str = "S256",
    ) -> str:
        """构造授权 URL。"""
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "scope": "openid profile email",
            "redirect_uri": redirect_uri,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": code_challenge_method,
        }
        return f"{self.auth_url}/auth?{urlencode(params)}"

    def build_logout_url(
        self,
        *,
        id_token_hint: str | None,
        post_logout_redirect_uri: str,
    ) -> str:
        """构造登出 URL。"""
        params = {
            "client_id": self.client_id,
            "post_logout_redirect_uri": post_logout_redirect_uri,
        }
        if id_token_hint:
            params["id_token_hint"] = id_token_hint
        return f"{self.auth_url}/logout?{urlencode(params)}"

    def _build_token_request_data(self, payload: dict[str, str]) -> dict[str, str]:
        """兼容 public/confidential client，两种模式统一从环境变量驱动。"""
        data = {
            **payload,
            "client_id": self.client_id,
        }
        if self.client_secret:
            data["client_secret"] = self.client_secret
        return data

    @staticmethod
    def _read_error_detail(response: httpx.Response) -> str | None:
        """从 Keycloak 错误响应中提取可读详情。"""
        response_text = response.text.strip()
        if not response_text:
            return None

        content_type = response.headers.get("content-type", "")
        if "application/json" not in content_type:
            return response_text

        try:
            payload = response.json()
        except ValueError:
            return response_text

        return (
            payload.get("error_description")
            or payload.get("message")
            or payload.get("error")
            or response_text
        )

    @classmethod
    def _raise_for_unsuccessful_response(
        cls,
        response: httpx.Response,
        *,
        action: str,
    ) -> None:
        """统一处理 Keycloak 非成功响应。"""
        if response.is_success:
            return

        raise KeycloakError(
            f"{action} failed: {response.status_code}",
            response.status_code,
            cls._read_error_detail(response),
        )

    @staticmethod
    def _read_json_payload(response: httpx.Response, *, action: str) -> dict[str, Any]:
        """统一解析成功响应 JSON，避免每个入口自己处理异常。"""
        try:
            payload = response.json()
        except ValueError as exc:
            raise KeycloakError(
                f"{action} failed: invalid JSON response",
                502,
                response.text.strip() or None,
            ) from exc
        if not isinstance(payload, dict):
            raise KeycloakError(
                f"{action} failed: invalid JSON payload",
                502,
                response.text.strip() or None,
            )
        return payload

    async def _post_form(
        self,
        *,
        action: str,
        path: str,
        data: dict[str, str],
    ) -> dict[str, Any]:
        """执行 form POST，并返回 JSON 响应。"""
        try:
            async with httpx.AsyncClient(verify=_get_httpx_verify(), timeout=10.0) as client:
                response = await client.post(
                    f"{self.auth_url}/{path}",
                    data=self._build_token_request_data(data),
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
        except httpx.HTTPError as exc:
            logger.error("%s transport failed", action, exc_info=exc)
            raise KeycloakError("Keycloak upstream unavailable", 503, str(exc)) from exc

        self._raise_for_unsuccessful_response(response, action=action)
        return self._read_json_payload(response, action=action)

    async def _get_json(
        self,
        *,
        action: str,
        path: str,
        headers: Mapping[str, str],
    ) -> dict[str, Any]:
        """执行 GET 并返回 JSON 响应。"""
        try:
            async with httpx.AsyncClient(verify=_get_httpx_verify(), timeout=10.0) as client:
                response = await client.get(f"{self.auth_url}/{path}", headers=dict(headers))
        except httpx.HTTPError as exc:
            logger.error("%s transport failed", action, exc_info=exc)
            raise KeycloakError("Keycloak upstream unavailable", 503, str(exc)) from exc

        self._raise_for_unsuccessful_response(response, action=action)
        return self._read_json_payload(response, action=action)

    @staticmethod
    def _parse_token_response(payload: Mapping[str, Any]) -> TokenResponse:
        """把 token JSON 响应收口到 dataclass。"""
        return TokenResponse(
            access_token=str(payload["access_token"]),
            expires_in=int(payload["expires_in"]),
            refresh_token=str(payload["refresh_token"]),
            refresh_expires_in=int(payload["refresh_expires_in"]),
            token_type=str(payload["token_type"]),
            id_token=str(payload["id_token"]),
            scope=str(payload["scope"]),
        )

    @staticmethod
    def _parse_user_info(payload: Mapping[str, Any]) -> KeycloakUserInfo:
        """把 userinfo JSON 响应收口到 dataclass。"""
        return KeycloakUserInfo(
            sub=str(payload["sub"]),
            name=str(payload.get("name", "")),
            preferred_username=str(payload.get("preferred_username", "")),
            given_name=payload.get("given_name"),
            family_name=payload.get("family_name"),
            email=payload.get("email"),
            email_verified=bool(payload.get("email_verified", False)),
        )

    async def exchange_code_for_tokens(
        self,
        *,
        code: str,
        redirect_uri: str,
        code_verifier: str,
    ) -> TokenResponse:
        """交换授权码获取 token。"""
        payload = await self._post_form(
            action="Token exchange",
            path="token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "code_verifier": code_verifier,
            },
        )
        return self._parse_token_response(payload)

    async def refresh_access_token(self, refresh_token: str) -> TokenResponse:
        """刷新 access token。"""
        payload = await self._post_form(
            action="Token refresh",
            path="token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
        )
        return self._parse_token_response(payload)

    async def fetch_user_info(self, access_token: str) -> KeycloakUserInfo:
        """获取用户信息。"""
        payload = await self._get_json(
            action="Fetch userinfo",
            path="userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        return self._parse_user_info(payload)


_keycloak_client: KeycloakClient | None = None


def get_keycloak_client() -> KeycloakClient:
    """获取 Keycloak 客户端单例。"""
    global _keycloak_client
    if _keycloak_client is None:
        _keycloak_client = KeycloakClient()
    return _keycloak_client
