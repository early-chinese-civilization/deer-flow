"""Keycloak OpenID Connect 客户端

实现 Authorization Code + PKCE 流程（Public Client）。
"""
import logging
import os
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

logger = logging.getLogger(__name__)


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
    given_name: str | None = None         # 名
    family_name: str | None = None        # 姓
    email: str | None = None              # 邮箱
    email_verified: bool = False          # 邮箱是否验证


class KeycloakError(Exception):
    """Keycloak 错误"""
    def __init__(self, message: str, status: int, detail: str | None = None):
        super().__init__(message)
        self.status = status
        self.detail = detail


def _is_tls_insecure() -> bool:
    """仅在显式开启时跳过 Keycloak TLS 校验，方便本地开发。"""
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
    """Keycloak 客户端（Authorization Code + PKCE）

    默认按 public client 运行；如果配置了 client_secret，也兼容 confidential client。
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
        self.client_secret = os.getenv("KEYCLOAK_CLIENT_SECRET", "")
        self.auth_url = f"{self.url}/realms/{self.realm}/protocol/openid-connect"

        if not all([self.url, self.realm, self.client_id]):
            raise ValueError("Keycloak configuration incomplete: KEYCLOAK_URL, KEYCLOAK_REALM, KEYCLOAK_CLIENT_ID are required")

        logger.info(
            "Keycloak client configured: realm=%s client_id=%s has_client_secret=%s tls_insecure=%s",
            self.realm,
            self.client_id,
            bool(self.client_secret),
            _is_tls_insecure(),
        )

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
        id_token_hint: str | None,
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
    def _raise_for_unsuccessful_response(cls, response: httpx.Response, *, action: str) -> None:
        """统一处理 Keycloak 非成功响应。"""
        if response.is_success:
            return

        raise KeycloakError(
            f"{action} failed: {response.status_code}",
            response.status_code,
            cls._read_error_detail(response),
        )

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
        try:
            async with httpx.AsyncClient(verify=_get_httpx_verify(), timeout=10.0) as client:
                response = await client.post(
                    f"{self.auth_url}/token",
                    data=self._build_token_request_data({
                        "grant_type": "authorization_code",
                        "code": code,
                        "redirect_uri": redirect_uri,
                        "code_verifier": code_verifier,  # PKCE 验证
                    }),
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
        except httpx.HTTPError as exc:
            logger.error("Keycloak token exchange transport failed", exc_info=exc)
            raise KeycloakError("Keycloak upstream unavailable", 503, str(exc)) from exc

        self._raise_for_unsuccessful_response(response, action="Token exchange")

        # Keycloak 可能返回额外字段（如 not-before-policy），只提取需要的字段
        data = response.json()
        return TokenResponse(
            access_token=data["access_token"],
            expires_in=data["expires_in"],
            refresh_token=data["refresh_token"],
            refresh_expires_in=data["refresh_expires_in"],
            token_type=data["token_type"],
            id_token=data["id_token"],
            scope=data["scope"],
        )

    async def refresh_access_token(self, refresh_token: str) -> TokenResponse:
        """刷新 access token

        Args:
            refresh_token: Refresh token

        Returns:
            TokenResponse 对象（包含新的 access_token 和 refresh_token）

        Raises:
            KeycloakError: 如果刷新失败
        """
        try:
            async with httpx.AsyncClient(verify=_get_httpx_verify(), timeout=10.0) as client:
                response = await client.post(
                    f"{self.auth_url}/token",
                    data=self._build_token_request_data({
                        "grant_type": "refresh_token",
                        "refresh_token": refresh_token,
                    }),
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
        except httpx.HTTPError as exc:
            logger.error("Keycloak token refresh transport failed", exc_info=exc)
            raise KeycloakError("Keycloak upstream unavailable", 503, str(exc)) from exc

        self._raise_for_unsuccessful_response(response, action="Token refresh")

        # 刷新接口同样可能返回额外字段，避免 dataclass 直接解包失败
        data = response.json()
        return TokenResponse(
            access_token=data["access_token"],
            expires_in=data["expires_in"],
            refresh_token=data["refresh_token"],
            refresh_expires_in=data["refresh_expires_in"],
            token_type=data["token_type"],
            id_token=data["id_token"],
            scope=data["scope"],
        )

    async def fetch_user_info(self, access_token: str) -> KeycloakUserInfo:
        """获取用户信息

        Args:
            access_token: Access token

        Returns:
            KeycloakUserInfo 对象

        Raises:
            KeycloakError: 如果获取失败
        """
        try:
            async with httpx.AsyncClient(verify=_get_httpx_verify(), timeout=10.0) as client:
                response = await client.get(
                    f"{self.auth_url}/userinfo",
                    headers={"Authorization": f"Bearer {access_token}"},
                )
        except httpx.HTTPError as exc:
            logger.error("Keycloak userinfo transport failed", exc_info=exc)
            raise KeycloakError("Keycloak upstream unavailable", 503, str(exc)) from exc

        self._raise_for_unsuccessful_response(response, action="Fetch userinfo")

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
_keycloak_client: KeycloakClient | None = None


def get_keycloak_client() -> KeycloakClient:
    """获取 Keycloak 客户端单例

    Returns:
        KeycloakClient 实例
    """
    global _keycloak_client
    if _keycloak_client is None:
        _keycloak_client = KeycloakClient()
    return _keycloak_client
