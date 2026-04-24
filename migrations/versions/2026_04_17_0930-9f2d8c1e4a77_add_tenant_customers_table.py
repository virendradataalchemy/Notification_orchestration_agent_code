"""add_tenant_customers_table

Revision ID: 9f2d8c1e4a77
Revises: c7e41a9f2d31
Create Date: 2026-04-17 09:30:00.000000+00:00

Compatibility migration restored so Alembic history can advance when
databases already reference this revision.
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "9f2d8c1e4a77"
down_revision = "c7e41a9f2d31"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # No-op compatibility placeholder.
    # Original migration file was missing from repository history.
    pass


def downgrade() -> None:
    # No-op compatibility placeholder.
    pass

