import boto3
from botocore.exceptions import ClientError
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
import re

from .base import NotificationProvider, Message, ProviderResponse, ProviderStatus
from src.config import settings


class EmailProvider(NotificationProvider):
    """Email provider using AWS SES."""

    def __init__(self, config: dict = None):
        super().__init__(config)
        self.client = boto3.client(
            'ses',
            region_name=settings.aws_ses_region,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
        )
        self.from_email = settings.aws_ses_from_email

    async def send(self, message: Message) -> ProviderResponse:
        """
        Send email via AWS SES.

        Args:
            message: Email message to send

        Returns:
            ProviderResponse with SES message ID
        """
        try:
            # Validate recipient email
            if not await self.validate_recipient(message.recipient):
                return ProviderResponse(
                    status=ProviderStatus.FAILED,
                    error_code="INVALID_EMAIL",
                    error_message=f"Invalid email address: {message.recipient}"
                )

            # Build email
            if message.attachments:
                # Use raw email for attachments
                response = await self._send_raw_email(message)
            else:
                # Use simple send for text-only
                response = self.client.send_email(
                    Source=self.from_email,
                    Destination={'ToAddresses': [message.recipient]},
                    Message={
                        'Subject': {'Data': message.subject or "Notification"},
                        'Body': {
                            'Html': {'Data': message.body} if '<html' in message.body.lower() else {},
                            'Text': {'Data': message.body} if '<html' not in message.body.lower() else {}
                        }
                    }
                )

            message_id = response['MessageId']

            return ProviderResponse(
                status=ProviderStatus.SUCCESS,
                message_id=message_id,
                metadata={'provider': 'aws_ses'}
            )

        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = e.response['Error']['Message']

            return ProviderResponse(
                status=ProviderStatus.FAILED,
                error_code=error_code,
                error_message=error_message
            )

        except Exception as e:
            return ProviderResponse(
                status=ProviderStatus.FAILED,
                error_code="UNKNOWN_ERROR",
                error_message=str(e)
            )

    async def _send_raw_email(self, message: Message) -> dict:
        """Send email with attachments using raw email format."""
        msg = MIMEMultipart()
        msg['Subject'] = message.subject or "Notification"
        msg['From'] = self.from_email
        msg['To'] = message.recipient

        # Add body
        if '<html' in message.body.lower():
            msg.attach(MIMEText(message.body, 'html'))
        else:
            msg.attach(MIMEText(message.body, 'plain'))

        # Add attachments
        for attachment_path in message.attachments:
            with open(attachment_path, 'rb') as f:
                part = MIMEApplication(f.read())
                part.add_header(
                    'Content-Disposition',
                    'attachment',
                    filename=attachment_path.split('/')[-1]
                )
                msg.attach(part)

        # Send raw email
        response = self.client.send_raw_email(
            Source=self.from_email,
            Destinations=[message.recipient],
            RawMessage={'Data': msg.as_string()}
        )

        return response

    async def get_status(self, message_id: str) -> ProviderResponse:
        """
        Get delivery status from SES.

        Note: SES doesn't provide a direct status check API.
        Status updates come via SNS notifications to webhooks.
        """
        return ProviderResponse(
            status=ProviderStatus.PENDING,
            message_id=message_id,
            metadata={'note': 'Status available via webhook'}
        )

    async def validate_recipient(self, recipient: str) -> bool:
        """
        Validate email address format.

        Args:
            recipient: Email address

        Returns:
            True if valid email format
        """
        email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(email_regex, recipient))

    def supports_channel(self) -> str:
        """Returns 'email'."""
        return "email"
