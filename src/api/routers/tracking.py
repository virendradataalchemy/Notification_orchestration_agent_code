"""Tracking, unsubscribe, and delivery log endpoints - Supabase REST based."""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel

from src.api.dependencies import get_authenticated_client
from src.core.supabase import supabase_client
from src.models import Client

router = APIRouter(prefix="/tracking", tags=["tracking-logs"])


class UnsubscribeRequest(BaseModel):
    candidate_id: int
    channels: Optional[List[str]] = None
    reason: Optional[str] = None


class UnsubscribeResponse(BaseModel):
    status: str
    message: str
    unsubscribed_channels: List[str]


@router.get("/logs/{communication_id}")
async def get_notification_logs(
    communication_id: int,
    client: Client = Depends(get_authenticated_client),
):
    comms = await supabase_client.select(
        "communications", "id,client_id,notification_type,candidate_id,created_at",
        limit=1, filters={"id": f"eq.{communication_id}", "client_id": f"eq.{client.id}"},
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
        "candidate_id": comm.get("candidate_id"),
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
    client: Client = Depends(get_authenticated_client),
):
    candidates = await supabase_client.select(
        "candidates", "id,metadata",
        limit=1, filters={"id": f"eq.{request.candidate_id}", "client_id": f"eq.{client.id}"},
    )
    if not candidates:
        raise HTTPException(status_code=404, detail="Candidate not found")
    metadata: Dict[str, Any] = candidates[0].get("metadata") or {}
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
    await supabase_client.update("candidates", {"metadata": metadata}, filters={"id": f"eq.{request.candidate_id}"})
    return UnsubscribeResponse(
        status="unsubscribed",
        message=f"Candidate unsubscribed from {len(unsubscribed_channels)} channel(s)",
        unsubscribed_channels=unsubscribed_channels,
    )


@router.get("/unsubscribed/{candidate_id}")
async def get_unsubscribed_channels(
    candidate_id: int,
    client: Client = Depends(get_authenticated_client),
):
    candidates = await supabase_client.select(
        "candidates", "id,metadata",
        limit=1, filters={"id": f"eq.{candidate_id}", "client_id": f"eq.{client.id}"},
    )
    if not candidates:
        raise HTTPException(status_code=404, detail="Candidate not found")
    metadata = candidates[0].get("metadata") or {}
    return {
        "candidate_id": candidate_id,
        "unsubscribed_channels": metadata.get("unsubscribed_channels", []),
        "unsubscribed_all": metadata.get("unsubscribed_all", False),
        "unsubscribe_reason": metadata.get("unsubscribe_reason"),
        "unsubscribed_at": metadata.get("unsubscribed_at"),
    }


@router.post("/resubscribe/{candidate_id}")
async def resubscribe(
    candidate_id: int,
    channels: Optional[List[str]] = Query(None),
    client: Client = Depends(get_authenticated_client),
):
    candidates = await supabase_client.select(
        "candidates", "id,metadata",
        limit=1, filters={"id": f"eq.{candidate_id}", "client_id": f"eq.{client.id}"},
    )
    if not candidates:
        raise HTTPException(status_code=404, detail="Candidate not found")
    metadata = candidates[0].get("metadata") or {}
    current = metadata.get("unsubscribed_channels", [])
    if channels is None:
        resubscribed = current
        metadata["unsubscribed_channels"] = []
        metadata["unsubscribed_all"] = False
    else:
        resubscribed = [ch for ch in channels if ch in current]
        metadata["unsubscribed_channels"] = [ch for ch in current if ch not in channels]
    metadata["resubscribed_at"] = datetime.utcnow().isoformat()
    await supabase_client.update("candidates", {"metadata": metadata}, filters={"id": f"eq.{candidate_id}"})
    return {
        "status": "resubscribed",
        "message": f"Candidate resubscribed to {len(resubscribed)} channel(s)",
        "resubscribed_channels": resubscribed,
    }
