from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Dict, Any
import uuid
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

from src.models import (
    Notification,
    NotificationChannel,
    NotificationStatus,
    Priority as DBPriority,
    ChannelStatus,
)
from src.api.schemas import (
    SendNotificationRequest,
    BatchNotificationRequest,
    NotificationResponse,
    BatchNotificationResponse,
    Priority,
)
from .router import MessageRouter
from .template_engine import TemplateEngine
from .tenant_template_engine import TenantTemplateEngine
from .usage_tracker import usage_tracker
from .orchestration_agent import OrchestrationAgent


class NotificationService:
    """Service for managing notifications."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.router = MessageRouter(db)
        self.template_engine = TemplateEngine()
        self.tenant_template_engine = TenantTemplateEngine()

    async def send_notification(
        self, tenant_id: str, request: SendNotificationRequest
    ) -> NotificationResponse:
        """
        Send a notification to a single recipient.

        Args:
            tenant_id: Tenant identifier
            request: Notification request data

        Returns:
            NotificationResponse with notification ID and status

        Raises:
            HTTPException: If tenant quota is exceeded
        """
        # Check tenant quota
        from fastapi import HTTPException, status as http_status
        from sqlalchemy import select

        allowed, usage_info = await usage_tracker.check_quota(self.db, tenant_id)
        if not allowed:
            raise HTTPException(
                status_code=http_status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Monthly quota exceeded. Used: {usage_info['used']}/{usage_info['quota']}. "
                       f"Resets on: {usage_info['reset_date']}"
            )

        # === Idempotency Check ===
        idempotency_key = getattr(request.notification, 'idempotency_key', None)
        if idempotency_key:
            # Check Redis cache first (faster)
            try:
                from src.core import get_redis_client
                from src.utils.deduplication import DeduplicationService

                redis = await get_redis_client()
                dedup = DeduplicationService(redis)
                existing_id = await dedup.check_idempotency_key(idempotency_key)

                if existing_id:
                    logger.info(f"Duplicate detected in Redis cache: {idempotency_key}")
                    return NotificationResponse(
                        notification_id=existing_id,
                        status=NotificationStatus.QUEUED,
                        channels={},
                        estimated_delivery=datetime.utcnow(),
                        created_at=datetime.utcnow(),
                    )
            except Exception as e:
                logger.warning(f"Redis idempotency check failed: {e}")

            # Check database as fallback
            try:
                existing_notif = await self.db.execute(
                    select(Notification).where(
                        Notification.tenant_id == tenant_id,
                        Notification.idempotency_key == idempotency_key
                    )
                )
                existing = existing_notif.scalar_one_or_none()

                if existing:
                    logger.info(f"Duplicate detected in database: {idempotency_key}")
                    # Return the existing notification
                    return NotificationResponse(
                        notification_id=str(existing.id),
                        status=NotificationStatus.QUEUED,  # Return original status
                        channels={},
                        estimated_delivery=datetime.utcnow(),
                        created_at=existing.created_at,
                    )
            except Exception as e:
                logger.error(f"Database idempotency check failed: {e}")
                await self.db.rollback()
                # Continue processing without idempotency check

        # === NEW: Orchestration Agent Processing ===
        llm_decision = None
        try:
            logger.info(f"Running orchestration agent for user {request.recipient.user_id}")

            agent = OrchestrationAgent(self.db)

            orchestration_result = await agent.process_notification(
                tenant_id=tenant_id,
                user_id=request.recipient.user_id,
                notification_type=request.notification.type,
                content=request.notification.body,
                priority=request.notification.priority.value,
                requested_channels=[c.value for c in request.notification.channels],
                metadata={
                    'idempotency_key': idempotency_key,
                    'tenant_id': tenant_id
                }
            )

            # Handle duplicates
            if orchestration_result['status'] == 'duplicate':
                logger.info(
                    f"Duplicate notification detected: {orchestration_result['reason']}"
                )
                # Get existing notification ID or generate a new one
                existing_id = orchestration_result.get('notification_id')
                if not existing_id:
                    # If no existing ID, this is a content hash duplicate
                    # Return a proper response indicating deduplication
                    existing_id = str(uuid.uuid4())

                return NotificationResponse(
                    notification_id=existing_id,
                    status=NotificationStatus.FAILED,
                    channels={},
                    estimated_delivery=datetime.utcnow(),
                    created_at=datetime.utcnow(),
                )

            # Store LLM decision for analytics
            llm_decision = orchestration_result.get('llm_decision')

            logger.info(
                f"Orchestration complete: channel={llm_decision.get('channel')}, "
                f"reasoning={llm_decision.get('reasoning')}"
            )

        except Exception as e:
            logger.error(f"Orchestration agent failed, using fallback: {e}")
            llm_decision = None

        # Map priority
        priority_map = {
            Priority.CRITICAL: DBPriority.CRITICAL,
            Priority.HIGH: DBPriority.HIGH,
            Priority.MEDIUM: DBPriority.MEDIUM,
            Priority.LOW: DBPriority.LOW,
        }

        # Create notification record with recipient info
        notification_data = request.notification.data or {}

        # Render template if template_id is provided
        subject = request.notification.subject
        body = request.notification.body

        if request.notification.template_id:
            # Determine the channel for template lookup (use first requested channel)
            template_channel = request.notification.channels[0].value if request.notification.channels else "email"

            # Render template with tenant-specific logic
            rendered = await self.tenant_template_engine.render_template(
                db=self.db,
                tenant_id=tenant_id,
                template_name=request.notification.template_id,
                channel=template_channel,
                data=notification_data,
                language="en"  # TODO: Get from user preferences
            )

            if rendered:
                # Use rendered content
                subject = rendered.get('subject') or subject
                body = rendered.get('body') or body
                logger.info(
                    f"Rendered template {request.notification.template_id} for tenant {tenant_id}"
                )
            else:
                # Template not found - log warning but continue with provided content
                logger.warning(
                    f"Template {request.notification.template_id} not found for tenant {tenant_id}, "
                    f"using provided subject/body"
                )

        # Validate that body is not None
        if body is None:
            body = ""
            logger.warning(
                f"Notification body is None for tenant {tenant_id}, "
                f"template_id={request.notification.template_id}. Using empty string."
            )

        # Add recipient information and content to data for worker processing
        notification_data.update({
            "email": request.recipient.email,
            "phone": request.recipient.phone,
            "slack_id": request.recipient.slack_id,
            "device_tokens": request.recipient.device_tokens,
            "subject": subject or "",
            "body": body,
        })

        notification = Notification(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            user_id=request.recipient.user_id,
            type=request.notification.type,
            priority=priority_map[request.notification.priority],
            status=NotificationStatus.QUEUED,
            template_id=request.notification.template_id,
            data=notification_data,
            scheduled_at=None,  # For immediate delivery
            llm_decision=llm_decision,  # NEW: Store AI decision
            idempotency_key=idempotency_key  # Use the variable we extracted earlier
        )

        self.db.add(notification)
        await self.db.flush()

        # Determine channels based on routing logic
        selected_channels = await self.router.select_channels(
            user_id=request.recipient.user_id,
            notification_type=request.notification.type,
            priority=request.notification.priority.value,
            requested_channels=[c.value for c in request.notification.channels],
        )

        # Create notification channel records
        channels_response = {}
        for channel_name in selected_channels:
            channel = NotificationChannel(
                id=uuid.uuid4(),
                notification_id=notification.id,
                channel=channel_name,
                provider=self._get_provider_for_channel(channel_name),
                status=ChannelStatus.QUEUED,
                attempts=0,
            )
            self.db.add(channel)

            channels_response[channel_name] = {
                "channel": channel_name,
                "provider": channel.provider,
                "message_id": None,
                "status": "queued",
                "delivered_at": None,
                "opened_at": None,
                "clicked_at": None,
            }

        await self.db.commit()

        # Store idempotency key in Redis cache (if provided)
        if idempotency_key:
            try:
                from src.core import get_redis_client
                from src.utils.deduplication import DeduplicationService

                redis = await get_redis_client()
                dedup = DeduplicationService(redis)
                await dedup.store_idempotency_key(
                    idempotency_key,
                    str(notification.id),
                    ttl=86400  # 24 hours
                )
                logger.info(f"Stored idempotency key for notification {notification.id}")
            except Exception as e:
                logger.error(f"Failed to store idempotency key: {e}")

        # Increment tenant usage counter
        await usage_tracker.increment_usage(tenant_id)

        # === NEW: Queue notification for async processing ===
        try:
            from src.tasks.notification_tasks import (
                send_notification_critical,
                send_notification_high,
                send_notification_medium,
                send_notification_low
            )

            # Map priority to task
            priority_tasks = {
                'critical': send_notification_critical,
                'high': send_notification_high,
                'medium': send_notification_medium,
                'low': send_notification_low
            }

            priority_value = request.notification.priority.value
            task = priority_tasks.get(priority_value, send_notification_medium)

            # Queue task asynchronously
            task.apply_async(args=[str(notification.id)])

            logger.info(
                f"Queued notification {notification.id} with priority {priority_value}"
            )

        except Exception as e:
            logger.error(f"Failed to queue notification: {e}")
            # Continue anyway - notification is in database

        return NotificationResponse(
            notification_id=str(notification.id),
            status=NotificationStatus.QUEUED,
            channels=channels_response,
            estimated_delivery=datetime.utcnow(),
            created_at=notification.created_at,
        )

    async def send_batch_notifications(
        self, tenant_id: str, request: BatchNotificationRequest
    ) -> BatchNotificationResponse:
        """
        Send notifications to multiple recipients in batch.

        Args:
            request: Batch notification request

        Returns:
            BatchNotificationResponse with batch ID and status
        """
        batch_id = str(uuid.uuid4())

        # Create notifications for each recipient
        for recipient in request.recipients:
            notification = Notification(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                user_id=recipient.user_id,
                type="batch_notification",
                priority=DBPriority.MEDIUM,
                status=NotificationStatus.QUEUED,
                template_id=request.template_id,
                data=recipient.data,
                scheduled_at=request.schedule_at,
            )
            self.db.add(notification)

            # Create channel record
            channel = NotificationChannel(
                id=uuid.uuid4(),
                notification_id=notification.id,
                channel=request.channel.value,
                provider=self._get_provider_for_channel(request.channel.value),
                status=ChannelStatus.QUEUED,
                attempts=0,
            )
            self.db.add(channel)

        await self.db.commit()

        # TODO: Queue batch for processing

        return BatchNotificationResponse(
            batch_id=batch_id,
            status="processing",
            total_recipients=len(request.recipients),
            estimated_completion=request.schedule_at or datetime.utcnow(),
        )

    def _get_provider_for_channel(self, channel: str) -> str:
        """Get the provider name for a channel."""
        provider_map = {
            "email": "mailgun",  # Changed to Mailgun as primary
            "sms": "twilio",
            "whatsapp": "twilio",
            "slack": "slack_api",
            "push": "fcm",
            "voice": "twilio",
            "inapp": "websocket",
        }
        return provider_map.get(channel, "unknown")
