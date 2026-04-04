"""ORM 模型定义。"""
from datetime import UTC, datetime

from sqlalchemy import BigInteger, Boolean, Column, DateTime, String
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
        default=lambda: datetime.now(UTC),
        comment="创建时间"
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        comment="更新时间"
    )
