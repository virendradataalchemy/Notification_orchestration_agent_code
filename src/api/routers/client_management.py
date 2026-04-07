"""Client management API - Supabase REST based."""

from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from datetime import datetime
import logging

from src.api.dependencies import get_authenticated_client
from src.core.supabase import supabase_client
from src.models import Client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/clients", tags=["client-management"])


class ClientResponse(BaseModel):
    id: int
    name: str
    status: str
    is_active: bool
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class UpdateClientRequest(BaseModel):
    name: Optional[str] = None
    is_active: Optional[bool] = None


def _serialize_client(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "name": row.get("name", f"Client {row['id']}"),
        "status": "active" if row.get("is_active", True) else "inactive",
        "is_active": row.get("is_active", True),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


def _serialize_created_client(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "name": row.get("name"),
        "is_active": row.get("is_active", True),
        "status": "active" if row.get("is_active", True) else "inactive",
        "default_language": row.get("default_language", "en"),
        "created_at": row.get("created_at"),
    }


@router.get("/", response_model=List[dict])
async def list_clients(client: Client = Depends(get_authenticated_client)):
    rows = await supabase_client.select(
        "clients", "id,name,is_active,created_at,updated_at"
    )
    return [_serialize_client(r) for r in rows]


@router.get("/me", response_model=dict)
async def get_current_client(client: Client = Depends(get_authenticated_client)):
    rows = await supabase_client.select(
        "clients", "id,name,is_active,created_at,updated_at",
        limit=1, filters={"id": f"eq.{client.id}"},
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Client not found")
    return _serialize_client(rows[0])


@router.get("/{client_id}", response_model=dict)
async def get_client(client_id: str, client: Client = Depends(get_authenticated_client)):
    rows = await supabase_client.select(
        "clients", "id,name,is_active,created_at,updated_at",
        limit=1, filters={"id": f"eq.{client_id}"},
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Client not found")
    return _serialize_client(rows[0])


@router.patch("/me", response_model=dict)
async def update_current_client(
    request: UpdateClientRequest,
    client: Client = Depends(get_authenticated_client),
):
    update_data: Dict[str, Any] = {"updated_at": datetime.utcnow().isoformat()}
    if request.name is not None:
        update_data["name"] = request.name
    if request.is_active is not None:
        update_data["is_active"] = request.is_active

    rows = await supabase_client.update("clients", update_data, filters={"id": f"eq.{client.id}"})
    if not rows:
        raise HTTPException(status_code=404, detail="Client not found")
    return _serialize_client(rows[0])


class CreateClientRequest(BaseModel):
    name: str
    default_language: Optional[str] = "en"
    is_active: Optional[bool] = True
    brand_color: Optional[str] = None
    client_slug: Optional[str] = None
    preferred_channels: Optional[list] = None
    quiet_hours: Optional[Dict[str, Any]] = None
    supabase_uid: Optional[str] = None


@router.post("/create", response_model=dict, status_code=201)
async def create_client(request: CreateClientRequest):
    """Create a new client and save to Supabase."""
    normalized_name = request.name.strip()
    if not normalized_name:
        raise HTTPException(status_code=422, detail="Client name is required")

    # Make signup idempotent when the auth user already has a provisioned profile.
    if request.supabase_uid:
        existing_rows = await supabase_client.select(
            "clients",
            "id,name,default_language,is_active,created_at",
            limit=1,
            filters={"supabase_uid": f"eq.{request.supabase_uid}"},
        )
        if existing_rows:
            return _serialize_created_client(existing_rows[0])

    # Get next ID
    latest = await supabase_client.select("clients", "id", limit=1, filters={"order": "id.desc"})
    next_id = int(latest[0]["id"]) + 1 if latest else 1

    now = datetime.utcnow().isoformat()
    rows = await supabase_client.insert("clients", {
        "id": next_id,
        "name": normalized_name,
        "default_language": request.default_language or "en",
        "is_active": request.is_active if request.is_active is not None else True,
        "brand_color": request.brand_color,
        "client_slug": request.client_slug or normalized_name.lower().replace(" ", "-"),
        "supabase_uid": request.supabase_uid,
        "created_at": now,
        "updated_at": now,
    })
    client = rows[0]

    # Save client-level preferences (channels, quiet hours, timezone)
    if request.preferred_channels or request.quiet_hours:
        try:
            await supabase_client.upsert("user_preferences", {
                "client_id": next_id,
                "preferred_channels": {"default": request.preferred_channels or []},
                "quiet_hours": request.quiet_hours or {"start": "22:00", "end": "08:00"},
                "timezone": "UTC",
                "language": request.default_language or "en",
            })
        except Exception:
            pass  # Non-critical, client still created

    return _serialize_created_client(client)


@router.get("/by-supabase/{uid}", response_model=dict)
async def get_client_by_supabase_uid(uid: str):
    """Retrieve client details using Supabase Auth UID."""
    rows = await supabase_client.select(
        "clients", "id,name,is_active,created_at,updated_at",
        limit=1, filters={"supabase_uid": f"eq.{uid}"},
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Client not found for this Supabase UID")
    return _serialize_client(rows[0])
