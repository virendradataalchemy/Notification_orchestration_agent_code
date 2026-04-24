from slack_sdk.web.async_client import AsyncWebClient
from slack_sdk.errors import SlackApiError

from .base import NotificationProvider, Message, ProviderResponse, ProviderStatus
from src.config import settings


class SlackProvider(NotificationProvider):
    """Slack provider using Slack SDK."""

    def __init__(self, config: dict = None):
        super().__init__(config)
        if settings.slack_bot_token:
            self.client = AsyncWebClient(token=settings.slack_bot_token)
        else:
            self.client = None
        self.default_channel_id = self.config.get("channel_id")

    async def send(self, message: Message) -> ProviderResponse:
        """
        Send Slack message.

        Args:
            message: Slack message to send
                     recipient should be channel ID or user ID

        Returns:
            ProviderResponse with Slack timestamp
        """
        if not self.client:
            return ProviderResponse(
                status=ProviderStatus.FAILED,
                error_code="NOT_CONFIGURED",
                error_message="Slack bot token not configured"
            )

        try:
            # Ensure body is not empty (Slack requires text)
            body_text = message.body or message.data.get('body', '') if message.data else ''
            if not body_text:
                body_text = message.data.get('message', '') if message.data else ''
            if not body_text:
                body_text = f"Slack: {message.subject or 'Notification'}"

            # Send message
            channel_target = message.recipient or self.default_channel_id
            if not channel_target:
                return ProviderResponse(
                    status=ProviderStatus.FAILED,
                    error_code="NO_CHANNEL",
                    error_message="Slack channel/user recipient is missing"
                )

            response = await self.client.chat_postMessage(
                channel=channel_target,
                text=body_text,
                blocks=message.data.get('blocks') if message.data else None
            )

            return ProviderResponse(
                status=ProviderStatus.SUCCESS,
                message_id=response['ts'],
                metadata={
                    'provider': 'slack',
                    'channel': response['channel']
                }
            )

        except SlackApiError as e:
            return ProviderResponse(
                status=ProviderStatus.FAILED,
                error_code=e.response['error'],
                error_message=str(e)
            )

        except Exception as e:
            return ProviderResponse(
                status=ProviderStatus.FAILED,
                error_code="UNKNOWN_ERROR",
                error_message=str(e)
            )

    async def get_status(self, message_id: str) -> ProviderResponse:
        """
        Get Slack message status.

        Note: Slack doesn't provide delivery confirmation.
        If message was sent successfully, it's considered delivered.
        """
        return ProviderResponse(
            status=ProviderStatus.SUCCESS,
            message_id=message_id,
            metadata={'note': 'Slack messages are immediately delivered'}
        )

    async def validate_recipient(self, recipient: str) -> bool:
        """
        Validate Slack channel or user ID.

        Args:
            recipient: Channel ID (C...) or User ID (U...)

        Returns:
            True if valid format
        """
        # Slack channel IDs start with C, user IDs start with U
        return recipient.startswith('C') or recipient.startswith('U') or recipient.startswith('@')

    def supports_channel(self) -> str:
        """Returns 'slack'."""
        return "slack"
