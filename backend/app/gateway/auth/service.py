"""DeerFlow auth adapters on top of the shared ecc-auth identity contract."""

from __future__ import annotations

from typing import Any

from ecc_auth.identity import AuthIdentity
from sqlalchemy.ext.asyncio import AsyncSession

from app.gateway.auth.schemas import AuthUserPayload
from app.gateway.db.models import User
from app.gateway.db.repository import UserRepository


async def sync_local_user_from_identity(
    *,
    db: AsyncSession,
    identity: AuthIdentity,
) -> User:
    """Project a shared identity into DeerFlow's local user table."""
    return await UserRepository.upsert_user(
        db=db,
        external_auth_id=identity.external_auth_id,
        username=identity.username,
        display_name=identity.display_name,
        email=identity.email,
        given_name=identity.given_name,
        family_name=identity.family_name,
        email_verified=identity.email_verified,
    )


async def build_current_user_payload(
    *,
    db: AsyncSession,
    identity: AuthIdentity,
) -> dict[str, Any]:
    """Build the DeerFlow user object for the shared `/me` response wrapper."""
    user = await sync_local_user_from_identity(db=db, identity=identity)
    return AuthUserPayload.from_user(user).model_dump()
