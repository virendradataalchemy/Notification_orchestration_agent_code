import enum
from sqlalchemy import Column, String, DateTime, ForeignKey, Enum, Text, Float, JSON, Boolean, UniqueConstraint
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

class InboundMessageRaw(Base, TimestampMixin):
    __tablename__ = "inbound_messages_raw"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(String(50), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    
    # E.g., candidate's user ID in external system
    candidate_id = Column(String(255), nullable=True)
    
    # E.g., email address, phone number
    sender_address = Column(String(255), nullable=False)
    
    # The channel the message came from
    channel = Column(Enum(InboundChannel, name="inbound_channel_enum", create_type=False), nullable=False)
    
    # Message ID from the provider (e.g. Mailgun message-id, Twilio message-sid)
    provider_message_id = Column(String(255), nullable=False)
    
    # Original raw payload from the webhook
    raw_payload = Column(JSON, nullable=False)
    
    # Data retention flag
    retention_date = Column(DateTime, nullable=True)

    # Link to the marketing team member who owns this conversation (if applicable)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("tenant_users.id", ondelete="SET NULL"), nullable=True)

    __table_args__ = (
        UniqueConstraint('tenant_id', 'provider_message_id', name='uq_tenant_provider_msg'),
    )

    # Relationships
    tenant = relationship("Tenant", backref="inbound_messages")
    owner = relationship("TenantUser", backref="owned_messages")
    parsed_message = relationship("InboundMessageParsed", back_populates="raw_message", uselist=False, cascade="all, delete-orphan")


class InboundMessageParsed(Base, TimestampMixin):
    __tablename__ = "inbound_messages_parsed"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    raw_message_id = Column(UUID(as_uuid=True), ForeignKey("inbound_messages_raw.id", ondelete="CASCADE"), nullable=False, unique=True)
    
    # Cleaned and parsed content
    parsed_content = Column(Text, nullable=True)
    
    parser_version = Column(String(50), nullable=True)
    
    status = Column(Enum(InboundStatus, name="inbound_status_enum", create_type=False), default=InboundStatus.RECEIVED, nullable=False)
    
    failure_reason = Column(Text, nullable=True)
    
    # Extracted metadata during parsing (e.g., Message-Id headers)
    metadata_json = Column(JSON, nullable=True)
    
    # Link back to the original outbound notification (if we can match it)
    reference_id = Column(String(255), nullable=True, index=True)

    # Relationships
    raw_message = relationship("InboundMessageRaw", back_populates="parsed_message")
    intent = relationship("InboundIntent", back_populates="parsed_message", uselist=False, cascade="all, delete-orphan")


class InboundIntent(Base, TimestampMixin):
    __tablename__ = "inbound_intents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    parsed_message_id = Column(UUID(as_uuid=True), ForeignKey("inbound_messages_parsed.id", ondelete="CASCADE"), nullable=False, unique=True)
    
    intent = Column(Enum(IntentCategory, name="intent_category_enum", create_type=False), nullable=False)
    
    # E.g., rules=1.0, LLM could be 0.85
    confidence = Column(Float, nullable=False)
    
    detection_method = Column(Enum(DetectionMethod, name="detection_method_enum", create_type=False), nullable=False)
    
    # The rationale for the decision (regex that matched or LLM reasoning)
    rationale = Column(Text, nullable=True)

    needs_review = Column(Boolean, default=False, nullable=False)

    # Relationships
    parsed_message = relationship("InboundMessageParsed", back_populates="intent")
    workflow_events = relationship("InboundWorkflowEvent", back_populates="intent", cascade="all, delete-orphan")


class InboundWorkflowEvent(Base, TimestampMixin):
    __tablename__ = "inbound_workflow_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    intent_id = Column(UUID(as_uuid=True), ForeignKey("inbound_intents.id", ondelete="CASCADE"), nullable=False)
    
    action_name = Column(String(255), nullable=False)
    success = Column(Boolean, nullable=False)
    error_message = Column(Text, nullable=True)

    # Relationships
    intent = relationship("InboundIntent", back_populates="workflow_events")
