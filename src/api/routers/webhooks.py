from fastapi import APIRouter, Depends, Request, HTTPException, status, BackgroundTasks, UploadFile
from starlette.datastructures import UploadFile as StarletteUploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
import uuid
import logging
from pathlib import Path

from src.core import get_db
from src.api.schemas import WebhookEvent
from src.models import Notification, NotificationChannel, ChannelStatus, Tenant
from src.models.inbound import InboundMessage, InboundChannel, InboundStatus
from src.tasks.inbound_tasks import process_inbound_message
from datetime import datetime
import json
from src.agents.async_learner import get_async_learner
from src.core.ws_manager import manager

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
logger = logging.getLogger(__name__)
INBOUND_UPLOAD_DIR = Path("inbound_uploads")


def _serialize_form_value(value):
    """Convert multipart values into JSON-serializable structures."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (bytes, bytearray)):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, (UploadFile, StarletteUploadFile)) or (
        hasattr(value, "filename") and hasattr(value, "content_type")
    ):
        return {
            "filename": getattr(value, "filename", None),
            "content_type": getattr(value, "content_type", None),
            "field_type": "file",
        }
    if isinstance(value, dict):
        return {k: _serialize_form_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_serialize_form_value(v) for v in value]
    return str(value)


def _form_to_json_safe_dict(form_data):
    """Build a JSON-safe dict from multipart form data."""
    payload = {}
    for key, value in form_data.multi_items():
        serialized = _serialize_form_value(value)
        if key in payload:
            existing = payload[key]
            if not isinstance(existing, list):
                payload[key] = [existing]
            payload[key].append(serialized)
        else:
            payload[key] = serialized
    return payload


def _safe_filename(name: str) -> str:
    base = Path(name or "attachment.bin").name
    return base.replace(" ", "_")


async def _save_mailgun_attachments(form_data):
    """
    Persist multipart file fields locally and return metadata list.
    """
    INBOUND_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    saved = []
    for key, value in form_data.multi_items():
        if isinstance(value, (UploadFile, StarletteUploadFile)) or (
            hasattr(value, "filename") and hasattr(value, "read")
        ):
            original_name = _safe_filename(getattr(value, "filename", "attachment.bin"))
            saved_name = f"{uuid.uuid4()}_{original_name}"
            dest = INBOUND_UPLOAD_DIR / saved_name

            content = await value.read()
            dest.write_bytes(content)

            saved.append(
                {
                    "field": key,
                    "filename": original_name,
                    "saved_as": saved_name,
                    "saved_path": str(dest),
                    "content_type": getattr(value, "content_type", None),
                    "size_bytes": len(content),
                }
            )
    return saved


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


@router.get("/inbound/mailgun/health")
async def mailgun_health_check():
    """
    Health check endpoint to verify Mailgun inbound routing is working.
    """
    return {"status": "healthy", "service": "mailgun_inbound", "timestamp": datetime.utcnow().isoformat()}


@router.api_route("/inbound/mailgun", methods=["GET", "POST", "HEAD"])
async def mailgun_inbound_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Handle inbound emails from Mailgun.
    """
    if request.method in ["GET", "HEAD"]:
        return {"status": "ok"}
        
    form_data = await request.form()
    
    # Mailgun sends multipart/form-data for inbound routes
    sender = form_data.get("sender", "")
    recipient = form_data.get("recipient", "")
    message_id = form_data.get("Message-Id", "")
    
    # Check if we have the standard inbound fields
    if not sender or not form_data:
        return {"status": "ignored", "reason": "missing sender"}

    # TODO: Verify Mailgun signature here using form_data.get("signature") etc.
    
    # Identify tenant
    tenant_id = "demo_corp"  # Default fallback
    
    # Try to resolve tenant from recipient address
    # recipient is usually something like 'notif-123@yourdomain.com' or 'tenant_id@yourdomain.com'
    if recipient:
        # If it's a Mailgun custom recipient, we might have tenant_id in it
        if "@" in recipient:
            local_part = recipient.split("@")[0]
            # Check if local part is a known tenant_id
            query = select(Tenant).where(Tenant.id == local_part)
            res = await db.execute(query)
            if res.scalar_one_or_none():
                tenant_id = local_part

    # Identify message owner (marketing member)
    owner_id = None
    # If the email is a reply, the Message-Id might be in In-Reply-To
    in_reply_to = form_data.get("In-Reply-To") or form_data.get("References", "")
    if in_reply_to:
        # Try to find the original notification by message_id
        # Mailgun usually puts the original message ID in these headers
        # We need to look up NotificationChannel where message_id matches
        original_msg_id = in_reply_to.strip("<>")
        query = select(Notification).join(NotificationChannel).where(
            NotificationChannel.message_id == original_msg_id
        )
        result = await db.execute(query)
        original_notif = result.scalar_one_or_none()
        if original_notif:
            owner_id = original_notif.owner_id
    
    # Fallback owner_id discovery if In-Reply-To didn't work
    if not owner_id:
        # Search for the last outbound message to this sender in this tenant
        query = select(Notification).where(
            Notification.tenant_id == tenant_id,
            or_(
                Notification.user_id == sender,
                Notification.data.op("->>")("email") == sender
            )
        ).order_by(Notification.created_at.desc()).limit(1)
        result = await db.execute(query)
        last_notif = result.scalar_one_or_none()
        if last_notif:
            owner_id = last_notif.owner_id

    attachment_files = await _save_mailgun_attachments(form_data)
    raw_payload = _form_to_json_safe_dict(form_data)
    if attachment_files:
        raw_payload["saved_attachments"] = attachment_files
    
    inbound_msg = InboundMessage(
        tenant_id=tenant_id,
        sender_address=sender,
        channel=InboundChannel.EMAIL,
        raw_payload=raw_payload,
        status=InboundStatus.RECEIVED,
        owner_id=owner_id,
        metadata_json={
            "message_id": message_id,
            "recipient": recipient,
            "attachments_count": len(attachment_files),
            "in_reply_to": in_reply_to
        }
    )
    db.add(inbound_msg)
    await db.commit()
    await db.refresh(inbound_msg)

    # Queue parsing & intent detection
    process_inbound_message.delay(str(inbound_msg.id))

    # Notify dashboard via WebSocket
    await manager.broadcast_to_tenant(tenant_id, {
        "event": "inbound_message",
        "tenant_id": tenant_id,
        "owner_id": owner_id,
        "message_id": str(inbound_msg.id)
    })

    return {"status": "processed", "id": str(inbound_msg.id)}


