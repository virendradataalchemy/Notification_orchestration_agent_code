from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import relationship
from datetime import datetime
from .base import Base, TimestampMixin

class UserEngagement(Base, TimestampMixin):
    """Tracks user engagement history for AI routing."""

    __tablename__ = "user_engagement"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(50), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(50), nullable=False, index=True)
    channel = Column(String(20), nullable=False, index=True)
    
    success_count = Column(Integer, nullable=False, default=0)
    failure_count = Column(Integer, nullable=False, default=0)
    total_sent = Column(Integer, nullable=False, default=0)
    avg_delivery_time_seconds = Column(Integer, nullable=True)
    last_successful_delivery = Column(DateTime, nullable=True)

    # Relationships
    tenant = relationship("Tenant")

    __table_args__ = (
        UniqueConstraint('tenant_id', 'user_id', 'channel', name='uq_user_engagement'),
    )

    def __repr__(self):
        return f"<UserEngagement(user_id={self.user_id}, channel={self.channel}, total_sent={self.total_sent})>"
