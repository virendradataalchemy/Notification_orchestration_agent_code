from __future__ import annotations

import asyncio
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, EmailStr
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core import get_db_optional, supabase_client
from src.core.cache import cached, invalidate_pattern
from src.api.dependencies import get_authenticated_admin
from src.core.supabase import ADMINS_TABLE
from src.models import Communication, CommunicationAttempt, Candidate, Provider, Template, Client
from src.models.channel import Channel
from src.models.notification import NotificationEvent

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(get_authenticated_admin)])
templates = Jinja2Templates(directory="src/templates")


def _parse_dt(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        normalized = value.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalized)
        except ValueError:
            return None
    return None


def _status_value(value: Any) -> str:
    return value.value if hasattr(value, "value") else str(value)


def _client_summary(client: Client) -> dict[str, Any]:
    return {
        "id": client.id,
        "name": client.name,
        "status": client.status,
        "admin_email": getattr(client, "admin_email", None),
        "notification_count": 0,
        "provider_configs": 0,
        "created_at": client.created_at.isoformat() if client.created_at else datetime.utcnow().isoformat(),
        "updated_at": client.updated_at.isoformat() if client.updated_at else datetime.utcnow().isoformat(),
    }


@cached("admin_data", ttl=600)  # 10 min
async def _load_supabase_admin_data() -> dict[str, Any]:
    clients, communications, channels, providers, candidates, attempts = await asyncio.gather(
        supabase_client.select("clients", "id,name,is_active,created_at,updated_at,default_language,client_slug"),
        supabase_client.select("communications", "id,client_id,candidate_id,notification_type,priority,status,channel_id,created_at,updated_at"),
        supabase_client.select("channels", "id,name"),
        supabase_client.select("providers", "id,client_id,channel_id,name,is_active"),
        supabase_client.select("candidates", "id,client_id,name,email"),
        supabase_client.select("communication_attempts", "id,communication_id,attempt_number,status,provider_id"),
    )
    return {
        "clients": clients,
        "communications": communications,
        "channels": channels,
        "providers": providers,
        "candidates": candidates,
        "attempts": attempts,
    }


@router.get("/api/me")
async def get_admin_session(admin: dict = Depends(get_authenticated_admin)) -> dict[str, Any]:
    return {
        "id": admin.get("id"),
        "name": admin.get("name"),
        "email": admin.get("email"),
        "supabase_uid": admin.get("supabase_uid"),
        "is_active": admin.get("is_active", True),
    }


class CreateAdminRequest(BaseModel):
    email: EmailStr
    password: str
    name: Optional[str] = None
    is_active: bool = True


@router.get("/api/admins")
async def list_admins(_: dict = Depends(get_authenticated_admin)) -> list[dict[str, Any]]:
    rows = await supabase_client.select(
        ADMINS_TABLE,
        "id,supabase_uid,email,name,is_active,created_at,updated_at",
        filters={"order": "created_at.desc"},
    )
    return rows


