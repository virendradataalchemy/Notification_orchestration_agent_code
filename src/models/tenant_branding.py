"""Tenant branding model for email footers and visual identity."""

from sqlalchemy import Column, String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from .base import Base
import uuid


class TenantBranding(Base):
    """
    Tenant-level branding configuration.
    
    Stores logo, colors, contact info that automatically applies to all emails
    sent by the tenant (whether using templates or raw content).
    """

    __tablename__ = "tenant_branding"

    id = Column(String(50), primary_key=True, default=lambda: f"branding_{uuid.uuid4().hex[:12]}")
    tenant_id = Column(String(50), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)

    # Visual branding
    logo_url = Column(Text, nullable=True)  # Public URL or base64 data URI
    company_name = Column(String(200), nullable=True)
    theme_color = Column(String(20), nullable=True, default="#1d4ed8")  # Hex color code

    # Contact information
    contact_email = Column(String(200), nullable=True)
    contact_phone = Column(String(50), nullable=True)
    website = Column(String(200), nullable=True)

    # Custom footer (optional Jinja2 HTML template)
    footer_html = Column(Text, nullable=True)

    # Configuration
    enabled = Column(Boolean, nullable=False, default=True)
    apply_to_all_channels = Column(Boolean, nullable=False, default=False)  # Future: SMS, etc.

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    tenant = relationship("Tenant", back_populates="branding")

    def to_dict(self):
        """Convert to dictionary for API responses."""
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "logo_url": self.logo_url,
            "company_name": self.company_name,
            "theme_color": self.theme_color,
            "contact_email": self.contact_email,
            "contact_phone": self.contact_phone,
            "website": self.website,
            "footer_html": self.footer_html,
            "enabled": self.enabled,
            "apply_to_all_channels": self.apply_to_all_channels,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self):
        return f"<TenantBranding(id={self.id}, tenant_id={self.tenant_id}, enabled={self.enabled})>"
