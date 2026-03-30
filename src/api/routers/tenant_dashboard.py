"""
Multi-tenant dashboard API showing per-tenant, per-channel statistics.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text
from typing import Dict, List, Any
from datetime import datetime, timedelta

from src.core import get_db
from src.models import Notification, NotificationChannel, Tenant, ChannelStatus

router = APIRouter(tags=["tenant-dashboard"])

# Templates
templates = Jinja2Templates(directory="src/templates")


@router.get("/tenant-dashboard", response_class=HTMLResponse)
async def tenant_dashboard_page(request: Request):
    """Render the multi-tenant dashboard page."""
    return templates.TemplateResponse("tenant_dashboard.html", {"request": request})


@router.get("/api/tenant-dashboard/stats")
async def get_tenant_dashboard_stats(
    days: int = 30,
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Get comprehensive multi-tenant statistics.

    Returns per-tenant, per-channel breakdown with success/failure rates.
    """
    since_date = datetime.utcnow() - timedelta(days=days)

    # Get tenant list with basic info
    tenants_query = select(Tenant).where(
        Tenant.status == "active",
        Tenant.deleted_at.is_(None)
    ).order_by(Tenant.name)

    tenants_result = await db.execute(tenants_query)
    tenants = tenants_result.scalars().all()

    tenant_stats = []

    for tenant in tenants:
        # Get channel statistics for this tenant
        channel_stats_query = text("""
            SELECT
                nc.channel,
                nc.status,
                COUNT(*) as count
            FROM notification_channels nc
            JOIN notifications n ON nc.notification_id = n.id
            WHERE n.tenant_id = :tenant_id
                AND n.created_at >= :since_date
            GROUP BY nc.channel, nc.status
            ORDER BY nc.channel
        """)

        result = await db.execute(
            channel_stats_query,
            {"tenant_id": tenant.id, "since_date": since_date}
        )
        channel_data = result.fetchall()

        # Organize by channel
        channels_breakdown = {}
        total_sent = 0
        total_failed = 0
        total_delivered = 0
        total_queued = 0

        for row in channel_data:
            channel = row.channel
            status = row.status
            count = row.count

            if channel not in channels_breakdown:
                channels_breakdown[channel] = {
                    "channel": channel,
                    "queued": 0,
                    "sent": 0,
                    "delivered": 0,
                    "failed": 0,
                    "total": 0,
                    "success_rate": 0
                }

            channels_breakdown[channel][status.lower()] = count
            channels_breakdown[channel]["total"] += count

            # Aggregate totals
            if status == "SENT":
                total_sent += count
            elif status == "DELIVERED":
                total_delivered += count
            elif status == "FAILED":
                total_failed += count
            elif status == "QUEUED":
                total_queued += count

        # Calculate success rates
        for channel, stats in channels_breakdown.items():
            successful = stats["sent"] + stats["delivered"]
            total = stats["total"]
            stats["success_rate"] = round((successful / total * 100) if total > 0 else 0, 1)

        # Get total notifications for tenant
        total_notifications = await db.execute(
            select(func.count(Notification.id)).where(
                Notification.tenant_id == tenant.id,
                Notification.created_at >= since_date
            )
        )
        total_notif_count = total_notifications.scalar() or 0

        # Overall success rate
        total_successful = total_sent + total_delivered
        total_attempts = total_sent + total_delivered + total_failed
        overall_success_rate = round(
            (total_successful / total_attempts * 100) if total_attempts > 0 else 0,
            1
        )

        # Get tier from config
        config = tenant.config or {}
        tier = config.get("tier", "free")

        tenant_stats.append({
            "tenant_id": tenant.id,
            "tenant_name": tenant.name,
            "tier": tier,
            "status": tenant.status,
            "total_notifications": total_notif_count,
            "total_channels": len(channels_breakdown),
            "channels": list(channels_breakdown.values()),
            "summary": {
                "queued": total_queued,
                "sent": total_sent,
                "delivered": total_delivered,
                "failed": total_failed,
                "total": total_queued + total_sent + total_delivered + total_failed,
                "success_rate": overall_success_rate
            },
            "created_at": tenant.created_at.isoformat() if tenant.created_at else None
        })

    # Get recent activity across all tenants
    recent_activity_query = text("""
        SELECT
            n.tenant_id,
            t.name as tenant_name,
            n.type,
            nc.channel,
            nc.status,
            n.created_at,
            nc.delivered_at,
            nc.error_message
        FROM notification_channels nc
        JOIN notifications n ON nc.notification_id = n.id
        JOIN tenants t ON n.tenant_id = t.id
        WHERE n.created_at >= :since_date
        ORDER BY n.created_at DESC
        LIMIT 50
    """)

    activity_result = await db.execute(
        recent_activity_query,
        {"since_date": since_date}
    )
    activity_data = activity_result.fetchall()

    recent_activity = [
        {
            "tenant_id": row.tenant_id,
            "tenant_name": row.tenant_name,
            "type": row.type,
            "channel": row.channel,
            "status": row.status,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "delivered_at": row.delivered_at.isoformat() if row.delivered_at else None,
            "error": row.error_message[:100] if row.error_message else None
        }
        for row in activity_data
    ]

    # Overall platform statistics
    platform_stats_query = text("""
        SELECT
            COUNT(DISTINCT n.tenant_id) as active_tenants,
            COUNT(DISTINCT n.id) as total_notifications,
            COUNT(nc.id) as total_channels,
            SUM(CASE WHEN nc.status = 'SENT' OR nc.status = 'DELIVERED' THEN 1 ELSE 0 END) as successful,
            SUM(CASE WHEN nc.status = 'FAILED' THEN 1 ELSE 0 END) as failed,
            SUM(CASE WHEN nc.status = 'QUEUED' THEN 1 ELSE 0 END) as queued
        FROM notifications n
        JOIN notification_channels nc ON nc.notification_id = n.id
        WHERE n.created_at >= :since_date
    """)

    platform_result = await db.execute(
        platform_stats_query,
        {"since_date": since_date}
    )
    platform_row = platform_result.fetchone()

    platform_total = (platform_row.successful or 0) + (platform_row.failed or 0)
    platform_success_rate = round(
        ((platform_row.successful or 0) / platform_total * 100) if platform_total > 0 else 0,
        1
    )

    return {
        "period_days": days,
        "generated_at": datetime.utcnow().isoformat(),
        "platform_summary": {
            "active_tenants": platform_row.active_tenants or 0,
            "total_notifications": platform_row.total_notifications or 0,
            "total_channels": platform_row.total_channels or 0,
            "successful": platform_row.successful or 0,
            "failed": platform_row.failed or 0,
            "queued": platform_row.queued or 0,
            "success_rate": platform_success_rate
        },
        "tenants": tenant_stats,
        "recent_activity": recent_activity
    }


