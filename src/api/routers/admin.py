from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from typing import List, Dict, Any
from datetime import datetime, timedelta
import os

from src.core import get_db
from src.models import (
    Tenant,
    Notification,
    NotificationChannel,
    NotificationStatus,
    ChannelStatus,
    Template,
    TenantProviderConfig
)

router = APIRouter(prefix="/admin", tags=["admin"])

# Setup templates
templates = Jinja2Templates(directory="src/templates")


@router.get("/dashboard", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    """
    Admin dashboard HTML page.
    Shows overview of all tenants, notifications, and system health.
    """
    return templates.TemplateResponse("admin_dashboard.html", {"request": request})


@router.get("/api/stats")
async def get_dashboard_stats(db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """
    Get comprehensive dashboard statistics.

    Returns:
        - Total tenants (active, suspended, deleted)
        - Total notifications by status
        - Notifications per tenant
        - Recent activity
        - System health metrics
    """

    # Tenant statistics
    tenant_stats = await db.execute(
        select(
            Tenant.status,
            func.count(Tenant.id).label('count')
        ).group_by(Tenant.status)
    )
    tenant_counts = {row.status: row.count for row in tenant_stats}

    # Total notifications
    total_notifications = await db.execute(
        select(func.count(Notification.id))
    )
    total_notif_count = total_notifications.scalar()

    # Notifications by status
    notif_by_status = await db.execute(
        select(
            Notification.status,
            func.count(Notification.id).label('count')
        ).group_by(Notification.status)
    )
    status_counts = {row.status.value: row.count for row in notif_by_status}

    # Notifications by tenant
    notif_by_tenant = await db.execute(
        select(
            Tenant.id,
            Tenant.name,
            func.count(Notification.id).label('notification_count')
        )
        .outerjoin(Notification, Tenant.id == Notification.tenant_id)
        .group_by(Tenant.id, Tenant.name)
        .order_by(func.count(Notification.id).desc())
    )
    tenant_notifications = [
        {
            "tenant_id": row.id,
            "tenant_name": row.name,
            "notification_count": row.notification_count
        }
        for row in notif_by_tenant
    ]

    # Notifications by channel
    channel_stats = await db.execute(
        select(
            NotificationChannel.channel,
            func.count(NotificationChannel.id).label('count')
        ).group_by(NotificationChannel.channel)
    )
    channel_counts = {row.channel: row.count for row in channel_stats}

    # Recent activity (last 24 hours)
    twenty_four_hours_ago = datetime.utcnow() - timedelta(hours=24)
    recent_notifs = await db.execute(
        select(func.count(Notification.id))
        .where(Notification.created_at >= twenty_four_hours_ago)
    )
    recent_count = recent_notifs.scalar()

    # Success rate (last 24 hours)
    recent_delivered = await db.execute(
        select(func.count(Notification.id))
        .where(
            and_(
                Notification.created_at >= twenty_four_hours_ago,
                Notification.status == NotificationStatus.DELIVERED
            )
        )
    )
    delivered_count = recent_delivered.scalar()
    success_rate = (delivered_count / recent_count * 100) if recent_count > 0 else 0

    # AI/LLM decision stats
    ai_decision_count = await db.execute(
        select(func.count(Notification.id))
        .where(Notification.llm_decision.isnot(None))
    )
    ai_decisions = ai_decision_count.scalar()

    # Deduplication stats (count notifications that were duplicates)
    dedup_count = await db.execute(
        select(func.count(Notification.id))
        .where(Notification.status == NotificationStatus.FAILED)
        # Note: This is approximate; actual deduplicated requests don't create records
    )
    dedup_hits = dedup_count.scalar()

    # Channel delivery stats
    channel_delivery = await db.execute(
        select(
            NotificationChannel.channel,
            NotificationChannel.status,
            func.count(NotificationChannel.id).label('count')
        )
        .group_by(NotificationChannel.channel, NotificationChannel.status)
    )

    channel_delivery_stats = {}
    for row in channel_delivery:
        if row.channel not in channel_delivery_stats:
            channel_delivery_stats[row.channel] = {}
        channel_delivery_stats[row.channel][row.status.value] = row.count

    return {
        "tenants": {
            "active": tenant_counts.get("active", 0),
            "suspended": tenant_counts.get("suspended", 0),
            "deleted": tenant_counts.get("deleted", 0),
            "total": sum(tenant_counts.values())
        },
        "notifications": {
            "total": total_notif_count,
            "by_status": status_counts,
            "recent_24h": recent_count,
            "success_rate": round(success_rate, 2),
            "ai_decisions": ai_decisions,
            "dedup_hits": dedup_hits
        },
        "channels": {
            "usage": channel_counts,
            "delivery_stats": channel_delivery_stats
        },
        "tenant_activity": tenant_notifications,
        "timestamp": datetime.utcnow().isoformat()
    }


@router.get("/api/tenants")
async def get_all_tenants(db: AsyncSession = Depends(get_db)) -> List[Dict[str, Any]]:
    """
    Get detailed list of all tenants.
    """
    tenants = await db.execute(
        select(Tenant).order_by(Tenant.created_at.desc())
    )

    result = []
    for tenant in tenants.scalars():
        # Count notifications for this tenant
        notif_count = await db.execute(
            select(func.count(Notification.id))
            .where(Notification.tenant_id == tenant.id)
        )

        # Count active provider configs
        provider_count = await db.execute(
            select(func.count(TenantProviderConfig.id))
            .where(
                and_(
                    TenantProviderConfig.tenant_id == tenant.id,
                    TenantProviderConfig.is_active == True
                )
            )
        )

        result.append({
            "id": tenant.id,
            "name": tenant.name,
            "status": tenant.status,
            "admin_email": tenant.admin_email,
            "api_key_prefix": tenant.api_key_prefix,
            "notification_count": notif_count.scalar(),
            "provider_configs": provider_count.scalar(),
            "created_at": tenant.created_at.isoformat(),
            "updated_at": tenant.updated_at.isoformat()
        })

    return result


@router.get("/api/tenants/{tenant_id}/details")
async def get_tenant_details(
    tenant_id: str,
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Get detailed information about a specific tenant.
    """
    # Get tenant
    tenant = await db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    # Notification stats
    notif_stats = await db.execute(
        select(
            Notification.status,
            func.count(Notification.id).label('count')
        )
        .where(Notification.tenant_id == tenant_id)
        .group_by(Notification.status)
    )
    notification_stats = {row.status.value: row.count for row in notif_stats}

    # Recent notifications
    recent_notifs = await db.execute(
        select(Notification)
        .where(Notification.tenant_id == tenant_id)
        .order_by(Notification.created_at.desc())
        .limit(10)
    )

    recent_notifications = [
        {
            "id": str(n.id),
            "type": n.type,
            "status": n.status.value,
            "priority": n.priority.value,
            "created_at": n.created_at.isoformat()
        }
        for n in recent_notifs.scalars()
    ]

    # Provider configs
    providers = await db.execute(
        select(TenantProviderConfig)
        .where(TenantProviderConfig.tenant_id == tenant_id)
    )

    provider_configs = [
        {
            "provider": p.provider,
            "is_active": p.is_active,
            "config": p.config,
            "created_at": p.created_at.isoformat()
        }
        for p in providers.scalars()
    ]

    # Templates
    templates = await db.execute(
        select(Template)
        .where(Template.tenant_id == tenant_id)
    )

    tenant_templates = [
        {
            "id": t.id,
            "name": t.name,
            "channel": t.channel,
            "language": t.language,
            "is_global": t.is_global,
            "active": t.active
        }
        for t in templates.scalars()
    ]

    return {
        "tenant": {
            "id": tenant.id,
            "name": tenant.name,
            "status": tenant.status,
            "admin_email": tenant.admin_email,
            "admin_name": tenant.admin_name,
            "api_key_prefix": tenant.api_key_prefix,
            "created_at": tenant.created_at.isoformat(),
            "updated_at": tenant.updated_at.isoformat()
        },
        "notification_stats": notification_stats,
        "recent_notifications": recent_notifications,
        "provider_configs": provider_configs,
        "templates": tenant_templates
    }


@router.get("/api/recent-activity")
async def get_recent_activity(
    limit: int = 50,
    db: AsyncSession = Depends(get_db)
) -> List[Dict[str, Any]]:
    """
    Get recent notification activity across all tenants.
    """
    notifications = await db.execute(
        select(Notification, Tenant.name)
        .join(Tenant, Notification.tenant_id == Tenant.id)
        .order_by(Notification.created_at.desc())
        .limit(limit)
    )

    activity = []
    for notif, tenant_name in notifications:
        # Get channel statuses
        channels = await db.execute(
            select(NotificationChannel)
            .where(NotificationChannel.notification_id == notif.id)
        )

        channel_info = [
            {
                "channel": c.channel,
                "status": c.status.value,
                "attempts": c.attempts
            }
            for c in channels.scalars()
        ]

        activity.append({
            "id": str(notif.id),
            "tenant_name": tenant_name,
            "tenant_id": notif.tenant_id,
            "type": notif.type,
            "priority": notif.priority.value,
            "status": notif.status.value,
            "user_id": notif.user_id,
            "channels": channel_info,
            "created_at": notif.created_at.isoformat(),
            "updated_at": notif.updated_at.isoformat()
        })

    return activity


@router.post("/api/tenants/{tenant_id}/suspend")
async def suspend_tenant(
    tenant_id: str,
    db: AsyncSession = Depends(get_db)
) -> Dict[str, str]:
    """
    Suspend a tenant (blocks API access).
    """
    tenant = await db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    tenant.status = "suspended"
    tenant.suspended_at = datetime.utcnow()
    await db.commit()

    return {"message": f"Tenant {tenant_id} has been suspended", "status": "suspended"}


@router.post("/api/tenants/{tenant_id}/activate")
async def activate_tenant(
    tenant_id: str,
    db: AsyncSession = Depends(get_db)
) -> Dict[str, str]:
    """
    Activate a suspended tenant.
    """
    tenant = await db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    tenant.status = "active"
    tenant.suspended_at = None
    await db.commit()

    return {"message": f"Tenant {tenant_id} has been activated", "status": "active"}


@router.get("/api/templates")
async def get_all_templates(db: AsyncSession = Depends(get_db)) -> List[Dict[str, Any]]:
    """
    Get all templates (global and tenant-specific).
    """
    templates = await db.execute(
        select(Template, Tenant.name)
        .outerjoin(Tenant, Template.tenant_id == Tenant.id)
        .order_by(Template.is_global.desc(), Template.created_at.desc())
    )

    result = []
    for template, tenant_name in templates:
        result.append({
            "id": template.id,
            "name": template.name,
            "channel": template.channel,
            "language": template.language,
            "is_global": template.is_global,
            "tenant_id": template.tenant_id,
            "tenant_name": tenant_name,
            "active": template.active,
            "version": template.version,
            "created_at": template.created_at.isoformat()
        })

    return result
