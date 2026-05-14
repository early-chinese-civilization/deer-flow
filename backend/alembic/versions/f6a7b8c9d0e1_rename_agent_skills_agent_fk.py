"""rename agent skills agent foreign key

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-05-14 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "f6a7b8c9d0e1"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return table_name in inspector.get_table_names()


def _has_constraint(table_name: str, constraint_name: str) -> bool:
    if not _has_table(table_name):
        return False
    inspector = sa.inspect(op.get_bind())
    if inspector.get_pk_constraint(table_name).get("name") == constraint_name:
        return True
    return (
        any(constraint["name"] == constraint_name for constraint in inspector.get_foreign_keys(table_name))
        or any(constraint["name"] == constraint_name for constraint in inspector.get_unique_constraints(table_name))
        or any(constraint["name"] == constraint_name for constraint in inspector.get_check_constraints(table_name))
    )


def _rename_constraint_if_exists(table_name: str, old_name: str, new_name: str) -> None:
    if _has_constraint(table_name, old_name) and not _has_constraint(table_name, new_name):
        op.execute(sa.text(f'ALTER TABLE "{table_name}" RENAME CONSTRAINT "{old_name}" TO "{new_name}"'))


def upgrade() -> None:
    _rename_constraint_if_exists("agent_skills", "agents_skills_agent_id_fkey", "fk_agent_skills_agent_id_agents")
    _rename_constraint_if_exists("agent_skills", "fk_agents_skills_agent_id_agents", "fk_agent_skills_agent_id_agents")


def downgrade() -> None:
    _rename_constraint_if_exists("agent_skills", "fk_agent_skills_agent_id_agents", "agents_skills_agent_id_fkey")
