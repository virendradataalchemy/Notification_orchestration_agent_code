"""Channel capability and policy definitions for API clients."""

from typing import Dict, Any, List, Set


# Product policy:
# - WhatsApp requires template_id for programmatic sends.
# - Other channels can send free-form body content.
CHANNEL_CAPABILITIES: Dict[str, Dict[str, Any]] = {
    "email": {
        "template_required": False,
        "required_recipient_fields": ["email"],
        "supports_subject": True,
        "requires_body": True,
        "notes": "Free-form or template-based content supported.",
    },
    "sms": {
        "template_required": False,
        "required_recipient_fields": ["phone"],
        "supports_subject": False,
        "requires_body": True,
        "notes": "Free-form text supported.",
    },
    "whatsapp": {
        "template_required": True,
        "required_recipient_fields": ["phone"],
        "supports_subject": False,
        "requires_body": True,
        "notes": "Template required by current platform policy for programmatic sends.",
    },
    "slack": {
        "template_required": False,
        "required_recipient_fields": ["slack_id"],
        "supports_subject": False,
        "requires_body": True,
        "notes": "Recipient can also come from tenant provider config fallback.",
    },
    "push": {
        "template_required": False,
        "required_recipient_fields": ["device_tokens"],
        "supports_subject": True,
        "requires_body": True,
        "notes": "Push title/body supported; recipient must have at least one device token.",
    },
    "voice": {
        "template_required": False,
        "required_recipient_fields": ["phone"],
        "supports_subject": False,
        "requires_body": True,
        "notes": "Body is used as TTS input.",
    },
    "inapp": {
        "template_required": False,
        "required_recipient_fields": ["user_id"],
        "supports_subject": True,
        "requires_body": True,
        "notes": "In-app messages are addressed by platform user id.",
    },
}


def get_provider_for_channel(channel: str) -> str:
    """Get the default provider name for a channel."""
    provider_map = {
        "email": "mailgun",
        "sms": "twilio",
        "whatsapp": "twilio",
        "slack": "slack_api",
        "push": "fcm",
        "voice": "twilio",
        "inapp": "websocket",
    }
    return provider_map.get(channel, "unknown")


def channels_requiring_templates() -> Set[str]:
    """Return channels that require template_id."""
    return {
        channel
        for channel, capability in CHANNEL_CAPABILITIES.items()
        if capability.get("template_required")
    }


def get_channel_capabilities() -> List[Dict[str, Any]]:
    """Return a sorted list of channel capability records."""
    records: List[Dict[str, Any]] = []
    for channel in sorted(CHANNEL_CAPABILITIES.keys()):
        capability = CHANNEL_CAPABILITIES[channel]
        records.append(
            {
                "channel": channel,
                "template_required": capability["template_required"],
                "required_recipient_fields": capability["required_recipient_fields"],
                "supports_subject": capability["supports_subject"],
                "requires_body": capability["requires_body"],
                "notes": capability["notes"],
            }
        )
    return records
