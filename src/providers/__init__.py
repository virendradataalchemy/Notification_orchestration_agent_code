from .base import NotificationProvider, ProviderResponse
from .email_provider import EmailProvider
from .mailgun_provider import MailgunProvider
from .sms_provider import SMSProvider
from .whatsapp_provider import WhatsAppProvider
from .slack_provider import SlackProvider
from .push_provider import PushProvider
from .voice_provider import VoiceProvider
from .inapp_provider import InAppProvider
from .mock_provider import (
    MockSMSProvider,
    MockEmailProvider,
    MockWhatsAppProvider,
    MockSlackProvider,
    MockPushProvider,
    MockVoiceProvider,
    MockInAppProvider,
)
from src.config import settings


def get_provider_for_channel(channel: str, provider_name: str = None, config: dict = None):
    """
    Get provider instance for a given channel.

    Args:
        channel: Channel type (email, sms, whatsapp, slack, push, voice, in_app)
        provider_name: Optional specific provider name (aws_ses, twilio, etc.)

    Returns:
        Provider instance or None if not available
    """
    # If mock mode is enabled, use mock providers
    if settings.use_mock_providers:
        mock_provider_map = {
            'email': MockEmailProvider,
            'sms': MockSMSProvider,
            'whatsapp': MockWhatsAppProvider,
            'slack': MockSlackProvider,
            'push': MockPushProvider,
            'voice': MockVoiceProvider,
            'in_app': MockInAppProvider,
            'inapp': MockInAppProvider,
        }
        provider_class = mock_provider_map.get(channel)
        if provider_class:
            return provider_class(config=config)
        return None

    # Real providers
    provider_map = {
        'email': {
            'mailgun': MailgunProvider,
            'aws_ses': EmailProvider,
            'default': MailgunProvider  # Changed to Mailgun as primary
        },
        'sms': {
            'twilio': SMSProvider,
            'default': SMSProvider
        },
        'whatsapp': {
            'twilio': WhatsAppProvider,
            'default': WhatsAppProvider
        },
        'slack': {
            'slack_api': SlackProvider,
            'default': SlackProvider
        },
        'push': {
            'fcm': PushProvider,
            'default': PushProvider
        },
        'voice': {
            'twilio': VoiceProvider,
            'default': VoiceProvider
        },
        'inapp': {
            'websocket': InAppProvider,
            'inapp': InAppProvider,
            'default': InAppProvider
        },
    }

    channel_providers = provider_map.get(channel, {})

    if not channel_providers:
        return None

    # Get specific provider or default
    provider_class = channel_providers.get(provider_name) or channel_providers.get('default')

    if provider_class:
        return provider_class(config=config)

    return None


__all__ = [
    "NotificationProvider",
    "ProviderResponse",
    "EmailProvider",
    "MailgunProvider",
    "SMSProvider",
    "WhatsAppProvider",
    "SlackProvider",
    "PushProvider",
    "VoiceProvider",
    "InAppProvider",
    "get_provider_for_channel",
]
