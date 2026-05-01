import enum
from sqlalchemy import Column, String, DateTime, ForeignKey, Enum, Text, Float, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid

from .base import Base, TimestampMixin

class InboundChannel(str, enum.Enum):
    EMAIL = "email"
    SMS = "sms"
    WHATSAPP = "whatsapp"
    CHAT = "chat"

class InboundStatus(str, enum.Enum):
    RECEIVED = "received"
    PARSED = "parsed"
    INTENT_DETECTED = "intent_detected"
    FAILED = "failed"
    IGNORED = "ignored"

class IntentCategory(str, enum.Enum):
    ACCEPT = "accept"
    REJECT = "reject"
    REQUEST = "request"
    QUERY = "query"
    UNKNOWN = "unknown"

class DetectionMethod(str, enum.Enum):
    RULES = "rules"
    LLM = "llm"
    MANUAL = "manual"

class InboundMessage(Base, TimestampMixin):
    __tablename__ = "inbound_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(String(50), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    
    # E.g., email address, phone number
    sender_address = Column(String(255), nullable=False)
    
    # The channel the message came from
    channel = Column(Enum(InboundChannel, name="inbound_channel_enum"), nullable=False)
    
    # Original raw payload from the webhook
    raw_payload = Column(JSON, nullable=False)
    
    # Cleaned and parsed content
    parsed_content = Column(Text, nullable=True)
    
    # Link back to the original outbound notification (if we can match it)
    reference_id = Column(String(255), nullable=True, index=True)
    
    status = Column(Enum(InboundStatus, name="inbound_status_enum"), default=InboundStatus.RECEIVED, nullable=False)
    
    # Extracted metadata during parsing (e.g., Message-Id headers)
    metadata_json = Column(JSON, nullable=True)

    # Link to the marketing team member who owns this conversation (if applicable)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("tenant_users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    tenant = relationship("Tenant", backref="inbound_messages")
    intent = relationship("InboundIntent", back_populates="message", uselist=False, cascade="all, delete-orphan")
    owner = relationship("TenantUser", backref="owned_messages")


class InboundIntent(Base, TimestampMixin):
    __tablename__ = "inbound_intents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    message_id = Column(UUID(as_uuid=True), ForeignKey("inbound_messages.id"), nullable=False, unique=True)
    
    intent = Column(Enum(IntentCategory, name="intent_category_enum"), nullable=False)
    
    # E.g., rules=1.0, LLM could be 0.85
    confidence = Column(Float, nullable=False)
    
    detection_method = Column(Enum(DetectionMethod, name="detection_method_enum"), nullable=False)
    
    # The rationale for the decision (regex that matched or LLM reasoning)
    rationale = Column(Text, nullable=True)

    # Relationships
    message = relationship("InboundMessage", back_populates="intent")
