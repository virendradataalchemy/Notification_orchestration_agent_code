from sqlalchemy import Column, String, Text, Integer, Boolean, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from datetime import datetime
from .base import Base


class Template(Base):
    """Notification template table.

    Supports both global templates (tenant_id=NULL) and tenant-specific templates.
    Tenant-specific templates can override or extend global templates.
    """

    __tablename__ = "templates"

    id = Column(String(50), primary_key=True)
    tenant_id = Column(String(50), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True)

    # Template identification
    name = Column(String(100), nullable=False)
    base_template_id = Column(String(50), nullable=True)  # Reference to global template if this is an override

    channel = Column(String(20), nullable=False, index=True)  # email|sms|whatsapp etc.
    language = Column(String(10), nullable=False, default="en")
    subject = Column(Text, nullable=True)  # For email
    body = Column(Text, nullable=False)
    provider_template_ref = Column(String(255), nullable=True)  # Internal mapping to provider-native template id
    provider_template_meta = Column(JSONB, nullable=True)  # Extra provider metadata
    version = Column(Integer, default=1)
    active = Column(Boolean, default=True, index=True)
    is_global = Column(Boolean, default=False, index=True)  # True for system templates
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    tenant = relationship("Tenant", back_populates="templates")

    __table_args__ = (
        # Ensure template names are unique per tenant (global templates have tenant_id=NULL)
        UniqueConstraint('tenant_id', 'name', 'channel', 'language', name='uq_tenant_template'),
    )

    def __repr__(self):
        return f"<Template(id={self.id}, tenant_id={self.tenant_id}, name={self.name}, channel={self.channel}, is_global={self.is_global})>"
