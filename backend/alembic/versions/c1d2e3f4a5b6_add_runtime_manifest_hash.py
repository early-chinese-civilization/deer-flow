"""add runtime manifest hash

Revision ID: c1d2e3f4a5b6
Revises: a7c9e2d5f604
Create Date: 2026-05-07 00:00:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "c1d2e3f4a5b6"
down_revision = "a7c9e2d5f604"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("runtime_manifests", sa.Column("manifest_hash", sa.String(length=128), nullable=False, server_default=""))
    op.alter_column("runtime_manifests", "manifest_hash", server_default=None)


def downgrade() -> None:
    op.drop_column("runtime_manifests", "manifest_hash")