@router.post("/inbound/twilio")
async def twilio_inbound_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Handle inbound SMS/WhatsApp from Twilio.
    """
    form_data = await request.form()
    
    sender = form_data.get("From", "")
    recipient = form_data.get("To", "")
    message_sid = form_data.get("MessageSid", "")
    
    if not sender or not message_sid:
        return {"status": "ignored", "reason": "missing from/sid"}
        
    channel = InboundChannel.WHATSAPP if sender.startswith("whatsapp:") else InboundChannel.SMS

    # TODO: Verify Twilio signature here
    
    # TODO: Resolve tenant from destination phone mapping table.
    # Using demo tenant for local/testing to satisfy FK constraint.
    tenant_id = "demo_corp"
    
    # Identify message owner (marketing member) for SMS/WhatsApp
    # This is harder for SMS as we don't have reply headers, but we can look for the last outbound message to this phone number
    owner_id = None
    phone_clean = sender.replace("whatsapp:", "").strip()
    
    # Search in notification data for this phone number
    query = select(Notification).where(
        Notification.tenant_id == tenant_id,
        or_(
            Notification.data.op("->>")("phone") == phone_clean,
            Notification.user_id == phone_clean
        )
    ).order_by(Notification.created_at.desc()).limit(1)
    
    result = await db.execute(query)
    last_notif = result.scalar_one_or_none()
    if last_notif:
        owner_id = last_notif.owner_id

    raw_payload = _form_to_json_safe_dict(form_data)
    
    inbound_msg = InboundMessage(
        tenant_id=tenant_id,
        sender_address=sender,
        channel=channel,
        raw_payload=raw_payload,
        status=InboundStatus.RECEIVED,
        owner_id=owner_id,
        metadata_json={"message_sid": message_sid, "to": recipient}
    )
    db.add(inbound_msg)
    await db.commit()
    await db.refresh(inbound_msg)

    # Queue parsing & intent detection
    process_inbound_message.delay(str(inbound_msg.id))

    # Notify dashboard via WebSocket
    await manager.broadcast_to_tenant(tenant_id, {
        "event": "inbound_message",
        "tenant_id": tenant_id,
        "owner_id": owner_id,
        "message_id": str(inbound_msg.id)
    })

    return {"status": "processed", "id": str(inbound_msg.id)}


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
