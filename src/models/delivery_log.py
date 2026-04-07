"""Delivery log model for tracking notification delivery and engagement."""

from datetime import datetime
from sqlalchemy import BigInteger, Column, DateTime, String, Text, ForeignKey, Integer
from sqlalchemy.orm import relationship

from .base import Base


class DeliveryLog(Base):
    """Track delivery status and engagement metrics for each notification."""
    
    __tablename__ = "delivery_logs"
    
    id = Column(BigInteger, primary_key=True)
    communication_id = Column(BigInteger, ForeignKey("communications.id"), nullable=False)
    channel_id = Column(BigInteger, ForeignKey("channels.id"), nullable=False)
    provider_id = Column(BigInteger, ForeignKey("providers.id"), nullable=False)
    provider_message_id = Column(String, nullable=True)
    status = Column(String, nullable=False)  # sent, delivered, bounced, failed
    error_message = Column(Text, nullable=True)
    language_used = Column(String, nullable=True)
    sent_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    delivered_at = Column(DateTime, nullable=True)
    opened_at = Column(DateTime, nullable=True)
    clicked_at = Column(DateTime, nullable=True)
    
    # Relationships
    communication = relationship("Communication", back_populates="delivery_logs")
    channel = relationship("Channel")
    provider = relationship("Provider")
    
    def __repr__(self):
        return f"<DeliveryLog(id={self.id}, communication_id={self.communication_id}, channel={self.channel_id}, status={self.status})>"
