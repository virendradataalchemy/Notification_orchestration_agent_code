from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum
import uuid


class Priority(str, Enum):
    """Notification priority."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Channel(str, Enum):
    """Notification channels."""
    EMAIL = "email"
    SMS = "sms"
    WHATSAPP = "whatsapp"
    SLACK = "slack"
    PUSH = "push"
    VOICE = "voice"
    INAPP = "inapp"


class NotificationStatus(str, Enum):
    """Notification status."""
    QUEUED = "queued"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"


# Request Schemas
class RecipientInfo(BaseModel):
    """Recipient information."""
    user_id: str = Field(..., description="Unique user identifier")
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    device_tokens: Optional[List[str]] = None
    slack_id: Optional[str] = None


class NotificationOptions(BaseModel):
    """Notification options."""
    idempotency_key: Optional[str] = None
    track_opens: bool = True
    track_clicks: bool = True
    attachments: Optional[List[str]] = None


class NotificationData(BaseModel):
    """Notification content data."""
    type: str = Field(..., description="Notification type (e.g., 'order_confirmation')")
    priority: Priority = Priority.MEDIUM
    channels: List[Channel] = [Channel.EMAIL]
    subject: Optional[str] = None
    body: Optional[str] = None
    template_id: Optional[str] = None
    data: Dict[str, Any] = Field(default_factory=dict, description="Template variables")
    idempotency_key: Optional[str] = Field(None, description="Unique key to prevent duplicate notifications")


class SendNotificationRequest(BaseModel):
    """Request to send a notification."""
    recipient: RecipientInfo
    notification: NotificationData
    options: Optional[NotificationOptions] = NotificationOptions()


class BatchRecipient(BaseModel):
    """Batch notification recipient."""
    user_id: str
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    data: Dict[str, Any] = Field(default_factory=dict)


class BatchNotificationRequest(BaseModel):
    """Request to send batch notifications."""
    template_id: str
    recipients: List[BatchRecipient]
    channel: Channel
    schedule_at: Optional[datetime] = None


# Response Schemas
class ChannelStatus(BaseModel):
    """Channel delivery status."""
    channel: str
    provider: str
    message_id: Optional[str] = None
    status: str
    delivered_at: Optional[datetime] = None
    opened_at: Optional[datetime] = None
    clicked_at: Optional[datetime] = None


class NotificationResponse(BaseModel):
    """Notification response."""
    notification_id: str
    status: str  # string to accept both enum values and raw strings from Supabase
    channels: Dict[str, Any]
    estimated_delivery: Optional[datetime] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class BatchNotificationResponse(BaseModel):
    """Batch notification response."""
    batch_id: str
    status: str
    total_recipients: int
    estimated_completion: Optional[datetime] = None


class NotificationStatusResponse(BaseModel):
    """Detailed notification status."""
    notification_id: str
    user_id: str
    type: str
    priority: Priority
    status: NotificationStatus
    channels: List[ChannelStatus]
    attempts: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Template Schemas
class TemplateCreate(BaseModel):
    """Create template request."""
    id: str
    name: str
    channel: Channel
    language: str = "en"
    subject: Optional[str] = None
    body: str
    version: int = 1


class TenantTemplateCreate(BaseModel):
    """Create tenant-specific template request."""
    name: str = Field(..., description="Template name (e.g., 'welcome_email')")
    channel: Channel = Field(..., description="Channel type")
    language: str = Field(default="en", description="Language code (ISO 639-1)")
    subject: Optional[str] = Field(None, description="Template subject (for email)")
    body: str = Field(..., description="Template body with Jinja2 variables")
    base_template_id: Optional[str] = Field(None, description="Global template ID to inherit from")
    description: Optional[str] = Field(None, description="Template description")


class TenantTemplateUpdate(BaseModel):
    """Update tenant template request."""
    name: Optional[str] = None
    subject: Optional[str] = None
    body: Optional[str] = None
    active: Optional[bool] = None
    description: Optional[str] = None


class TemplatePreviewRequest(BaseModel):
    """Preview template rendering."""
    subject: Optional[str] = Field(None, description="Template subject (optional)")
    body: str = Field(..., description="Template body with Jinja2 variables")
    sample_data: Dict[str, Any] = Field(..., description="Sample data for rendering")


class TemplatePreviewResponse(BaseModel):
    """Previewed template output."""
    rendered_subject: Optional[str] = None
    rendered_body: str
    valid: bool
    error: Optional[str] = None
    variables_used: List[str] = Field(default_factory=list, description="Variables found in template")


class TemplateCloneRequest(BaseModel):
    """Clone template request."""
    global_template_id: str = Field(..., description="Global template ID to clone")
    new_name: Optional[str] = Field(None, description="New template name (defaults to original)")
    customizations: Optional[Dict[str, str]] = Field(None, description="Fields to customize")


class TemplateResponse(BaseModel):
    """Template response."""
    id: int | str
    tenant_id: Optional[int | str] = None
    name: str
    channel: str
    language: str
    subject: Optional[str] = None
    body: str
    version: int
    active: bool
    is_global: bool
    base_template_id: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class TenantTemplateListResponse(BaseModel):
    """List of tenant templates."""
    tenant_id: int | str
    tenant_name: Optional[str] = None
    templates: List[TemplateResponse]
    global_templates_count: int
    tenant_templates_count: int


# User Preference Schemas
class UserPreferenceUpdate(BaseModel):
    """Update user preferences."""
    preferred_channels: Optional[Dict[str, List[str]]] = None
    quiet_hours: Optional[Dict[str, str]] = None
    unsubscribed: Optional[List[str]] = None
    language: Optional[str] = None
    timezone: Optional[str] = None


class UserPreferenceResponse(BaseModel):
    """User preference response."""
    user_id: str
    preferred_channels: Optional[Dict[str, List[str]]] = None
    quiet_hours: Optional[Dict[str, str]] = None
    unsubscribed: Optional[List[str]] = None
    language: Optional[str] = None
    timezone: Optional[str] = None

    class Config:
        from_attributes = True


# Webhook Schemas
class WebhookEvent(BaseModel):
    """Webhook event payload."""
    event: str
    notification_id: str
    channel: str
    timestamp: datetime
    metadata: Dict[str, Any] = Field(default_factory=dict)


# Tenant Authentication Schemas
class TenantLoginRequest(BaseModel):
    """Tenant portal login request."""
    username: str = Field(..., description="Tenant username")
    password: str = Field(..., description="Tenant password")


class TenantLoginResponse(BaseModel):
    """Tenant portal login response."""
    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field(default="bearer", description="Token type")
    tenant_id: int | str
    tenant_name: str
    expires_in: int = Field(description="Token expiration in seconds")


# Health Check
class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    timestamp: datetime
    version: str
    services: Dict[str, str]
