"""Neutralize legacy direct system Skill Agent bindings.

Revision ID: 7d3a2b1c0e9f
Revises: 9f4d2c7b1a63
Create Date: 2026-05-08 00:00:00.000000
"""

from __future__ import annotations

revision = "7d3a2b1c0e9f"
down_revision = "9f4d2c7b1a63"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Legacy direct system bindings are not part of the terminal schema."""


def downgrade() -> None:
    """No-op because upgrade does not add legacy direct system binding columns."""
