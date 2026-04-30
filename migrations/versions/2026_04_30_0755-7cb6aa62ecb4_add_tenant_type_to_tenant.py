"""add_tenant_type_to_tenant

Revision ID: 7cb6aa62ecb4
Revises: 6d74fd46f831
Create Date: 2026-04-30 07:55:35.733409+00:00

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "7cb6aa62ecb4"
down_revision = "6d74fd46f831"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add tenant_type column with default 'client'
    op.add_column("tenants", sa.Column("tenant_type", sa.String(length=20), nullable=False, server_default='client'))
    op.create_index(op.f("ix_tenants_tenant_type"), "tenants", ["tenant_type"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_tenants_tenant_type"), table_name="tenants")
    op.drop_column("tenants", "tenant_type")
