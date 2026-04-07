"""Tenant management API - Supabase REST based."""

from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from datetime import datetime
import logging

from src.api.dependencies import get_authenticated_tenant
from src.core.supabase import supabase_client
from src.models import Tenant

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tenants", tags=["tenant-management"])


class TenantResponse(BaseModel):
    id: int
    name: str
    status: str
    is_active: bool
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class UpdateTenantRequest(BaseModel):
    name: Optional[str] = None
    is_active: Optional[bool] = None


def _serialize_tenant(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "name": row.get("name", f"Tenant {row['id']}"),
        "status": "active" if row.get("is_active", True) else "inactive",
        "is_active": row.get("is_active", True),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


@router.get("/", response_model=List[dict])
async def list_tenants(tenant: Tenant = Depends(get_authenticated_tenant)):
    rows = await supabase_client.select(
        "tenants", "id,name,is_active,created_at,updated_at"
    )
    return [_serialize_tenant(r) for r in rows]


@router.get("/me", response_model=dict)
async def get_current_tenant(tenant: Tenant = Depends(get_authenticated_tenant)):
    rows = await supabase_client.select(
        "tenants", "id,name,is_active,created_at,updated_at",
        limit=1, filters={"id": f"eq.{tenant.id}"},
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return _serialize_tenant(rows[0])


@router.get("/{tenant_id}", response_model=dict)
async def get_tenant(tenant_id: str, tenant: Tenant = Depends(get_authenticated_tenant)):
    rows = await supabase_client.select(
        "tenants", "id,name,is_active,created_at,updated_at",
        limit=1, filters={"id": f"eq.{tenant_id}"},
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return _serialize_tenant(rows[0])


@router.patch("/me", response_model=dict)
async def update_current_tenant(
    request: UpdateTenantRequest,
    tenant: Tenant = Depends(get_authenticated_tenant),
):
    update_data: Dict[str, Any] = {"updated_at": datetime.utcnow().isoformat()}
    if request.name is not None:
        update_data["name"] = request.name
    if request.is_active is not None:
        update_data["is_active"] = request.is_active

    rows = await supabase_client.update("tenants", update_data, filters={"id": f"eq.{tenant.id}"})
    if not rows:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return _serialize_tenant(rows[0])


class CreateTenantRequest(BaseModel):
    name: str
    default_language: Optional[str] = "en"
    is_active: Optional[bool] = True
    brand_color: Optional[str] = None
    tenant_slug: Optional[str] = None
    preferred_channels: Optional[list] = None
    quiet_hours: Optional[Dict[str, Any]] = None


@router.post("/create", response_model=dict, status_code=201)
async def create_tenant(request: CreateTenantRequest):
    """Create a new tenant and save to Supabase."""
    # Get next ID
    latest = await supabase_client.select("tenants", "id", limit=1, filters={"order": "id.desc"})
    next_id = int(latest[0]["id"]) + 1 if latest else 1

    now = datetime.utcnow().isoformat()
    rows = await supabase_client.insert("tenants", {
        "id": next_id,
        "name": request.name,
        "default_language": request.default_language or "en",
        "is_active": request.is_active if request.is_active is not None else True,
        "brand_color": request.brand_color,
        "tenant_slug": request.tenant_slug or request.name.lower().replace(" ", "-"),
        "created_at": now,
        "updated_at": now,
    })
    tenant = rows[0]

    # Save tenant-level preferences (channels, quiet hours, timezone)
    if request.preferred_channels or request.quiet_hours:
        try:
            await supabase_client.upsert("user_preferences", {
                "tenant_id": next_id,
                "preferred_channels": {"default": request.preferred_channels or []},
                "quiet_hours": request.quiet_hours or {"start": "22:00", "end": "08:00"},
                "timezone": "UTC",
                "language": request.default_language or "en",
            })
        except Exception:
            pass  # Non-critical, tenant still created

    return {
        "id": tenant["id"],
        "name": tenant.get("name"),
        "is_active": tenant.get("is_active", True),
        "status": "active" if tenant.get("is_active", True) else "inactive",
        "default_language": tenant.get("default_language", "en"),
        "created_at": tenant.get("created_at"),
    }
