"""Client management API - Supabase REST based."""

from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from datetime import datetime
import logging

from src.api.dependencies import get_authenticated_client
from src.core.supabase import CLIENT_PREFERENCES_TABLE, CLIENTS_TABLE, supabase_client
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
        "client_slug": row.get("client_slug"),
        "status": "active" if row.get("is_active", True) else "inactive",
        "is_active": row.get("is_active", True),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


def _serialize_created_client(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "name": row.get("name"),
        "client_slug": row.get("client_slug"),
        "is_active": row.get("is_active", True),
        "status": "active" if row.get("is_active", True) else "inactive",
        "default_language": row.get("default_language", "en"),
        "created_at": row.get("created_at"),
    }


async def _update_existing_client_for_signup(
    client_row: Dict[str, Any],
    *,
    normalized_name: str,
    request: "CreateClientRequest",
    now: str,
) -> Dict[str, Any]:
    update_data = {
        "name": normalized_name,
        "default_language": request.default_language or client_row.get("default_language") or "en",
        "is_active": request.is_active if request.is_active is not None else client_row.get("is_active", True),
        "brand_color": request.brand_color if request.brand_color is not None else client_row.get("brand_color"),
        "client_slug": request.client_slug or client_row.get("client_slug") or normalized_name.lower().replace(" ", "-"),
        "updated_at": now,
    }
    if request.supabase_uid and not client_row.get("supabase_uid"):
        update_data["supabase_uid"] = request.supabase_uid

    rows = await supabase_client.update(
        CLIENTS_TABLE,
        update_data,
        filters={"id": f"eq.{client_row['id']}"},
    )
    await _upsert_client_preferences(
        int(client_row["id"]),
        preferred_channels=request.preferred_channels,
        quiet_hours=request.quiet_hours,
        language=request.default_language or client_row.get("default_language") or "en",
    )
    return rows[0] if rows else {**client_row, **update_data}


async def _upsert_client_preferences(
    client_id: int,
    *,
    preferred_channels: Optional[list] = None,
    quiet_hours: Optional[Dict[str, Any]] = None,
    language: Optional[str] = None,
) -> None:
    if preferred_channels is None and quiet_hours is None and language is None:
        return

    payload: Dict[str, Any] = {}
    if preferred_channels is not None:
        payload["preferred_channels"] = {"default": preferred_channels}
    if quiet_hours is not None:
        payload["quiet_hours"] = quiet_hours
    if language is not None:
        payload["language"] = language
    payload["timezone"] = "UTC"

    existing = await supabase_client.select(
        CLIENT_PREFERENCES_TABLE,
        "client_id",
        limit=1,
        filters={"client_id": f"eq.{client_id}"},
    )
    if existing:
        await supabase_client.update(
            CLIENT_PREFERENCES_TABLE,
            payload,
            filters={"client_id": f"eq.{client_id}"},
        )
        return

    await supabase_client.insert(
        CLIENT_PREFERENCES_TABLE,
        {
            "client_id": client_id,
            **payload,
        },
    )


@router.get("/", response_model=List[dict])
async def list_clients(client: Client = Depends(get_authenticated_client)):
    rows = await supabase_client.select(
        CLIENTS_TABLE, "id,name,client_slug,is_active,created_at,updated_at"
    )
    return [_serialize_client(r) for r in rows]


