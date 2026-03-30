from sqlalchemy import Column, String, Text, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSONB
import uuid
from datetime import datetime
from .base import Base


class AuditLog(Base):
    """Audit log for compliance tracking."""

    __tablename__ = "audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_type = Column(String(50), nullable=False, index=True)  # api_access|status_change|config_change|security_event
    user_id = Column(String(50), nullable=True, index=True)
    resource_type = Column(String(50), nullable=True)  # notification|template|preference
    resource_id = Column(String(100), nullable=True)
    action = Column(String(50), nullable=False)  # create|read|update|delete
    details = Column(JSONB, nullable=True)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    def __repr__(self):
        return f"<AuditLog(id={self.id}, event_type={self.event_type}, action={self.action})>"
