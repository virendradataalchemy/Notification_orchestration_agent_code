from sqlalchemy import Column, String, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
import uuid

from .base import Base, TimestampMixin


class TenantChannelPreference(Base, TimestampMixin):
    """Tenant-level channel enable/disable preferences."""

    __tablename__ = "tenant_channel_preferences"

    id = Column(String(50), primary_key=True, default=lambda: uuid.uuid4().hex[:32])
    tenant_id = Column(
        String(50),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    channel = Column(String(20), nullable=False, index=True)  # email|sms|whatsapp|slack|push|voice|inapp
    enabled = Column(Boolean, nullable=False, default=True)

    tenant = relationship("Tenant", back_populates="channel_preferences")

    __table_args__ = (
        UniqueConstraint("tenant_id", "channel", name="uq_tenant_channel_preference"),
    )

    def __repr__(self):
        return (
            f"<TenantChannelPreference(tenant_id={self.tenant_id}, "
            f"channel={self.channel}, enabled={self.enabled})>"
        )