@router.get("/me", response_model=dict)
async def get_current_client(client: Client = Depends(get_authenticated_client)):
    rows = await supabase_client.select(
        CLIENTS_TABLE, "id,name,client_slug,is_active,created_at,updated_at",
        limit=1, filters={"id": f"eq.{client.id}"},
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Client not found")
    return _serialize_client(rows[0])


@router.get("/{client_id}", response_model=dict)
async def get_client(client_id: str, client: Client = Depends(get_authenticated_client)):
    rows = await supabase_client.select(
        CLIENTS_TABLE, "id,name,client_slug,is_active,created_at,updated_at",
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

    rows = await supabase_client.update(CLIENTS_TABLE, update_data, filters={"id": f"eq.{client.id}"})
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

    now = datetime.utcnow().isoformat()
    desired_slug = request.client_slug or normalized_name.lower().replace(" ", "-")

    # Make signup idempotent when the auth user already has a provisioned profile.
    if request.supabase_uid:
        existing_rows = await supabase_client.select(
            CLIENTS_TABLE,
            "id,name,default_language,is_active,brand_color,client_slug,supabase_uid,created_at,updated_at",
            limit=1,
            filters={"supabase_uid": f"eq.{request.supabase_uid}"},
        )
        if existing_rows:
            updated = await _update_existing_client_for_signup(
                existing_rows[0],
                normalized_name=normalized_name,
                request=request,
                now=now,
            )
            return _serialize_created_client(updated)

    # Reuse a pre-created client row with the same slug or exact name.
    conflict_filters = [
        {"client_slug": f"eq.{desired_slug}"},
        {"name": f"eq.{normalized_name}"},
    ]
    for filters in conflict_filters:
        existing_rows = await supabase_client.select(
            CLIENTS_TABLE,
            "id,name,default_language,is_active,brand_color,client_slug,supabase_uid,created_at,updated_at",
            limit=1,
            filters=filters,
        )
        if existing_rows:
            updated = await _update_existing_client_for_signup(
                existing_rows[0],
                normalized_name=normalized_name,
                request=request,
                now=now,
            )
            return _serialize_created_client(updated)

    # Get next ID
    latest = await supabase_client.select(CLIENTS_TABLE, "id", limit=1, filters={"order": "id.desc"})
    next_id = int(latest[0]["id"]) + 1 if latest else 1

    try:
        rows = await supabase_client.insert(CLIENTS_TABLE, {
            "id": next_id,
            "name": normalized_name,
            "default_language": request.default_language or "en",
            "is_active": request.is_active if request.is_active is not None else True,
            "brand_color": request.brand_color,
            "client_slug": desired_slug,
            "supabase_uid": request.supabase_uid,
            "created_at": now,
            "updated_at": now,
        })
    except Exception as exc:
        logger.warning("Client signup insert conflicted for name='%s', slug='%s': %s", normalized_name, desired_slug, exc)
        fallback_rows = await supabase_client.select(
            CLIENTS_TABLE,
            "id,name,default_language,is_active,brand_color,client_slug,supabase_uid,created_at,updated_at",
            limit=1,
            filters={"or": f"(supabase_uid.eq.{request.supabase_uid},client_slug.eq.{desired_slug},name.eq.{normalized_name})"} if request.supabase_uid else {"or": f"(client_slug.eq.{desired_slug},name.eq.{normalized_name})"},
        )
        if not fallback_rows:
            raise
        updated = await _update_existing_client_for_signup(
            fallback_rows[0],
            normalized_name=normalized_name,
            request=request,
            now=now,
        )
        return _serialize_created_client(updated)
    client = rows[0]

    try:
        await _upsert_client_preferences(
            next_id,
            preferred_channels=request.preferred_channels,
            quiet_hours=request.quiet_hours,
            language=request.default_language or "en",
        )
    except Exception:
        pass  # Non-critical, client still created

    return _serialize_created_client(client)


@router.get("/by-supabase/{uid}", response_model=dict)
async def get_client_by_supabase_uid(uid: str):
    """Retrieve client details using Supabase Auth UID."""
    rows = await supabase_client.select(
        CLIENTS_TABLE, "id,name,client_slug,is_active,created_at,updated_at",
        limit=1, filters={"supabase_uid": f"eq.{uid}"},
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Client not found for this Supabase UID")
    return _serialize_client(rows[0])


@router.get("/by-id/{client_id}", response_model=dict)
async def get_client_by_id(client_id: str):
    rows = await supabase_client.select(
        CLIENTS_TABLE,
        "id,name,client_slug,is_active,created_at,updated_at",
        limit=1,
        filters={"id": f"eq.{client_id}"},
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Client not found")
    return _serialize_client(rows[0])


@router.get("/by-slug/{client_slug}", response_model=dict)
async def get_client_by_slug(client_slug: str):
    rows = await supabase_client.select(
        CLIENTS_TABLE,
        "id,name,client_slug,is_active,created_at,updated_at",
        limit=1,
        filters={"client_slug": f"eq.{client_slug}"},
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Client not found for this slug")
    return _serialize_client(rows[0])
