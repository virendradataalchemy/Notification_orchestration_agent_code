from fastapi import APIRouter, Depends, Request, HTTPException, status, BackgroundTasks, UploadFile
from starlette.datastructures import UploadFile as StarletteUploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from sqlalchemy.exc import IntegrityError
import uuid
import logging
from pathlib import Path
from html import unescape

from src.core import get_db
from src.models import Notification, NotificationChannel, ChannelStatus, Tenant, TenantProviderConfig, NotificationStatus
from src.models.inbound import InboundMessageRaw, InboundChannel
from src.api.schemas import WebhookEvent, InboundMessageCanonical
from src.tasks.inbound_tasks import process_inbound_message
from datetime import datetime
import json
import re
import hmac
import hashlib
from twilio.request_validator import RequestValidator
from src.config.settings import settings
from src.core.ws_manager import manager
from src.providers import get_provider_for_channel
from src.providers.base import Message, ProviderStatus

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
logger = logging.getLogger(__name__)
INBOUND_UPLOAD_DIR = Path("inbound_uploads")
UNSOLICITED_MAIL_PATTERNS = (
    "unsolicited mail",
    "5.7.1",
    "spam",
    "likely unsolicited",
)


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


def _normalize_sender_address(sender: str) -> str:
    """Extract bare email/phone from 'Name <user@example.com>' style senders."""
    if not sender:
        return sender
    sender = sender.strip()
    angle_match = re.search(r"<([^>]+)>", sender)
    if angle_match:
        return angle_match.group(1).strip()
    return sender


def _extract_inbound_preview(payload: dict) -> str:
    """Best-effort preview text for immediate dashboard rendering."""
    if not payload:
        return ""
    for key in ("stripped-text", "body-plain", "Body", "body", "text"):
        value = payload.get(key)
        if value:
            return str(value).strip()
    return ""


def _extract_outbound_recipient(notification: Notification, channel_name: str) -> str:
    data = notification.data or {}
    if channel_name == "email":
        return data.get("email") or notification.user_id
    if channel_name in {"sms", "whatsapp", "voice"}:
        return data.get("phone") or notification.user_id
    if channel_name == "slack":
        return data.get("slack_id") or notification.user_id
    return data.get("email") or data.get("phone") or notification.user_id


def _looks_like_html(content: str) -> bool:
    lowered = (content or "").lower()
    return any(tag in lowered for tag in ("<html", "<body", "<p", "<div", "<table", "<br"))


def _html_to_plain_text(content: str) -> str:
    if not content:
        return ""
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", content)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</p\s*>", "\n\n", text)
    text = re.sub(r"(?i)</div\s*>", "\n", text)
    text = re.sub(r"(?i)</li\s*>", "\n", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = unescape(text)
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def _strip_subject_for_rescue(subject: str) -> str:
    cleaned = re.sub(r"[^\x20-\x7E]+", " ", subject or "")
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" -")
    return cleaned or "Notification"


def _is_unsolicited_delivery_failure(error_message: str) -> bool:
    msg = (error_message or "").lower()
    return any(pattern in msg for pattern in UNSOLICITED_MAIL_PATTERNS)


async def _get_tenant_channel_config(db: AsyncSession, tenant_id: str, channel: str) -> dict:
    query = select(TenantProviderConfig).where(
        TenantProviderConfig.tenant_id == tenant_id,
        TenantProviderConfig.provider == channel,
        TenantProviderConfig.is_active == True,
    )
    result = await db.execute(query)
    row = result.scalar_one_or_none()
    return (row.config or {}) if row else {}