@router.post("/api/admins", status_code=201)
async def create_admin(
    request: CreateAdminRequest,
    _: dict = Depends(get_authenticated_admin),
) -> dict[str, Any]:
    existing = await supabase_client.select(
        ADMINS_TABLE,
        "id,supabase_uid,email,name,is_active,created_at,updated_at",
        limit=1,
        filters={"email": f"eq.{request.email}"},
    )
    if existing:
        raise HTTPException(status_code=409, detail="An admin with this email already exists")

    if len(request.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters long")

    try:
        auth_user = await supabase_client.create_auth_user(
            email=request.email,
            password=request.password,
            email_confirm=True,
            user_metadata={"name": request.name or request.email.split("@")[0]},
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to create Supabase auth user: {exc}") from exc

    rows = await supabase_client.insert(
        ADMINS_TABLE,
        {
            "supabase_uid": auth_user["id"],
            "email": request.email,
            "name": request.name,
            "is_active": request.is_active,
        },
    )
    return rows[0]


@router.get("/dashboard", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    return templates.TemplateResponse(request, "admin_dashboard.html")


@router.get("/client-detail-modern/{client_id}", response_class=HTMLResponse)
async def client_detail_modern(request: Request, client_id: str):
    """Modern client detail dashboard"""
    return templates.TemplateResponse(request, "client_detail_modern.html", {"client_id": client_id})



@router.get("/api/stats")
async def get_dashboard_stats(db: AsyncSession | None = Depends(get_db_optional)) -> Dict[str, Any]:
    now = datetime.utcnow()
    twenty_four_hours_ago = now - timedelta(hours=24)

    if db is not None:
        client_rows = (await db.execute(select(Client))).scalars().all()
        comm_rows = (await db.execute(select(Communication))).scalars().all()
        channel_rows = (await db.execute(select(Channel))).scalars().all()

        client_counter = Counter(client.status for client in client_rows)
        status_counter = Counter(_status_value(comm.status) for comm in comm_rows)
        recent_rows = [comm for comm in comm_rows if (comm.created_at and comm.created_at >= twenty_four_hours_ago)]
        recent_count = len(recent_rows)
        delivered_recent = sum(1 for comm in recent_rows if _status_value(comm.status) == "delivered")
        success_rate = round((delivered_recent / recent_count * 100), 2) if recent_count else 0

        client_activity_counter = Counter(comm.client_id for comm in comm_rows)
        client_activity = [
            {
                "client_id": client.id,
                "client_name": client.name,
                "notification_count": client_activity_counter.get(client.id, 0),
            }
            for client in client_rows
        ]
        client_activity.sort(key=lambda row: row["notification_count"], reverse=True)

        channel_map = {channel.id: channel.name for channel in channel_rows}
        channel_usage = Counter(channel_map.get(comm.channel_id, "unknown") for comm in comm_rows)

        return {
            "clients": {
                "active": client_counter.get("active", 0),
                "suspended": client_counter.get("suspended", 0),
                "deleted": client_counter.get("deleted", 0),
                "total": len(client_rows),
            },
            "notifications": {
                "total": len(comm_rows),
                "by_status": dict(status_counter),
                "recent_24h": recent_count,
                "success_rate": success_rate,
                "ai_decisions": 0,
                "dedup_hits": 0,
            },
            "channels": {
                "usage": dict(channel_usage),
                "delivery_stats": {},
            },
            "client_activity": client_activity,
            "timestamp": now.isoformat(),
        }

    if not supabase_client.configured:
        raise HTTPException(status_code=503, detail="No database backend available")

    data = await _load_supabase_admin_data()
    client_counter = Counter("active" if client.get("is_active", True) else "inactive" for client in data["clients"])
    status_counter = Counter(str(comm.get("status", "unknown")).lower() for comm in data["communications"])

    recent_rows = []
    for comm in data["communications"]:
        created_at = _parse_dt(comm.get("created_at"))
        if created_at and created_at >= twenty_four_hours_ago:
            recent_rows.append(comm)
    recent_count = len(recent_rows)
    delivered_recent = sum(1 for comm in recent_rows if str(comm.get("status", "")).lower() == "delivered")
    success_rate = round((delivered_recent / recent_count * 100), 2) if recent_count else 0

    client_name_map = {client["id"]: client.get("name", f"Client {client['id']}") for client in data["clients"]}
    client_activity_counter = Counter(comm.get("client_id") for comm in data["communications"])
    client_activity = [
        {
            "client_id": client["id"],
            "client_name": client.get("name", f"Client {client['id']}"),
            "notification_count": client_activity_counter.get(client["id"], 0),
        }
        for client in data["clients"]
    ]
    client_activity.sort(key=lambda row: row["notification_count"], reverse=True)

    channel_map = {channel["id"]: str(channel.get("name", "unknown")).lower() for channel in data["channels"]}
    channel_usage = Counter(channel_map.get(comm.get("channel_id"), "unknown") for comm in data["communications"])

    return {
        "clients": {
            "active": client_counter.get("active", 0),
            "suspended": client_counter.get("suspended", 0),
            "deleted": client_counter.get("deleted", 0),
            "total": len(data["clients"]),
        },
        "notifications": {
            "total": len(data["communications"]),
            "by_status": dict(status_counter),
            "recent_24h": recent_count,
            "success_rate": success_rate,
            "ai_decisions": 0,
            "dedup_hits": 0,
        },
        "channels": {
            "usage": dict(channel_usage),
            "delivery_stats": {},
        },
        "client_activity": client_activity,
        "timestamp": now.isoformat(),
    }


@router.get("/api/clients")
async def get_all_clients(db: AsyncSession | None = Depends(get_db_optional)) -> List[Dict[str, Any]]:
    if db is not None:
        client_rows = (await db.execute(select(Client).order_by(Client.created_at.desc()))).scalars().all()
        comm_counts = Counter(
            row[0] for row in (await db.execute(select(Communication.client_id))).all()
        )
        provider_counts = Counter(
            row[0] for row in (await db.execute(select(Provider.client_id).where(Provider.is_active == True))).all()
        )
        result = []
        for client in client_rows:
            row = _client_summary(client)
            row["notification_count"] = comm_counts.get(client.id, 0)
            row["provider_configs"] = provider_counts.get(client.id, 0)
            result.append(row)
        return result

    if not supabase_client.configured:
        raise HTTPException(status_code=503, detail="No database backend available")

    data = await _load_supabase_admin_data()
    comm_counts = Counter(comm.get("client_id") for comm in data["communications"])
    provider_counts = Counter(
        provider.get("client_id") for provider in data["providers"] if provider.get("is_active", True)
    )
    result = []
    for client in sorted(data["clients"], key=lambda row: row.get("created_at") or "", reverse=True):
        result.append(
            {
                "id": client["id"],
                "name": client.get("name", f"Client {client['id']}"),
                "status": "active" if client.get("is_active", True) else "inactive",
                "admin_email": client.get("admin_email"),
                "notification_count": comm_counts.get(client["id"], 0),
                "provider_configs": provider_counts.get(client["id"], 0),
                "created_at": client.get("created_at") or datetime.utcnow().isoformat(),
                "updated_at": client.get("updated_at") or datetime.utcnow().isoformat(),
            }
        )
    return result


@router.get("/api/clients/{client_id}/details")
async def get_client_details(client_id: str, db: AsyncSession | None = Depends(get_db_optional)) -> Dict[str, Any]:
    client_pk = int(client_id)

    if db is not None:
        client = await db.get(Client, client_pk)
        if not client:
            raise HTTPException(status_code=404, detail="Client not found")

        communications = (
            await db.execute(
                select(Communication)
                .where(Communication.client_id == client_pk)
                .order_by(Communication.created_at.desc())
            )
        ).scalars().all()
        providers = (await db.execute(select(Provider).where(or_(Provider.client_id == client_pk, Provider.client_id.is_(None))))).scalars().all()
        templates_rows = (await db.execute(select(Template).where(Template.client_id == client_pk))).scalars().all()
        channel_rows = (await db.execute(select(Channel))).scalars().all()
        channel_map = {channel.id: channel.name for channel in channel_rows}

        return {
            "client": _client_summary(client),
            "notification_stats": dict(Counter(_status_value(comm.status) for comm in communications)),
            "recent_notifications": [
                {
                    "id": str(comm.id),
                    "type": comm.notification_type,
                    "status": _status_value(comm.status),
                    "priority": _status_value(comm.priority),
                    "created_at": comm.created_at.isoformat() if comm.created_at else datetime.utcnow().isoformat(),
                }
                for comm in communications[:10]
            ],
            "provider_configs": [
                {
                    "provider": provider.name,
                    "is_active": provider.is_active,
                    "config": {"config_ref": provider.config_ref},
                    "created_at": provider.created_at.isoformat() if provider.created_at else datetime.utcnow().isoformat(),
                }
                for provider in providers
            ],
            "templates": [
                {
                    "id": template.id,
                    "name": template.name,
                    "channel": channel_map.get(template.channel_id, "unknown"),
                    "language": template.language,
                    "is_global": template.is_global,
                    "active": template.active,
                }
                for template in templates_rows
            ],
        }

    if not supabase_client.configured:
        raise HTTPException(status_code=503, detail="No database backend available")

    data = await _load_supabase_admin_data()
    client = next((row for row in data["clients"] if row["id"] == client_pk), None)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    channel_map = {channel["id"]: str(channel.get("name", "unknown")).lower() for channel in data["channels"]}
    communications = [comm for comm in data["communications"] if comm.get("client_id") == client_pk]
    providers = [provider for provider in data["providers"] if provider.get("client_id") in (None, client_pk)]
    templates_rows = await supabase_client.select(
        "templates",
        "id,client_id,name,language,subject,content,version,is_active,channel_id,created_at",
        filters={"client_id": f"eq.{client_pk}"},
    )

    return {
        "client": {
            "id": client["id"],
            "name": client.get("name", f"Client {client['id']}"),
            "status": "active" if client.get("is_active", True) else "inactive",
            "admin_email": client.get("admin_email"),
            "notification_count": len(communications),
            "provider_configs": len(providers),
            "created_at": client.get("created_at") or datetime.utcnow().isoformat(),
            "updated_at": client.get("updated_at") or datetime.utcnow().isoformat(),
        },
        "notification_stats": dict(Counter(str(comm.get("status", "unknown")).lower() for comm in communications)),
        "recent_notifications": [
            {
                "id": str(comm["id"]),
                "type": comm.get("notification_type"),
                "status": str(comm.get("status", "unknown")).lower(),
                "priority": str(comm.get("priority", "medium")).lower(),
                "created_at": comm.get("created_at") or datetime.utcnow().isoformat(),
            }
            for comm in sorted(communications, key=lambda row: row.get("created_at") or "", reverse=True)[:10]
        ],
        "provider_configs": [
            {
                "provider": provider.get("name"),
                "is_active": provider.get("is_active", True),
                "config": {"config_ref": provider.get("config_ref")},
                "created_at": provider.get("created_at") or datetime.utcnow().isoformat(),
            }
            for provider in providers
        ],
        "templates": [
            {
                "id": template["id"],
                "name": template.get("name"),
                "channel": channel_map.get(template.get("channel_id"), "unknown"),
                "language": template.get("language"),
                "is_global": template.get("client_id") is None,
                "active": template.get("is_active", True),
            }
            for template in templates_rows
        ],
    }


@router.get("/api/recent-activity")
async def get_recent_activity(limit: int = 50, db: AsyncSession | None = Depends(get_db_optional)) -> List[Dict[str, Any]]:
    if db is not None:
        communications = (
            await db.execute(
                select(Communication)
                .order_by(Communication.created_at.desc())
                .limit(limit)
            )
        ).scalars().all()
        clients = {client.id: client.name for client in (await db.execute(select(Client))).scalars().all()}
        channels = {channel.id: channel.name for channel in (await db.execute(select(Channel))).scalars().all()}
        attempts = (await db.execute(select(CommunicationAttempt))).scalars().all()
        attempt_map: dict[int, list[CommunicationAttempt]] = defaultdict(list)
        for attempt in attempts:
            attempt_map[attempt.communication_id].append(attempt)

        return [
            {
                "id": str(comm.id),
                "client_name": clients.get(comm.client_id, f"Client {comm.client_id}"),
                "client_id": comm.client_id,
                "type": comm.notification_type,
                "priority": _status_value(comm.priority),
                "status": _status_value(comm.status),
                "user_id": str(comm.candidate_id),
                "channels": [
                    {
                        "channel": channels.get(comm.channel_id, "unknown"),
                        "status": _status_value(comm.status),
                        "attempts": max((a.attempt_number for a in attempt_map.get(comm.id, [])), default=0),
                    }
                ],
                "created_at": comm.created_at.isoformat() if comm.created_at else datetime.utcnow().isoformat(),
                "updated_at": comm.updated_at.isoformat() if comm.updated_at else datetime.utcnow().isoformat(),
            }
            for comm in communications
        ]

    if not supabase_client.configured:
        raise HTTPException(status_code=503, detail="No database backend available")

    data = await _load_supabase_admin_data()
    client_names = {client["id"]: client.get("name", f"Client {client['id']}") for client in data["clients"]}
    channel_names = {channel["id"]: str(channel.get("name", "unknown")).lower() for channel in data["channels"]}
    candidate_names = {candidate["id"]: candidate.get("email") or candidate.get("name") or str(candidate["id"]) for candidate in data["candidates"]}
    attempt_counter: dict[int, int] = defaultdict(int)
    for attempt in data["attempts"]:
        comm_id = attempt.get("communication_id")
        attempt_counter[comm_id] = max(attempt_counter[comm_id], int(attempt.get("attempt_number") or 0))

    communications = sorted(data["communications"], key=lambda row: row.get("created_at") or "", reverse=True)[:limit]
    return [
        {
            "id": str(comm["id"]),
            "client_name": client_names.get(comm.get("client_id"), f"Client {comm.get('client_id')}"),
            "client_id": comm.get("client_id"),
            "type": comm.get("notification_type"),
            "priority": str(comm.get("priority", "medium")).lower(),
            "status": str(comm.get("status", "unknown")).lower(),
            "user_id": candidate_names.get(comm.get("candidate_id"), str(comm.get("candidate_id"))),
            "channels": [
                {
                    "channel": channel_names.get(comm.get("channel_id"), "unknown"),
                    "status": str(comm.get("status", "unknown")).lower(),
                    "attempts": attempt_counter.get(comm["id"], 0),
                }
            ],
            "created_at": comm.get("created_at") or datetime.utcnow().isoformat(),
            "updated_at": comm.get("updated_at") or datetime.utcnow().isoformat(),
        }
        for comm in communications
    ]


@router.post("/api/clients/{client_id}/suspend")
async def suspend_client(client_id: str, db: AsyncSession | None = Depends(get_db_optional)) -> Dict[str, str]:
    client_pk = int(client_id)
    if db is not None:
        client = await db.get(Client, client_pk)
        if not client:
            raise HTTPException(status_code=404, detail="Client not found")
        client.is_active = False
        await db.commit()
        return {"message": f"Client {client_id} has been suspended", "status": "suspended"}

    if not supabase_client.configured:
        raise HTTPException(status_code=503, detail="No database backend available")
    rows = await supabase_client.update("clients", {"is_active": False}, filters={"id": f"eq.{client_pk}"})
    if not rows:
        raise HTTPException(status_code=404, detail="Client not found")
    return {"message": f"Client {client_id} has been suspended", "status": "suspended"}


@router.post("/api/clients/{client_id}/activate")
async def activate_client(client_id: str, db: AsyncSession | None = Depends(get_db_optional)) -> Dict[str, str]:
    client_pk = int(client_id)
    if db is not None:
        client = await db.get(Client, client_pk)
        if not client:
            raise HTTPException(status_code=404, detail="Client not found")
        client.is_active = True
        await db.commit()
        return {"message": f"Client {client_id} has been activated", "status": "active"}

    if not supabase_client.configured:
        raise HTTPException(status_code=503, detail="No database backend available")
    rows = await supabase_client.update("clients", {"is_active": True}, filters={"id": f"eq.{client_pk}"})
    if not rows:
        raise HTTPException(status_code=404, detail="Client not found")
    return {"message": f"Client {client_id} has been activated", "status": "active"}


@router.get("/api/templates")
async def get_all_templates(db: AsyncSession | None = Depends(get_db_optional)) -> List[Dict[str, Any]]:
    if db is not None:
        templates_rows = (await db.execute(select(Template).order_by(Template.created_at.desc()))).scalars().all()
        clients = {client.id: client.name for client in (await db.execute(select(Client))).scalars().all()}
        channels = {channel.id: channel.name for channel in (await db.execute(select(Channel))).scalars().all()}
        return [
            {
                "id": template.id,
                "name": template.name,
                "channel": channels.get(template.channel_id, "unknown"),
                "language": template.language,
                "is_global": template.is_global,
                "client_id": template.client_id,
                "client_name": clients.get(template.client_id),
                "active": template.active,
                "version": template.version,
                "created_at": template.created_at.isoformat() if template.created_at else datetime.utcnow().isoformat(),
            }
            for template in templates_rows
        ]

    if not supabase_client.configured:
        raise HTTPException(status_code=503, detail="No database backend available")

    templates_rows = await supabase_client.select(
        "templates",
        "id,client_id,name,language,version,is_active,created_at,channel_id",
    )
    clients = await supabase_client.select("clients", "id,name")
    channels = await supabase_client.select("channels", "id,name")
    client_names = {client["id"]: client.get("name") for client in clients}
    channel_names = {channel["id"]: str(channel.get("name", "unknown")).lower() for channel in channels}
    return [
        {
            "id": template["id"],
            "name": template.get("name"),
            "channel": channel_names.get(template.get("channel_id"), "unknown"),
            "language": template.get("language"),
            "is_global": template.get("client_id") is None,
            "client_id": template.get("client_id"),
            "client_name": client_names.get(template.get("client_id")),
            "active": template.get("is_active", True),
            "version": template.get("version", 1),
            "created_at": template.get("created_at") or datetime.utcnow().isoformat(),
        }
        for template in templates_rows
    ]
