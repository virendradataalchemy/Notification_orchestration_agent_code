from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException
import asyncio
from concurrent.futures import ThreadPoolExecutor

from .base import NotificationProvider, Message, ProviderResponse, ProviderStatus
from src.config import settings


class VoiceProvider(NotificationProvider):
    """Voice call provider using Twilio."""

    def __init__(self, config: dict = None):
        super().__init__(config)
        if settings.twilio_account_sid and settings.twilio_auth_token:
            self.client = Client(
                settings.twilio_account_sid,
                settings.twilio_auth_token
            )
        else:
            self.client = None
        self.from_number = settings.twilio_phone_number
        self.executor = ThreadPoolExecutor(max_workers=5)

    async def send(self, message: Message) -> ProviderResponse:
        """
        Send voice call via Twilio with recording enabled.

        Args:
            message: Voice message to send
                     body contains the text to be spoken
                     metadata can contain 'record_call': True/False

        Returns:
            ProviderResponse with Twilio call SID
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

            # Check if recording is enabled (default: True)
            enable_recording = message.metadata.get('record_call', True) if message.metadata else True
            
            # Create TwiML for text-to-speech
            twiml = f'<Response><Say>{message.body}</Say></Response>'
            
            # Build status callback URL for recording
            base_url = settings.app_base_url or "http://localhost:8000"
            status_callback = f"{base_url}/api/webhooks/twilio/voice-status"
            recording_status_callback = f"{base_url}/api/webhooks/twilio/recording-status"

            # Make voice call in thread pool since Twilio client is sync
            loop = asyncio.get_running_loop()
            
            call_params = {
                'to': message.recipient,
                'from_': self.from_number,
                'twiml': twiml,
                'status_callback': status_callback,
                'status_callback_event': ['initiated', 'ringing', 'answered', 'completed']
            }
            
            # Add recording parameters if enabled
            if enable_recording:
                call_params['record'] = True
                call_params['recording_status_callback'] = recording_status_callback
                call_params['recording_status_callback_event'] = ['completed']
                call_params['recording_channels'] = 'dual'  # Record both sides
            
            call = await loop.run_in_executor(
                self.executor,
                lambda: self.client.calls.create(**call_params)
            )

            return ProviderResponse(
                status=ProviderStatus.SUCCESS,
                message_id=call.sid,
                metadata={
                    'provider': 'twilio_voice',
                    'status': call.status,
                    'direction': call.direction,
                    'recording_enabled': enable_recording
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
        """Get voice call status from Twilio."""
        if not self.client:
            return ProviderResponse(
                status=ProviderStatus.FAILED,
                error_code="NOT_CONFIGURED"
            )

        try:
            loop = asyncio.get_running_loop()
            call = await loop.run_in_executor(
                self.executor,
                lambda: self.client.calls(message_id).fetch()
            )

            status_map = {
                'completed': ProviderStatus.SUCCESS,
                'busy': ProviderStatus.FAILED,
                'no-answer': ProviderStatus.FAILED,
                'failed': ProviderStatus.FAILED,
                'canceled': ProviderStatus.FAILED,
                'ringing': ProviderStatus.PENDING,
                'in-progress': ProviderStatus.PENDING,
                'queued': ProviderStatus.PENDING,
            }

            return ProviderResponse(
                status=status_map.get(call.status, ProviderStatus.PENDING),
                message_id=message_id,
                metadata={'twilio_status': call.status, 'duration': call.duration}
            )

        except Exception as e:
            return ProviderResponse(
                status=ProviderStatus.FAILED,
                error_code="STATUS_CHECK_FAILED",
                error_message=str(e)
            )

    async def validate_recipient(self, recipient: str) -> bool:
        """
        Validate phone number.

        Args:
            recipient: Phone number in E.164 format

        Returns:
            True if valid format
        """
        # Should start with + and be at least 10 digits
        return recipient.startswith('+') and len(recipient) >= 10

    def supports_channel(self) -> str:
        """Returns 'voice'."""
        return "voice"
