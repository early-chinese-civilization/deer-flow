"""ORM 模型定义

定义用户和认证会话的数据库模型。
"""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import BigInteger, Boolean, Column, DateTime, String, Text
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """ORM 基类"""
    pass


class User(Base):
    """用户表

    存储从 Keycloak 同步的用户基础信息。
    """
    __tablename__ = "users"

    # 主键
    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="用户ID")

    # Keycloak 用户标识（sub）
    external_auth_id = Column(
        String(255),
        nullable=False,
        unique=True,
        index=True,
        comment="Keycloak 用户标识 (sub)"
    )

    # 用户基本信息
    username = Column(String(255), nullable=False, comment="用户名")
    display_name = Column(String(255), nullable=False, comment="显示名称")
    email = Column(String(255), nullable=True, comment="邮箱")
    given_name = Column(String(255), nullable=True, comment="名")
    family_name = Column(String(255), nullable=True, comment="姓")
    email_verified = Column(Boolean, nullable=False, default=False, comment="邮箱是否验证")

    # 时间戳
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        comment="创建时间"
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        comment="更新时间"
    )


class AuthSession(Base):
    """认证会话表

    存储用户的登录会话和 Keycloak token 信息。
    refresh_token 必须加密存储。
    """
    __tablename__ = "auth_sessions"

    # 主键：会话ID
    session_id = Column(String(64), primary_key=True, comment="会话ID")

    # 关联用户
    user_id = Column(BigInteger, nullable=False, index=True, comment="用户ID")

    # Token 信息（refresh_token 必须加密）
    refresh_token_encrypted = Column(Text, nullable=False, comment="加密的 refresh token")
    access_token = Column(Text, nullable=True, comment="Access token（可选存储）")
    id_token = Column(Text, nullable=True, comment="ID token（可选存储）")

    # 过期时间
    expires_at = Column(
        DateTime(timezone=True),
        nullable=False,
        comment="会话过期时间"
    )

    # 时间戳
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        comment="创建时间"
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        comment="更新时间"
    )
