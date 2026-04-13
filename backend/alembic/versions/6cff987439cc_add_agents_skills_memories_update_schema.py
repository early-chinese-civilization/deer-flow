"""add_agents_skills_memories_update_schema

Revision ID: 6cff987439cc
Revises: 0a6f3e9b2c1d
Create Date: 2026-04-10 17:51:29.448688

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6cff987439cc"
down_revision: str | Sequence[str] | None = "0a6f3e9b2c1d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create agents table
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
    op.create_index("ix_agents_user_id", "agents", ["user_id"], unique=False)
    op.create_index("ix_agents_deleted_at", "agents", ["deleted_at"], unique=False)
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

    # Create skills table
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
    op.create_index("ix_skills_user_id", "skills", ["user_id"], unique=False)
    op.create_index("ix_skills_deleted_at", "skills", ["deleted_at"], unique=False)
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

    # Create agents_skills table
    op.create_table(
        "agents_skills",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="Association ID"),
        sa.Column("agent_id", sa.BigInteger(), nullable=False, comment="Agent ID"),
        sa.Column("skill_id", sa.BigInteger(), nullable=False, comment="Skill ID"),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0", comment="Display order"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true"), comment="Enabled flag"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, comment="Created at"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True, comment="Soft delete timestamp"),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agents_skills_agent_id", "agents_skills", ["agent_id"], unique=False)
    op.create_index("ix_agents_skills_skill_id", "agents_skills", ["skill_id"], unique=False)
    op.create_index("ix_agents_skills_deleted_at", "agents_skills", ["deleted_at"], unique=False)
    op.create_index(
        "uq_agents_skills_active",
        "agents_skills",
        ["agent_id", "skill_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # Create memories table
    op.create_table(
        "memories",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="Memory ID"),
        sa.Column("user_id", sa.BigInteger(), nullable=False, comment="User ID"),
        sa.Column(
            "memory_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
            comment="Memory content JSON",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, comment="Created at"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, comment="Updated at"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True, comment="Soft delete timestamp"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_memories_deleted_at", "memories", ["deleted_at"], unique=False)
    op.create_index(
        "uq_memories_user_id_active",
        "memories",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # Add file_path column to workspaces
    op.add_column("workspaces", sa.Column("file_path", sa.Text(), nullable=True, comment="Workspace OSS root prefix"))

    # Insert default system agent (user_id=NULL)
    op.execute(
        """
        INSERT INTO agents (id, user_id, name, description, soul, mcp_config, created_at, updated_at)
        VALUES (1, NULL, 'Default Agent', 'System default agent', NULL, NULL, NOW(), NOW())
        """
    )
    op.execute(
        """
        SELECT setval(
            pg_get_serial_sequence('agents', 'id'),
            (SELECT COALESCE(MAX(id), 1) FROM agents)
        )
        """
    )

    # Add agent_id column to threads (nullable)
    op.add_column("threads", sa.Column("agent_id", sa.BigInteger(), nullable=True, comment="Agent ID (optional)"))

    # Add foreign key constraint
    op.create_foreign_key("fk_threads_agent_id", "threads", "agents", ["agent_id"], ["id"], ondelete="SET NULL")

    # Drop workspace_files table
    op.drop_index("ix_workspace_files_workspace_id", table_name="workspace_files")
    op.drop_table("workspace_files")


def downgrade() -> None:
    """Downgrade schema."""
    # Recreate workspace_files table
    op.create_table(
        "workspace_files",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="File ID"),
        sa.Column("workspace_id", sa.UUID(), nullable=False, comment="Workspace ID"),
        sa.Column("file_path", sa.Text(), nullable=False, comment="Relative path within workspace"),
        sa.Column("content", sa.LargeBinary(), nullable=False, comment="File content"),
        sa.Column("file_size", sa.BigInteger(), nullable=False, comment="File size in bytes"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, comment="Created at"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, comment="Updated at"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "file_path", name="uq_workspace_files_workspace_path"),
    )
    op.create_index("ix_workspace_files_workspace_id", "workspace_files", ["workspace_id"], unique=False)

    # Remove agent_id from threads
    op.drop_constraint("fk_threads_agent_id", "threads", type_="foreignkey")
    op.drop_column("threads", "agent_id")

    # Remove file_path from workspaces
    op.drop_column("workspaces", "file_path")

    # Drop new tables
    op.drop_index("uq_memories_user_id_active", table_name="memories")
    op.drop_index("ix_memories_deleted_at", table_name="memories")
    op.drop_table("memories")

    op.drop_index("uq_agents_skills_active", table_name="agents_skills")
    op.drop_index("ix_agents_skills_deleted_at", table_name="agents_skills")
    op.drop_index("ix_agents_skills_skill_id", table_name="agents_skills")
    op.drop_index("ix_agents_skills_agent_id", table_name="agents_skills")
    op.drop_table("agents_skills")

    op.drop_index("uq_skills_system_name_active", table_name="skills")
    op.drop_index("uq_skills_user_name_active", table_name="skills")
    op.drop_index("ix_skills_deleted_at", table_name="skills")
    op.drop_index("ix_skills_user_id", table_name="skills")
    op.drop_table("skills")

    op.drop_index("uq_agents_system_name_active", table_name="agents")
    op.drop_index("uq_agents_user_name_active", table_name="agents")
    op.drop_index("ix_agents_deleted_at", table_name="agents")
    op.drop_index("ix_agents_user_id", table_name="agents")
    op.drop_table("agents")