def _build_email_rescue_message(notification: Notification) -> Message:
    data = notification.data or {}
    channel_specific = (data.get("channel_content_map") or {}).get("email", {})
    subject = _strip_subject_for_rescue(channel_specific.get("subject") or data.get("subject") or "Notification")
    body = channel_specific.get("body") or data.get("body") or ""
    if _looks_like_html(body):
        body = _html_to_plain_text(body)
    if not body:
        body = data.get("text") or subject

    rescue_data = dict(data)
    rescue_data["text"] = body
    rescue_data["body"] = body
    rescue_data["delivery_rescue"] = True
    rescue_data["delivery_rescue_reason"] = "mailbox_unsolicited_mail_retry"

    return Message(
        recipient=data.get("email") or notification.user_id,
        subject=subject,
        body=body,
        data=rescue_data,
        metadata={
            "notification_id": str(notification.id),
            "tenant_id": notification.tenant_id,
            "user_id": notification.user_id,
            "priority": notification.priority.value if notification.priority else None,
            "channel": "email",
            "v:delivery_rescue": "1",
        },
    )


async def _attempt_mailgun_delivery_rescue(
    db: AsyncSession,
    channel: NotificationChannel,
    error_message: str,
) -> bool:
    if channel.channel != "email":
        return False
    if channel.attempts and channel.attempts >= 2:
        return False
    if not _is_unsolicited_delivery_failure(error_message):
        return False

    notification = await db.get(Notification, channel.notification_id)
    if not notification:
        return False

    tenant_provider_config = await _get_tenant_channel_config(db, notification.tenant_id, "email")
    provider = get_provider_for_channel("email", channel.provider or "mailgun", config=tenant_provider_config)
    if not provider:
        logger.warning("Delivery rescue skipped: provider %s unavailable", channel.provider)
        return False

    rescue_message = _build_email_rescue_message(notification)
    response = await provider.send(rescue_message)
    if response.status != ProviderStatus.SUCCESS:
        logger.warning(
            "Delivery rescue failed for notification %s recipient %s: %s",
            notification.id,
            rescue_message.recipient,
            response.error_message or response.error_code,
        )
        return False

    channel.status = ChannelStatus.SENT
    channel.message_id = response.message_id
    channel.attempts = (channel.attempts or 0) + 1
    channel.error_code = "DELIVERY_RESCUE_SENT"
    channel.error_message = "Automatic plain-text retry sent after mailbox spam rejection"
    notification.status = NotificationStatus.SENT
    notification.failed_at = None
    await db.commit()
    await _publish_outbound_status_update(db, channel, status=channel.status.value)
    logger.info(
        "Triggered one-time Mailgun delivery rescue for notification %s recipient %s",
        notification.id,
        rescue_message.recipient,
    )
    return True


async def _publish_outbound_status_update(
    db: AsyncSession,
    channel: NotificationChannel,
    *,
    status: str,
) -> None:
    notification = await db.get(Notification, channel.notification_id)
    if not notification:
        return

    await manager.publish_to_tenant(
        notification.tenant_id,
        {
            "event": "notification_channel_updated",
            "tenant_id": notification.tenant_id,
            "owner_id": str(notification.owner_id) if notification.owner_id else None,
            "notification_id": str(notification.id),
            "message": {
                "notification_id": str(notification.id),
                "channel": str(channel.channel),
                "recipient": _extract_outbound_recipient(notification, str(channel.channel)),
                "status": status,
                "provider": channel.provider,
                "message_id": channel.message_id,
                "error_message": channel.error_message,
            },
        },
    )


async def _persist_inbound_message(
    db: AsyncSession,
    inbound_msg: InboundMessageRaw,
) -> tuple[InboundMessageRaw, bool]:
    """
    Insert the inbound message, tolerating provider retries by reusing the
    existing record if the provider message id already exists for the tenant.
    """
    existing_query = select(InboundMessageRaw).where(
        InboundMessageRaw.tenant_id == inbound_msg.tenant_id,
        InboundMessageRaw.provider_message_id == inbound_msg.provider_message_id,
    )
    existing = (await db.execute(existing_query)).scalar_one_or_none()
    if existing:
        return existing, False

    db.add(inbound_msg)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing = (await db.execute(existing_query)).scalar_one_or_none()
        if existing:
            return existing, False
        raise

    await db.refresh(inbound_msg)
    return inbound_msg, True


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


