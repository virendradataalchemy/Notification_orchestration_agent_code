from sqlalchemy import Column, String, Boolean, DateTime, Text, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from datetime import datetime
import hashlib
import secrets
from passlib.context import CryptContext
from .base import Base, TimestampMixin

# Password hashing context (added pbkdf2_sha256 for environment compatibility)
pwd_context = CryptContext(schemes=["pbkdf2_sha256", "bcrypt"], deprecated="auto")


class Tenant(Base, TimestampMixin):
    """Multi-tenant table for B2B SaaS."""

    __tablename__ = "tenants"

    id = Column(String(50), primary_key=True)  # e.g., "tenant_acme_corp"
    name = Column(String(255), nullable=False)  # Company name
    status = Column(String(20), nullable=False, default="active", index=True)  # active|suspended|deleted
    tenant_type = Column(String(20), nullable=False, default="client", index=True)  # client|marketing

    # Portal Authentication (username/password for web UI)
    username = Column(String(100), unique=True, nullable=True, index=True)  # For portal login
    password_hash = Column(String(255), nullable=True)  # Hashed password

    # API Authentication (API key for programmatic access)
    api_key_hash = Column(String(255), nullable=False, unique=True, index=True)  # Hashed API key
    api_key_prefix = Column(String(50), nullable=False)  # For display: "sk_live_abc..."

    # Configuration
    config = Column(JSONB, nullable=True)  # Tenant-specific settings
    tenant_metadata = Column(JSONB, nullable=True)  # Additional metadata (billing tier, etc.)

    # Contact
    admin_email = Column(String(255), nullable=True)
    admin_name = Column(String(255), nullable=True)

    # Timestamps
    suspended_at = Column(DateTime, nullable=True)
    deleted_at = Column(DateTime, nullable=True)

    # Relationships
    notifications = relationship("Notification", back_populates="tenant", cascade="all, delete-orphan")
    templates = relationship("Template", back_populates="tenant", cascade="all, delete-orphan")
    user_preferences = relationship("UserPreference", back_populates="tenant", cascade="all, delete-orphan")
    provider_configs = relationship("TenantProviderConfig", back_populates="tenant", cascade="all, delete-orphan")
    channel_preferences = relationship(
        "TenantChannelPreference",
        back_populates="tenant",
        cascade="all, delete-orphan"
    )
    def __repr__(self):
        return f"<Tenant(id={self.id}, name={self.name}, status={self.status})>"

    @staticmethod
    def generate_api_key(tenant_id: str, env: str = "live") -> tuple[str, str, str]:
        """
        Generate a new API key for a tenant.

        Returns:
            tuple: (api_key, api_key_hash, api_key_prefix)
            - api_key: Full key to give to tenant (only shown once)
            - api_key_hash: Hashed key to store in database
            - api_key_prefix: Prefix for display purposes
        """
        # Format: sk_{env}_{tenant_id}_{random}
        random_part = secrets.token_urlsafe(32)
        api_key = f"sk_{env}_{tenant_id}_{random_part}"

        # Hash for storage
        api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()

        # Prefix for display
        api_key_prefix = f"sk_{env}_{'*' * 20}"

        return api_key, api_key_hash, api_key_prefix

    @staticmethod
    def hash_api_key(api_key: str) -> str:
        """Hash an API key for comparison."""
        return hashlib.sha256(api_key.encode()).hexdigest()

    @staticmethod
    def hash_password(password: str) -> str:
        """Hash a password for storage."""
        return pwd_context.hash(password)

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Verify a password against a hash."""
        return pwd_context.verify(plain_password, hashed_password)

    @staticmethod
    def generate_username(tenant_id: str) -> str:
        """Generate a username from tenant ID."""
        # Remove 'tenant_' prefix if exists and convert to lowercase
        username = tenant_id.replace('tenant_', '').replace('_', '.').lower()
        return username


class TenantProviderConfig(Base, TimestampMixin):
    """Tenant-specific provider configurations."""

    __tablename__ = "tenant_provider_configs"

    id = Column(String(50), primary_key=True)
    tenant_id = Column(String(50), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)

    provider = Column(String(50), nullable=False, index=True)  # slack, email, sms, whatsapp, push

    # Provider-specific configuration
    config = Column(JSONB, nullable=False)
    # Examples:
    # Slack: {"channel_id": "#general", "webhook_url": "https://..."}
    # Email: {"from_name": "ACME Corp", "reply_to": "support@acme.com"}
    # SMS: {"sender_id": "ACME"}

    is_active = Column(Boolean, default=True, index=True)
    notes = Column(Text, nullable=True)

    # Relationships
    tenant = relationship("Tenant", back_populates="provider_configs")

    __table_args__ = (
        UniqueConstraint('tenant_id', 'provider', name='uq_tenant_provider'),
    )

    def __repr__(self):
        return f"<TenantProviderConfig(tenant_id={self.tenant_id}, provider={self.provider}, active={self.is_active})>"