@router.get("/tenant-detail/{tenant_id}", response_class=HTMLResponse)
async def tenant_detail_page(request: Request, tenant_id: str):
    """Render the tenant detail page with channel tabs."""
    return templates.TemplateResponse(
        "tenant_detail.html",
        {"request": request, "tenant_id": tenant_id}
    )


@router.get("/tenant-detail-enhanced/{tenant_id}", response_class=HTMLResponse)
async def tenant_detail_enhanced_page(request: Request, tenant_id: str):
    """Render the enhanced tenant detail page with AI features."""
    return templates.TemplateResponse(
        "tenant_detail_enhanced.html",
        {"request": request, "tenant_id": tenant_id}
    )


@router.get("/api/tenant-dashboard/tenant/{tenant_id}/overview")
async def get_tenant_overview(
    tenant_id: str,
    days: int = 30,
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """Get tenant overview with all channels summary."""
    since_date = datetime.utcnow() - timedelta(days=days)

    # Get tenant info
    tenant = await db.execute(
        select(Tenant).where(Tenant.id == tenant_id)
    )
    tenant_obj = tenant.scalar_one_or_none()

    if not tenant_obj:
        return {"error": "Tenant not found"}

    # Get channel statistics
    channel_stats_query = text("""
        SELECT
            nc.channel,
            nc.status,
            COUNT(*) as count,
            MIN(n.created_at) as first_sent,
            MAX(n.created_at) as last_sent
        FROM notification_channels nc
        JOIN notifications n ON nc.notification_id = n.id
        WHERE n.tenant_id = :tenant_id
            AND n.created_at >= :since_date
        GROUP BY nc.channel, nc.status
        ORDER BY nc.channel
    """)

    result = await db.execute(
        channel_stats_query,
        {"tenant_id": tenant_id, "since_date": since_date}
    )
    channel_data = result.fetchall()

    # Organize by channel
    channels = {}
    for row in channel_data:
        if row.channel not in channels:
            channels[row.channel] = {
                "channel": row.channel,
                "queued": 0,
                "sent": 0,
                "delivered": 0,
                "failed": 0,
                "total": 0,
                "success_rate": 0,
                "first_sent": None,
                "last_sent": None
            }

        channels[row.channel][row.status.lower()] = row.count
        channels[row.channel]["total"] += row.count

        # Update timestamps - keep as datetime for comparison
        if row.first_sent:
            if channels[row.channel]["first_sent"] is None or row.first_sent < channels[row.channel]["first_sent"]:
                channels[row.channel]["first_sent"] = row.first_sent

        if row.last_sent:
            if channels[row.channel]["last_sent"] is None or row.last_sent > channels[row.channel]["last_sent"]:
                channels[row.channel]["last_sent"] = row.last_sent

    # Calculate success rates and convert datetime to ISO strings
    for channel_name, stats in channels.items():
        successful = stats["sent"] + stats["delivered"]
        total = stats["total"]
        stats["success_rate"] = round((successful / total * 100) if total > 0 else 0, 1)

        # Convert datetime objects to ISO strings
        if stats["first_sent"]:
            stats["first_sent"] = stats["first_sent"].isoformat()
        if stats["last_sent"]:
            stats["last_sent"] = stats["last_sent"].isoformat()

    config = tenant_obj.config or {}

    return {
        "tenant_id": tenant_id,
        "tenant_name": tenant_obj.name,
        "tier": config.get("tier", "free"),
        "status": tenant_obj.status,
        "created_at": tenant_obj.created_at.isoformat() if tenant_obj.created_at else None,
        "channels": list(channels.values()),
        "period_days": days
    }


@router.get("/api/tenant-dashboard/tenant/{tenant_id}/channel/{channel_name}")
async def get_tenant_channel_data(
    tenant_id: str,
    channel_name: str,
    days: int = 30,
    limit: int = 50,
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """Get detailed data for a specific channel of a tenant."""
    since_date = datetime.utcnow() - timedelta(days=days)

    # Get notifications for this channel
    notifications_query = text("""
        SELECT
            n.id,
            n.type,
            n.priority,
            n.user_id,
            nc.status,
            nc.message_id,
            nc.attempts,
            nc.error_message,
            nc.delivered_at,
            nc.opened_at,
            nc.clicked_at,
            n.created_at,
            n.data,
            n.llm_decision
        FROM notifications n
        JOIN notification_channels nc ON nc.notification_id = n.id
        WHERE n.tenant_id = :tenant_id
            AND nc.channel = :channel_name
            AND n.created_at >= :since_date
        ORDER BY n.created_at DESC
        LIMIT :limit
    """)

    result = await db.execute(
        notifications_query,
        {
            "tenant_id": tenant_id,
            "channel_name": channel_name,
            "since_date": since_date,
            "limit": limit
        }
    )
    rows = result.fetchall()

    notifications = []
    for row in rows:
        data = row.data or {}
        llm_decision = row.llm_decision or {}
        notifications.append({
            "id": str(row.id),
            "type": row.type,
            "priority": row.priority,
            "user_id": row.user_id,
            "status": row.status,
            "message_id": row.message_id,
            "attempts": row.attempts,
            "error_message": row.error_message,
            "recipient": data.get("email") or data.get("phone") or data.get("slack_id") or "N/A",
            "subject": data.get("subject", ""),
            "delivered_at": row.delivered_at.isoformat() if row.delivered_at else None,
            "opened_at": row.opened_at.isoformat() if row.opened_at else None,
            "clicked_at": row.clicked_at.isoformat() if row.clicked_at else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "llm_decision": llm_decision
        })

    # Get statistics for this channel
    stats_query = text("""
        SELECT
            nc.status,
            COUNT(*) as count
        FROM notification_channels nc
        JOIN notifications n ON nc.notification_id = n.id
        WHERE n.tenant_id = :tenant_id
            AND nc.channel = :channel_name
            AND n.created_at >= :since_date
        GROUP BY nc.status
    """)

    stats_result = await db.execute(
        stats_query,
        {"tenant_id": tenant_id, "channel_name": channel_name, "since_date": since_date}
    )
    stats_rows = stats_result.fetchall()

    stats = {
        "queued": 0,
        "sent": 0,
        "delivered": 0,
        "failed": 0,
        "total": 0
    }

    for row in stats_rows:
        stats[row.status.lower()] = row.count
        stats["total"] += row.count

    successful = stats["sent"] + stats["delivered"]
    stats["success_rate"] = round((successful / stats["total"] * 100) if stats["total"] > 0 else 0, 1)

    return {
        "tenant_id": tenant_id,
        "channel": channel_name,
        "statistics": stats,
        "notifications": notifications,
        "period_days": days
    }


@router.get("/api/tenant-dashboard/tenant/{tenant_id}/recent-notifications")
async def get_tenant_recent_notifications(
    tenant_id: str,
    limit: int = 20,
    db: AsyncSession = Depends(get_db)
) -> List[Dict[str, Any]]:
    """Get recent notifications for tenant with LLM decisions."""
    notifications_query = text("""
        SELECT
            n.id,
            n.type,
            n.priority,
            n.user_id,
            n.status,
            n.llm_decision,
            n.created_at,
            n.data,
            ARRAY_AGG(DISTINCT nc.channel) as channels,
            ARRAY_AGG(DISTINCT nc.status) as channel_statuses
        FROM notifications n
        LEFT JOIN notification_channels nc ON nc.notification_id = n.id
        WHERE n.tenant_id = :tenant_id
        GROUP BY n.id, n.type, n.priority, n.user_id, n.status, n.llm_decision, n.created_at, n.data
        ORDER BY n.created_at DESC
        LIMIT :limit
    """)

    result = await db.execute(
        notifications_query,
        {"tenant_id": tenant_id, "limit": limit}
    )
    rows = result.fetchall()

    notifications = []
    for row in rows:
        data = row.data or {}
        notifications.append({
            "id": str(row.id),
            "type": row.type,
            "priority": row.priority,
            "user_id": row.user_id,
            "status": row.status,
            "subject": data.get("subject", "N/A"),
            "body": data.get("body", "")[:100] + "..." if data.get("body", "") else "",
            "channels": row.channels or [],
            "channel_statuses": row.channel_statuses or [],
            "llm_decision": row.llm_decision,
            "created_at": row.created_at.isoformat() if row.created_at else None
        })

    return notifications


@router.get("/api/tenant-dashboard/tenant/{tenant_id}/provider-health")
async def get_tenant_provider_health(
    tenant_id: str,
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """Get provider health statistics for a tenant."""
    from src.services.provider_manager import ProviderManager

    provider_mgr = ProviderManager(db)

    # Get provider stats
    all_stats = await provider_mgr.get_provider_stats()

    # Get provider health summary
    health_summary = await provider_mgr.get_provider_health_summary()

    return {
        "tenant_id": tenant_id,
        "provider_stats": all_stats,
        "health_summary": health_summary,
        "timestamp": datetime.utcnow().isoformat()
    }


@router.get("/api/tenant-dashboard/tenant/{tenant_id}/deduplication-stats")
async def get_tenant_deduplication_stats(
    tenant_id: str,
    days: int = 30,
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """Get deduplication statistics for a tenant."""
    since_date = datetime.utcnow() - timedelta(days=days)

    # Count notifications with idempotency keys
    idempotency_query = text("""
        SELECT
            COUNT(*) as total_with_idempotency,
            COUNT(DISTINCT idempotency_key) as unique_idempotency_keys
        FROM notifications
        WHERE tenant_id = :tenant_id
            AND idempotency_key IS NOT NULL
            AND created_at >= :since_date
    """)

    result = await db.execute(
        idempotency_query,
        {"tenant_id": tenant_id, "since_date": since_date}
    )
    row = result.fetchone()

    # Count total notifications
    total_query = text("""
        SELECT COUNT(*) as total
        FROM notifications
        WHERE tenant_id = :tenant_id
            AND created_at >= :since_date
    """)

    total_result = await db.execute(
        total_query,
        {"tenant_id": tenant_id, "since_date": since_date}
    )
    total_row = total_result.fetchone()

    total_notifications = total_row.total if total_row else 0
    total_with_idempotency = row.total_with_idempotency if row else 0
    unique_keys = row.unique_idempotency_keys if row else 0

    # Calculate potential duplicates prevented (rough estimate)
    potential_duplicates = total_with_idempotency - unique_keys

    return {
        "tenant_id": tenant_id,
        "period_days": days,
        "total_notifications": total_notifications,
        "total_with_idempotency": total_with_idempotency,
        "unique_idempotency_keys": unique_keys,
        "potential_duplicates_prevented": max(0, potential_duplicates),
        "deduplication_percentage": round(
            (potential_duplicates / total_with_idempotency * 100) if total_with_idempotency > 0 else 0,
            1
        ),
        "timestamp": datetime.utcnow().isoformat()
    }


@router.get("/api/tenant-dashboard/tenant/{tenant_id}/llm-decisions")
async def get_tenant_llm_decisions(
    tenant_id: str,
    limit: int = 50,
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """Get LLM routing decisions for a tenant."""
    decisions_query = text("""
        SELECT
            n.id,
            n.type,
            n.priority,
            n.llm_decision,
            n.created_at,
            ARRAY_AGG(DISTINCT nc.channel) as channels_used,
            ARRAY_AGG(DISTINCT nc.status) as channel_statuses
        FROM notifications n
        LEFT JOIN notification_channels nc ON nc.notification_id = n.id
        WHERE n.tenant_id = :tenant_id
            AND n.llm_decision IS NOT NULL
        GROUP BY n.id, n.type, n.priority, n.llm_decision, n.created_at
        ORDER BY n.created_at DESC
        LIMIT :limit
    """)

    result = await db.execute(
        decisions_query,
        {"tenant_id": tenant_id, "limit": limit}
    )
    rows = result.fetchall()

    decisions = []
    for row in rows:
        llm_decision = row.llm_decision or {}
        decisions.append({
            "id": str(row.id),
            "type": row.type,
            "priority": row.priority,
            "llm_channel": llm_decision.get('channel'),
            "llm_timing": llm_decision.get('timing'),
            "retry_strategy": llm_decision.get('retry_strategy'),
            "reasoning": llm_decision.get('reasoning'),
            "channels_used": row.channels_used or [],
            "channel_statuses": row.channel_statuses or [],
            "created_at": row.created_at.isoformat() if row.created_at else None
        })

    # Calculate statistics
    total_decisions = len(decisions)
    channel_distribution = {}
    timing_distribution = {}

    for dec in decisions:
        channel = dec['llm_channel']
        timing = dec['llm_timing']

        if channel:
            channel_distribution[channel] = channel_distribution.get(channel, 0) + 1
        if timing:
            timing_distribution[timing] = timing_distribution.get(timing, 0) + 1

    return {
        "tenant_id": tenant_id,
        "total_llm_decisions": total_decisions,
        "channel_distribution": channel_distribution,
        "timing_distribution": timing_distribution,
        "decisions": decisions,
        "timestamp": datetime.utcnow().isoformat()
    }
