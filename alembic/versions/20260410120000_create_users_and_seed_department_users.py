"""create users table and seed department users

Revision ID: 20260410120000
Revises: 20260409162723
Create Date: 2026-04-10 12:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260410120000"
down_revision = "20260409162723"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # users table already exists in Supabase — just seed the department users
    op.execute(
        """
        INSERT INTO users (client_id, email, name, role, is_active, created_at, updated_at)
        VALUES
            (1, 'prachikushwaha.dataalchemy@gmail.com', 'Prachi Kushwaha', 'hr', true, NOW(), NOW()),
            (1, 'prateekgaur.prateek.1609@gmail.com',  'Prateek Gaur',    'it', true, NOW(), NOW())
        ON CONFLICT (email) DO UPDATE
            SET name       = EXCLUDED.name,
                role       = EXCLUDED.role,
                client_id  = EXCLUDED.client_id,
                is_active  = EXCLUDED.is_active,
                updated_at = NOW()
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM users
        WHERE client_id = 1
          AND email IN (
            'prachikushwaha.dataalchemy@gmail.com',
            'prateekgaur.prateek.1609@gmail.com'
          )
        """
    )
