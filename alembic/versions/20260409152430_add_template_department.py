"""add template department

Revision ID: 20260409152430
Revises:
Create Date: 2026-04-09 15:24:30
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260409152430"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("templates", sa.Column("department", sa.String(length=50), nullable=True))
    op.create_index("ix_templates_department", "templates", ["department"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_templates_department", table_name="templates")
    op.drop_column("templates", "department")
