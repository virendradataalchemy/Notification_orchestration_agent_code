from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json

from .base import NotificationProvider, Message, ProviderResponse, ProviderStatus
from src.config import settings


class WhatsAppProvider(NotificationProvider):
    """WhatsApp provider using Twilio."""

    def __init__(self, config: dict = None):
        super().__init__(config)
        if settings.twilio_account_sid and settings.twilio_auth_token:
            self.client = Client(
                settings.twilio_account_sid,
                settings.twilio_auth_token
            )
        else:
            self.client = None
        self.from_number = (
            self.config.get("from_number")
            or self.config.get("sender_id")
            or settings.twilio_whatsapp_number
        )
        self.executor = ThreadPoolExecutor(max_workers=5)

    async def send(self, message: Message) -> ProviderResponse:
        """
        Send WhatsApp message via Twilio.

        Args:
            message: WhatsApp message to send

        Returns:
            ProviderResponse with Twilio message SID
        """
        if not self.client:
            return ProviderResponse(
                status=ProviderStatus.FAILED,
                error_code="NOT_CONFIGURED",
                error_message="Twilio WhatsApp credentials not configured"
            )

        if not self.from_number:
            return ProviderResponse(
                status=ProviderStatus.FAILED,
                error_code="NO_FROM_NUMBER",
                error_message="Twilio WhatsApp number not configured"
            )

        try:
            # Ensure recipient has whatsapp: prefix
            to_number = message.recipient
            if not to_number.startswith('whatsapp:'):
                to_number = f'whatsapp:{to_number}'
            from_number = self.from_number
            if from_number and not from_number.startswith('whatsapp:'):
                from_number = f'whatsapp:{from_number}'

            template_id = message.data.get("template_id")
            template_vars = message.data.get("template_variables") or {}
            provider_template_refs = message.data.get("provider_template_refs") or {}

            # Resolve provider-native template ref (Twilio Content SID) from internal mapping
            content_sid = (
                provider_template_refs.get("whatsapp")
                or (self.config.get("template_refs") or {}).get(template_id)
            )

            create_kwargs = {
                "to": to_number,
                "from_": from_number,
            }
            if content_sid:
                create_kwargs["content_sid"] = content_sid
                create_kwargs["content_variables"] = json.dumps(template_vars or {})
            else:
                # Fallback to body send when no provider template mapping exists
                body_text = message.body or message.data.get('body', '')
                if not body_text:
                    body_text = message.data.get('message', '') or f"WhatsApp: {message.subject or 'Notification'}"
                create_kwargs["body"] = body_text

            # Send WhatsApp message in thread pool
            loop = asyncio.get_event_loop()
            twilio_message = await loop.run_in_executor(
                self.executor,
                lambda: self.client.messages.create(
                    **create_kwargs
                )
            )

            return ProviderResponse(
                status=ProviderStatus.SUCCESS,
                message_id=twilio_message.sid,
                metadata={
                    'provider': 'twilio_whatsapp',
                    'status': twilio_message.status
                }
            )

        except TwilioRestException as e:
            return ProviderResponse(
                status=ProviderStatus.FAILED,
                error_code=str(e.code),
                error_message=e.msg
            )

        except Exception as e:
            return ProviderResponse(
                status=ProviderStatus.FAILED,
                error_code="UNKNOWN_ERROR",
                error_message=str(e)
            )

    async def get_status(self, message_id: str) -> ProviderResponse:
        """Get WhatsApp message status from Twilio."""
        if not self.client:
            return ProviderResponse(
                status=ProviderStatus.FAILED,
                error_code="NOT_CONFIGURED"
            )

        try:
            loop = asyncio.get_event_loop()
            message = await loop.run_in_executor(
                self.executor,
                lambda: self.client.messages(message_id).fetch()
            )

            status_map = {
                'delivered': ProviderStatus.SUCCESS,
                'read': ProviderStatus.SUCCESS,
                'sent': ProviderStatus.PENDING,
                'queued': ProviderStatus.PENDING,
                'failed': ProviderStatus.FAILED,
            }

            return ProviderResponse(
                status=status_map.get(message.status, ProviderStatus.PENDING),
                message_id=message_id,
                metadata={'twilio_status': message.status}
            )

        except Exception as e:
            return ProviderResponse(
                status=ProviderStatus.FAILED,
                error_code="STATUS_CHECK_FAILED",
                error_message=str(e)
            )

    async def validate_recipient(self, recipient: str) -> bool:
        """
        Validate WhatsApp phone number.

        Args:
            recipient: Phone number (with or without whatsapp: prefix)

        Returns:
            True if valid format
        """
        # Remove whatsapp: prefix if present
        phone = recipient.replace('whatsapp:', '')

        # Basic validation - should start with +
        return phone.startswith('+') and len(phone) >= 10

    def supports_channel(self) -> str:
        """Returns 'whatsapp'."""
        return "whatsapp"
