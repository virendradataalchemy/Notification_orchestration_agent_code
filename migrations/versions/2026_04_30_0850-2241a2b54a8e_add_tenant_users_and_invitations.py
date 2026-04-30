"""add_tenant_users_and_invitations

Revision ID: 2241a2b54a8e
Revises: 7cb6aa62ecb4
Create Date: 2026-04-30 08:50:10.326398+00:00

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "2241a2b54a8e"
down_revision = "7cb6aa62ecb4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create tenant_users table
    op.create_table(
        "tenant_users",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.String(length=50), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("username", sa.String(length=100), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=True),
        sa.Column("role", sa.String(length=20), nullable=False, server_default='marketing'),
        sa.Column("permissions", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=True, server_default='true'),
        sa.Column("last_login_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_tenant_users_email"), "tenant_users", ["email"], unique=False)
    op.create_index(op.f("ix_tenant_users_is_active"), "tenant_users", ["is_active"], unique=False)
    op.create_index(op.f("ix_tenant_users_tenant_id"), "tenant_users", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_tenant_users_username"), "tenant_users", ["username"], unique=True)

    # Create tenant_invitations table
    op.create_table(
        "tenant_invitations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.String(length=50), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("token", sa.String(length=100), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False, server_default='marketing'),
        sa.Column("permissions", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("invited_by_user_id", sa.UUID(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("accepted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(
            ["invited_by_user_id"],
            ["tenant_users.id"],
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_tenant_invitations_tenant_id"), "tenant_invitations", ["tenant_id"], unique=False
    )
    op.create_index(
        op.f("ix_tenant_invitations_token"), "tenant_invitations", ["token"], unique=True
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_tenant_invitations_token"), table_name="tenant_invitations")
    op.drop_index(op.f("ix_tenant_invitations_tenant_id"), table_name="tenant_invitations")
    op.drop_table("tenant_invitations")
    op.drop_index(op.f("ix_tenant_users_username"), table_name="tenant_users")
    op.drop_index(op.f("ix_tenant_users_tenant_id"), table_name="tenant_users")
    op.drop_index(op.f("ix_tenant_users_is_active"), table_name="tenant_users")
    op.drop_index(op.f("ix_tenant_users_email"), table_name="tenant_users")
    op.drop_table("tenant_users")
