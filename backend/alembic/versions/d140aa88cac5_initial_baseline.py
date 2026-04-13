"""Create the current Gateway baseline schema in a single revision.

Revision ID: d140aa88cac5
Revises:
Create Date: 2026-04-13 14:52:51.672684
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d140aa88cac5"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the full Gateway-owned PostgreSQL schema."""
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="User ID"),
        sa.Column("external_auth_id", sa.String(length=255), nullable=False, comment="Keycloak subject (sub)"),
        sa.Column("username", sa.String(length=255), nullable=False, comment="Username"),
        sa.Column("display_name", sa.String(length=255), nullable=False, comment="Display name"),
        sa.Column("email", sa.String(length=255), nullable=True, comment="Email address"),
        sa.Column("given_name", sa.String(length=255), nullable=True, comment="Given name"),
        sa.Column("family_name", sa.String(length=255), nullable=True, comment="Family name"),
        sa.Column("email_verified", sa.Boolean(), nullable=False, comment="Email verified"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, comment="Created at"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, comment="Updated at"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_external_auth_id", "users", ["external_auth_id"], unique=True)

    op.create_table(
        "workspaces",
        sa.Column("id", sa.UUID(), nullable=False, comment="Workspace ID"),
        sa.Column("user_id", sa.BigInteger(), nullable=False, comment="User ID"),
        sa.Column("name", sa.String(length=255), nullable=True, comment="Workspace display name"),
        sa.Column("file_path", sa.Text(), nullable=True, comment="Workspace OSS root prefix"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, comment="Created at"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, comment="Updated at"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_workspaces_user_id", "workspaces", ["user_id"], unique=False)

    op.create_table(
        "agents",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="Agent ID"),
        sa.Column("user_id", sa.BigInteger(), nullable=True, comment="User ID (NULL for system agents)"),
        sa.Column("name", sa.String(length=255), nullable=False, comment="Agent name"),
        sa.Column("description", sa.Text(), nullable=True, comment="Agent description"),
        sa.Column("soul", sa.Text(), nullable=True, comment="Agent personality definition"),
        sa.Column("mcp_config", postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment="Agent MCP configuration"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, comment="Created at"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, comment="Updated at"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True, comment="Soft delete timestamp"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_agents_user_name_active",
        "agents",
        ["user_id", "name"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL AND user_id IS NOT NULL"),
    )
    op.create_index(
        "uq_agents_system_name_active",
        "agents",
        ["name"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL AND user_id IS NULL"),
    )
    op.create_index("ix_agents_user_id", "agents", ["user_id"], unique=False)
    op.create_index("ix_agents_deleted_at", "agents", ["deleted_at"], unique=False)

    op.create_table(
        "skills",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="Skill ID"),
        sa.Column("user_id", sa.BigInteger(), nullable=True, comment="User ID (NULL for system skills)"),
        sa.Column("name", sa.String(length=255), nullable=False, comment="Skill name"),
        sa.Column("display_name", sa.String(length=255), nullable=True, comment="Display name"),
        sa.Column("description", sa.Text(), nullable=True, comment="Skill description"),
        sa.Column("file_path", sa.String(length=500), nullable=False, comment="OSS file path"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, comment="Created at"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, comment="Updated at"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True, comment="Soft delete timestamp"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_skills_user_name_active",
        "skills",
        ["user_id", "name"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL AND user_id IS NOT NULL"),
    )
    op.create_index(
        "uq_skills_system_name_active",
        "skills",
        ["name"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL AND user_id IS NULL"),
    )
    op.create_index("ix_skills_user_id", "skills", ["user_id"], unique=False)
    op.create_index("ix_skills_deleted_at", "skills", ["deleted_at"], unique=False)

    op.create_table(
        "threads",
        sa.Column("thread_id", sa.String(length=255), nullable=False, comment="Thread ID"),
        sa.Column("user_id", sa.BigInteger(), nullable=False, comment="User ID"),
        sa.Column("agent_id", sa.BigInteger(), nullable=True, comment="Agent ID (optional)"),
        sa.Column("workspace_id", sa.UUID(), nullable=True, comment="Optional bound workspace ID"),
        sa.Column("title", sa.Text(), nullable=True, comment="Thread title"),
        sa.Column("status", sa.String(length=50), nullable=False, comment="Thread status: idle, busy, interrupted, error"),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment="Thread metadata",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, comment="Created at"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, comment="Updated at"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("thread_id"),
    )
    op.create_index("ix_threads_user_updated", "threads", ["user_id", "updated_at"], unique=False)
    op.create_index("ix_threads_status", "threads", ["status"], unique=False)

    op.create_table(
        "agents_skills",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="Association ID"),
        sa.Column("agent_id", sa.BigInteger(), nullable=False, comment="Agent ID"),
        sa.Column("skill_id", sa.BigInteger(), nullable=False, comment="Skill ID"),
        sa.Column("display_order", sa.Integer(), nullable=False, comment="Display order"),
        sa.Column("enabled", sa.Boolean(), nullable=False, comment="Enabled flag"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, comment="Created at"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True, comment="Soft delete timestamp"),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_agents_skills_active",
        "agents_skills",
        ["agent_id", "skill_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index("ix_agents_skills_agent_id", "agents_skills", ["agent_id"], unique=False)
    op.create_index("ix_agents_skills_skill_id", "agents_skills", ["skill_id"], unique=False)
    op.create_index("ix_agents_skills_deleted_at", "agents_skills", ["deleted_at"], unique=False)

    op.create_table(
        "memories",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="Memory ID"),
        sa.Column("user_id", sa.BigInteger(), nullable=False, comment="User ID"),
        sa.Column(
            "memory_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment="Memory content JSON",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, comment="Created at"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, comment="Updated at"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True, comment="Soft delete timestamp"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_memories_user_id_active",
        "memories",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index("ix_memories_deleted_at", "memories", ["deleted_at"], unique=False)


def downgrade() -> None:
    """Drop the Gateway baseline schema."""
    op.drop_index("ix_memories_deleted_at", table_name="memories")
    op.drop_index("uq_memories_user_id_active", table_name="memories")
    op.drop_table("memories")

    op.drop_index("ix_agents_skills_deleted_at", table_name="agents_skills")
    op.drop_index("ix_agents_skills_skill_id", table_name="agents_skills")
    op.drop_index("ix_agents_skills_agent_id", table_name="agents_skills")
    op.drop_index("uq_agents_skills_active", table_name="agents_skills")
    op.drop_table("agents_skills")

    op.drop_index("ix_threads_status", table_name="threads")
    op.drop_index("ix_threads_user_updated", table_name="threads")
    op.drop_table("threads")

    op.drop_index("ix_skills_deleted_at", table_name="skills")
    op.drop_index("ix_skills_user_id", table_name="skills")
    op.drop_index("uq_skills_system_name_active", table_name="skills")
    op.drop_index("uq_skills_user_name_active", table_name="skills")
    op.drop_table("skills")

    op.drop_index("ix_agents_deleted_at", table_name="agents")
    op.drop_index("ix_agents_user_id", table_name="agents")
    op.drop_index("uq_agents_system_name_active", table_name="agents")
    op.drop_index("uq_agents_user_name_active", table_name="agents")
    op.drop_table("agents")

    op.drop_index("ix_workspaces_user_id", table_name="workspaces")
    op.drop_table("workspaces")

    op.drop_index("ix_users_external_auth_id", table_name="users")
    op.drop_table("users")
