"""add tenant branding

Revision ID: a8f9e2d1c5b3
Revises: 7e68ac545ef0
Create Date: 2026-05-12 22:05:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'a8f9e2d1c5b3'
down_revision = '7e68ac545ef0'
branch_labels = None
depends_on = None


def upgrade():
    # Create tenant_branding table
    op.create_table(
        'tenant_branding',
        sa.Column('id', sa.String(50), primary_key=True),
        sa.Column('tenant_id', sa.String(50), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('logo_url', sa.Text, nullable=True),
        sa.Column('company_name', sa.String(200), nullable=True),
        sa.Column('theme_color', sa.String(20), nullable=True, server_default='#1d4ed8'),
        sa.Column('contact_email', sa.String(200), nullable=True),
        sa.Column('contact_phone', sa.String(50), nullable=True),
        sa.Column('website', sa.String(200), nullable=True),
        sa.Column('footer_html', sa.Text, nullable=True),  # Custom footer HTML (Jinja2)
        sa.Column('enabled', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('apply_to_all_channels', sa.Boolean, nullable=False, server_default='false'),  # Apply to SMS, etc.
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.text('NOW()'), onupdate=sa.text('NOW()')),
    )
    
    # Create index on tenant_id for faster lookups
    op.create_index('ix_tenant_branding_tenant_id', 'tenant_branding', ['tenant_id'])


def downgrade():
    op.drop_index('ix_tenant_branding_tenant_id', 'tenant_branding')
    op.drop_table('tenant_branding')
