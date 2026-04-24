"""initial_base_tables

Revision ID: 0000_initial_base
Revises: 
Create Date: 2026-04-21 09:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '0000_initial_base'
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    # 0. Create Enum Types explicitly (UPPERCASE to match SQLAlchemy member names)
    op.execute("CREATE TYPE priority AS ENUM ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW')")
    op.execute("CREATE TYPE notificationstatus AS ENUM ('QUEUED', 'SENT', 'DELIVERED', 'FAILED')")
    op.execute("CREATE TYPE channelstatus AS ENUM ('QUEUED', 'SENT', 'DELIVERED', 'FAILED', 'BOUNCED')")

    # 1. Tenants Table
    op.create_table(
        'tenants',
        sa.Column('id', sa.String(length=50), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('status', sa.String(length=20), server_default='active', nullable=False),
        sa.Column('username', sa.String(length=100), nullable=True),
        sa.Column('password_hash', sa.String(length=255), nullable=True),
        sa.Column('api_key_hash', sa.String(length=255), nullable=False),
        sa.Column('api_key_prefix', sa.String(length=50), nullable=False),
        sa.Column('config', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('tenant_metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('admin_email', sa.String(length=255), nullable=True),
        sa.Column('admin_name', sa.String(length=255), nullable=True),
        sa.Column('suspended_at', sa.DateTime(), nullable=True),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('api_key_hash'),
        sa.UniqueConstraint('username')
    )
    op.create_index(op.f('ix_tenants_api_key_hash'), 'tenants', ['api_key_hash'], unique=True)
    op.create_index(op.f('ix_tenants_status'), 'tenants', ['status'], unique=False)
    op.create_index(op.f('ix_tenants_username'), 'tenants', ['username'], unique=True)

    # 2. Tenant Provider Configs
    op.create_table(
        'tenant_provider_configs',
        sa.Column('id', sa.String(length=50), nullable=False),
        sa.Column('tenant_id', sa.String(length=50), nullable=False),
        sa.Column('provider', sa.String(length=50), nullable=False),
        sa.Column('config', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'provider', name='uq_tenant_provider')
    )
    op.create_index(op.f('ix_tenant_provider_configs_is_active'), 'tenant_provider_configs', ['is_active'], unique=False)
    op.create_index(op.f('ix_tenant_provider_configs_provider'), 'tenant_provider_configs', ['provider'], unique=False)
    op.create_index(op.f('ix_tenant_provider_configs_tenant_id'), 'tenant_provider_configs', ['tenant_id'], unique=False)

    # 3. Notifications Table
    op.create_table(
        'notifications',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tenant_id', sa.String(length=50), nullable=False),
        sa.Column('user_id', sa.String(length=50), nullable=False),
        sa.Column('type', sa.String(length=50), nullable=False),
        sa.Column('priority', postgresql.ENUM('CRITICAL', 'HIGH', 'MEDIUM', 'LOW', name='priority', create_type=False), nullable=False),
        sa.Column('status', postgresql.ENUM('QUEUED', 'SENT', 'DELIVERED', 'FAILED', name='notificationstatus', create_type=False), server_default='QUEUED', nullable=False),
        sa.Column('template_id', sa.String(length=50), nullable=True),
        sa.Column('data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('scheduled_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_notifications_priority'), 'notifications', ['priority'], unique=False)
    op.create_index(op.f('ix_notifications_scheduled_at'), 'notifications', ['scheduled_at'], unique=False)
    op.create_index(op.f('ix_notifications_status'), 'notifications', ['status'], unique=False)
    op.create_index(op.f('ix_notifications_tenant_id'), 'notifications', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_notifications_user_id'), 'notifications', ['user_id'], unique=False)

    # 4. Notification Channels
    op.create_table(
        'notification_channels',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('notification_id', sa.UUID(), nullable=False),
        sa.Column('channel', sa.String(length=20), nullable=False),
        sa.Column('provider', sa.String(length=30), nullable=False),
        sa.Column('message_id', sa.String(length=100), nullable=True),
        sa.Column('status', postgresql.ENUM('QUEUED', 'SENT', 'DELIVERED', 'FAILED', 'BOUNCED', name='channelstatus', create_type=False), server_default='QUEUED', nullable=False),
        sa.Column('attempts', sa.Integer(), server_default='0', nullable=True),
        sa.Column('error_code', sa.String(length=50), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('delivered_at', sa.DateTime(), nullable=True),
        sa.Column('opened_at', sa.DateTime(), nullable=True),
        sa.Column('clicked_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['notification_id'], ['notifications.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_notification_channels_message_id'), 'notification_channels', ['message_id'], unique=False)
    op.create_index(op.f('ix_notification_channels_notification_id'), 'notification_channels', ['notification_id'], unique=False)
    op.create_index(op.f('ix_notification_channels_status'), 'notification_channels', ['status'], unique=False)

    # 5. Templates Table
    op.create_table(
        'templates',
        sa.Column('id', sa.String(length=50), nullable=False),
        sa.Column('tenant_id', sa.String(length=50), nullable=True),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('base_template_id', sa.String(length=50), nullable=True),
        sa.Column('channel', sa.String(length=20), nullable=False),
        sa.Column('language', sa.String(length=10), server_default='en', nullable=False),
        sa.Column('subject', sa.Text(), nullable=True),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('version', sa.Integer(), server_default='1', nullable=True),
        sa.Column('active', sa.Boolean(), server_default='true', nullable=True),
        sa.Column('is_global', sa.Boolean(), server_default='false', nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'name', 'channel', 'language', name='uq_tenant_template')
    )
    op.create_index(op.f('ix_templates_active'), 'templates', ['active'], unique=False)
    op.create_index(op.f('ix_templates_channel'), 'templates', ['channel'], unique=False)
    op.create_index(op.f('ix_templates_is_global'), 'templates', ['is_global'], unique=False)
    op.create_index(op.f('ix_templates_tenant_id'), 'templates', ['tenant_id'], unique=False)

    # 6. User Preferences
    op.create_table(
        'user_preferences',
        sa.Column('tenant_id', sa.String(length=50), nullable=False),
        sa.Column('user_id', sa.String(length=50), nullable=False),
        sa.Column('preferred_channels', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('quiet_hours', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('unsubscribed', postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column('language', sa.String(length=10), server_default='en', nullable=True),
        sa.Column('timezone', sa.String(length=50), server_default='UTC', nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('tenant_id', 'user_id')
    )

    # 7. Audit Logs
    op.create_table(
        'audit_logs',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('event_type', sa.String(length=50), nullable=False),
        sa.Column('user_id', sa.String(length=50), nullable=True),
        sa.Column('resource_type', sa.String(length=50), nullable=True),
        sa.Column('resource_id', sa.String(length=100), nullable=True),
        sa.Column('action', sa.String(length=50), nullable=False),
        sa.Column('details', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_audit_logs_created_at'), 'audit_logs', ['created_at'], unique=False)
    op.create_index(op.f('ix_audit_logs_event_type'), 'audit_logs', ['event_type'], unique=False)
    op.create_index(op.f('ix_audit_logs_user_id'), 'audit_logs', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_table('audit_logs')
    op.drop_table('user_preferences')
    op.drop_table('templates')
    op.drop_table('notification_channels')
    op.drop_table('notifications')
    op.drop_table('tenant_provider_configs')
    op.drop_table('tenants')
    
    # Drop Enums
    op.execute("DROP TYPE channelstatus")
    op.execute("DROP TYPE notificationstatus")
    op.execute("DROP TYPE priority")
