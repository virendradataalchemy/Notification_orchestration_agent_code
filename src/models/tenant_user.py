from sqlalchemy import Column, String, ForeignKey, DateTime, Boolean
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
import uuid
from datetime import datetime
from .base import Base, TimestampMixin

class TenantUser(Base, TimestampMixin):
    """Individual users/team members within a tenant organization."""

    __tablename__ = "tenant_users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(String(50), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    
    email = Column(String(255), nullable=False, index=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    
    full_name = Column(String(255), nullable=True)
    role = Column(String(20), nullable=False, default="marketing")  # root|admin|marketing
    permissions = Column(JSONB, nullable=True)  # Detailed IAM permissions
    
    is_active = Column(Boolean, default=True, index=True)
    last_login_at = Column(DateTime, nullable=True)

    # Relationships
    tenant = relationship("Tenant")

    def __repr__(self):
        return f"<TenantUser(id={self.id}, email={self.email}, role={self.role})>"


class TenantInvitation(Base, TimestampMixin):
    """Pending team invitations for a tenant."""

    __tablename__ = "tenant_invitations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(String(50), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    
    email = Column(String(255), nullable=False)
    token = Column(String(100), unique=True, nullable=False, index=True)
    role = Column(String(20), nullable=False, default="marketing")
    permissions = Column(JSONB, nullable=True)
    
    invited_by_user_id = Column(UUID(as_uuid=True), ForeignKey("tenant_users.id"), nullable=True)
    expires_at = Column(DateTime, nullable=False)
    accepted_at = Column(DateTime, nullable=True)

    # Relationships
    tenant = relationship("Tenant")

    def __repr__(self):
        return f"<TenantInvitation(email={self.email}, tenant_id={self.tenant_id}, status={'accepted' if self.accepted_at else 'pending'})>"
