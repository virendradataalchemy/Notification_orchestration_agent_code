from sqlalchemy import Column, String, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, ARRAY
from sqlalchemy.orm import relationship
from .base import Base, TimestampMixin


class UserPreference(Base, TimestampMixin):
    """User notification preferences (tenant-scoped)."""

    __tablename__ = "user_preferences"

    tenant_id = Column(String(50), ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True)
    user_id = Column(String(50), primary_key=True)  # Composite key with tenant_id

    preferred_channels = Column(JSONB, nullable=True)  # {type: [channels]} mapping
    quiet_hours = Column(JSONB, nullable=True)  # {start: '22:00', end: '08:00', timezone: 'America/New_York'}
    unsubscribed = Column(ARRAY(String), nullable=True)  # Array of notification types opted out
    language = Column(String(10), nullable=True, default="en")
    timezone = Column(String(50), nullable=True, default="UTC")

    # Relationships
    tenant = relationship("Tenant", back_populates="user_preferences")

    def __repr__(self):
        return f"<UserPreference(tenant_id={self.tenant_id}, user_id={self.user_id}, language={self.language})>"
