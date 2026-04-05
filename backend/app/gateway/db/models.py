"""Gateway ORM models for authentication and Phase 2 product tables."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    """Base class for Gateway-owned ORM models."""


class User(Base):
    """Local user mapped from Keycloak identity data."""

    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="User ID")
    external_auth_id = Column(
        String(255),
        nullable=False,
        unique=True,
        index=True,
        comment="Keycloak subject (sub)",
    )
    username = Column(String(255), nullable=False, comment="Username")
    display_name = Column(String(255), nullable=False, comment="Display name")
    email = Column(String(255), nullable=True, comment="Email address")
    given_name = Column(String(255), nullable=True, comment="Given name")
    family_name = Column(String(255), nullable=True, comment="Family name")
    email_verified = Column(Boolean, nullable=False, default=False, comment="Email verified")
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        comment="Created at",
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        comment="Updated at",
    )

    chats = relationship("Chat", back_populates="owner", cascade="all, delete-orphan")


class Chat(Base):
    """Product chat record keyed directly by LangGraph ``thread_id``."""

    __tablename__ = "chats"

    thread_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="LangGraph thread ID",
    )
    owner_user_id = Column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Owning user ID",
    )
    workspace_id = Column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
        comment="Hidden workspace ID for v1 auto-created workspaces",
    )
    agent_id = Column(Text, nullable=True, comment="Bound agent identifier")
    agent_snapshot = Column(JSONB, nullable=True, comment="Frozen agent snapshot")
    title = Column(Text, nullable=True, comment="Chat title")
    status = Column(
        String(50),
        nullable=False,
        default="idle",
        comment="Chat status: idle, busy, interrupted, error",
    )
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        comment="Created at",
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        comment="Updated at",
    )

    owner = relationship("User", back_populates="chats")
    messages = relationship(
        "Message",
        back_populates="chat",
        cascade="all, delete-orphan",
        order_by="Message.seq",
    )

    __table_args__ = (Index("ix_chats_owner_updated", "owner_user_id", "updated_at"),)


class Message(Base):
    """Final user-visible message truth table for a chat thread."""

    __tablename__ = "messages"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="Message ID")
    thread_id = Column(
        UUID(as_uuid=True),
        ForeignKey("chats.thread_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Thread ID",
    )
    source_message_id = Column(
        String(255),
        nullable=False,
        comment="Stable upstream message identifier",
    )
    role = Column(String(50), nullable=False, comment="Message role")
    content = Column(Text, nullable=False, comment="Message content")
    seq = Column(BigInteger, nullable=False, comment="Final display order within the thread")
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        comment="Created at",
    )

    chat = relationship("Chat", back_populates="messages")

    __table_args__ = (
        UniqueConstraint("thread_id", "seq", name="uq_messages_thread_seq"),
        UniqueConstraint(
            "thread_id",
            "source_message_id",
            name="uq_messages_thread_source_message",
        ),
        Index("ix_messages_thread_created", "thread_id", "created_at"),
    )
