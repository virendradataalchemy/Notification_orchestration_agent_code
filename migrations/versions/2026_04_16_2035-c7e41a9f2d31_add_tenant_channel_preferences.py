"""add_tenant_channel_preferences

Revision ID: c7e41a9f2d31
Revises: 5b107ba8fc1a
Create Date: 2026-04-16 20:35:00.000000+00:00

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c7e41a9f2d31"
down_revision = "5b107ba8fc1a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenant_channel_preferences",
        sa.Column("id", sa.String(length=50), nullable=False),
        sa.Column("tenant_id", sa.String(length=50), nullable=False),
        sa.Column("channel", sa.String(length=20), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "channel", name="uq_tenant_channel_preference"),
    )

    op.create_index(
        "ix_tenant_channel_preferences_tenant_id",
        "tenant_channel_preferences",
        ["tenant_id"],
    )
    op.create_index(
        "ix_tenant_channel_preferences_channel",
        "tenant_channel_preferences",
        ["channel"],
    )


def downgrade() -> None:
    op.drop_index("ix_tenant_channel_preferences_channel", table_name="tenant_channel_preferences")
    op.drop_index("ix_tenant_channel_preferences_tenant_id", table_name="tenant_channel_preferences")
    op.drop_table("tenant_channel_preferences")

