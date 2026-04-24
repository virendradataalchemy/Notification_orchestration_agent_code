"""add_agentic_orchestration_tables

Revision ID: 5b107ba8fc1a
Revises: 
Create Date: 2026-03-24 09:02:21.257844+00:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '5b107ba8fc1a'
down_revision = '0000_initial_base'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Note: pgvector extension will be enabled in a separate migration
    # once it's installed on the PostgreSQL server

    # 1. Create notification_events table (audit log)
    op.create_table(
        'notification_events',
        sa.Column('id', sa.UUID(), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('notification_id', sa.UUID(), nullable=False),
        sa.Column('event_type', sa.String(50), nullable=False),
        sa.Column('channel', sa.String(20), nullable=True),
        sa.Column('provider', sa.String(30), nullable=True),
        sa.Column('metadata', sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['notification_id'], ['notifications.id'], ondelete='CASCADE')
    )
    op.create_index('idx_events_notification_id', 'notification_events', ['notification_id'])
    op.create_index('idx_events_type', 'notification_events', ['event_type'])
    op.create_index('idx_events_created', 'notification_events', ['created_at'])

    # 2. Create provider_health table
    op.create_table(
        'provider_health',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('provider_name', sa.String(100), nullable=False),
        sa.Column('channel', sa.String(50), nullable=False),
        sa.Column('success_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('failure_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('avg_latency_ms', sa.Integer(), nullable=True),
        sa.Column('is_healthy', sa.Boolean(), nullable=False, server_default='TRUE'),
        sa.Column('last_check', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('provider_name', 'channel', name='uq_provider_channel')
    )
    op.create_index('idx_provider_health_channel', 'provider_health', ['channel'])
    op.create_index('idx_provider_health_is_healthy', 'provider_health', ['is_healthy'])

    # 3. Create user_engagement table
    op.create_table(
        'user_engagement',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('tenant_id', sa.String(50), nullable=False),
        sa.Column('user_id', sa.String(50), nullable=False),
        sa.Column('channel', sa.String(20), nullable=False),
        sa.Column('success_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('failure_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_sent', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('avg_delivery_time_seconds', sa.Integer(), nullable=True),
        sa.Column('last_successful_delivery', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('tenant_id', 'user_id', 'channel', name='uq_user_engagement')
    )
    op.create_index('idx_user_engagement_tenant_user', 'user_engagement', ['tenant_id', 'user_id'])
    op.create_index('idx_user_engagement_channel', 'user_engagement', ['channel'])

    # 4. Create notification_embeddings table (without pgvector for now)
    # Will add vector column in separate migration once pgvector is installed
    op.create_table(
        'notification_embeddings',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('tenant_id', sa.String(50), nullable=False),
        sa.Column('user_id', sa.String(50), nullable=False),
        sa.Column('content_hash', sa.String(64), nullable=False),
        sa.Column('notification_content', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_embeddings_hash', 'notification_embeddings', ['content_hash'])
    op.create_index('idx_embeddings_created', 'notification_embeddings', ['created_at'])
    op.create_index('idx_embeddings_tenant_user', 'notification_embeddings', ['tenant_id', 'user_id'])

    # 5. Add new columns to notifications table (non-breaking)
    op.add_column('notifications', sa.Column('sent_at', sa.DateTime(), nullable=True))
    op.add_column('notifications', sa.Column('delivered_at', sa.DateTime(), nullable=True))
    op.add_column('notifications', sa.Column('failed_at', sa.DateTime(), nullable=True))
    op.add_column('notifications', sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('notifications', sa.Column('llm_decision', sa.dialects.postgresql.JSONB(), nullable=True))
    op.add_column('notifications', sa.Column('idempotency_key', sa.String(255), nullable=True))
    op.create_index('idx_notifications_idempotency', 'notifications', ['idempotency_key'])

    # 6. Create trigger function to auto-delete old embeddings (10 minute TTL)
    op.execute('''
        CREATE OR REPLACE FUNCTION delete_old_embeddings() RETURNS TRIGGER AS $$
        BEGIN
            DELETE FROM notification_embeddings WHERE created_at < NOW() - INTERVAL '10 minutes';
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
    ''')

    op.execute('''
        CREATE TRIGGER trigger_cleanup_embeddings
        AFTER INSERT ON notification_embeddings
        EXECUTE FUNCTION delete_old_embeddings();
    ''')


def downgrade() -> None:
    # Drop trigger and function
    op.execute('DROP TRIGGER IF EXISTS trigger_cleanup_embeddings ON notification_embeddings')
    op.execute('DROP FUNCTION IF EXISTS delete_old_embeddings()')

    # Drop indexes and columns from notifications
    op.drop_index('idx_notifications_idempotency', 'notifications')
    op.drop_column('notifications', 'idempotency_key')
    op.drop_column('notifications', 'llm_decision')
    op.drop_column('notifications', 'retry_count')
    op.drop_column('notifications', 'failed_at')
    op.drop_column('notifications', 'delivered_at')
    op.drop_column('notifications', 'sent_at')

    # Drop notification_embeddings table
    op.drop_index('idx_embeddings_tenant_user', 'notification_embeddings')
    op.drop_index('idx_embeddings_created', 'notification_embeddings')
    op.drop_index('idx_embeddings_hash', 'notification_embeddings')
    op.drop_table('notification_embeddings')

    # Drop user_engagement table
    op.drop_index('idx_user_engagement_channel', 'user_engagement')
    op.drop_index('idx_user_engagement_tenant_user', 'user_engagement')
    op.drop_table('user_engagement')

    # Drop provider_health table
    op.drop_index('idx_provider_health_is_healthy', 'provider_health')
    op.drop_index('idx_provider_health_channel', 'provider_health')
    op.drop_table('provider_health')

    # Drop notification_events table
    op.drop_index('idx_events_created', 'notification_events')
    op.drop_index('idx_events_type', 'notification_events')
    op.drop_index('idx_events_notification_id', 'notification_events')
    op.drop_table('notification_events')
