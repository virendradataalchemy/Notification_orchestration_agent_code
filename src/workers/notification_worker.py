"""
Background worker to process queued notifications.

This worker continuously polls the database for queued notifications
and sends them through the appropriate providers.
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.models import (
    Notification,
    NotificationChannel,
    NotificationStatus,
    ChannelStatus,
)
from src.providers.base import Message
from src.providers.email_provider import EmailProvider
from src.providers.sms_provider import SMSProvider
from src.providers.whatsapp_provider import WhatsAppProvider
from src.providers.slack_provider import SlackProvider
from src.providers.push_provider import PushProvider
from src.providers.inapp_provider import InAppProvider

logger = logging.getLogger(__name__)


class NotificationWorker:
    """Worker to process queued notifications."""

    def __init__(self):
        self.providers = {
            "email": EmailProvider(),
            "sms": SMSProvider(),
            "whatsapp": WhatsAppProvider(),
            "slack": SlackProvider(),
            "push": PushProvider(),
            "inapp": InAppProvider(),
        }
        self.running = False

    async def start(self, poll_interval: int = 5):
        """Start the worker to process notifications."""
        self.running = True
        logger.info("Notification worker started")

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
        logger.info("Notification worker stopped")

    async def process_pending_notifications(self, db: AsyncSession):
        """Process all pending notification channels."""
        # Find all queued channels
        query = select(NotificationChannel).where(
            NotificationChannel.status == ChannelStatus.QUEUED
        ).limit(50)  # Process in batches

        result = await db.execute(query)
        channels = result.scalars().all()

        if not channels:
            return

        logger.info(f"Processing {len(channels)} queued notifications")

        for channel_record in channels:
            try:
                # Get the notification details
                notification_query = select(Notification).where(
                    Notification.id == channel_record.notification_id
                )
                notification_result = await db.execute(notification_query)
                notification = notification_result.scalar_one_or_none()

                if not notification:
                    logger.warning(f"Notification {channel_record.notification_id} not found")
                    continue

                # Process this channel
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
                channel_record.updated_at = datetime.utcnow()

        await db.commit()

    async def send_notification_channel(
        self,
        db: AsyncSession,
        notification: Notification,
        channel_record: NotificationChannel,
    ):
        """Send notification through a specific channel."""
        channel_name = channel_record.channel
        provider = self.providers.get(channel_name)

        if not provider:
            logger.error(f"No provider found for channel: {channel_name}")
            channel_record.status = ChannelStatus.FAILED
            channel_record.error_message = f"Provider not configured: {channel_name}"
            return

        logger.info(
            f"Sending notification {notification.id} via {channel_name}"
        )

        # Build recipient info from notification data
        recipient_info = self._extract_recipient_info(notification, channel_name)

        if not recipient_info:
            logger.error(f"Could not extract recipient for {channel_name}")
            channel_record.status = ChannelStatus.FAILED
            channel_record.error_message = "Recipient information missing"
            channel_record.attempts += 1
            return

        # Create message
        message = Message(
            recipient=recipient_info,
            subject=notification.subject or notification.type,
            body=notification.content,
            data=notification.data or {},
            metadata={
                "notification_id": str(notification.id),
                "type": notification.type,
                "priority": notification.priority.value,
            },
        )

        # Send via provider
        channel_record.attempts += 1
        channel_record.updated_at = datetime.utcnow()

        try:
            response = await provider.send(message)

            if response.status.value == "success":
                channel_record.status = ChannelStatus.SENT
                channel_record.provider_message_id = response.message_id
                channel_record.sent_at = datetime.utcnow()

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
        self, notification: Notification, channel: str
    ) -> str:
        """Extract recipient information from notification data."""
        data = notification.data or {}

        # Try to get recipient from data
        recipient_map = {
            "email": data.get("email") or data.get("recipient_email"),
            "sms": data.get("phone") or data.get("recipient_phone"),
            "whatsapp": data.get("phone") or data.get("recipient_phone"),
            "slack": data.get("slack_channel") or data.get("slack_user"),
            "push": data.get("device_token") or data.get("recipient_token"),
            "inapp": notification.user_id,
        }

        recipient = recipient_map.get(channel)

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

        notification.updated_at = datetime.utcnow()


async def run_worker():
    """Run the notification worker."""
    worker = NotificationWorker()

    try:
        await worker.start(poll_interval=5)
    except KeyboardInterrupt:
        logger.info("Worker interrupted by user")
        worker.stop()
    except Exception as e:
        logger.error(f"Worker crashed: {e}", exc_info=True)
        worker.stop()


if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Run worker
    asyncio.run(run_worker())
