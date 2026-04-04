"""Keycloak OpenID Connect 客户端

实现 Authorization Code + PKCE 流程（Public Client）。
"""
import os
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlencode

import httpx


@dataclass
class TokenResponse:
    """Token 响应"""
    access_token: str
    expires_in: int
    refresh_token: str
    refresh_expires_in: int
    token_type: str
    id_token: str
    scope: str


@dataclass
class KeycloakUserInfo:
    """Keycloak 用户信息"""
    sub: str                              # Keycloak 用户标识
    name: str                             # 全名
    preferred_username: str               # 用户名
    given_name: Optional[str] = None      # 名
    family_name: Optional[str] = None     # 姓
    email: Optional[str] = None           # 邮箱
    email_verified: bool = False          # 邮箱是否验证


class KeycloakError(Exception):
    """Keycloak 错误"""
    def __init__(self, message: str, status: int, detail: Optional[str] = None):
        super().__init__(message)
        self.status = status
        self.detail = detail


class KeycloakClient:
    """Keycloak 客户端（Public Client + PKCE）

    注意：这是 Public Client 实现，不使用 client_secret。
    """

    def __init__(self):
        """初始化 Keycloak 客户端

        从环境变量读取配置：
        - KEYCLOAK_URL: Keycloak 服务器地址
        - KEYCLOAK_REALM: Realm 名称
        - KEYCLOAK_CLIENT_ID: Client ID
        """
        self.url = os.getenv("KEYCLOAK_URL", "")
        self.realm = os.getenv("KEYCLOAK_REALM", "")
        self.client_id = os.getenv("KEYCLOAK_CLIENT_ID", "")
        self.auth_url = f"{self.url}/realms/{self.realm}/protocol/openid-connect"

        if not all([self.url, self.realm, self.client_id]):
            raise ValueError("Keycloak configuration incomplete: KEYCLOAK_URL, KEYCLOAK_REALM, KEYCLOAK_CLIENT_ID are required")

    def build_auth_url(
        self,
        redirect_uri: str,
        state: str,
        code_challenge: str,
        code_challenge_method: str = "S256"
    ) -> str:
        """构造授权 URL（PKCE）

        Args:
            redirect_uri: 回调地址
            state: State 参数（包含 nonce 和 returnTo）
            code_challenge: PKCE code_challenge
            code_challenge_method: PKCE 方法（默认 S256）

        Returns:
            Keycloak 授权 URL
        """
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
        id_token_hint: Optional[str],
        post_logout_redirect_uri: str
    ) -> str:
        """构造登出 URL

        Args:
            id_token_hint: ID token（用于识别会话）
            post_logout_redirect_uri: 登出后跳转地址

        Returns:
            Keycloak 登出 URL
        """
        params = {
            "client_id": self.client_id,
            "post_logout_redirect_uri": post_logout_redirect_uri,
        }
        if id_token_hint:
            params["id_token_hint"] = id_token_hint
        return f"{self.auth_url}/logout?{urlencode(params)}"

    async def exchange_code_for_tokens(
        self,
        code: str,
        redirect_uri: str,
        code_verifier: str
    ) -> TokenResponse:
        """交换授权码获取 token（PKCE）

        Args:
            code: 授权码
            redirect_uri: 回调地址（必须与授权时一致）
            code_verifier: PKCE code_verifier

        Returns:
            TokenResponse 对象

        Raises:
            KeycloakError: 如果交换失败
        """
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{self.auth_url}/token",
                data={
                    "grant_type": "authorization_code",
                    "client_id": self.client_id,
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "code_verifier": code_verifier,  # PKCE 验证
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

        if not response.is_success:
            raise KeycloakError(
                f"Token exchange failed: {response.status_code}",
                response.status_code,
                response.text
            )

        data = response.json()
        return TokenResponse(**data)

    async def refresh_access_token(self, refresh_token: str) -> TokenResponse:
        """刷新 access token

        Args:
            refresh_token: Refresh token

        Returns:
            TokenResponse 对象（包含新的 access_token 和 refresh_token）

        Raises:
            KeycloakError: 如果刷新失败
        """
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{self.auth_url}/token",
                data={
                    "grant_type": "refresh_token",
                    "client_id": self.client_id,
                    "refresh_token": refresh_token,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

        if not response.is_success:
            raise KeycloakError(
                f"Token refresh failed: {response.status_code}",
                response.status_code,
                response.text
            )

        data = response.json()
        return TokenResponse(**data)

    async def fetch_user_info(self, access_token: str) -> KeycloakUserInfo:
        """获取用户信息

        Args:
            access_token: Access token

        Returns:
            KeycloakUserInfo 对象

        Raises:
            KeycloakError: 如果获取失败
        """
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{self.auth_url}/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
            )

        if not response.is_success:
            raise KeycloakError(
                f"Fetch userinfo failed: {response.status_code}",
                response.status_code,
                response.text
            )

        data = response.json()
        return KeycloakUserInfo(
            sub=data["sub"],
            name=data.get("name", ""),
            preferred_username=data.get("preferred_username", ""),
            given_name=data.get("given_name"),
            family_name=data.get("family_name"),
            email=data.get("email"),
            email_verified=data.get("email_verified", False),
        )


# 全局单例
_keycloak_client: Optional[KeycloakClient] = None


def get_keycloak_client() -> KeycloakClient:
    """获取 Keycloak 客户端单例

    Returns:
        KeycloakClient 实例
    """
    global _keycloak_client
    if _keycloak_client is None:
        _keycloak_client = KeycloakClient()
    return _keycloak_client
