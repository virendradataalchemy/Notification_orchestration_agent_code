"""add template visibility

Revision ID: 20260409154340
Revises: 20260409152430
Create Date: 2026-04-09 15:43:40
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260409154340"
down_revision = "20260409152430"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "templates",
        sa.Column("visibility", sa.String(length=20), server_default="public", nullable=False),
    )
    op.create_check_constraint(
        "ck_templates_visibility",
        "templates",
        "visibility IN ('private', 'public')",
    )
    op.create_index("ix_templates_visibility", "templates", ["visibility"], unique=False)
    op.create_index("ix_templates_client_visibility", "templates", ["client_id", "visibility"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_templates_client_visibility", table_name="templates")
    op.drop_index("ix_templates_visibility", table_name="templates")
    op.drop_constraint("ck_templates_visibility", "templates", type_="check")
    op.drop_column("templates", "visibility")
