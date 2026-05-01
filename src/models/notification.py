from sqlalchemy import Column, String, Enum, DateTime, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
import uuid
import enum
from .base import Base, TimestampMixin


class Priority(str, enum.Enum):
    """Notification priority levels."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class NotificationStatus(str, enum.Enum):
    """Notification status."""

    QUEUED = "queued"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"


class ChannelStatus(str, enum.Enum):
    """Channel-specific status."""

    QUEUED = "queued"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
    BOUNCED = "bounced"


class Notification(Base, TimestampMixin):
    """Main notification table."""

    __tablename__ = "notifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(String(50), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(50), nullable=False, index=True)
    type = Column(String(50), nullable=False)
    priority = Column(Enum(Priority), nullable=False, index=True)
    status = Column(Enum(NotificationStatus), nullable=False, default=NotificationStatus.QUEUED, index=True)
    template_id = Column(String(50), nullable=True)
    data = Column(JSONB, nullable=True)
    scheduled_at = Column(DateTime, nullable=True, index=True)
    llm_decision = Column(JSONB, nullable=True)  # AI routing decision
    idempotency_key = Column(String(255), nullable=True, index=True)  # For deduplication
    
    # Track which team member (marketing/admin) initiated this notification
    # Useful for threading replies back to the right person
    owner_id = Column(UUID(as_uuid=True), ForeignKey("tenant_users.id", ondelete="SET NULL"), nullable=True)

    sent_at = Column(DateTime, nullable=True)  # When notification was sent
    delivered_at = Column(DateTime, nullable=True)  # When all channels delivered
    failed_at = Column(DateTime, nullable=True)  # When all channels failed
    retry_count = Column(Integer, nullable=False, default=0)  # Aggregate retry attempts

    # Relationships
    tenant = relationship("Tenant", back_populates="notifications")
    channels = relationship(
        "NotificationChannel",
        back_populates="notification",
        cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Notification(id={self.id}, tenant_id={self.tenant_id}, user_id={self.user_id}, type={self.type}, status={self.status})>"


class NotificationChannel(Base, TimestampMixin):
    """Tracks delivery status for each channel."""

    __tablename__ = "notification_channels"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    notification_id = Column(
        UUID(as_uuid=True),
        ForeignKey("notifications.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    channel = Column(String(20), nullable=False)  # email|sms|whatsapp|slack|push|voice|inapp
    provider = Column(String(30), nullable=False)  # aws_ses|twilio|fcm etc.
    message_id = Column(String(100), nullable=True, index=True)
    status = Column(Enum(ChannelStatus), nullable=False, default=ChannelStatus.QUEUED, index=True)
    attempts = Column(Integer, default=0)
    error_code = Column(String(50), nullable=True)
    error_message = Column(Text, nullable=True)
    delivered_at = Column(DateTime, nullable=True)
    opened_at = Column(DateTime, nullable=True)
    clicked_at = Column(DateTime, nullable=True)

    # Relationships
    notification = relationship("Notification", back_populates="channels")

    def __repr__(self):
        return f"<NotificationChannel(id={self.id}, channel={self.channel}, status={self.status})>"
