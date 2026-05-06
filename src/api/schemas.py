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
    # PUSH = "push"
    VOICE = "voice"
    # INAPP = "inapp"


class DeliveryMode(str, Enum):
    """Delivery execution mode for selected channels."""
    PARALLEL_ALL = "parallel_all"
    SEQUENTIAL_FAILOVER = "sequential_failover"


class NotificationStatus(str, Enum):
    """Notification status."""
    QUEUED = "queued"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"


class InboundMessageCanonical(BaseModel):
    """Universal canonical format for incoming messages from any channel."""
    tenant_id: str
    channel: Channel
    sender_address: str
    provider_message_id: str
    raw_payload: Dict[str, Any]
    candidate_id: Optional[str] = None
    owner_id: Optional[str] = None
    retention_date: Optional[datetime] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

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
    channels: List[Channel] = Field(default_factory=list)
    subject: Optional[str] = None
    body: Optional[str] = None
    template_id: Optional[str] = None
    channel_template_map: Optional[Dict[str, str]] = None
    channel_subject_map: Optional[Dict[str, str]] = None
    channel_body_map: Optional[Dict[str, str]] = None
    data: Dict[str, Any] = Field(default_factory=dict, description="Template variables")
    idempotency_key: Optional[str] = Field(None, description="Unique key to prevent duplicate notifications")
    delivery_mode: Optional[DeliveryMode] = None
    strict_client_priority: bool = True
    ai_fallback_enabled: bool = True
    ai_on_no_channel_preference: bool = True


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
    slack_id: Optional[str] = None
    device_tokens: Optional[List[str]] = None
    data: Dict[str, Any] = Field(default_factory=dict)


class BatchNotificationRequest(BaseModel):
    """Request to send batch notifications."""
    template_id: Optional[str] = None
    subject: Optional[str] = None
    body: Optional[str] = None
    data: Dict[str, Any] = Field(default_factory=dict)
    recipients: List[BatchRecipient]
    channel: Channel
    schedule_at: Optional[datetime] = None


class BatchMultiChannelNotificationRequest(BaseModel):
    """Request to send batch notifications across multiple channels."""
    template_id: Optional[str] = None
    subject: Optional[str] = None
    body: Optional[str] = None
    channel_template_map: Optional[Dict[str, str]] = None
    channel_subject_map: Optional[Dict[str, str]] = None
    channel_body_map: Optional[Dict[str, str]] = None
    data: Dict[str, Any] = Field(default_factory=dict)
    recipients: List[BatchRecipient]
    channels: List[Channel] = Field(default_factory=list)
    delivery_mode: Optional[DeliveryMode] = None
    strict_client_priority: bool = True
    ai_fallback_enabled: bool = True
    ai_on_no_channel_preference: bool = True
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
    status: NotificationStatus
    channels: Dict[str, ChannelStatus]
    estimated_delivery: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class BatchNotificationResponse(BaseModel):
    """Batch notification response."""
    batch_id: str
    status: str
    total_recipients: int = 0
    estimated_completion: Optional[datetime] = None


class BatchMultiChannelNotificationResponse(BaseModel):
    """Batch multi-channel notification response."""
    batch_id: str
    status: str
    total_recipients: int = 0
    total_notifications: int = 0
    total_channel_records: int = 0
    channels: List[str] = Field(default_factory=list)
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
    provider_template_ref: Optional[str] = Field(
        None,
        description="Optional provider-native template reference (internal use, e.g., Twilio Content SID)"
    )
    provider_template_meta: Optional[Dict[str, Any]] = Field(
        None,
        description="Optional provider metadata for template dispatch"
    )
    description: Optional[str] = Field(None, description="Template description")


class TenantTemplateUpdate(BaseModel):
    """Update tenant template request."""
    name: Optional[str] = None
    subject: Optional[str] = None
    body: Optional[str] = None
    active: Optional[bool] = None
    provider_template_ref: Optional[str] = None
    provider_template_meta: Optional[Dict[str, Any]] = None
    description: Optional[str] = None


class TemplatePreviewRequest(BaseModel):
    """Preview template rendering."""
    subject: Optional[str] = Field(None, description="Template subject (optional)")
    body: str = Field(..., description="Template body with Jinja2 variables")
    sample_data: Dict[str, Any] = Field(..., description="Sample data for rendering")
    wrap_variables: bool = Field(False, description="Wrap variables in spans for visual editing")


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
    id: str
    tenant_id: Optional[str] = None
    name: str
    channel: str
    language: str
    subject: Optional[str] = None
    body: str
    version: int
    active: bool
    is_global: bool
    base_template_id: Optional[str] = None
    provider_template_ref: Optional[str] = None
    provider_template_meta: Optional[Dict[str, Any]] = None
    created_at: datetime

    class Config:
        from_attributes = True


class TenantTemplateListResponse(BaseModel):
    """List of tenant templates."""
    tenant_id: str
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
    tenant_id: str
    tenant_name: str
    tenant_type: str = Field(default="client", description="Type of tenant account (client/marketing)")
    expires_in: int = Field(description="Token expiration in seconds")


class ChannelCapability(BaseModel):
    """Channel capability record for API clients."""
    channel: Channel
    template_required: bool
    required_recipient_fields: List[str]
    supports_subject: bool
    requires_body: bool
    notes: str


class ChannelCapabilitiesResponse(BaseModel):
    """List of capabilities for all supported channels."""
    channels: List[ChannelCapability]


# Health Check
class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    timestamp: datetime
    version: str
    services: Dict[str, str]


class AITemplateGenerateRequest(BaseModel):
    """Request to generate a template using AI."""
    content: str = Field(..., description="Raw content or instructions for the template")
    channel: Channel = Field(..., description="Target channel for the template")


class MultiChannelTemplateRequest(BaseModel):
    """Request to generate multi-channel templates using AI."""
    content: str = Field(..., description="Instructions for the templates")
    channels: List[Channel] = Field(..., description="Channels to generate templates for")


class AITemplateGenerateResponse(BaseModel):
    """AI generated template response."""
    name: Optional[str] = Field(None, description="Suggested template name")
    subject: Optional[str] = None
    body: str
    description: str


class MultiChannelTemplateResponse(BaseModel):
    """Response containing AI generated templates for multiple channels."""
    templates: Dict[Channel, AITemplateGenerateResponse]
