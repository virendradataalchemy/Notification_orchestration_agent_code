from fastapi import APIRouter, Depends, Request, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import uuid
import logging

from src.core import get_db
from src.api.schemas import WebhookEvent
from src.models import Notification, NotificationChannel, ChannelStatus
from datetime import datetime
from src.agents.async_learner import get_async_learner

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
logger = logging.getLogger(__name__)


@router.post("/ses")
async def ses_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Handle AWS SES delivery status webhooks.

    Processes bounce, complaint, and delivery notifications from SES.
    """
    body = await request.json()

    # Handle SNS subscription confirmation
    if body.get("Type") == "SubscriptionConfirmation":
        return {"message": "Subscription confirmed"}

    # Process notification
    message = body.get("Message", {})
    notification_type = message.get("notificationType")
    message_id = message.get("mail", {}).get("messageId")

    if not message_id:
        return {"status": "ignored"}

    # Find notification channel
    query = select(NotificationChannel).where(
        NotificationChannel.message_id == message_id
    )
    result = await db.execute(query)
    channel = result.scalar_one_or_none()

    if not channel:
        return {"status": "not_found"}

    # Update status based on notification type
    if notification_type == "Delivery":
        channel.status = ChannelStatus.DELIVERED
        channel.delivered_at = datetime.utcnow()
    elif notification_type == "Bounce":
        channel.status = ChannelStatus.BOUNCED
        bounce_type = message.get("bounce", {}).get("bounceType")
        channel.error_code = bounce_type
    elif notification_type == "Complaint":
        channel.error_code = "COMPLAINT"

    await db.commit()

    return {"status": "processed"}


@router.post("/twilio")
async def twilio_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Handle Twilio status callbacks for SMS, WhatsApp, and Voice.
    """
    form_data = await request.form()
    message_sid = form_data.get("MessageSid") or form_data.get("CallSid")
    message_status = form_data.get("MessageStatus") or form_data.get("CallStatus")

    if not message_sid:
        return {"status": "ignored"}

    # Find notification channel
    query = select(NotificationChannel).where(
        NotificationChannel.message_id == message_sid
    )
    result = await db.execute(query)
    channel = result.scalar_one_or_none()

    if not channel:
        return {"status": "not_found"}

    # Map Twilio status to our status
    status_mapping = {
        "delivered": ChannelStatus.DELIVERED,
        "sent": ChannelStatus.SENT,
        "failed": ChannelStatus.FAILED,
        "undelivered": ChannelStatus.FAILED,
        "completed": ChannelStatus.DELIVERED,
    }

    channel_status = status_mapping.get(message_status.lower())
    if channel_status:
        channel.status = channel_status
        if channel_status == ChannelStatus.DELIVERED:
            channel.delivered_at = datetime.utcnow()

    await db.commit()

    return {"status": "processed"}


@router.post("/slack")
async def slack_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Handle Slack event callbacks.
    """
    body = await request.json()

    # Handle URL verification
    if body.get("type") == "url_verification":
        return {"challenge": body.get("challenge")}

    # Process event
    event = body.get("event", {})
    event_type = event.get("type")

    # Handle different event types as needed
    return {"status": "processed"}


@router.post("/fcm")
async def fcm_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Handle Firebase Cloud Messaging status updates.
    """
    body = await request.json()

    # Process FCM delivery reports
    # Implementation depends on FCM setup

    return {"status": "processed"}


@router.post("/notification-outcome")
async def notification_outcome_webhook(
    request: Request,
    background_tasks: BackgroundTasks
):
    """
    Handle notification outcome events for agentic learning.

    This endpoint triggers the async learner agent to:
    1. Calculate reward based on outcome
    2. Store decision in ChromaDB memory
    3. Store experience in S3 for ML retraining
    4. Check if retraining threshold reached

    Expected payload:
    {
        "notification_id": "uuid",
        "user_id": "string",
        "channel": "email|sms|push|...",
        "notification_type": "string",
        "priority": "critical|high|medium|low",
        "event": "delivered|opened|clicked|failed",
        "delivery_time_seconds": 45,
        "timestamp": "ISO8601",
        "provider": "sendgrid|twilio|..."
    }

    Processing happens asynchronously - returns immediately.
    """
    try:
        payload = await request.json()

        # Validate required fields
        notification_id = payload.get("notification_id")
        user_id = payload.get("user_id")
        channel = payload.get("channel")
        event = payload.get("event")

        if not all([notification_id, user_id, channel, event]):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing required fields: notification_id, user_id, channel, event"
            )

        # Build outcome dict
        outcome = {
            "event": event,
            "delivered": event in ["delivered", "opened", "clicked"],
            "opened": event in ["opened", "clicked"],
            "clicked": event == "clicked",
            "failed": event == "failed",
            "channel": channel,
            "delivery_time_seconds": payload.get("delivery_time_seconds"),
            "timestamp": payload.get("timestamp"),
            "provider": payload.get("provider")
        }

        # Get async learner
        learner = get_async_learner()

        # Add to background tasks (non-blocking)
        background_tasks.add_task(
            learner.record_outcome,
            notification_id=notification_id,
            user_id=user_id,
            channel=channel,
            notification_type=payload.get("notification_type", "unknown"),
            priority=payload.get("priority", "medium"),
            outcome=outcome
        )

        logger.info(
            f"Outcome accepted for async learning: "
            f"notification={notification_id}, event={event}"
        )

        # Return immediately (learning happens in background)
        return {
            "status": "accepted",
            "notification_id": notification_id,
            "message": "Outcome will be processed asynchronously"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Webhook processing failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Webhook processing failed: {str(e)}"
        )
