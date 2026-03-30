"""
Mock providers for testing without hitting real APIs.

These providers simulate successful delivery for demo/testing purposes.
Enable by setting USE_MOCK_PROVIDERS=True in .env
"""

import uuid
from datetime import datetime
from .base import NotificationProvider, Message, ProviderResponse, ProviderStatus


class MockSMSProvider(NotificationProvider):
    """Mock SMS provider for testing."""

    def __init__(self, config: dict = None):
        super().__init__(config)

    async def send(self, message: Message) -> ProviderResponse:
        """Simulate SMS sending."""
        return ProviderResponse(
            status=ProviderStatus.SUCCESS,
            message_id=f"mock_sms_{uuid.uuid4().hex[:12]}",
            metadata={
                'provider': 'mock_twilio',
                'status': 'delivered',
                'mock': True,
                'to': message.recipient,
                'body_length': len(message.body) if message.body else 0
            }
        )

    async def get_status(self, message_id: str) -> ProviderResponse:
        """Simulate status check."""
        return ProviderResponse(
            status=ProviderStatus.SUCCESS,
            message_id=message_id,
            metadata={'status': 'delivered', 'mock': True}
        )

    async def validate_recipient(self, recipient: str) -> bool:
        """Accept any phone-like format."""
        return recipient.startswith('+') or recipient.replace('-', '').replace(' ', '').isdigit()

    def supports_channel(self) -> str:
        return "sms"


class MockEmailProvider(NotificationProvider):
    """Mock email provider for testing."""

    def __init__(self, config: dict = None):
        super().__init__(config)

    async def send(self, message: Message) -> ProviderResponse:
        """Simulate email sending."""
        return ProviderResponse(
            status=ProviderStatus.SUCCESS,
            message_id=f"mock_email_{uuid.uuid4().hex[:12]}",
            metadata={
                'provider': 'mock_mailgun',
                'status': 'delivered',
                'mock': True,
                'to': message.recipient,
                'subject': message.subject,
                'has_html': message.html is not None
            }
        )

    async def get_status(self, message_id: str) -> ProviderResponse:
        """Simulate status check."""
        return ProviderResponse(
            status=ProviderStatus.SUCCESS,
            message_id=message_id,
            metadata={'status': 'delivered', 'mock': True}
        )

    async def validate_recipient(self, recipient: str) -> bool:
        """Accept any email-like format."""
        return '@' in recipient and '.' in recipient.split('@')[1]

    def supports_channel(self) -> str:
        return "email"


class MockWhatsAppProvider(NotificationProvider):
    """Mock WhatsApp provider for testing."""

    def __init__(self, config: dict = None):
        super().__init__(config)

    async def send(self, message: Message) -> ProviderResponse:
        """Simulate WhatsApp sending."""
        return ProviderResponse(
            status=ProviderStatus.SUCCESS,
            message_id=f"mock_whatsapp_{uuid.uuid4().hex[:12]}",
            metadata={
                'provider': 'mock_twilio_whatsapp',
                'status': 'delivered',
                'mock': True,
                'to': message.recipient
            }
        )

    async def get_status(self, message_id: str) -> ProviderResponse:
        return ProviderResponse(
            status=ProviderStatus.SUCCESS,
            message_id=message_id,
            metadata={'status': 'delivered', 'mock': True}
        )

    async def validate_recipient(self, recipient: str) -> bool:
        return recipient.startswith('+') or recipient.startswith('whatsapp:')

    def supports_channel(self) -> str:
        return "whatsapp"


class MockSlackProvider(NotificationProvider):
    """Mock Slack provider for testing."""

    def __init__(self, config: dict = None):
        super().__init__(config)

    async def send(self, message: Message) -> ProviderResponse:
        """Simulate Slack sending."""
        return ProviderResponse(
            status=ProviderStatus.SUCCESS,
            message_id=f"mock_slack_{uuid.uuid4().hex[:12]}",
            metadata={
                'provider': 'mock_slack',
                'status': 'delivered',
                'mock': True,
                'channel': message.recipient
            }
        )

    async def get_status(self, message_id: str) -> ProviderResponse:
        return ProviderResponse(
            status=ProviderStatus.SUCCESS,
            message_id=message_id,
            metadata={'status': 'delivered', 'mock': True}
        )

    async def validate_recipient(self, recipient: str) -> bool:
        return recipient.startswith('C') or recipient.startswith('U') or recipient.startswith('#')

    def supports_channel(self) -> str:
        return "slack"


class MockPushProvider(NotificationProvider):
    """Mock Push notification provider for testing."""

    def __init__(self, config: dict = None):
        super().__init__(config)

    async def send(self, message: Message) -> ProviderResponse:
        """Simulate Push sending."""
        return ProviderResponse(
            status=ProviderStatus.SUCCESS,
            message_id=f"mock_push_{uuid.uuid4().hex[:12]}",
            metadata={
                'provider': 'mock_firebase',
                'status': 'delivered',
                'mock': True,
                'token': message.recipient
            }
        )

    async def get_status(self, message_id: str) -> ProviderResponse:
        return ProviderResponse(
            status=ProviderStatus.SUCCESS,
            message_id=message_id,
            metadata={'status': 'delivered', 'mock': True}
        )

    async def validate_recipient(self, recipient: str) -> bool:
        return len(recipient) > 10  # Basic token validation

    def supports_channel(self) -> str:
        return "push"


class MockVoiceProvider(NotificationProvider):
    """Mock Voice provider for testing."""

    def __init__(self, config: dict = None):
        super().__init__(config)

    async def send(self, message: Message) -> ProviderResponse:
        """Simulate Voice call."""
        return ProviderResponse(
            status=ProviderStatus.SUCCESS,
            message_id=f"mock_voice_{uuid.uuid4().hex[:12]}",
            metadata={
                'provider': 'mock_twilio_voice',
                'status': 'completed',
                'mock': True,
                'to': message.recipient,
                'duration': '30s'
            }
        )

    async def get_status(self, message_id: str) -> ProviderResponse:
        return ProviderResponse(
            status=ProviderStatus.SUCCESS,
            message_id=message_id,
            metadata={'status': 'completed', 'mock': True}
        )

    async def validate_recipient(self, recipient: str) -> bool:
        return recipient.startswith('+') or recipient.replace('-', '').replace(' ', '').isdigit()

    def supports_channel(self) -> str:
        return "voice"


class MockInAppProvider(NotificationProvider):
    """Mock In-App notification provider for testing."""

    def __init__(self, config: dict = None):
        super().__init__(config)

    async def send(self, message: Message) -> ProviderResponse:
        """Simulate In-App notification."""
        return ProviderResponse(
            status=ProviderStatus.SUCCESS,
            message_id=f"mock_inapp_{uuid.uuid4().hex[:12]}",
            metadata={
                'provider': 'mock_inapp',
                'status': 'delivered',
                'mock': True,
                'user_id': message.recipient
            }
        )

    async def get_status(self, message_id: str) -> ProviderResponse:
        return ProviderResponse(
            status=ProviderStatus.SUCCESS,
            message_id=message_id,
            metadata={'status': 'delivered', 'mock': True}
        )

    async def validate_recipient(self, recipient: str) -> bool:
        return len(recipient) > 0

    def supports_channel(self) -> str:
        return "in_app"
