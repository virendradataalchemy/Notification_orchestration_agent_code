"""add api key columns to clients

Revision ID: 20260416153100
Revises: 20260410120000
Create Date: 2026-04-16 15:31:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260416153100"
down_revision = "20260410120000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("clients", sa.Column("api_key_hash", sa.String(length=64), nullable=True))
    op.add_column("clients", sa.Column("api_key_prefix", sa.String(length=50), nullable=True))
    op.create_index("ix_clients_api_key_hash", "clients", ["api_key_hash"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_clients_api_key_hash", table_name="clients")
    op.drop_column("clients", "api_key_prefix")
    op.drop_column("clients", "api_key_hash")
