"""Gateway ORM models for authentication and canonical thread/workspace storage."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text, text
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
    agents = relationship("Agent", back_populates="user", cascade="all, delete-orphan")
    skills = relationship("Skill", back_populates="user", cascade="all, delete-orphan", foreign_keys="Skill.user_id")
    memories = relationship("Memory", back_populates="user", cascade="all, delete-orphan")


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
    file_path = Column(Text, nullable=True, comment="Workspace OSS root prefix")
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
    threads = relationship("Thread", back_populates="workspace")


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
    agent_id = Column(
        BigInteger,
        ForeignKey("agents.id", ondelete="SET NULL"),
        nullable=True,
        comment="Agent ID (optional)",
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
    agent = relationship("Agent", back_populates="threads")
    workspace = relationship("Workspace", back_populates="threads")


class Agent(Base):
    """User-defined Agent configuration."""

    __tablename__ = "agents"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="Agent ID")
    user_id = Column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        comment="User ID (NULL for system agents)",
    )
    name = Column(String(255), nullable=False, comment="Agent name")
    description = Column(Text, nullable=True, comment="Agent description")
    soul = Column(Text, nullable=True, comment="Agent personality definition")
    mcp_config = Column(JSONB(astext_type=Text()), nullable=True, comment="Agent MCP configuration")
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
    deleted_at = Column(DateTime(timezone=True), nullable=True, comment="Soft delete timestamp")

    user = relationship("User", back_populates="agents")
    threads = relationship("Thread", back_populates="agent")
    agent_skills = relationship("AgentSkill", back_populates="agent", cascade="all, delete-orphan")

    __table_args__ = (
        Index(
            "uq_agents_user_name_active",
            "user_id",
            "name",
            unique=True,
            postgresql_where=text("deleted_at IS NULL AND user_id IS NOT NULL"),
        ),
        Index(
            "uq_agents_system_name_active",
            "name",
            unique=True,
            postgresql_where=text("deleted_at IS NULL AND user_id IS NULL"),
        ),
        Index("ix_agents_user_id", "user_id"),
        Index("ix_agents_deleted_at", "deleted_at"),
    )


class Skill(Base):
    """System and user-level skills."""

    __tablename__ = "skills"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="Skill ID")
    user_id = Column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        comment="User ID (NULL for public skills)",
    )
    owner_user_id = Column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="Publisher user ID for display/audit only",
    )
    name = Column(String(255), nullable=False, comment="Skill name")
    display_name = Column(String(255), nullable=True, comment="Display name")
    description = Column(Text, nullable=True, comment="Skill description")
    file_path = Column(String(500), nullable=False, comment="Shared skills filesystem path")
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
    deleted_at = Column(DateTime(timezone=True), nullable=True, comment="Soft delete timestamp")

    user = relationship("User", back_populates="skills", foreign_keys=[user_id])
    owner_user = relationship("User", foreign_keys=[owner_user_id])
    agent_skills = relationship("AgentSkill", back_populates="skill", cascade="all, delete-orphan")
    source_releases = relationship("SkillRelease", foreign_keys="SkillRelease.source_skill_id", back_populates="source_skill")
    published_releases = relationship("SkillRelease", foreign_keys="SkillRelease.published_skill_id", back_populates="published_skill")

    __table_args__ = (
        Index(
            "uq_skills_user_name_active",
            "user_id",
            "name",
            unique=True,
            postgresql_where=text("deleted_at IS NULL AND user_id IS NOT NULL"),
        ),
        Index(
            "uq_skills_public_owner_name_active",
            "owner_user_id",
            "name",
            unique=True,
            postgresql_where=text("deleted_at IS NULL AND user_id IS NULL AND owner_user_id IS NOT NULL"),
        ),
        Index("ix_skills_user_id", "user_id"),
        Index("ix_skills_owner_user_id", "owner_user_id"),
        Index("ix_skills_deleted_at", "deleted_at"),
    )


class SkillRelease(Base):
    """Immutable record of a skill publish event."""

    __tablename__ = "skill_releases"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="Skill release ID")
    skill_name = Column(String(255), nullable=False, comment="Published skill name")
    release_version = Column(String(64), nullable=False, unique=True, comment="System-generated immutable release version")
    package_version = Column(String(255), nullable=True, comment="Optional SKILL.md package version")
    description = Column(Text, nullable=True, comment="Skill description at publish time")
    status = Column(String(50), nullable=False, default="published", comment="Release status")
    artifact_path = Column(String(500), nullable=False, comment="Published artifact filesystem path")
    publisher_user_id = Column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="Publisher user ID",
    )
    source_skill_id = Column(
        BigInteger,
        ForeignKey("skills.id", ondelete="SET NULL"),
        nullable=True,
        comment="Source custom skill ID",
    )
    published_skill_id = Column(
        BigInteger,
        ForeignKey("skills.id", ondelete="SET NULL"),
        nullable=True,
        comment="Public latest skill row produced by this release",
    )
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        comment="Created at",
    )

    publisher_user = relationship("User", foreign_keys=[publisher_user_id])
    source_skill = relationship("Skill", foreign_keys=[source_skill_id], back_populates="source_releases")
    published_skill = relationship("Skill", foreign_keys=[published_skill_id], back_populates="published_releases")

    __table_args__ = (
        Index("ix_skill_releases_skill_name_created", "skill_name", "created_at"),
        Index("ix_skill_releases_published_skill_id", "published_skill_id"),
        Index("ix_skill_releases_status", "status"),
    )


class AgentSkill(Base):
    """Many-to-many relationship between agents and skills."""

    __tablename__ = "agents_skills"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="Association ID")
    agent_id = Column(
        BigInteger,
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
        comment="Agent ID",
    )
    skill_id = Column(
        BigInteger,
        ForeignKey("skills.id", ondelete="CASCADE"),
        nullable=False,
        comment="Skill ID",
    )
    display_order = Column(Integer, nullable=False, default=0, comment="Display order")
    enabled = Column(Boolean, nullable=False, default=True, comment="Enabled flag")
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        comment="Created at",
    )
    deleted_at = Column(DateTime(timezone=True), nullable=True, comment="Soft delete timestamp")

    agent = relationship("Agent", back_populates="agent_skills")
    skill = relationship("Skill", back_populates="agent_skills")

    __table_args__ = (
        Index(
            "uq_agents_skills_active",
            "agent_id",
            "skill_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_agents_skills_agent_id", "agent_id"),
        Index("ix_agents_skills_skill_id", "skill_id"),
        Index("ix_agents_skills_deleted_at", "deleted_at"),
    )


class Memory(Base):
    """User memory storage."""

    __tablename__ = "memories"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="Memory ID")
    user_id = Column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="User ID",
    )
    memory_json = Column(JSONB(astext_type=Text()), nullable=False, default=dict, comment="Memory content JSON")
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
    deleted_at = Column(DateTime(timezone=True), nullable=True, comment="Soft delete timestamp")

    user = relationship("User", back_populates="memories")

    __table_args__ = (
        Index(
            "uq_memories_user_id_active",
            "user_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_memories_deleted_at", "deleted_at"),
    )
