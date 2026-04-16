"""认证接口响应模型。"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.gateway.db.models import User


class AuthUserPayload(BaseModel):
    """返回给前端的当前用户结构。"""

    id: int = Field(description="本地用户 ID")
    externalAuthId: str = Field(description="第三方认证系统中的用户标识")
    username: str = Field(description="用户名")
    displayName: str = Field(description="显示名称")
    email: str | None = Field(default=None, description="邮箱")
    givenName: str | None = Field(default=None, description="名")
    familyName: str | None = Field(default=None, description="姓")
    emailVerified: bool = Field(default=False, description="邮箱是否已验证")

    @classmethod
    def from_user(cls, user: User) -> AuthUserPayload:
        """把数据库用户模型映射成 API 载荷。"""
        return cls(
            id=user.id,
            externalAuthId=user.external_auth_id,
            username=user.username,
            displayName=user.display_name,
            email=user.email,
            givenName=user.given_name,
            familyName=user.family_name,
            emailVerified=user.email_verified,
        )
