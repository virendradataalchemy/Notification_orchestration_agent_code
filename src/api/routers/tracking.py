"""Tracking, unsubscribe, and delivery log endpoints - Supabase REST based."""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel

from src.api.dependencies import get_authenticated_tenant
from src.core.supabase import supabase_client
from src.models import Tenant

router = APIRouter(prefix="/tracking", tags=["tracking-logs"])


class UnsubscribeRequest(BaseModel):
    contact_id: int
    channels: Optional[List[str]] = None
    reason: Optional[str] = None


class UnsubscribeResponse(BaseModel):
    status: str
    message: str
    unsubscribed_channels: List[str]


@router.get("/logs/{communication_id}")
async def get_notification_logs(
    communication_id: int,
    tenant: Tenant = Depends(get_authenticated_tenant),
):
    comms = await supabase_client.select(
        "communications", "id,tenant_id,notification_type,contact_id,created_at",
        limit=1, filters={"id": f"eq.{communication_id}", "tenant_id": f"eq.{tenant.id}"},
    )
    if not comms:
        raise HTTPException(status_code=404, detail="Communication not found")
    comm = comms[0]
    logs = await supabase_client.select(
        "delivery_logs",
        "id,channel_id,provider_id,provider_message_id,status,sent_at,delivered_at,opened_at,clicked_at,error_message",
        filters={"communication_id": f"eq.{communication_id}"},
    )
    channels_map: Dict[int, str] = {}
    for log in logs:
        cid = log.get("channel_id")
        if cid and cid not in channels_map:
            rows = await supabase_client.select("channels", "name", limit=1, filters={"id": f"eq.{cid}"})
            channels_map[cid] = rows[0]["name"] if rows else "unknown"
    return {
        "communication_id": communication_id,
        "notification_type": comm.get("notification_type"),
        "contact_id": comm.get("contact_id"),
        "created_at": comm.get("created_at"),
        "channels": [
            {
                "id": log["id"],
                "channel": channels_map.get(log.get("channel_id"), "unknown"),
                "provider_id": log.get("provider_id"),
                "provider_message_id": log.get("provider_message_id"),
                "status": log.get("status"),
                "sent_at": log.get("sent_at"),
                "delivered_at": log.get("delivered_at"),
                "opened_at": log.get("opened_at"),
                "clicked_at": log.get("clicked_at"),
                "error_message": log.get("error_message"),
            }
            for log in logs
        ],
    }


@router.post("/track-open/{communication_id}")
async def track_open(communication_id: int, channel_id: Optional[int] = Query(None)):
    filters: Dict[str, str] = {"communication_id": f"eq.{communication_id}"}
    if channel_id:
        filters["channel_id"] = f"eq.{channel_id}"
    logs = await supabase_client.select("delivery_logs", "id", limit=1, filters=filters)
    if not logs:
        return {"status": "not_found", "message": "Delivery log not found"}
    now = datetime.utcnow().isoformat()
    await supabase_client.update("delivery_logs", {"opened_at": now}, filters={"id": f"eq.{logs[0]['id']}"})
    return {"status": "tracked", "message": "Open event recorded", "opened_at": now}


@router.post("/track-click/{communication_id}")
async def track_click(
    communication_id: int,
    channel_id: Optional[int] = Query(None),
    link_url: Optional[str] = Query(None),
):
    filters: Dict[str, str] = {"communication_id": f"eq.{communication_id}"}
    if channel_id:
        filters["channel_id"] = f"eq.{channel_id}"
    logs = await supabase_client.select("delivery_logs", "id", limit=1, filters=filters)
    if not logs:
        return {"status": "not_found", "message": "Delivery log not found"}
    now = datetime.utcnow().isoformat()
    await supabase_client.update("delivery_logs", {"clicked_at": now}, filters={"id": f"eq.{logs[0]['id']}"})
    return {"status": "tracked", "message": "Click event recorded", "clicked_at": now, "link_url": link_url}


@router.post("/unsubscribe", response_model=UnsubscribeResponse)
async def unsubscribe(
    request: UnsubscribeRequest,
    tenant: Tenant = Depends(get_authenticated_tenant),
):
    contacts = await supabase_client.select(
        "contacts", "id,metadata",
        limit=1, filters={"id": f"eq.{request.contact_id}", "tenant_id": f"eq.{tenant.id}"},
    )
    if not contacts:
        raise HTTPException(status_code=404, detail="Contact not found")
    metadata: Dict[str, Any] = contacts[0].get("metadata") or {}
    if request.channels is None:
        ch_rows = await supabase_client.select("channels", "name", filters={"is_active": "eq.true"})
        unsubscribed_channels = [r["name"] for r in ch_rows]
        metadata["unsubscribed_channels"] = unsubscribed_channels
        metadata["unsubscribed_all"] = True
    else:
        current = metadata.get("unsubscribed_channels") or []
        metadata["unsubscribed_channels"] = list(set(current + request.channels))
        unsubscribed_channels = request.channels
    if request.reason:
        metadata["unsubscribe_reason"] = request.reason
    metadata["unsubscribed_at"] = datetime.utcnow().isoformat()
    await supabase_client.update("contacts", {"metadata": metadata}, filters={"id": f"eq.{request.contact_id}"})
    return UnsubscribeResponse(
        status="unsubscribed",
        message=f"Contact unsubscribed from {len(unsubscribed_channels)} channel(s)",
        unsubscribed_channels=unsubscribed_channels,
    )


@router.get("/unsubscribed/{contact_id}")
async def get_unsubscribed_channels(
    contact_id: int,
    tenant: Tenant = Depends(get_authenticated_tenant),
):
    contacts = await supabase_client.select(
        "contacts", "id,metadata",
        limit=1, filters={"id": f"eq.{contact_id}", "tenant_id": f"eq.{tenant.id}"},
    )
    if not contacts:
        raise HTTPException(status_code=404, detail="Contact not found")
    metadata = contacts[0].get("metadata") or {}
    return {
        "contact_id": contact_id,
        "unsubscribed_channels": metadata.get("unsubscribed_channels", []),
        "unsubscribed_all": metadata.get("unsubscribed_all", False),
        "unsubscribe_reason": metadata.get("unsubscribe_reason"),
        "unsubscribed_at": metadata.get("unsubscribed_at"),
    }


@router.post("/resubscribe/{contact_id}")
async def resubscribe(
    contact_id: int,
    channels: Optional[List[str]] = Query(None),
    tenant: Tenant = Depends(get_authenticated_tenant),
):
    contacts = await supabase_client.select(
        "contacts", "id,metadata",
        limit=1, filters={"id": f"eq.{contact_id}", "tenant_id": f"eq.{tenant.id}"},
    )
    if not contacts:
        raise HTTPException(status_code=404, detail="Contact not found")
    metadata = contacts[0].get("metadata") or {}
    current = metadata.get("unsubscribed_channels", [])
    if channels is None:
        resubscribed = current
        metadata["unsubscribed_channels"] = []
        metadata["unsubscribed_all"] = False
    else:
        resubscribed = [ch for ch in channels if ch in current]
        metadata["unsubscribed_channels"] = [ch for ch in current if ch not in channels]
    metadata["resubscribed_at"] = datetime.utcnow().isoformat()
    await supabase_client.update("contacts", {"metadata": metadata}, filters={"id": f"eq.{contact_id}"})
    return {
        "status": "resubscribed",
        "message": f"Contact resubscribed to {len(resubscribed)} channel(s)",
        "resubscribed_channels": resubscribed,
    }
