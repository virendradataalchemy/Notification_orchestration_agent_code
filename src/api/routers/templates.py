"""Templates API - Supabase REST based."""

from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional, Dict, Any

from src.api.dependencies import get_authenticated_client, verify_api_key
from src.api.schemas import TemplateCreate, TemplateResponse
from src.core.supabase import supabase_client
from src.models import Client

router = APIRouter(prefix="/templates", tags=["templates"])


async def _channel_id(channel_name: str) -> Optional[int]:
    rows = await supabase_client.select("channels", "id", limit=1, filters={"name": f"eq.{channel_name}"})
    return rows[0]["id"] if rows else None


async def _channel_name(channel_id: int) -> str:
    rows = await supabase_client.select("channels", "name", limit=1, filters={"id": f"eq.{channel_id}"})
    return rows[0]["name"] if rows else "unknown"


def _serialize(row: Dict[str, Any], channel: str = "unknown") -> Dict[str, Any]:
    return {
        "id": row.get("id"),
        "client_id": row.get("client_id"),
        "name": row.get("name"),
        "channel": channel,
        "language": row.get("language") or "en",
        "subject": row.get("subject"),
        "body": row.get("content") or row.get("body") or "",
        "version": row.get("version") or 1,
        "active": row.get("is_active", True),
        "is_global": row.get("client_id") is None,
        "created_at": row.get("created_at"),
    }


@router.post("/", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_template(
    template: TemplateCreate,
    client: Client = Depends(get_authenticated_client),
):
    ch_id = await _channel_id(template.channel.value if hasattr(template.channel, "value") else template.channel)
    if not ch_id:
        raise HTTPException(status_code=400, detail=f"Channel '{template.channel}' not configured")

    rows = await supabase_client.insert("templates", {
        "client_id": client.id,
        "name": template.name,
        "channel_id": ch_id,
        "language": template.language if hasattr(template, "language") else "en",
        "subject": template.subject if hasattr(template, "subject") else None,
        "content": template.body if hasattr(template, "body") else "",
        "version": 1,
        "is_active": True,
        "notification_type": template.name,
    })
    row = rows[0]
    row["channel"] = template.channel.value if hasattr(template.channel, "value") else template.channel
    return _serialize(row, row["channel"])


@router.get("/{template_id}", response_model=dict)
async def get_template(
    template_id: str,
    client: Client = Depends(get_authenticated_client),
):
    rows = await supabase_client.select(
        "templates",
        "id,client_id,name,language,subject,content,version,is_active,channel_id,created_at",
        limit=1,
        filters={"id": f"eq.{template_id}", "client_id": f"eq.{client.id}", "is_active": "eq.true"},
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Template not found")
    row = rows[0]
    ch = await _channel_name(row["channel_id"])
    return _serialize(row, ch)


@router.get("/", response_model=List[dict])
async def list_templates(
    channel: Optional[str] = None,
    client: Client = Depends(get_authenticated_client),
):
    filters: Dict[str, str] = {"client_id": f"eq.{client.id}", "is_active": "eq.true"}
    rows = await supabase_client.select(
        "templates",
        "id,client_id,name,language,subject,content,version,is_active,channel_id,created_at",
        filters=filters,
    )
    ch_cache: Dict[int, str] = {}
    result = []
    for row in rows:
        cid = row.get("channel_id")
        if cid not in ch_cache:
            ch_cache[cid] = await _channel_name(cid)
        if channel and ch_cache[cid] != channel:
            continue
        result.append(_serialize(row, ch_cache[cid]))
    return result


@router.put("/{template_id}", response_model=dict)
async def update_template(
    template_id: str,
    template: TemplateCreate,
    client: Client = Depends(get_authenticated_client),
):
    existing = await supabase_client.select(
        "templates", "id,version", limit=1,
        filters={"id": f"eq.{template_id}", "client_id": f"eq.{client.id}"},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Template not found")

    new_version = (existing[0].get("version") or 1) + 1
    rows = await supabase_client.update(
        "templates",
        {
            "name": template.name,
            "subject": template.subject if hasattr(template, "subject") else None,
            "content": template.body if hasattr(template, "body") else "",
            "version": new_version,
        },
        filters={"id": f"eq.{template_id}"},
    )
    row = rows[0] if rows else existing[0]
    ch = await _channel_name(row.get("channel_id", 0))
    return _serialize(row, ch)


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: str,
    client: Client = Depends(get_authenticated_client),
):
    existing = await supabase_client.select(
        "templates", "id", limit=1,
        filters={"id": f"eq.{template_id}", "client_id": f"eq.{client.id}"},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Template not found")
    await supabase_client.update("templates", {"is_active": False}, filters={"id": f"eq.{template_id}"})
    return None
