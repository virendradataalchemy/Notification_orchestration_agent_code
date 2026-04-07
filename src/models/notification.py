from __future__ import annotations

import enum
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Priority(str, enum.Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class NotificationStatus(str, enum.Enum):
    QUEUED = "queued"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
    INITIATED = "initiated"
    RINGING = "ringing"


class ChannelStatus(str, enum.Enum):
    QUEUED = "queued"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
    BOUNCED = "bounced"
    INITIATED = "initiated"
    RINGING = "ringing"


class Communication(Base):
    __tablename__ = "communications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    contact_id: Mapped[int] = mapped_column(ForeignKey("contacts.id"), nullable=False, index=True)
    triggered_by_user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    batch_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    notification_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"), nullable=False, index=True)
    priority: Mapped[Priority] = mapped_column(Enum(Priority), nullable=False, default=Priority.MEDIUM)
    template_id: Mapped[Optional[int]] = mapped_column(ForeignKey("templates.id"), nullable=True)
    status: Mapped[NotificationStatus] = mapped_column(
        Enum(NotificationStatus),
        nullable=False,
        default=NotificationStatus.QUEUED,
        index=True,
    )
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    scheduled_at: Mapped[Optional[DateTime]] = mapped_column(DateTime, nullable=True)
    sent_at: Mapped[Optional[DateTime]] = mapped_column(DateTime, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    created_at: Mapped[Optional[DateTime]] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[Optional[DateTime]] = mapped_column(DateTime, nullable=True)

    tenant = relationship("Tenant", back_populates="communications")
    contact = relationship("Contact", back_populates="communications")
    channel_ref = relationship("Channel", back_populates="communications")
    template = relationship("Template", back_populates="communications")
    payloads = relationship("CommunicationPayload", back_populates="communication")
    attempts = relationship("CommunicationAttempt", back_populates="communication")
    events = relationship("NotificationEvent", back_populates="communication")
    delivery_logs = relationship("DeliveryLog", back_populates="communication")

    @property
    def type(self) -> str:
        return self.notification_type

    @property
    def user_id(self) -> str:
        return str(self.contact_id)

    @property
    def channels(self) -> list["NotificationChannel"]:
        channel_name = self.channel_ref.name if self.channel_ref else None
        return [
            NotificationChannel(
                communication=self,
                channel=channel_name or "unknown",
                provider=(self.attempts[-1].provider.name if self.attempts and self.attempts[-1].provider else None),
                message_id=None,
                status=self.status,
                attempts=max((a.attempt_number for a in self.attempts), default=0),
                error_message=self.attempts[-1].error_message if self.attempts else None,
                delivered_at=None,
                opened_at=None,
                clicked_at=None,
            )
        ]


Notification = Communication


class CommunicationPayload(Base):
    __tablename__ = "communication_payloads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    communication_id: Mapped[int] = mapped_column(ForeignKey("communications.id"), nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(255), nullable=False)
    value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    communication = relationship("Communication", back_populates="payloads")


class CommunicationAttempt(Base):
    __tablename__ = "communication_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    communication_id: Mapped[int] = mapped_column(ForeignKey("communications.id"), nullable=False, index=True)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    provider_id: Mapped[Optional[int]] = mapped_column(ForeignKey("providers.id"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[Optional[DateTime]] = mapped_column(DateTime, nullable=True)

    communication = relationship("Communication", back_populates="attempts")
    provider = relationship("Provider", back_populates="attempts")


class NotificationEvent(Base):
    __tablename__ = "notification_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    communication_id: Mapped[int] = mapped_column(ForeignKey("communications.id"), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    channel_id: Mapped[Optional[int]] = mapped_column(ForeignKey("channels.id"), nullable=True, index=True)
    status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    event_metadata: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, nullable=True)
    created_at: Mapped[Optional[DateTime]] = mapped_column(DateTime, nullable=True)

    communication = relationship("Communication", back_populates="events")
    channel_ref = relationship("Channel", back_populates="events")


class NotificationChannel:
    """Compatibility projection used by legacy response-building code."""

    def __init__(
        self,
        communication: Communication,
        channel: str,
        provider: Optional[str],
        message_id: Optional[str],
        status,
        attempts: int,
        error_message: Optional[str],
        delivered_at,
        opened_at,
        clicked_at,
    ):
        self.notification = communication
        self.channel = channel
        self.provider = provider or "unknown"
        self.message_id = message_id
        self.status = status
        self.attempts = attempts
        self.error_message = error_message
        self.delivered_at = delivered_at
        self.opened_at = opened_at
        self.clicked_at = clicked_at
