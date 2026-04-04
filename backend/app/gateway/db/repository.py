"""数据访问层

提供用户和会话的数据库操作方法。
"""
from typing import Optional

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.gateway.db.models import AuthSession, User


class UserRepository:
    """用户数据访问层"""

    @staticmethod
    async def upsert_user(
        db: AsyncSession,
        external_auth_id: str,
        username: str,
        display_name: str,
        email: Optional[str] = None,
        given_name: Optional[str] = None,
        family_name: Optional[str] = None,
        email_verified: bool = False,
    ) -> User:
        """插入或更新用户

        如果用户已存在（根据 external_auth_id），则更新信息。

        Args:
            db: 数据库会话
            external_auth_id: Keycloak 用户标识 (sub)
            username: 用户名
            display_name: 显示名称
            email: 邮箱
            given_name: 名
            family_name: 姓
            email_verified: 邮箱是否验证

        Returns:
            User 对象
        """
        stmt = insert(User).values(
            external_auth_id=external_auth_id,
            username=username,
            display_name=display_name,
            email=email,
            given_name=given_name,
            family_name=family_name,
            email_verified=email_verified,
        )

        # 如果冲突则更新
        stmt = stmt.on_conflict_do_update(
            index_elements=["external_auth_id"],
            set_={
                "username": username,
                "display_name": display_name,
                "email": email,
                "given_name": given_name,
                "family_name": family_name,
                "email_verified": email_verified,
            },
        )

        await db.execute(stmt)
        await db.commit()

        # 查询并返回用户
        result = await db.execute(
            select(User).where(User.external_auth_id == external_auth_id)
        )
        return result.scalar_one()

    @staticmethod
    async def get_user_by_id(db: AsyncSession, user_id: int) -> Optional[User]:
        """根据 ID 获取用户

        Args:
            db: 数据库会话
            user_id: 用户ID

        Returns:
            User 对象，如果不存在则返回 None
        """
        stmt = select(User).where(User.id == user_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_user_by_external_auth_id(
        db: AsyncSession, external_auth_id: str
    ) -> Optional[User]:
        """根据 external_auth_id 获取用户

        Args:
            db: 数据库会话
            external_auth_id: Keycloak 用户标识

        Returns:
            User 对象，如果不存在则返回 None
        """
        stmt = select(User).where(User.external_auth_id == external_auth_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()


class SessionRepository:
    """会话数据访问层"""

    @staticmethod
    async def get_session(
        db: AsyncSession, session_id: str
    ) -> Optional[AuthSession]:
        """根据 session_id 获取会话

        Args:
            db: 数据库会话
            session_id: 会话ID

        Returns:
            AuthSession 对象，如果不存在则返回 None
        """
        stmt = select(AuthSession).where(AuthSession.session_id == session_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def delete_session(db: AsyncSession, session_id: str) -> None:
        """删除会话

        Args:
            db: 数据库会话
            session_id: 会话ID
        """
        session = await SessionRepository.get_session(db, session_id)
        if session:
            await db.delete(session)
            await db.commit()
