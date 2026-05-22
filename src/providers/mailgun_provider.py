"""Mailgun email provider for mass email sending."""

import asyncio
import aiohttp
from typing import Optional, List
import re
import json
from html import unescape

import requests

from .base import NotificationProvider, Message, ProviderResponse, ProviderStatus
from src.config import settings


def _looks_like_html(content: str) -> bool:
    lowered = (content or "").lower()
    return "<html" in lowered or "<body" in lowered or "<p" in lowered or "<div" in lowered or "<table" in lowered


def _html_to_plain_text(content: str) -> str:
    if not content:
        return ""
    text = re.sub(r"(?is)<(script|style).*?>.*?</\\1>", " ", content)
    text = re.sub(r"(?i)<br\\s*/?>", "\n", text)
    text = re.sub(r"(?i)</p\\s*>", "\n\n", text)
    text = re.sub(r"(?i)</div\\s*>", "\n", text)
    text = re.sub(r"(?i)</li\\s*>", "\n", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = unescape(text)
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


class MailgunProvider(NotificationProvider):
    """Email provider using Mailgun API for mass email campaigns."""

    def __init__(self, config: dict = None):
        super().__init__(config)
        self.api_key = self.config.get("api_key") or settings.mailgun_api_key
        self.domain = self.config.get("domain") or settings.mailgun_domain or "sandbox123456.mailgun.org"
        self.from_email = (
            self.config.get("from_email")
            or self.config.get("sender_email")
            or settings.mailgun_from_email
            or "noreply@dataalchemy.ai"
        )
        self.base_url = self.config.get("base_url") or settings.mailgun_base_url or "https://api.mailgun.net/v3"

    async def send(self, message: Message) -> ProviderResponse:
        """
        Send email via Mailgun API.

        Args:
            message: Email message to send

        Returns:
            ProviderResponse with Mailgun message ID
        """
        try:
            # Validate recipient email
            if not await self.validate_recipient(message.recipient):
                return ProviderResponse(
                    status=ProviderStatus.FAILED,
                    error_code="INVALID_EMAIL",
                    error_message=f"Invalid email address: {message.recipient}"
                )

            # Prepare Mailgun API request
            url = f"{self.base_url}/{self.domain}/messages"

            template_id = message.data.get("template_id")
            template_vars = message.data.get("template_variables") or {}
            provider_template_refs = message.data.get("provider_template_refs") or {}
            mailgun_template_ref = (
                provider_template_refs.get("email")
                or (self.config.get("template_refs") or {}).get(template_id)
            )

            data = {
                "from": self.from_email,
                "to": message.recipient,
            }

            if mailgun_template_ref:
                data["template"] = mailgun_template_ref
                data["t:variables"] = json.dumps(template_vars or {})
                if message.subject:
                    data["subject"] = message.subject
            else:
                # Ensure body is not empty for raw-body sends
                body_text = message.body or message.data.get('body', '')
                if not body_text:
                    body_text = message.data.get('message', '') or message.data.get('text', '')
                if not body_text:
                    body_text = message.subject or "Notification"

                data["subject"] = message.subject or "Notification"
                html_body = message.body if _looks_like_html(message.body or "") else ""
                explicit_text = message.data.get("text") or ""
                data["text"] = explicit_text or _html_to_plain_text(html_body or body_text) or "Notification"

                if html_body:
                    data["html"] = html_body

            # Add CC recipients if provided
            if message.metadata and message.metadata.get('cc'):
                data["cc"] = message.metadata.get('cc')

            # Add BCC recipients if provided
            if message.metadata and message.metadata.get('bcc'):
                data["bcc"] = message.metadata.get('bcc')

            # Add custom variables for tracking
            if message.metadata:
                for key, value in message.metadata.items():
                    if key.startswith('v:'):
                        data[key] = value

            reply_to = (
                (message.metadata or {}).get("reply_to")
                or message.data.get("reply_to")
                or self.config.get("reply_to")
            )
            if reply_to:
                data["h:Reply-To"] = reply_to

            # Make API request using aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    auth=aiohttp.BasicAuth('api', self.api_key),
                    data=data,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:

                    # Check response
                    if response.status == 200:
                        response_data = await response.json()
                        message_id = response_data.get('id', '')

                        return ProviderResponse(
                            status=ProviderStatus.SUCCESS,
                            message_id=message_id,
                            metadata={
                                'provider': 'mailgun',
                                'domain': self.domain
                            }
                        )
                    else:
                        try:
                            error_data = await response.json()
                            error_msg = error_data.get('message', 'Unknown error')
                        except Exception:
                            error_msg = await response.text()
                            
                        return ProviderResponse(
                            status=ProviderStatus.FAILED,
                            error_code=f"MAILGUN_{response.status}",
                            error_message=error_msg
                        )

        except asyncio.TimeoutError:
            return ProviderResponse(
                status=ProviderStatus.FAILED,
                error_code="TIMEOUT",
                error_message="Mailgun API request timed out"
            )

        except aiohttp.ClientError as e:
            return ProviderResponse(
                status=ProviderStatus.FAILED,
                error_code="REQUEST_ERROR",
                error_message=str(e)
            )

        except Exception as e:
            return ProviderResponse(
                status=ProviderStatus.FAILED,
                error_code="UNKNOWN_ERROR",
                error_message=str(e)
            )

    async def validate_recipient(self, recipient: str) -> bool:
        """
        Validate email address format.

        Args:
            recipient: Email address to validate

        Returns:
            True if valid, False otherwise
        """
        if not recipient:
            return False

        # Basic email validation regex
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(email_pattern, recipient))

    async def send_batch(self, messages: List[Message]) -> List[ProviderResponse]:
        """
        Send multiple emails in batch.

        Args:
            messages: List of email messages to send

        Returns:
            List of ProviderResponse objects
        """
        responses = []
        for message in messages:
            response = await self.send(message)
            responses.append(response)

        return responses

    async def send_bulk(self, recipients: List[str], subject: str, body: str, **kwargs) -> ProviderResponse:
        """
        Send bulk email to multiple recipients using Mailgun's batch sending.

        Args:
            recipients: List of email addresses
            subject: Email subject
            body: Email body
            **kwargs: Additional parameters (html, tags, etc.)

        Returns:
            ProviderResponse with batch message ID
        """
        try:
            url = f"{self.base_url}/{self.domain}/messages"

            # Prepare data for bulk sending
            data = {
                "from": self.from_email,
                "to": recipients,  # Mailgun accepts list for batch sending
                "subject": subject,
                "text": body,
            }

            # Add HTML if provided
            if kwargs.get('html'):
                data["html"] = kwargs.get('html')

            # Add tags for tracking
            if kwargs.get('tags'):
                data["o:tag"] = kwargs.get('tags')

            # Make API request
            response = requests.post(
                url,
                auth=("api", self.api_key),
                data=data,
                timeout=30
            )

            if response.status_code == 200:
                response_data = response.json()
                message_id = response_data.get('id', '')

                return ProviderResponse(
                    status=ProviderStatus.SUCCESS,
                    message_id=message_id,
                    metadata={
                        'provider': 'mailgun',
                        'recipients_count': len(recipients),
                        'bulk_send': True
                    }
                )
            else:
                error_data = response.json()
                return ProviderResponse(
                    status=ProviderStatus.FAILED,
                    error_code=f"MAILGUN_{response.status_code}",
                    error_message=error_data.get('message', 'Unknown error')
                )

        except Exception as e:
            return ProviderResponse(
                status=ProviderStatus.FAILED,
                error_code="BULK_SEND_ERROR",
                error_message=str(e)
            )

    async def get_status(self, message_id: str) -> ProviderResponse:
        """
        Get delivery status for a message from Mailgun.

        Args:
            message_id: Mailgun message ID

        Returns:
            ProviderResponse with current status
        """
        try:
            # Extract domain and message ID from full message ID
            # Format is typically: <uniqueid@domain>
            if not message_id:
                return ProviderResponse(
                    status=ProviderStatus.FAILED,
                    error_code="INVALID_MESSAGE_ID",
                    error_message="Message ID is required"
                )

            # For now, return success as Mailgun webhooks handle status updates
            return ProviderResponse(
                status=ProviderStatus.SUCCESS,
                message_id=message_id,
                metadata={'note': 'Status tracking via Mailgun webhooks'}
            )

        except Exception as e:
            return ProviderResponse(
                status=ProviderStatus.FAILED,
                error_code="STATUS_CHECK_ERROR",
                error_message=str(e)
            )

    def supports_channel(self) -> str:
        """Returns 'email'."""
        return "email"
