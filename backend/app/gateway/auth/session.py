"""Session 管理

提供会话的创建、查询、更新和删除功能。
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.gateway.auth.security import decrypt_token, encrypt_token, generate_session_id
from app.gateway.db.models import AuthSession, User


class SessionManager:
    """Session 管理器"""

    @staticmethod
    async def create_session(
        db: AsyncSession,
        user_id: int,
        refresh_token: str,
        access_token: Optional[str],
        id_token: Optional[str],
        expires_in: int,
    ) -> str:
        """创建会话

        Args:
            db: 数据库会话
            user_id: 用户ID
            refresh_token: Refresh token（将被加密存储）
            access_token: Access token（可选存储）
            id_token: ID token（可选存储）
            expires_in: 过期时间（秒）

        Returns:
            会话ID
        """
        session_id = generate_session_id()
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

        # 加密 refresh_token
        refresh_token_encrypted = encrypt_token(refresh_token)

        session = AuthSession(
            session_id=session_id,
            user_id=user_id,
            refresh_token_encrypted=refresh_token_encrypted,
            access_token=access_token,
            id_token=id_token,
            expires_at=expires_at,
        )

        db.add(session)
        await db.commit()

        return session_id

    @staticmethod
    async def get_session(
        db: AsyncSession,
        session_id: str
    ) -> Optional[AuthSession]:
        """获取会话

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
    async def update_session_tokens(
        db: AsyncSession,
        session_id: str,
        refresh_token: str,
        access_token: Optional[str],
        id_token: Optional[str],
        expires_in: int,
    ) -> None:
        """更新会话 token

        Args:
            db: 数据库会话
            session_id: 会话ID
            refresh_token: 新的 refresh token
            access_token: 新的 access token
            id_token: 新的 id token
            expires_in: 过期时间（秒）
        """
        session = await SessionManager.get_session(db, session_id)
        if not session:
            return

        # 更新 token 和过期时间
        session.refresh_token_encrypted = encrypt_token(refresh_token)
        session.access_token = access_token
        session.id_token = id_token
        session.expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        session.updated_at = datetime.now(timezone.utc)

        await db.commit()

    @staticmethod
    async def delete_session(db: AsyncSession, session_id: str) -> None:
        """删除会话

        Args:
            db: 数据库会话
            session_id: 会话ID
        """
        session = await SessionManager.get_session(db, session_id)
        if session:
            await db.delete(session)
            await db.commit()

    @staticmethod
    def get_refresh_token(session: AuthSession) -> str:
        """解密并获取 refresh_token

        Args:
            session: AuthSession 对象

        Returns:
            明文 refresh_token
        """
        return decrypt_token(session.refresh_token_encrypted)
