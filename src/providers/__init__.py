from importlib import import_module

from .base import NotificationProvider, ProviderResponse
from .mock_provider import (
    MockSMSProvider,
    MockEmailProvider,
    MockWhatsAppProvider,
    MockSlackProvider,
    # MockPushProvider,
    MockVoiceProvider,
    # MockInAppProvider,
)
from src.config import settings


def _load_provider_class(module_name: str, class_name: str):
    """
    Lazily import provider implementations so optional channel SDKs are only
    required when that specific channel is actually used.
    """
    module = import_module(f"src.providers.{module_name}")
    return getattr(module, class_name)


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
            # 'push': MockPushProvider,
            'voice': MockVoiceProvider,
            # 'in_app': MockInAppProvider,
            # 'inapp': MockInAppProvider,
        }
        provider_class = mock_provider_map.get(channel)
        if provider_class:
            return provider_class(config=config)
        return None

    # Real providers
    provider_map = {
        'email': {
            'mailgun': ('mailgun_provider', 'MailgunProvider'),
            # 'aws_ses': ('email_provider', 'EmailProvider'),  # Deprecated in favor of Mailgun
            'default': ('mailgun_provider', 'MailgunProvider')
        },
        'sms': {
            'twilio': ('sms_provider', 'SMSProvider'),
            'default': ('sms_provider', 'SMSProvider')
        },
        'whatsapp': {
            'twilio': ('whatsapp_provider', 'WhatsAppProvider'),
            'default': ('whatsapp_provider', 'WhatsAppProvider')
        },
        'slack': {
            'slack_api': ('slack_provider', 'SlackProvider'),
            'default': ('slack_provider', 'SlackProvider')
        },
        # 'push': {
        #     'fcm': ('push_provider', 'PushProvider'),
        #     'default': ('push_provider', 'PushProvider')
        # },
        'voice': {
            'twilio': ('voice_provider', 'VoiceProvider'),
            'default': ('voice_provider', 'VoiceProvider')
        },
        # 'inapp': {
        #     'websocket': ('inapp_provider', 'InAppProvider'),
        #     'inapp': ('inapp_provider', 'InAppProvider'),
        #     'default': ('inapp_provider', 'InAppProvider')
        # },
    }

    channel_providers = provider_map.get(channel, {})

    if not channel_providers:
        return None

    # Get specific provider or default
    provider_target = channel_providers.get(provider_name) or channel_providers.get('default')

    if provider_target:
        module_name, class_name = provider_target
        provider_class = _load_provider_class(module_name, class_name)
        return provider_class(config=config)

    return None


__all__ = [
    "NotificationProvider",
    "ProviderResponse",
    "get_provider_for_channel",
]
