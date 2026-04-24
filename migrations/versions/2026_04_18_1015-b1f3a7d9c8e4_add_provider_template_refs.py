"""add_provider_template_refs

Revision ID: b1f3a7d9c8e4
Revises: 9f2d8c1e4a77
Create Date: 2026-04-18 10:15:00.000000+00:00
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "b1f3a7d9c8e4"
down_revision = "9f2d8c1e4a77"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("templates", sa.Column("provider_template_ref", sa.String(length=255), nullable=True))
    op.add_column("templates", sa.Column("provider_template_meta", sa.dialects.postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("templates", "provider_template_meta")
    op.drop_column("templates", "provider_template_ref")
