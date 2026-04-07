from __future__ import annotations

from typing import Any, Dict, List

import httpx
from fastapi import APIRouter, Depends, HTTPException, status

from src.api.dependencies import get_authenticated_tenant, user_rate_limiter
from src.api.schemas import (
    BatchNotificationRequest,
    BatchNotificationResponse,
    NotificationResponse,
    NotificationStatusResponse,
    SendNotificationRequest,
)
from src.models import Tenant
from src.services.supabase_notification_service import SupabaseNotificationService

router = APIRouter(prefix="/notifications", tags=["notifications"])
service = SupabaseNotificationService()


def _notification_response_from_result(result: dict[str, Any]) -> NotificationResponse:
    primary = result["channels"][0] if result.get("channels") else {}
    created_at = None
    channels_payload = {}
    for channel in result.get("channels", []):
        channels_payload[channel["channel"]] = {
            "channel": channel["channel"],
            "provider": channel.get("provider") or "unknown",
            "message_id": channel.get("message_id"),
            "status": channel.get("status") or "queued",
            "delivered_at": None,
            "opened_at": None,
            "clicked_at": None,
        }
    return NotificationResponse(
        notification_id=str(primary.get("communication_id") or result.get("existing_communication_id") or "pending"),
        status=primary.get("status", "queued"),
        channels=channels_payload,
        estimated_delivery=None,
        created_at=created_at,
    )


@router.post(
    "/send",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(user_rate_limiter)],
)
async def send_notification(
    request: SendNotificationRequest,
    tenant: Tenant = Depends(get_authenticated_tenant),
):
    payload = request.model_dump()
    merged = {
        "contact_id": payload["recipient"]["user_id"],
        "email": payload["recipient"].get("email"),
        "phone": payload["recipient"].get("phone"),
        "notification_type": payload["notification"]["type"],
        "priority": payload["notification"]["priority"],
        "channels": payload["notification"]["channels"],
        "template_id": payload["notification"].get("template_id"),
        "subject": payload["notification"].get("subject"),
        "body": payload["notification"].get("body"),
        "data": payload["notification"].get("data") or {},
        "idempotency_key": payload["notification"].get("idempotency_key"),
    }
    try:
        return await service.send_notification(tenant.id, merged)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text if exc.response is not None else str(exc)
        raise HTTPException(status_code=502, detail=detail) from exc


@router.post(
    "/batch",
    response_model=BatchNotificationResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(user_rate_limiter)],
)
async def send_batch_notifications(
    request: BatchNotificationRequest,
    tenant: Tenant = Depends(get_authenticated_tenant),
):
    sent = []
    for recipient in request.recipients:
        result = await service.send_notification(
            tenant.id,
            {
                "contact_id": recipient.user_id,
                "email": recipient.email,
                "phone": recipient.phone,
                "notification_type": request.template_id,
                "priority": "medium",
                "channels": [request.channel.value],
                "template_id": request.template_id,
                "data": recipient.data,
            },
        )
        sent.append(result)
    return BatchNotificationResponse(
        batch_id=f"batch-{tenant.id}-{len(sent)}",
        status="processing",
        total_recipients=len(sent),
        estimated_completion=request.schedule_at,
    )


@router.get("/demo/options")
async def get_demo_options(tenant: Tenant = Depends(get_authenticated_tenant)):
    return await service.get_demo_options(tenant.id)


@router.post("/demo/send", status_code=status.HTTP_201_CREATED)
async def send_demo_notification(payload: dict[str, Any], tenant: Tenant = Depends(get_authenticated_tenant)):
    try:
        return await service.send_notification(tenant.id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text if exc.response is not None else str(exc)
        raise HTTPException(status_code=502, detail=detail) from exc


@router.get("/history")
async def get_notification_history(limit: int = 20, tenant: Tenant = Depends(get_authenticated_tenant)):
    return await service.get_history(tenant.id, limit=limit)


@router.get("/{notification_id}", response_model=dict)
async def get_notification_status(notification_id: str, tenant: Tenant = Depends(get_authenticated_tenant)):
    try:
        communication_id = int(notification_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid notification ID format") from exc
    try:
        return await service.get_notification_status(tenant.id, communication_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/user/{user_id}", response_model=List[dict])
async def get_user_notifications(user_id: str, limit: int = 50, tenant: Tenant = Depends(get_authenticated_tenant)):
    history = await service.get_history(tenant.id, limit=limit * 2)
    return [item for item in history if str(item.get("recipient")) == str(user_id) or str(item.get("contact_name")) == str(user_id)][:limit]
