from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException
import phonenumbers
import asyncio
from concurrent.futures import ThreadPoolExecutor

from .base import NotificationProvider, Message, ProviderResponse, ProviderStatus
from src.config import settings


class SMSProvider(NotificationProvider):
    """SMS provider using Twilio."""

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
            or settings.twilio_phone_number
        )
        self.executor = ThreadPoolExecutor(max_workers=5)

    async def send(self, message: Message) -> ProviderResponse:
        """
        Send SMS via Twilio.

        Args:
            message: SMS message to send

        Returns:
            ProviderResponse with Twilio message SID
        """
        if not self.client:
            return ProviderResponse(
                status=ProviderStatus.FAILED,
                error_code="NOT_CONFIGURED",
                error_message="Twilio credentials not configured"
            )

        if not self.from_number:
            return ProviderResponse(
                status=ProviderStatus.FAILED,
                error_code="NO_FROM_NUMBER",
                error_message="Twilio phone number not configured"
            )

        try:
            # Validate phone number
            if not await self.validate_recipient(message.recipient):
                return ProviderResponse(
                    status=ProviderStatus.FAILED,
                    error_code="INVALID_PHONE",
                    error_message=f"Invalid phone number: {message.recipient}"
                )

            # Ensure body is not empty (Twilio requires it)
            body_text = message.body or message.data.get('body', '')
            if not body_text:
                body_text = message.data.get('message', '') or f"SMS: {message.subject or 'Notification'}"

            # Send SMS in thread pool since Twilio client is sync
            loop = asyncio.get_event_loop()
            twilio_message = await loop.run_in_executor(
                self.executor,
                lambda: self.client.messages.create(
                    to=message.recipient,
                    from_=self.from_number,
                    body=body_text
                )
            )

            return ProviderResponse(
                status=ProviderStatus.SUCCESS,
                message_id=twilio_message.sid,
                metadata={
                    'provider': 'twilio',
                    'status': twilio_message.status,
                    'price': twilio_message.price,
                    'price_unit': twilio_message.price_unit
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
        """
        Get SMS delivery status from Twilio.

        Args:
            message_id: Twilio message SID

        Returns:
            ProviderResponse with current status
        """
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
                'sent': ProviderStatus.PENDING,
                'queued': ProviderStatus.PENDING,
                'failed': ProviderStatus.FAILED,
                'undelivered': ProviderStatus.FAILED,
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
        Validate phone number format.

        Args:
            recipient: Phone number (E.164 format recommended)

        Returns:
            True if valid phone number
        """
        try:
            parsed = phonenumbers.parse(recipient, None)
            return phonenumbers.is_valid_number(parsed)
        except Exception:
            return False

    def supports_channel(self) -> str:
        """Returns 'sms'."""
        return "sms"
