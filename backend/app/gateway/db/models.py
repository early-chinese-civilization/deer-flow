"""Gateway ORM models for authentication and canonical thread/workspace storage."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, String, Text, UniqueConstraint, and_, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, foreign, relationship

INTERNAL_SYSTEM_EXTERNAL_AUTH_ID = "system:deerflow"


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
    skills = relationship("Skill", back_populates="owner_user", foreign_keys="Skill.owner_user_id")
    legacy_skills = relationship("LegacySkill", back_populates="user", cascade="all, delete-orphan", foreign_keys="LegacySkill.user_id")
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
    """Terminal stable Skill identity.

    Legacy BIGINT rows live in ``legacy_skills`` during the migration window.
    New code must treat this UUID primary key as the Skill business identity.
    """

    __tablename__ = "skills"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Stable Skill identity",
    )
    owner_user_id = Column(
        BigInteger,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        comment="System or community owner user ID",
    )
    name = Column(String(255), nullable=False, comment="Skill name")
    display_name = Column(String(255), nullable=True, comment="Display name")
    description = Column(Text, nullable=True, comment="Skill description")
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

    owner_user = relationship("User", back_populates="skills", foreign_keys=[owner_user_id])
    legacy_identity_mapping = relationship("SkillIdentityMigrationMap", back_populates="skill", uselist=False, cascade="all, delete-orphan")
    versions = relationship("SkillVersion", back_populates="skill")
    installations = relationship("SkillInstallation", back_populates="skill")
    releases = relationship("SkillRelease", back_populates="skill")

    __table_args__ = (
        Index("ix_skills_owner_user_id", "owner_user_id"),
        Index("ix_skills_deleted_at", "deleted_at"),
    )


class LegacySkill(Base):
    """Legacy BIGINT skill rows kept only as migration input."""

    __tablename__ = "legacy_skills"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="Legacy skill row ID")
    user_id = Column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        comment="Legacy user ID (NULL for public skills)",
    )
    owner_user_id = Column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="Legacy publisher user ID for display/audit only",
    )
    name = Column(String(255), nullable=False, comment="Legacy skill name")
    display_name = Column(String(255), nullable=True, comment="Legacy display name")
    description = Column(Text, nullable=True, comment="Legacy skill description")
    file_path = Column(String(500), nullable=False, comment="Legacy shared skills filesystem path")
    skill_definition_id = Column(
        BigInteger,
        ForeignKey("skill_definitions.id", ondelete="SET NULL"),
        nullable=True,
        comment="Legacy SkillDefinition bridge",
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
    deleted_at = Column(DateTime(timezone=True), nullable=True, comment="Soft delete timestamp")

    user = relationship("User", back_populates="legacy_skills", foreign_keys=[user_id])
    owner_user = relationship("User", foreign_keys=[owner_user_id])
    definition = relationship("SkillDefinition", foreign_keys=[skill_definition_id], back_populates="legacy_skills")
    source_releases = relationship("SkillRelease", foreign_keys="SkillRelease.source_skill_id", back_populates="source_skill")
    published_releases = relationship("SkillRelease", foreign_keys="SkillRelease.published_skill_id", back_populates="published_skill")
    terminal_identity_mappings = relationship("SkillIdentityMigrationMap", back_populates="legacy_skill")

    __table_args__ = (
        Index(
            "uq_legacy_skills_user_definition_active",
            "user_id",
            "skill_definition_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL AND user_id IS NOT NULL AND skill_definition_id IS NOT NULL"),
        ),
        Index(
            "uq_legacy_skills_user_name_active",
            "user_id",
            "name",
            unique=True,
            postgresql_where=text("deleted_at IS NULL AND user_id IS NOT NULL AND skill_definition_id IS NULL"),
        ),
        Index(
            "uq_legacy_skills_public_owner_name_active",
            "owner_user_id",
            "name",
            unique=True,
            postgresql_where=text("deleted_at IS NULL AND user_id IS NULL AND owner_user_id IS NOT NULL"),
        ),
        Index("ix_legacy_skills_user_id", "user_id"),
        Index("ix_legacy_skills_owner_user_id", "owner_user_id"),
        Index("ix_legacy_skills_skill_definition_id", "skill_definition_id"),
        Index("ix_legacy_skills_deleted_at", "deleted_at"),
    )


class SkillDefinition(Base):
    """Stable platform identity for a skill across immutable content versions."""

    __tablename__ = "skill_definitions"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="Skill definition ID")
    name = Column(String(255), nullable=False, comment="Stable skill name")
    display_name = Column(String(255), nullable=True, comment="Display name")
    description = Column(Text, nullable=True, comment="Latest description")
    source_type = Column(String(50), nullable=False, default="legacy", comment="Definition source namespace type")
    source_identifier = Column(String(255), nullable=False, default="legacy", comment="Definition source namespace identifier")
    owner_user_id = Column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="Initial creator/publisher user ID for audit",
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
    deleted_at = Column(DateTime(timezone=True), nullable=True, comment="Soft delete timestamp")

    owner_user = relationship("User", foreign_keys=[owner_user_id])
    versions = relationship("SkillVersion", back_populates="definition", cascade="all, delete-orphan")
    installs = relationship("SkillInstallation", back_populates="definition", cascade="all, delete-orphan")
    legacy_skills = relationship("LegacySkill", back_populates="definition")
    terminal_identity_mapping = relationship("SkillIdentityMigrationMap", back_populates="definition", uselist=False, cascade="all, delete-orphan")

    __table_args__ = (
        Index(
            "uq_skill_definitions_source_name_active",
            "source_type",
            "source_identifier",
            "name",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_skill_definitions_source", "source_type", "source_identifier"),
        Index("ix_skill_definitions_deleted_at", "deleted_at"),
    )


class SkillIdentityMigrationMap(Base):
    """Deterministic bridge from legacy SkillDefinition identity to terminal Skill UUID."""

    __tablename__ = "skill_identity_migration_map"

    old_skill_definition_id = Column(
        BigInteger,
        ForeignKey("skill_definitions.id", name="fk_skill_id_map_definition", ondelete="CASCADE"),
        primary_key=True,
        comment="Legacy SkillDefinition ID",
    )
    skill_id = Column(
        UUID(as_uuid=True),
        ForeignKey("skills.id", name="fk_skill_id_map_skill", ondelete="CASCADE"),
        nullable=False,
        comment="Terminal Skill UUID",
    )
    old_skill_id = Column(
        BigInteger,
        ForeignKey("legacy_skills.id", name="fk_skill_id_map_legacy_skill", ondelete="SET NULL"),
        nullable=True,
        comment="Representative legacy skills row that contributed display/path migration input",
    )
    migration_source = Column(String(255), nullable=False, comment="Deterministic UUIDv5 source string")
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        comment="Created at",
    )

    definition = relationship("SkillDefinition", back_populates="terminal_identity_mapping", foreign_keys=[old_skill_definition_id])
    skill = relationship("Skill", back_populates="legacy_identity_mapping", foreign_keys=[skill_id])
    legacy_skill = relationship("LegacySkill", back_populates="terminal_identity_mappings", foreign_keys=[old_skill_id])

    __table_args__ = (
        UniqueConstraint("skill_id", name="uq_skill_identity_migration_map_skill_id"),
        UniqueConstraint("migration_source", name="uq_skill_identity_migration_map_migration_source"),
        Index("ix_skill_identity_migration_map_skill_id", "skill_id"),
        Index("ix_skill_identity_migration_map_old_skill_id", "old_skill_id"),
    )


class SkillVersion(Base):
    """Immutable platform-managed version of skill content."""

    __tablename__ = "skill_versions"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="Skill version ID")
    skill_id = Column(
        UUID(as_uuid=True),
        ForeignKey("skills.id", ondelete="CASCADE"),
        nullable=False,
        comment="Terminal Skill UUID that scopes version_number",
    )
    skill_definition_id = Column(
        BigInteger,
        ForeignKey("skill_definitions.id", ondelete="CASCADE"),
        nullable=False,
        comment="Legacy SkillDefinition compatibility ID",
    )
    version_number = Column(Integer, nullable=False, comment="Platform-managed monotonically increasing version")
    source_package_version = Column(String(255), nullable=True, comment="Optional source SKILL.md version metadata")
    description = Column(Text, nullable=True, comment="Description captured from this version")
    content_hash = Column(String(128), nullable=False, comment="Canonical content hash excluding source package version")
    file_manifest_hash = Column(String(128), nullable=False, comment="Raw file manifest hash")
    created_by_user_id = Column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="User that uploaded this version",
    )
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        comment="Created at",
    )

    skill = relationship("Skill", back_populates="versions", foreign_keys=[skill_id])
    definition = relationship("SkillDefinition", back_populates="versions")
    created_by_user = relationship("User", foreign_keys=[created_by_user_id])
    releases = relationship(
        "SkillRelease",
        back_populates="skill_version",
        primaryjoin=lambda: and_(
            SkillVersion.skill_id == foreign(SkillRelease.skill_id),
            SkillVersion.version_number == foreign(SkillRelease.version_number),
        ),
        viewonly=True,
    )
    installs_current = relationship("SkillInstallation", foreign_keys="SkillInstallation.current_version_id", back_populates="current_version")
    installs_initial = relationship("SkillInstallation", foreign_keys="SkillInstallation.installed_version_id", back_populates="installed_version")

    __table_args__ = (
        UniqueConstraint("skill_id", "version_number", name="uq_skill_versions_skill_version_number"),
        UniqueConstraint("skill_id", "content_hash", name="uq_skill_versions_skill_content_hash"),
        UniqueConstraint("skill_definition_id", "version_number", name="uq_skill_versions_definition_version"),
        UniqueConstraint("skill_definition_id", "content_hash", name="uq_skill_versions_definition_content_hash"),
        Index("ix_skill_versions_skill_id_created", "skill_id", "created_at"),
        Index("ix_skill_versions_definition_created", "skill_definition_id", "created_at"),
    )


class SkillInstallation(Base):
    """Terminal user-available Skill version relation.

    Legacy route code still imports ``SkillInstall`` and reads the numeric
    version compatibility columns during the migration window.
    """

    __tablename__ = "skill_installations"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="Skill install ID")
    user_id = Column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="Installing user ID",
    )
    skill_id = Column(
        UUID(as_uuid=True),
        ForeignKey("skills.id", ondelete="CASCADE"),
        nullable=False,
        comment="Terminal Skill UUID selected by this installation",
    )
    version_number = Column(Integer, nullable=False, comment="Terminal runtime version number selected for this installation")
    status = Column(String(50), nullable=False, default="active", comment="Installation status")
    skill_definition_id = Column(
        BigInteger,
        ForeignKey("skill_definitions.id", ondelete="CASCADE"),
        nullable=False,
        comment="Legacy SkillDefinition compatibility ID",
    )
    installed_version_id = Column(
        BigInteger,
        ForeignKey("skill_versions.id", ondelete="RESTRICT"),
        nullable=False,
        comment="Legacy initial SkillVersion row ID",
    )
    current_version_id = Column(
        BigInteger,
        ForeignKey("skill_versions.id", ondelete="RESTRICT"),
        nullable=False,
        comment="Legacy current SkillVersion row ID",
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
    deleted_at = Column(DateTime(timezone=True), nullable=True, comment="Soft delete timestamp")

    user = relationship("User", foreign_keys=[user_id])
    skill = relationship("Skill", back_populates="installations", foreign_keys=[skill_id])
    definition = relationship("SkillDefinition", back_populates="installs")
    installed_version = relationship("SkillVersion", foreign_keys=[installed_version_id], back_populates="installs_initial")
    current_version = relationship("SkillVersion", foreign_keys=[current_version_id], back_populates="installs_current")
    agent_skills = relationship("AgentSkill", back_populates="skill_install")

    __table_args__ = (
        ForeignKeyConstraint(
            ["skill_id", "version_number"],
            ["skill_versions.skill_id", "skill_versions.version_number"],
            name="fk_skill_installations_skill_version_composite",
            ondelete="RESTRICT",
        ),
        Index(
            "uq_skill_installations_user_skill_active",
            "user_id",
            "skill_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "uq_skill_installations_user_definition_active",
            "user_id",
            "skill_definition_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_skill_installations_skill_version", "skill_id", "version_number"),
        Index("ix_skill_installations_current_version_id", "current_version_id"),
        Index("ix_skill_installations_deleted_at", "deleted_at"),
    )


SkillInstall = SkillInstallation


class SkillRelease(Base):
    """Visibility state for an exact terminal Skill version."""

    __tablename__ = "skill_releases"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="Skill release ID")
    skill_id = Column(
        UUID(as_uuid=True),
        ForeignKey("skills.id", ondelete="CASCADE"),
        nullable=False,
        comment="Terminal Skill UUID published by this release row",
    )
    version_number = Column(Integer, nullable=False, comment="Terminal Skill version number published by this release row")
    skill_name = Column(String(255), nullable=False, comment="Published skill name")
    release_version = Column(String(64), nullable=False, unique=True, comment="System-generated immutable release version")
    package_version = Column(String(255), nullable=True, comment="Optional SKILL.md package version")
    description = Column(Text, nullable=True, comment="Skill description at publish time")
    release_notes = Column(Text, nullable=True, comment="Optional notes for this publish event")
    status = Column(String(50), nullable=False, default="published", comment="Release status")
    publisher_user_id = Column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="Publisher user ID",
    )
    source_skill_id = Column(
        BigInteger,
        ForeignKey("legacy_skills.id", ondelete="SET NULL"),
        nullable=True,
        comment="Legacy source custom skill ID",
    )
    published_skill_id = Column(
        BigInteger,
        ForeignKey("legacy_skills.id", ondelete="SET NULL"),
        nullable=True,
        comment="Legacy public row compatibility reference; not terminal release identity",
    )
    published_at = Column(DateTime(timezone=True), nullable=True, comment="Published at")
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

    skill = relationship("Skill", back_populates="releases", foreign_keys=[skill_id])
    publisher_user = relationship("User", foreign_keys=[publisher_user_id])
    source_skill = relationship("LegacySkill", foreign_keys=[source_skill_id], back_populates="source_releases")
    published_skill = relationship("LegacySkill", foreign_keys=[published_skill_id], back_populates="published_releases")
    skill_version = relationship(
        "SkillVersion",
        back_populates="releases",
        primaryjoin=lambda: and_(
            foreign(SkillRelease.skill_id) == SkillVersion.skill_id,
            foreign(SkillRelease.version_number) == SkillVersion.version_number,
        ),
        viewonly=True,
        uselist=False,
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["skill_id", "version_number"],
            ["skill_versions.skill_id", "skill_versions.version_number"],
            name="fk_skill_releases_skill_version_composite",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("skill_id", "version_number", name="uq_skill_releases_skill_version"),
        Index("ix_skill_releases_skill_name_created", "skill_name", "created_at"),
        Index("ix_skill_releases_published_skill_id", "published_skill_id"),
        Index("ix_skill_releases_status_skill_version", "status", "skill_id", "version_number"),
        Index("ix_skill_releases_status", "status"),
    )


class AgentSkill(Base):
    """Custom Agent binding to a user-owned Skill installation."""

    __tablename__ = "agent_skills"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="Association ID")
    agent_id = Column(
        BigInteger,
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
        comment="Agent ID",
    )
    skill_installation_id = Column(
        "skill_installation_id",
        BigInteger,
        ForeignKey("skill_installations.id", ondelete="CASCADE"),
        nullable=False,
        comment="Terminal skill_installations.id binding column",
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
    skill_install = relationship("SkillInstallation", back_populates="agent_skills")

    __table_args__ = (
        Index(
            "uq_agent_skills_agent_installation_active",
            "agent_id",
            "skill_installation_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_agent_skills_agent_id", "agent_id"),
        Index("ix_agent_skills_skill_installation_id", "skill_installation_id"),
        Index("ix_agent_skills_deleted_at", "deleted_at"),
    )


class RuntimeManifest(Base):
    """Persisted audit snapshot generated from already-resolved runtime Skill descriptors."""

    __tablename__ = "runtime_manifests"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Runtime descriptor audit snapshot ID",
    )
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, comment="Runtime user ID")
    agent_id = Column(BigInteger, ForeignKey("agents.id", ondelete="SET NULL"), nullable=True, comment="Resolved agent ID")
    agent_name = Column(String(255), nullable=True, comment="Resolved agent name")
    manifest_json = Column(JSONB(astext_type=Text()), nullable=False, default=dict, comment="Resolved descriptor audit payload")
    manifest_hash = Column(String(128), nullable=False, comment="Deterministic audit hash of manifest_json")
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        comment="Created at",
    )

    user = relationship("User", foreign_keys=[user_id])
    agent = relationship("Agent", foreign_keys=[agent_id])

    __table_args__ = (Index("ix_runtime_manifests_user_created", "user_id", "created_at"),)


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
