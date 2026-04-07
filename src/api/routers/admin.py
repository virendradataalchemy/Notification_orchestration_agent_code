from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core import get_db_optional, supabase_client
from src.models import Communication, CommunicationAttempt, Contact, Provider, Template, Tenant
from src.models.channel import Channel
from src.models.notification import NotificationEvent

router = APIRouter(prefix="/admin", tags=["admin"])
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


def _tenant_summary(tenant: Tenant) -> dict[str, Any]:
    return {
        "id": tenant.id,
        "name": tenant.name,
        "status": tenant.status,
        "admin_email": getattr(tenant, "admin_email", None),
        "notification_count": 0,
        "provider_configs": 0,
        "created_at": tenant.created_at.isoformat() if tenant.created_at else datetime.utcnow().isoformat(),
        "updated_at": tenant.updated_at.isoformat() if tenant.updated_at else datetime.utcnow().isoformat(),
    }


async def _load_supabase_admin_data() -> dict[str, Any]:
    tenants = await supabase_client.select(
        "tenants",
        "id,name,is_active,created_at,updated_at,default_language,tenant_slug",
    )
    communications = await supabase_client.select(
        "communications",
        "id,tenant_id,contact_id,notification_type,priority,status,channel_id,created_at,updated_at",
    )
    channels = await supabase_client.select("channels", "id,name")
    providers = await supabase_client.select("providers", "id,tenant_id,channel_id,name,is_active")
    contacts = await supabase_client.select("contacts", "id,tenant_id,name,email")
    attempts = await supabase_client.select("communication_attempts", "id,communication_id,attempt_number,status,provider_id")
    return {
        "tenants": tenants,
        "communications": communications,
        "channels": channels,
        "providers": providers,
        "contacts": contacts,
        "attempts": attempts,
    }


