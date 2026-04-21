"""Webhook endpoints - Supabase REST based."""

from fastapi import APIRouter, Request, HTTPException, status, BackgroundTasks
from datetime import datetime
import logging

from src.core.supabase import supabase_client

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
logger = logging.getLogger(__name__)


async def _update_comm_by_message_id(message_id: str, new_status: str, delivered: bool = False):
    """Find communication by idempotency_key (message_id) and update status."""
    rows = await supabase_client.select(
        "communications", "id",
        limit=1, filters={"idempotency_key": f"eq.{message_id}"},
    )
    if not rows:
        return False
    comm_id = rows[0]["id"]
    update: dict = {"status": new_status, "updated_at": datetime.utcnow().isoformat()}
    if delivered:
        update["sent_at"] = datetime.utcnow().isoformat()
    await supabase_client.update("communications", update, filters={"id": f"eq.{comm_id}"})
    return True


@router.post("/ses")
async def ses_webhook(request: Request):
    body = await request.json()
    if body.get("Type") == "SubscriptionConfirmation":
        return {"message": "Subscription confirmed"}
    message = body.get("Message", {})
    notification_type = message.get("notificationType")
    message_id = message.get("mail", {}).get("messageId")
    if not message_id:
        return {"status": "ignored"}
    status_map = {"Delivery": ("sent", True), "Bounce": ("failed", False), "Complaint": ("failed", False)}
    new_status, delivered = status_map.get(notification_type, ("queued", False))
    found = await _update_comm_by_message_id(message_id, new_status, delivered)
    return {"status": "processed" if found else "not_found"}


@router.post("/twilio")
async def twilio_webhook(request: Request):
    form_data = await request.form()
    message_sid = form_data.get("MessageSid") or form_data.get("CallSid")
    message_status = form_data.get("MessageStatus") or form_data.get("CallStatus")
    if not message_sid:
        return {"status": "ignored"}
    status_map = {
        "delivered": ("sent", True), "sent": ("sent", False),
        "failed": ("failed", False), "undelivered": ("failed", False),
        "completed": ("sent", True),
    }
    new_status, delivered = status_map.get((message_status or "").lower(), ("queued", False))
    found = await _update_comm_by_message_id(message_sid, new_status, delivered)
    return {"status": "processed" if found else "not_found"}


@router.post("/slack")
async def slack_webhook(request: Request):
    body = await request.json()
    if body.get("type") == "url_verification":
        return {"challenge": body.get("challenge")}
    return {"status": "processed"}


@router.post("/fcm")
async def fcm_webhook(request: Request):
    return {"status": "processed"}


@router.post("/notification-outcome")
async def notification_outcome_webhook(request: Request, background_tasks: BackgroundTasks):
    try:
        payload = await request.json()
        notification_id = payload.get("notification_id")
        user_id = payload.get("user_id")
        channel = payload.get("channel")
        event = payload.get("event")
        if not all([notification_id, user_id, channel, event]):
            raise HTTPException(status_code=400, detail="Missing required fields")

        outcome = {
            "event": event,
            "delivered": event in ["delivered", "opened", "clicked"],
            "opened": event in ["opened", "clicked"],
            "clicked": event == "clicked",
            "failed": event == "failed",
            "channel": channel,
            "delivery_time_seconds": payload.get("delivery_time_seconds"),
            "provider": payload.get("provider"),
        }

        try:
            from src.agents.async_learner import get_async_learner
            learner = get_async_learner()
            background_tasks.add_task(
                learner.record_outcome,
                notification_id=notification_id,
                user_id=user_id,
                channel=channel,
                notification_type=payload.get("notification_type", "unknown"),
                priority=payload.get("priority", "medium"),
                outcome=outcome,
            )
        except Exception:
            pass  # Learner is optional

        return {"status": "accepted", "notification_id": notification_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Webhook error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
