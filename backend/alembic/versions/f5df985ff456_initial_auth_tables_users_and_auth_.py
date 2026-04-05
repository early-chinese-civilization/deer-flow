"""Initial auth schema baseline for local users.

Revision ID: f5df985ff456
Revises:
Create Date: 2026-04-04 13:58:32.498001
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f5df985ff456"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """创建 v1 认证基线，只保留本地用户映射表。"""
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="用户ID"),
        sa.Column(
            "external_auth_id",
            sa.String(length=255),
            nullable=False,
            comment="Keycloak 用户标识 (sub)",
        ),
        sa.Column("username", sa.String(length=255), nullable=False, comment="用户名"),
        sa.Column("display_name", sa.String(length=255), nullable=False, comment="显示名称"),
        sa.Column("email", sa.String(length=255), nullable=True, comment="邮箱"),
        sa.Column("given_name", sa.String(length=255), nullable=True, comment="名"),
        sa.Column("family_name", sa.String(length=255), nullable=True, comment="姓"),
        sa.Column("email_verified", sa.Boolean(), nullable=False, comment="邮箱是否验证"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="创建时间",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="更新时间",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_users_external_auth_id",
        "users",
        ["external_auth_id"],
        unique=True,
    )


def downgrade() -> None:
    """回滚本地用户映射表。"""
    op.drop_index("ix_users_external_auth_id", table_name="users")
    op.drop_table("users")
