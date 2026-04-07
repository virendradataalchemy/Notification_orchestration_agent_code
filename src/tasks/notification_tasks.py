"""Async notification delivery - no Celery, direct async/await using Supabase REST."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from src.providers import get_provider_for_channel
from src.providers.base import Message, ProviderStatus
from src.core.supabase import supabase_client

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Celery stubs - commented out, not used
# ---------------------------------------------------------------------------
# from celery import Task
# from src.celery_app import celery_app
#
# class NotificationTask(Task):
#     autoretry_for = (Exception,)
#     retry_kwargs = {"max_retries": 3}
#     retry_backoff = True
#
# @celery_app.task(base=NotificationTask, name="tasks.send_notification_critical", bind=True)
# def send_notification_critical(self, notification_id: str):
#     return _send_notification_sync(notification_id)
#
# @celery_app.task(base=NotificationTask, name="tasks.send_notification_high", bind=True)
# def send_notification_high(self, notification_id: str):
#     return _send_notification_sync(notification_id)
#
# @celery_app.task(base=NotificationTask, name="tasks.send_notification_medium", bind=True)
# def send_notification_medium(self, notification_id: str):
#     return _send_notification_sync(notification_id)
#
# @celery_app.task(base=NotificationTask, name="tasks.send_notification_low", bind=True)
# def send_notification_low(self, notification_id: str):
#     return _send_notification_sync(notification_id)
#
# def _send_notification_sync(notification_id: str) -> Dict[str, Any]:
#     return asyncio.run(_send_notification_async(notification_id))
# ---------------------------------------------------------------------------


async def send_notification(notification_id: str) -> Dict[str, Any]:
    """Public entry point - send a single communication by ID."""
    return await _send_notification_async(notification_id)


async def _send_notification_async(notification_id: str) -> Dict[str, Any]:
    """Core delivery logic using Supabase REST directly."""
    if not str(notification_id).isdigit():
        return {"status": "error", "reason": "invalid_id"}

    comm_id = int(notification_id)

    # Load communication
    comm = await _load_communication(comm_id)
    if not comm:
        return {"status": "error", "reason": "not_found"}

    channel_name = comm.get("channel_name", "unknown")
    candidate = comm.get("candidate", {})

    # Unsubscribe check
    metadata = candidate.get("metadata") or {}
    if isinstance(metadata, dict):
        if channel_name in metadata.get("unsubscribed_channels", []) or metadata.get("unsubscribed_all"):
            logger.info(f"Candidate {comm['candidate_id']} unsubscribed from {channel_name}. Skipping.")
            await _update_status(comm_id, "failed")
            await _append_event(comm_id, comm["channel_id"], "unsubscribed", "failed", {"channel": channel_name})
            return {"status": "skipped", "reason": "unsubscribed"}

    # Resolve provider
    provider_name = await _get_provider_name(channel_name, comm["client_id"])
    provider_instance = get_provider_for_channel(channel_name, _normalize_provider_name(provider_name))

    if provider_instance is None:
        await _record_failure(comm_id, comm["channel_id"], provider_name, "Provider not configured")
        return {"status": "failed", "reason": "provider_unavailable"}

    # Build message from payload
    payload = comm.get("payload", {})
    message = Message(
        recipient=_get_recipient(channel_name, candidate, payload),
        subject=payload.get("subject"),
        body=payload.get("body", ""),
        data=payload,
        metadata={"communication_id": comm_id, "client_id": comm["client_id"], "candidate_id": comm["candidate_id"]},
    )

    await _append_event(comm_id, comm["channel_id"], "attempting", None, {"provider": provider_name})
    await _increment_retry(comm_id, comm.get("retry_count", 0))

    try:
        response = await provider_instance.send(message)
    except Exception as exc:
        await _record_failure(comm_id, comm["channel_id"], provider_name, str(exc))
        return {"status": "failed", "error": str(exc)}

    if response.status == ProviderStatus.SUCCESS:
        final_status = "delivered" if channel_name in {"in_app", "slack"} else "sent"
        await _update_status(comm_id, final_status, sent_at=datetime.utcnow().isoformat())
        await _insert_attempt(comm_id, comm.get("retry_count", 1), provider_name, final_status)
        await _append_event(
            comm_id, comm["channel_id"], final_status, final_status,
            {"provider": provider_name, "message_id": response.message_id}
        )
        logger.info(f"Notification {comm_id} sent via {channel_name}, message_id={response.message_id}")
        return {"status": "success", "message_id": response.message_id}

    await _record_failure(
        comm_id, comm["channel_id"], provider_name,
        response.error_message or response.error_code or "provider_failed",
        response.error_code,
    )
    return {"status": "failed", "error": response.error_message}


# ---------------------------------------------------------------------------
# Supabase helpers
# ---------------------------------------------------------------------------

async def _load_communication(comm_id: int) -> Optional[Dict[str, Any]]:
    """Load communication + candidate + payload from Supabase."""
    rows = await supabase_client.select(
        "communications",
        "id,client_id,candidate_id,channel_id,notification_type,priority,status,retry_count,template_id",
        limit=1,
        filters={"id": f"eq.{comm_id}"},
    )
    if not rows:
        return None
    comm = rows[0]

    # Load channel name
    ch_rows = await supabase_client.select("channels", "id,name", limit=1, filters={"id": f"eq.{comm['channel_id']}"})
    comm["channel_name"] = ch_rows[0]["name"] if ch_rows else "unknown"

    # Load candidate
    candidate_rows = await supabase_client.select(
        "candidates", "id,name,email,phone,whatsapp_number,metadata",
        limit=1, filters={"id": f"eq.{comm['candidate_id']}"}
    )
    comm["candidate"] = candidate_rows[0] if candidate_rows else {}

    # Load payload
    payload_rows = await supabase_client.select(
        "communication_payloads", "key,value",
        filters={"communication_id": f"eq.{comm_id}"}
    )
    comm["payload"] = {r["key"]: r["value"] for r in payload_rows}

    return comm


async def _get_provider_name(channel_name: str, client_id: int) -> str:
    rows = await supabase_client.select(
        "providers", "name",
        limit=1,
        filters={"channel_id": f"eq.(select id from channels where name=eq.{channel_name})", "is_active": "eq.true"},
    )
    # Simpler: join via channels table separately
    ch_rows = await supabase_client.select("channels", "id", limit=1, filters={"name": f"eq.{channel_name}"})
    if not ch_rows:
        return "unknown"
    channel_id = ch_rows[0]["id"]
    p_rows = await supabase_client.select(
        "providers", "name",
        limit=1,
        filters={"channel_id": f"eq.{channel_id}", "is_active": "eq.true"},
    )
    return p_rows[0]["name"] if p_rows else "unknown"


async def _update_status(comm_id: int, status: str, sent_at: Optional[str] = None) -> None:
    payload: Dict[str, Any] = {"status": status, "updated_at": datetime.utcnow().isoformat()}
    if sent_at:
        payload["sent_at"] = sent_at
    await supabase_client.update("communications", payload, filters={"id": f"eq.{comm_id}"})


async def _increment_retry(comm_id: int, current_count: int) -> None:
    await supabase_client.update(
        "communications",
        {"retry_count": current_count + 1, "updated_at": datetime.utcnow().isoformat()},
        filters={"id": f"eq.{comm_id}"},
    )


async def _insert_attempt(comm_id: int, attempt_number: int, provider_name: str, status: str,
                           error_message: Optional[str] = None, error_code: Optional[str] = None) -> None:
    latest = await supabase_client.select("communication_attempts", "id", limit=1, filters={"order": "id.desc"})
    next_id = int(latest[0]["id"]) + 1 if latest else 1
    await supabase_client.insert("communication_attempts", {
        "id": next_id,
        "communication_id": comm_id,
        "attempt_number": attempt_number,
        "provider_id": None,
        "status": status,
        "error_message": error_message,
        "error_code": error_code,
        "created_at": datetime.utcnow().isoformat(),
    })


async def _append_event(comm_id: int, channel_id: int, event_type: str,
                         status: Optional[str], metadata: Dict[str, Any]) -> None:
    latest = await supabase_client.select("notification_events", "id", limit=1, filters={"order": "id.desc"})
    next_id = int(latest[0]["id"]) + 1 if latest else 1
    await supabase_client.insert("notification_events", {
        "id": next_id,
        "communication_id": comm_id,
        "event_type": event_type,
        "channel_id": channel_id,
        "status": status,
        "metadata": metadata,
        "created_at": datetime.utcnow().isoformat(),
    })


async def _record_failure(comm_id: int, channel_id: int, provider_name: str,
                           error_message: str, error_code: Optional[str] = None) -> None:
    await _update_status(comm_id, "failed")
    await _insert_attempt(comm_id, 1, provider_name, "failed", error_message, error_code)
    await _append_event(comm_id, channel_id, "channel_failed", "failed",
                        {"provider": provider_name, "error": error_message})


def _normalize_provider_name(provider_name: str) -> str:
    return {
        "twilio_sms": "twilio",
        "twilio_whatsapp": "twilio",
        "twilio_voice": "twilio",
        "sendgrid": "mailgun",
    }.get(provider_name, provider_name)


def _get_recipient(channel_name: str, candidate: Dict[str, Any], payload: Dict[str, Any]) -> str:
    if channel_name == "email":
        return payload.get("email") or candidate.get("email") or ""
    if channel_name in {"sms", "voice"}:
        return payload.get("phone") or candidate.get("phone") or ""
    if channel_name == "whatsapp":
        return payload.get("whatsapp_number") or candidate.get("whatsapp_number") or candidate.get("phone") or ""
    if channel_name == "in_app":
        return str(candidate.get("id", ""))
    return payload.get("recipient") or ""
