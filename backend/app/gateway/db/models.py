"""Gateway ORM models for authentication and canonical thread/workspace storage."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, Index, LargeBinary, String, Text, UniqueConstraint
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

    workspaces = relationship("Workspace", back_populates="user", cascade="all, delete-orphan")
    threads = relationship("Thread", back_populates="user", cascade="all, delete-orphan")


class Workspace(Base):
    """Canonical workspace storage independently bindable to threads."""

    __tablename__ = "workspaces"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Workspace ID",
    )
    user_id = Column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="User ID",
    )
    name = Column(String(255), nullable=True, comment="Workspace display name")
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

    user = relationship("User", back_populates="workspaces")
    files = relationship("WorkspaceFile", back_populates="workspace", cascade="all, delete-orphan")
    threads = relationship("Thread", back_populates="workspace")


class WorkspaceFile(Base):
    """File storage within canonical workspace."""

    __tablename__ = "workspace_files"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="File ID")
    workspace_id = Column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Workspace ID",
    )
    file_path = Column(Text, nullable=False, comment="Relative path within workspace")
    content = Column(LargeBinary, nullable=False, comment="File content")
    file_size = Column(BigInteger, nullable=False, comment="File size in bytes")
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

    workspace = relationship("Workspace", back_populates="files")

    __table_args__ = (UniqueConstraint("workspace_id", "file_path", name="uq_workspace_files_workspace_path"),)


class Thread(Base):
    """Canonical business record for a user-owned thread."""

    __tablename__ = "threads"
    __table_args__ = (
        Index("ix_threads_user_updated", "user_id", "updated_at"),
        Index("ix_threads_status", "status"),
    )

    thread_id = Column(String(255), primary_key=True, comment="Thread ID")
    user_id = Column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="User ID",
    )
    workspace_id = Column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="SET NULL"),
        nullable=True,
        comment="Optional bound workspace ID",
    )
    title = Column(Text, nullable=True, comment="Thread title")
    status = Column(
        String(50),
        nullable=False,
        default="idle",
        comment="Thread status: idle, busy, interrupted, error",
    )
    thread_metadata = Column(
        "metadata",
        JSONB(astext_type=Text()),
        nullable=False,
        default=dict,
        comment="Thread metadata",
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

    user = relationship("User", back_populates="threads")
    workspace = relationship("Workspace", back_populates="threads")