@router.api_route("/mailgun/delivery", methods=["POST"])
async def mailgun_delivery_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Handle Mailgun delivery status webhooks (delivered, failed, rejected).
    """
    body = await request.json()
    
    # Mailgun encapsulates event data inside 'event-data'
    event_data = body.get("event-data", {})
    if not event_data:
        return {"status": "ignored", "reason": "missing event-data"}
        
    signature_data = body.get("signature", {})
    timestamp = signature_data.get("timestamp")
    token = signature_data.get("token")
    signature = signature_data.get("signature")
    
    # Verify Mailgun signature
    signing_key = settings.mailgun_signing_key or settings.mailgun_api_key
    if signing_key and signature and timestamp and token:
        hmac_digest = hmac.new(
            key=signing_key.encode(),
            msg=('{}{}'.format(timestamp, token)).encode(),
            digestmod=hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(str(signature), str(hmac_digest)):
            raise HTTPException(status_code=401, detail="Invalid Mailgun signature")
    elif signing_key:
        raise HTTPException(status_code=401, detail="Missing Mailgun signature fields")

    # Get the message ID to look up the channel
    # Mailgun message IDs in webhooks often have < > around them, sometimes not.
    message_id = event_data.get("message", {}).get("headers", {}).get("message-id", "")
    if not message_id:
        return {"status": "ignored", "reason": "missing message-id"}
        
    # Find notification channel
    # Message ID in DB might have <> around it or might not
    stripped_id = message_id.strip("<>")
    bracketed_id = f"<{stripped_id}>"
    
    query = select(NotificationChannel).where(
        or_(
            NotificationChannel.message_id == message_id,
            NotificationChannel.message_id == stripped_id,
            NotificationChannel.message_id == bracketed_id
        )
    )
    result = await db.execute(query)
    channel = result.scalar_one_or_none()
    
    if not channel:
        logger.warning(f"Mailgun delivery webhook: NotificationChannel not found for message_id {message_id} or {stripped_id} or {bracketed_id}")
        return {"status": "not_found", "message_id": message_id}
        
    event_type = event_data.get("event")
    
    rescue_triggered = False

    if event_type == "delivered":
        channel.status = ChannelStatus.DELIVERED
        channel.delivered_at = datetime.utcnow()
    elif event_type == "opened":
        channel.status = ChannelStatus.DELIVERED  # Could also add an 'opened_at' timestamp if model supports it
        channel.opened_at = datetime.utcnow()
    elif event_type == "clicked":
        channel.status = ChannelStatus.DELIVERED
        channel.clicked_at = datetime.utcnow()
    elif event_type in ["failed", "rejected", "bounced", "complained", "temporary_fail", "permanent_fail"]:
        channel.status = ChannelStatus.FAILED
        channel.error_code = event_data.get("severity") or event_type
        channel.error_message = event_data.get("delivery-status", {}).get("description") or event_data.get("delivery-status", {}).get("message") or event_type

        rescue_triggered = await _attempt_mailgun_delivery_rescue(
            db,
            channel,
            channel.error_message,
        )

    if not rescue_triggered:
        await db.commit()
        await _publish_outbound_status_update(db, channel, status=channel.status.value)
    return {"status": "processed"}

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
    await _publish_outbound_status_update(db, channel, status=channel.status.value)

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
    if channel_status:
        await _publish_outbound_status_update(db, channel, status=channel.status.value)

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
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """
    Handle inbound emails from Mailgun.
    """
    if request.method in ["GET", "HEAD"]:
        return {"status": "ok"}
        
    form_data = await request.form()
    
    # Mailgun sends multipart/form-data for inbound routes
    sender = _normalize_sender_address(form_data.get("sender", "") or form_data.get("From", ""))
    recipient = form_data.get("recipient", "") or form_data.get("To", "")
    message_id = form_data.get("Message-Id", "") or form_data.get("message-id", "")
    
    # Check if we have the standard inbound fields
    if not sender or not form_data:
        return {"status": "ignored", "reason": "missing sender"}

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
    candidate_id = None
    # If the email is a reply, the Message-Id might be in In-Reply-To
    in_reply_to = form_data.get("In-Reply-To") or form_data.get("References", "")
    if in_reply_to:
        # Try to find the original notification by message_id
        original_msg_id = in_reply_to.strip("<>")
        query = select(Notification).join(NotificationChannel).where(
            NotificationChannel.message_id == original_msg_id
        )
        result = await db.execute(query)
        original_notif = result.scalar_one_or_none()
        if original_notif:
            owner_id = original_notif.owner_id
            candidate_id = original_notif.user_id
            tenant_id = original_notif.tenant_id
    
    # Fallback owner_id discovery if In-Reply-To didn't work
    if not owner_id:
        # Search globally for the sender to find their most recent tenant
        query = select(Notification).where(
            or_(
                Notification.user_id == sender,
                Notification.data.op("->>")("email") == sender
            )
        ).order_by(Notification.created_at.desc()).limit(1)
        result = await db.execute(query)
        last_notif = result.scalar_one_or_none()
        if last_notif:
            owner_id = last_notif.owner_id
            candidate_id = last_notif.user_id
            tenant_id = last_notif.tenant_id

    attachment_files = await _save_mailgun_attachments(form_data)
    raw_payload = _form_to_json_safe_dict(form_data)
    if attachment_files:
        raw_payload["saved_attachments"] = attachment_files
    
    canonical = InboundMessageCanonical(
        tenant_id=tenant_id,
        channel=InboundChannel.EMAIL,
        sender_address=sender,
        provider_message_id=message_id,
        raw_payload=raw_payload,
        candidate_id=candidate_id,
        owner_id=str(owner_id) if owner_id else None,
        metadata={
            "recipient": recipient,
            "attachments_count": len(attachment_files),
            "in_reply_to": in_reply_to
        }
    )

    inbound_msg = InboundMessageRaw(
        tenant_id=canonical.tenant_id,
        candidate_id=canonical.candidate_id,
        sender_address=canonical.sender_address,
        channel=canonical.channel,
        provider_message_id=canonical.provider_message_id,
        raw_payload=canonical.raw_payload,
        owner_id=canonical.owner_id
    )
    inbound_msg, created = await _persist_inbound_message(db, inbound_msg)

    logger.info(
        "Stored inbound email id=%s tenant=%s sender=%s created=%s",
        inbound_msg.id,
        tenant_id,
        sender,
        created,
    )

    # Queue parsing & intent detection (fall back to inline if Celery is down)
    if created:
        try:
            process_inbound_message.delay(str(inbound_msg.id))
        except Exception as celery_err:
            logger.warning("Celery unavailable (%s), processing inbound inline", celery_err)
            from src.tasks.inbound_tasks import run_inbound_pipeline
            background_tasks.add_task(run_inbound_pipeline, str(inbound_msg.id))

    # Notify dashboard via WebSocket
    await manager.publish_to_tenant(tenant_id, {
        "event": "inbound_message",
        "tenant_id": tenant_id,
        "owner_id": str(owner_id) if owner_id else None,
        "message_id": str(inbound_msg.id),
        "message": {
            "id": str(inbound_msg.id),
            "timestamp": inbound_msg.created_at.isoformat() if inbound_msg.created_at else None,
            "sender_address": sender,
            "channel": canonical.channel.value,
            "content": _extract_inbound_preview(raw_payload),
            "status": "received",
            "ai_status": "detecting",
        }
    })

    return {"status": "processed", "id": str(inbound_msg.id), "created": created}


@router.post("/inbound/twilio")
async def twilio_inbound_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
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

    # Verify Twilio signature
    if settings.twilio_auth_token:
        validator = RequestValidator(settings.twilio_auth_token)
        signature = request.headers.get("X-Twilio-Signature", "")
        # Starlette's request.url might differ from what Twilio sees if behind proxy, 
        # but standard validation:
        url = str(request.url)
        post_vars = dict(form_data)
        if not validator.validate(url, post_vars, signature):
            from src.models.audit_log import AuditLog
            audit_entry = AuditLog(
                event_type="security_alert",
                user_id="system",
                resource_type="webhook",
                resource_id=message_sid,
                action="verify_signature",
                details={"reason": "Invalid Twilio signature", "provider": "twilio", "sender": sender}
            )
            db.add(audit_entry)
            await db.commit()
            raise HTTPException(status_code=401, detail="Invalid Twilio signature")

    # TODO: Resolve tenant from destination phone mapping table.
    # Using demo tenant for local/testing to satisfy FK constraint.
    tenant_id = "demo_corp"
    
    # Identify message owner (marketing member) for SMS/WhatsApp
    owner_id = None
    candidate_id = None
    phone_clean = sender.replace("whatsapp:", "").strip()
    
    # Search globally for the sender to find their most recent tenant
    query = select(Notification).where(
        or_(
            Notification.data.op("->>")("phone") == phone_clean,
            Notification.user_id == phone_clean
        )
    ).order_by(Notification.created_at.desc()).limit(1)
    
    result = await db.execute(query)
    last_notif = result.scalar_one_or_none()
    if last_notif:
        owner_id = last_notif.owner_id
        candidate_id = last_notif.user_id
        tenant_id = last_notif.tenant_id

    raw_payload = _form_to_json_safe_dict(form_data)
    
    canonical = InboundMessageCanonical(
        tenant_id=tenant_id,
        channel=channel,
        sender_address=sender,
        provider_message_id=message_sid,
        raw_payload=raw_payload,
        candidate_id=candidate_id,
        owner_id=str(owner_id) if owner_id else None,
        metadata={"to": recipient}
    )

    inbound_msg = InboundMessageRaw(
        tenant_id=canonical.tenant_id,
        candidate_id=canonical.candidate_id,
        sender_address=canonical.sender_address,
        channel=canonical.channel,
        provider_message_id=canonical.provider_message_id,
        raw_payload=canonical.raw_payload,
        owner_id=canonical.owner_id
    )
    inbound_msg, created = await _persist_inbound_message(db, inbound_msg)

    # Queue parsing & intent detection
    if created:
        try:
            process_inbound_message.delay(str(inbound_msg.id))
        except Exception as celery_err:
            logger.warning("Celery unavailable (%s), processing inbound inline", celery_err)
            from src.tasks.inbound_tasks import run_inbound_pipeline
            background_tasks.add_task(run_inbound_pipeline, str(inbound_msg.id))

    # Notify dashboard via WebSocket
    await manager.publish_to_tenant(tenant_id, {
        "event": "inbound_message",
        "tenant_id": tenant_id,
        "owner_id": str(owner_id) if owner_id else None,
        "message_id": str(inbound_msg.id),
        "message": {
            "id": str(inbound_msg.id),
            "timestamp": inbound_msg.created_at.isoformat() if inbound_msg.created_at else None,
            "sender_address": sender,
            "channel": canonical.channel.value,
            "content": _extract_inbound_preview(raw_payload),
            "status": "received",
            "ai_status": "detecting",
        }
    })

    return {"status": "processed", "id": str(inbound_msg.id), "created": created}


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
    Agentic/ML outcome learning is disabled for the current internal-module
    deployment.

    This stub is intentionally preserved so the learning webhook contract can be
    re-enabled later without rebuilding the endpoint shape.
    """
    return {
        "status": "disabled",
        "message": "Notification outcome learning is disabled in this deployment."
    }
