"""
Tenant-aware notification worker that uses tenant-specific provider configurations.

This worker processes queued notifications and applies tenant-specific settings
such as custom Slack channels, email sender names, SMS sender IDs, etc.
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.models import (
    Notification,
    NotificationChannel,
    NotificationStatus,
    ChannelStatus,
    TenantProviderConfig,
    Tenant,
)
from src.providers.base import Message
from src.providers.mailgun_provider import MailgunProvider
from src.providers.sms_provider import SMSProvider
from src.providers.whatsapp_provider import WhatsAppProvider
from src.providers.slack_provider import SlackProvider
from src.providers.push_provider import PushProvider
from src.providers.voice_provider import VoiceProvider
from src.providers.inapp_provider import InAppProvider

logger = logging.getLogger(__name__)


class TenantAwareWorker:
    """Worker that processes notifications with tenant-specific configurations."""

    def __init__(self):
        # Base providers (will be configured per tenant)
        self.provider_classes = {
            "email": MailgunProvider,  # Using Mailgun for reliable email delivery
            "sms": SMSProvider,
            "whatsapp": WhatsAppProvider,
            "slack": SlackProvider,
            "push": PushProvider,
            "voice": VoiceProvider,
            "inapp": InAppProvider,
        }
        self.running = False

        # Cache for tenant configs (TTL-based)
        self.tenant_config_cache: Dict[str, Dict] = {}
        self.cache_ttl = 300  # 5 minutes

    async def start(self, poll_interval: int = 5):
        """Start the worker to process notifications."""
        self.running = True
        logger.info("Tenant-aware notification worker started")

        while self.running:
            try:
                async for db in get_db():
                    await self.process_pending_notifications(db)
            except Exception as e:
                logger.error(f"Error in worker loop: {e}", exc_info=True)

            await asyncio.sleep(poll_interval)

    def stop(self):
        """Stop the worker."""
        self.running = False
        logger.info("Tenant-aware notification worker stopped")

    async def process_pending_notifications(self, db: AsyncSession):
        """Process all pending notification channels."""
        # Find all queued channels with their notifications
        query = (
            select(NotificationChannel, Notification)
            .join(Notification, NotificationChannel.notification_id == Notification.id)
            .where(NotificationChannel.status == ChannelStatus.QUEUED)
            .limit(50)  # Process in batches
        )

        result = await db.execute(query)
        records = result.all()

        if not records:
            return

        logger.info(f"Processing {len(records)} queued notifications")

        for channel_record, notification in records:
            try:
                # Process this channel with tenant-specific config
                await self.send_notification_channel(
                    db, notification, channel_record
                )

            except Exception as e:
                logger.error(
                    f"Error processing channel {channel_record.id}: {e}",
                    exc_info=True
                )
                # Mark as failed
                channel_record.status = ChannelStatus.FAILED
                channel_record.error_message = str(e)
                channel_record.attempts += 1

        await db.commit()

    async def get_tenant_provider_config(
        self, db: AsyncSession, tenant_id: str, provider: str
    ) -> Optional[Dict]:
        """
        Get tenant-specific provider configuration.

        Args:
            db: Database session
            tenant_id: Tenant identifier
            provider: Provider name (email, slack, sms, etc.)

        Returns:
            Provider configuration dict or None
        """
        # Check cache first
        cache_key = f"{tenant_id}:{provider}"
        if cache_key in self.tenant_config_cache:
            cached = self.tenant_config_cache[cache_key]
            if (datetime.utcnow() - cached['timestamp']).seconds < self.cache_ttl:
                return cached['config']

        # Query database
        query = select(TenantProviderConfig).where(
            TenantProviderConfig.tenant_id == tenant_id,
            TenantProviderConfig.provider == provider,
            TenantProviderConfig.is_active == True
        )

        result = await db.execute(query)
        config_record = result.scalar_one_or_none()

        if config_record:
            # Cache it
            self.tenant_config_cache[cache_key] = {
                'config': config_record.config,
                'timestamp': datetime.utcnow()
            }
            return config_record.config

        return None

    async def send_notification_channel(
        self,
        db: AsyncSession,
        notification: Notification,
        channel_record: NotificationChannel,
    ):
        """Send notification through a specific channel with tenant config."""
        channel_name = channel_record.channel
        tenant_id = notification.tenant_id

        # Get tenant-specific config
        tenant_config = await self.get_tenant_provider_config(
            db, tenant_id, channel_name
        )

        # Get provider class
        provider_class = self.provider_classes.get(channel_name)
        if not provider_class:
            logger.error(f"No provider found for channel: {channel_name}")
            channel_record.status = ChannelStatus.FAILED
            channel_record.error_message = f"Provider not configured: {channel_name}"
            return

        # Initialize provider (potentially with tenant config)
        provider = provider_class()

        logger.info(
            f"Sending notification {notification.id} via {channel_name} "
            f"for tenant {tenant_id}"
        )

        # Apply tenant-specific configuration
        if tenant_config:
            logger.debug(f"Applying tenant config for {tenant_id}: {tenant_config}")
            # This would be provider-specific logic
            # For now, we'll pass it in the message metadata
        else:
            logger.debug(f"No tenant config found for {tenant_id}/{channel_name}, using defaults")

        # Build recipient info from notification data
        recipient_info = self._extract_recipient_info(
            notification, channel_name, tenant_config
        )

        if not recipient_info:
            logger.error(f"Could not extract recipient for {channel_name}")
            channel_record.status = ChannelStatus.FAILED
            channel_record.error_message = "Recipient information missing"
            channel_record.attempts += 1
            return

        # Extract subject and body from notification data
        data = notification.data or {}
        subject = data.get('subject') or notification.type
        body = data.get('body') or ''

        # CRITICAL FIX: Ensure body is never empty
        if not body:
            # Try alternative fields
            body = data.get('message', '') or data.get('text', '')
            if not body:
                # Last resort: create body from subject and type
                body = f"{subject}: {notification.type}"
                logger.warning(
                    f"No body found for notification {notification.id}, "
                    f"using fallback: '{body}'"
                )

        # Create message with tenant config
        message = Message(
            recipient=recipient_info,
            subject=subject,
            body=body,
            data={
                **(notification.data or {}),
                '_tenant_config': tenant_config or {},  # Pass tenant config to provider
            },
            metadata={
                "notification_id": str(notification.id),
                "tenant_id": tenant_id,
                "type": notification.type,
                "priority": notification.priority.value,
            },
        )

        # Send via provider
        channel_record.attempts += 1

        try:
            response = await provider.send(message)

            if response.status.value == "success":
                channel_record.status = ChannelStatus.SENT
                channel_record.message_id = response.message_id

                # For immediate delivery channels, mark as delivered
                if channel_name in ["slack", "inapp"]:
                    channel_record.status = ChannelStatus.DELIVERED
                    channel_record.delivered_at = datetime.utcnow()

                logger.info(
                    f"Successfully sent notification {notification.id} via {channel_name}"
                )

                # Update overall notification status
                await self._update_notification_status(db, notification)

            else:
                channel_record.status = ChannelStatus.FAILED
                channel_record.error_code = response.error_code
                channel_record.error_message = response.error_message

                logger.error(
                    f"Failed to send via {channel_name}: {response.error_message}"
                )

        except Exception as e:
            channel_record.status = ChannelStatus.FAILED
            channel_record.error_message = str(e)
            logger.error(
                f"Exception sending via {channel_name}: {e}",
                exc_info=True
            )

    def _extract_recipient_info(
        self, notification: Notification, channel: str, tenant_config: Optional[Dict] = None
    ) -> Optional[str]:
        """
        Extract recipient information from notification data.

        Uses tenant config as fallback if available.
        """
        data = notification.data or {}

        # Try to get recipient from data
        recipient_map = {
            "email": data.get("email") or data.get("recipient_email"),
            "sms": data.get("phone") or data.get("recipient_phone"),
            "whatsapp": data.get("phone") or data.get("recipient_phone"),
            "slack": data.get("slack_id") or data.get("slack_user"),
            "push": data.get("device_tokens") or data.get("device_token"),
            "voice": data.get("phone") or data.get("recipient_phone"),
            "inapp": notification.user_id,
        }

        recipient = recipient_map.get(channel)

        # For Slack, use tenant config channel if no specific recipient
        if not recipient and channel == "slack" and tenant_config:
            recipient = tenant_config.get("channel_id")

        # For push notifications, handle list of device tokens
        if channel == "push" and recipient and isinstance(recipient, list):
            recipient = recipient[0] if recipient else None

        if not recipient:
            logger.warning(
                f"No recipient found for {channel} in notification data. "
                f"Available keys: {list(data.keys())}"
            )

        return recipient

    async def _update_notification_status(
        self, db: AsyncSession, notification: Notification
    ):
        """Update overall notification status based on channel statuses."""
        # Get all channels for this notification
        query = select(NotificationChannel).where(
            NotificationChannel.notification_id == notification.id
        )
        result = await db.execute(query)
        channels = result.scalars().all()

        # Check statuses
        all_delivered = all(
            c.status == ChannelStatus.DELIVERED for c in channels
        )
        any_sent = any(
            c.status in [ChannelStatus.SENT, ChannelStatus.DELIVERED]
            for c in channels
        )
        all_failed = all(c.status == ChannelStatus.FAILED for c in channels)

        # Update notification status
        if all_delivered:
            notification.status = NotificationStatus.DELIVERED
        elif any_sent:
            notification.status = NotificationStatus.SENT
        elif all_failed:
            notification.status = NotificationStatus.FAILED


# Singleton instance
worker = TenantAwareWorker()


async def start_worker():
    """Start the tenant-aware notification worker."""
    await worker.start()


def stop_worker():
    """Stop the tenant-aware notification worker."""
    worker.stop()