@router.get("/dashboard", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    return templates.TemplateResponse(request, "admin_dashboard.html")


@router.get("/tenant-detail-modern/{tenant_id}", response_class=HTMLResponse)
async def tenant_detail_modern(request: Request, tenant_id: str):
    """Modern tenant detail dashboard"""
    return templates.TemplateResponse(request, "tenant_detail_modern.html", {"tenant_id": tenant_id})



@router.get("/api/stats")
async def get_dashboard_stats(db: AsyncSession | None = Depends(get_db_optional)) -> Dict[str, Any]:
    now = datetime.utcnow()
    twenty_four_hours_ago = now - timedelta(hours=24)

    if db is not None:
        tenant_rows = (await db.execute(select(Tenant))).scalars().all()
        comm_rows = (await db.execute(select(Communication))).scalars().all()
        channel_rows = (await db.execute(select(Channel))).scalars().all()

        tenant_counter = Counter(tenant.status for tenant in tenant_rows)
        status_counter = Counter(_status_value(comm.status) for comm in comm_rows)
        recent_rows = [comm for comm in comm_rows if (comm.created_at and comm.created_at >= twenty_four_hours_ago)]
        recent_count = len(recent_rows)
        delivered_recent = sum(1 for comm in recent_rows if _status_value(comm.status) == "delivered")
        success_rate = round((delivered_recent / recent_count * 100), 2) if recent_count else 0

        tenant_activity_counter = Counter(comm.tenant_id for comm in comm_rows)
        tenant_activity = [
            {
                "tenant_id": tenant.id,
                "tenant_name": tenant.name,
                "notification_count": tenant_activity_counter.get(tenant.id, 0),
            }
            for tenant in tenant_rows
        ]
        tenant_activity.sort(key=lambda row: row["notification_count"], reverse=True)

        channel_map = {channel.id: channel.name for channel in channel_rows}
        channel_usage = Counter(channel_map.get(comm.channel_id, "unknown") for comm in comm_rows)

        return {
            "tenants": {
                "active": tenant_counter.get("active", 0),
                "suspended": tenant_counter.get("suspended", 0),
                "deleted": tenant_counter.get("deleted", 0),
                "total": len(tenant_rows),
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
            "tenant_activity": tenant_activity,
            "timestamp": now.isoformat(),
        }

    if not supabase_client.configured:
        raise HTTPException(status_code=503, detail="No database backend available")

    data = await _load_supabase_admin_data()
    tenant_counter = Counter("active" if tenant.get("is_active", True) else "inactive" for tenant in data["tenants"])
    status_counter = Counter(str(comm.get("status", "unknown")).lower() for comm in data["communications"])

    recent_rows = []
    for comm in data["communications"]:
        created_at = _parse_dt(comm.get("created_at"))
        if created_at and created_at >= twenty_four_hours_ago:
            recent_rows.append(comm)
    recent_count = len(recent_rows)
    delivered_recent = sum(1 for comm in recent_rows if str(comm.get("status", "")).lower() == "delivered")
    success_rate = round((delivered_recent / recent_count * 100), 2) if recent_count else 0

    tenant_name_map = {tenant["id"]: tenant.get("name", f"Tenant {tenant['id']}") for tenant in data["tenants"]}
    tenant_activity_counter = Counter(comm.get("tenant_id") for comm in data["communications"])
    tenant_activity = [
        {
            "tenant_id": tenant["id"],
            "tenant_name": tenant.get("name", f"Tenant {tenant['id']}"),
            "notification_count": tenant_activity_counter.get(tenant["id"], 0),
        }
        for tenant in data["tenants"]
    ]
    tenant_activity.sort(key=lambda row: row["notification_count"], reverse=True)

    channel_map = {channel["id"]: str(channel.get("name", "unknown")).lower() for channel in data["channels"]}
    channel_usage = Counter(channel_map.get(comm.get("channel_id"), "unknown") for comm in data["communications"])

    return {
        "tenants": {
            "active": tenant_counter.get("active", 0),
            "suspended": tenant_counter.get("suspended", 0),
            "deleted": tenant_counter.get("deleted", 0),
            "total": len(data["tenants"]),
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
        "tenant_activity": tenant_activity,
        "timestamp": now.isoformat(),
    }


@router.get("/api/tenants")
async def get_all_tenants(db: AsyncSession | None = Depends(get_db_optional)) -> List[Dict[str, Any]]:
    if db is not None:
        tenant_rows = (await db.execute(select(Tenant).order_by(Tenant.created_at.desc()))).scalars().all()
        comm_counts = Counter(
            row[0] for row in (await db.execute(select(Communication.tenant_id))).all()
        )
        provider_counts = Counter(
            row[0] for row in (await db.execute(select(Provider.tenant_id).where(Provider.is_active == True))).all()
        )
        result = []
        for tenant in tenant_rows:
            row = _tenant_summary(tenant)
            row["notification_count"] = comm_counts.get(tenant.id, 0)
            row["provider_configs"] = provider_counts.get(tenant.id, 0)
            result.append(row)
        return result

    if not supabase_client.configured:
        raise HTTPException(status_code=503, detail="No database backend available")

    data = await _load_supabase_admin_data()
    comm_counts = Counter(comm.get("tenant_id") for comm in data["communications"])
    provider_counts = Counter(
        provider.get("tenant_id") for provider in data["providers"] if provider.get("is_active", True)
    )
    result = []
    for tenant in sorted(data["tenants"], key=lambda row: row.get("created_at") or "", reverse=True):
        result.append(
            {
                "id": tenant["id"],
                "name": tenant.get("name", f"Tenant {tenant['id']}"),
                "status": "active" if tenant.get("is_active", True) else "inactive",
                "admin_email": tenant.get("admin_email"),
                "notification_count": comm_counts.get(tenant["id"], 0),
                "provider_configs": provider_counts.get(tenant["id"], 0),
                "created_at": tenant.get("created_at") or datetime.utcnow().isoformat(),
                "updated_at": tenant.get("updated_at") or datetime.utcnow().isoformat(),
            }
        )
    return result


@router.get("/api/tenants/{tenant_id}/details")
async def get_tenant_details(tenant_id: str, db: AsyncSession | None = Depends(get_db_optional)) -> Dict[str, Any]:
    tenant_pk = int(tenant_id)

    if db is not None:
        tenant = await db.get(Tenant, tenant_pk)
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found")

        communications = (
            await db.execute(
                select(Communication)
                .where(Communication.tenant_id == tenant_pk)
                .order_by(Communication.created_at.desc())
            )
        ).scalars().all()
        providers = (await db.execute(select(Provider).where(or_(Provider.tenant_id == tenant_pk, Provider.tenant_id.is_(None))))).scalars().all()
        templates_rows = (await db.execute(select(Template).where(Template.tenant_id == tenant_pk))).scalars().all()
        channel_rows = (await db.execute(select(Channel))).scalars().all()
        channel_map = {channel.id: channel.name for channel in channel_rows}

        return {
            "tenant": _tenant_summary(tenant),
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
    tenant = next((row for row in data["tenants"] if row["id"] == tenant_pk), None)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    channel_map = {channel["id"]: str(channel.get("name", "unknown")).lower() for channel in data["channels"]}
    communications = [comm for comm in data["communications"] if comm.get("tenant_id") == tenant_pk]
    providers = [provider for provider in data["providers"] if provider.get("tenant_id") in (None, tenant_pk)]
    templates_rows = await supabase_client.select(
        "templates",
        "id,tenant_id,name,language,subject,content,version,is_active,channel_id,created_at",
        filters={"tenant_id": f"eq.{tenant_pk}"},
    )

    return {
        "tenant": {
            "id": tenant["id"],
            "name": tenant.get("name", f"Tenant {tenant['id']}"),
            "status": "active" if tenant.get("is_active", True) else "inactive",
            "admin_email": tenant.get("admin_email"),
            "notification_count": len(communications),
            "provider_configs": len(providers),
            "created_at": tenant.get("created_at") or datetime.utcnow().isoformat(),
            "updated_at": tenant.get("updated_at") or datetime.utcnow().isoformat(),
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
                "is_global": template.get("tenant_id") is None,
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
        tenants = {tenant.id: tenant.name for tenant in (await db.execute(select(Tenant))).scalars().all()}
        channels = {channel.id: channel.name for channel in (await db.execute(select(Channel))).scalars().all()}
        attempts = (await db.execute(select(CommunicationAttempt))).scalars().all()
        attempt_map: dict[int, list[CommunicationAttempt]] = defaultdict(list)
        for attempt in attempts:
            attempt_map[attempt.communication_id].append(attempt)

        return [
            {
                "id": str(comm.id),
                "tenant_name": tenants.get(comm.tenant_id, f"Tenant {comm.tenant_id}"),
                "tenant_id": comm.tenant_id,
                "type": comm.notification_type,
                "priority": _status_value(comm.priority),
                "status": _status_value(comm.status),
                "user_id": str(comm.contact_id),
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
    tenant_names = {tenant["id"]: tenant.get("name", f"Tenant {tenant['id']}") for tenant in data["tenants"]}
    channel_names = {channel["id"]: str(channel.get("name", "unknown")).lower() for channel in data["channels"]}
    contact_names = {contact["id"]: contact.get("email") or contact.get("name") or str(contact["id"]) for contact in data["contacts"]}
    attempt_counter: dict[int, int] = defaultdict(int)
    for attempt in data["attempts"]:
        comm_id = attempt.get("communication_id")
        attempt_counter[comm_id] = max(attempt_counter[comm_id], int(attempt.get("attempt_number") or 0))

    communications = sorted(data["communications"], key=lambda row: row.get("created_at") or "", reverse=True)[:limit]
    return [
        {
            "id": str(comm["id"]),
            "tenant_name": tenant_names.get(comm.get("tenant_id"), f"Tenant {comm.get('tenant_id')}"),
            "tenant_id": comm.get("tenant_id"),
            "type": comm.get("notification_type"),
            "priority": str(comm.get("priority", "medium")).lower(),
            "status": str(comm.get("status", "unknown")).lower(),
            "user_id": contact_names.get(comm.get("contact_id"), str(comm.get("contact_id"))),
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


@router.post("/api/tenants/{tenant_id}/suspend")
async def suspend_tenant(tenant_id: str, db: AsyncSession | None = Depends(get_db_optional)) -> Dict[str, str]:
    tenant_pk = int(tenant_id)
    if db is not None:
        tenant = await db.get(Tenant, tenant_pk)
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found")
        tenant.is_active = False
        await db.commit()
        return {"message": f"Tenant {tenant_id} has been suspended", "status": "suspended"}

    if not supabase_client.configured:
        raise HTTPException(status_code=503, detail="No database backend available")
    rows = await supabase_client.update("tenants", {"is_active": False}, filters={"id": f"eq.{tenant_pk}"})
    if not rows:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return {"message": f"Tenant {tenant_id} has been suspended", "status": "suspended"}


@router.post("/api/tenants/{tenant_id}/activate")
async def activate_tenant(tenant_id: str, db: AsyncSession | None = Depends(get_db_optional)) -> Dict[str, str]:
    tenant_pk = int(tenant_id)
    if db is not None:
        tenant = await db.get(Tenant, tenant_pk)
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found")
        tenant.is_active = True
        await db.commit()
        return {"message": f"Tenant {tenant_id} has been activated", "status": "active"}

    if not supabase_client.configured:
        raise HTTPException(status_code=503, detail="No database backend available")
    rows = await supabase_client.update("tenants", {"is_active": True}, filters={"id": f"eq.{tenant_pk}"})
    if not rows:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return {"message": f"Tenant {tenant_id} has been activated", "status": "active"}


@router.get("/api/templates")
async def get_all_templates(db: AsyncSession | None = Depends(get_db_optional)) -> List[Dict[str, Any]]:
    if db is not None:
        templates_rows = (await db.execute(select(Template).order_by(Template.created_at.desc()))).scalars().all()
        tenants = {tenant.id: tenant.name for tenant in (await db.execute(select(Tenant))).scalars().all()}
        channels = {channel.id: channel.name for channel in (await db.execute(select(Channel))).scalars().all()}
        return [
            {
                "id": template.id,
                "name": template.name,
                "channel": channels.get(template.channel_id, "unknown"),
                "language": template.language,
                "is_global": template.is_global,
                "tenant_id": template.tenant_id,
                "tenant_name": tenants.get(template.tenant_id),
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
        "id,tenant_id,name,language,version,is_active,created_at,channel_id",
    )
    tenants = await supabase_client.select("tenants", "id,name")
    channels = await supabase_client.select("channels", "id,name")
    tenant_names = {tenant["id"]: tenant.get("name") for tenant in tenants}
    channel_names = {channel["id"]: str(channel.get("name", "unknown")).lower() for channel in channels}
    return [
        {
            "id": template["id"],
            "name": template.get("name"),
            "channel": channel_names.get(template.get("channel_id"), "unknown"),
            "language": template.get("language"),
            "is_global": template.get("tenant_id") is None,
            "tenant_id": template.get("tenant_id"),
            "tenant_name": tenant_names.get(template.get("tenant_id")),
            "active": template.get("is_active", True),
            "version": template.get("version", 1),
            "created_at": template.get("created_at") or datetime.utcnow().isoformat(),
        }
        for template in templates_rows
    ]
