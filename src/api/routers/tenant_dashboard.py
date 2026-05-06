"""
Multi-tenant dashboard API showing per-tenant, per-channel statistics.
"""

from fastapi import APIRouter, Depends, Request, HTTPException, status, Header
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta

from src.core import get_db
from src.core.security import verify_token
from src.api.dependencies import get_authenticated_tenant, require_admin_access
from src.models import Notification, NotificationChannel, Tenant, TenantUser, ChannelStatus
from src.utils.logger import setup_logger

logger = setup_logger(__name__)

router = APIRouter(tags=["tenant-dashboard"])

# Templates
templates = Jinja2Templates(directory="src/templates")


async def require_tenant_path_access(
    tenant_id: str,
    tenant: Tenant = Depends(get_authenticated_tenant)
) -> Tenant:
    """Ensure authenticated tenant can only access their own tenant_id path."""
    if tenant.id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied for requested tenant"
        )
    return tenant


async def require_tenant_or_admin_path_access(
    request: Request,
    tenant_id: str,
    x_admin_key: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db)
) -> Tenant:
    """
    Allow access to tenant dashboard APIs for:
    - Admin users (any tenant_id)
    - Authenticated tenant users (only their own tenant_id)
    """
    is_admin = False
    try:
        await require_admin_access(request, x_admin_key=x_admin_key, authorization=authorization)
        is_admin = True
    except HTTPException as admin_error:
        if admin_error.status_code != status.HTTP_401_UNAUTHORIZED:
            raise

    if is_admin:
        tenant_obj = await db.get(Tenant, tenant_id)
        if not tenant_obj:
            raise HTTPException(status_code=404, detail="Tenant not found")
        # Mark as admin for internal routing logic if needed
        tenant_obj.is_platform_admin = True
        return tenant_obj

    tenant = await get_authenticated_tenant(x_api_key=x_api_key, authorization=authorization, db=db)
    if tenant.id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied for requested tenant"
        )
    return tenant


async def get_optional_authenticated_user(
    request: Request,
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db)
) -> Optional[TenantUser]:
    """Get authenticated user if token is present, else None."""
    if not authorization or not authorization.startswith("Bearer "):
        # Check cookie
        token = request.cookies.get("tenant_access_token")
    else:
        token = authorization.replace("Bearer ", "")

    if not token:
        return None

    payload = verify_token(token)
    if not payload:
        return None

    user_id = payload.get("user_id")
    tenant_id = payload.get("tenant_id")
    if not user_id or not tenant_id:
        return None

    user_query = select(TenantUser).where(
        TenantUser.id == user_id,
        TenantUser.tenant_id == tenant_id,
        TenantUser.is_active == True
    )
    result = await db.execute(user_query)
    return result.scalar_one_or_none()


@router.get("/tenant-dashboard", response_class=HTMLResponse)
async def tenant_dashboard_page(
    request: Request,
    _: bool = Depends(require_admin_access)
):
    """Render the multi-tenant dashboard page."""
    return templates.TemplateResponse("tenant_dashboard.html", {"request": request})


@router.get("/api/tenant-dashboard/stats")
async def get_tenant_dashboard_stats(
    days: int = 30,
    _: bool = Depends(require_admin_access),
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
            "status": str(row.status),
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
async def tenant_detail_page(
    request: Request,
    tenant_id: str,
    _: bool = Depends(require_admin_access)
):
    """Render the unified tenant detail page (includes AI insights)."""
    return templates.TemplateResponse(
        "tenant_detail_enhanced.html",
        {"request": request, "tenant_id": tenant_id}
    )


@router.get("/tenant-detail-enhanced/{tenant_id}", response_class=HTMLResponse)
async def tenant_detail_enhanced_page(
    request: Request,
    tenant_id: str,
    _: bool = Depends(require_admin_access)
):
    """Legacy route redirected to unified tenant detail page."""
    return RedirectResponse(url=f"/tenant-detail/{tenant_id}", status_code=303)


@router.get("/api/tenant-dashboard/tenant/{tenant_id}/overview")
async def get_tenant_overview(
    tenant_id: str,
    days: int = 30,
    tenant: Tenant = Depends(require_tenant_or_admin_path_access),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """Get tenant overview with all channels summary."""
    since_date = datetime.utcnow() - timedelta(days=days)

    # If it's a marketing user, filter by their own ID
    owner_id_filter = None
    if hasattr(tenant, "current_user_role") and tenant.current_user_role == "marketing":
        owner_id_filter = tenant.current_user_id

    # Get tenant info
    tenant_obj = await db.get(Tenant, tenant_id)
    if not tenant_obj:
        raise HTTPException(status_code=404, detail="Tenant not found")

    # Get channel statistics
    query_params = {"tenant_id": tenant_id, "since_date": since_date}
    owner_clause = ""
    if owner_id_filter:
        owner_clause = "AND n.owner_id = :owner_id"
        query_params["owner_id"] = owner_id_filter

    channel_stats_query = text(f"""
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
            {owner_clause}
        GROUP BY nc.channel, nc.status
        ORDER BY nc.channel
    """)

    result = await db.execute(channel_stats_query, query_params)
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

        status_key = str(row.status).lower()
        if status_key in channels[row.channel]:
            channels[row.channel][status_key] = row.count
        else:
            # Fallback for unexpected status names
            channels[row.channel][status_key] = row.count
            
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
    tenant: Tenant = Depends(require_tenant_or_admin_path_access),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """Get detailed data for a specific channel of a tenant."""
    since_date = datetime.utcnow() - timedelta(days=days)

    # If it's a marketing user, filter by their own ID
    owner_id_filter = None
    if hasattr(tenant, "current_user_role") and tenant.current_user_role == "marketing":
        owner_id_filter = tenant.current_user_id

    query_params = {
        "tenant_id": tenant_id,
        "channel_name": channel_name,
        "since_date": since_date,
        "limit": limit
    }
    owner_clause = ""
    if owner_id_filter:
        owner_clause = "AND n.owner_id = :owner_id"
        query_params["owner_id"] = owner_id_filter

    # Get notifications for this channel
    notifications_query = text(f"""
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
            {owner_clause}
        ORDER BY n.created_at DESC
        LIMIT :limit
    """)

    result = await db.execute(notifications_query, query_params)
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
    stats_query = text(f"""
        SELECT
            nc.status,
            COUNT(*) as count
        FROM notification_channels nc
        JOIN notifications n ON nc.notification_id = n.id
        WHERE n.tenant_id = :tenant_id
            AND nc.channel = :channel_name
            AND n.created_at >= :since_date
            {owner_clause}
        GROUP BY nc.status
    """)

    stats_result = await db.execute(stats_query, query_params)
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
    tenant: Tenant = Depends(require_tenant_or_admin_path_access),
    db: AsyncSession = Depends(get_db)
) -> List[Dict[str, Any]]:
    """Get recent notifications for tenant with LLM decisions."""
    # If it's a marketing user, filter by their own ID
    owner_id_filter = None
    if hasattr(tenant, "current_user_role") and tenant.current_user_role == "marketing":
        owner_id_filter = tenant.current_user_id

    query_params = {"tenant_id": tenant_id, "limit": limit}
    owner_clause = ""
    if owner_id_filter:
        owner_clause = "AND n.owner_id = :owner_id"
        query_params["owner_id"] = owner_id_filter

    notifications_query = text(f"""
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
            {owner_clause}
        GROUP BY n.id, n.type, n.priority, n.user_id, n.status, n.llm_decision, n.created_at, n.data
        ORDER BY n.created_at DESC
        LIMIT :limit
    """)

    result = await db.execute(notifications_query, query_params)
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


@router.get("/api/tenant-dashboard/tenant/{tenant_id}/delivery-activity")
async def get_tenant_delivery_activity(
    tenant_id: str,
    limit: int = 50,
    tenant: Tenant = Depends(require_tenant_or_admin_path_access),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """Get tenant delivery-first activity feed (channel-level)."""
    try:
        # If it's a marketing user, filter by their own ID
        owner_id_filter = None
        if hasattr(tenant, "current_user_role") and tenant.current_user_role == "marketing":
            owner_id_filter = getattr(tenant, "current_user_id", None)

        query_params = {"tenant_id": tenant_id, "limit": limit}
        owner_clause = ""
        if owner_id_filter:
            owner_clause = "AND n.owner_id = :owner_id"
            query_params["owner_id"] = owner_id_filter

        activity_query = text(f"""
            SELECT
                n.id AS notification_id,
                n.type,
                n.priority,
                n.template_id,
                n.data,
                n.created_at,
                nc.channel,
                nc.provider,
                nc.status,
                nc.attempts,
                nc.message_id,
                nc.error_message
            FROM notification_channels nc
            JOIN notifications n ON nc.notification_id = n.id
            WHERE n.tenant_id = :tenant_id
                {owner_clause}
            ORDER BY n.created_at DESC, nc.id DESC
            LIMIT :limit
        """)

        result = await db.execute(activity_query, query_params)
        rows = result.fetchall()

        records: List[Dict[str, Any]] = []
        for row in rows:
            try:
                payload = row.data or {}
                channel = row.channel
                recipient = (
                    payload.get("email") if channel == "email" else
                    payload.get("phone") if channel in {"sms", "whatsapp", "voice"} else
                    payload.get("slack_id") if channel == "slack" else
                    (payload.get("device_tokens") or [None])[0] if channel == "voice" else
                    payload.get("email") or payload.get("phone") or payload.get("slack_id")
                )
                body_text = payload.get("body") or ""

                records.append({
                    "notification_id": str(row.notification_id),
                    "type": row.type,
                    "priority": str(row.priority), # Cast Enum to string
                    "channel": channel,
                    "provider": row.provider,
                    "recipient": recipient or "N/A",
                    "message_preview": (body_text[:120] + "...") if len(body_text) > 120 else body_text,
                    "template_mode": "template" if (row.template_id or payload.get("template_id")) else "raw",
                    "template_id": row.template_id or payload.get("template_id"),
                    "status": str(row.status), # Cast Enum to string
                    "attempts": row.attempts or 0,
                    "message_id": row.message_id,
                    "error_message": row.error_message,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                })
            except Exception as row_err:
                logger.error(f"Error processing delivery row: {row_err}")
                continue

        return {
            "tenant_id": tenant_id,
            "count": len(records),
            "records": records,
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        logger.error(f"Failed to get delivery activity: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/tenant-dashboard/tenant/{tenant_id}/provider-health")
async def get_tenant_provider_health(
    tenant_id: str,
    tenant: Tenant = Depends(require_tenant_or_admin_path_access),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """Get tenant-scoped provider performance statistics."""
    # If it's a marketing user, filter by their own ID
    owner_id_filter = None
    if hasattr(tenant, "current_user_role") and tenant.current_user_role == "marketing":
        owner_id_filter = tenant.current_user_id

    query_params = {"tenant_id": tenant_id}
    owner_clause = ""
    if owner_id_filter:
        owner_clause = "AND n.owner_id = :owner_id"
        query_params["owner_id"] = owner_id_filter

    provider_stats_query = text(f"""
        SELECT
            nc.provider as provider_name,
            nc.channel as channel,
            COUNT(*) as total_sent,
            SUM(CASE WHEN nc.status IN ('SENT', 'DELIVERED') THEN 1 ELSE 0 END) as success_count,
            SUM(CASE WHEN nc.status IN ('FAILED', 'BOUNCED') THEN 1 ELSE 0 END) as failure_count
        FROM notification_channels nc
        JOIN notifications n ON nc.notification_id = n.id
        WHERE n.tenant_id = :tenant_id
            {owner_clause}
        GROUP BY nc.provider, nc.channel
        ORDER BY nc.channel, nc.provider
    """)

    result = await db.execute(provider_stats_query, query_params)
    rows = result.fetchall()

    provider_stats = []
    health_summary = {}

    for row in rows:
        total_sent = row.total_sent or 0
        success_count = row.success_count or 0
        failure_count = row.failure_count or 0
        success_rate = round((success_count / total_sent * 100) if total_sent > 0 else 0.0, 2)

        provider_stats.append({
            "provider": row.provider_name,
            "channel": row.channel,
            "success_count": int(success_count),
            "failure_count": int(failure_count),
            "total_sent": int(total_sent),
            "success_rate": success_rate,
            "is_healthy": success_rate >= 90.0
        })

        if row.channel not in health_summary:
            health_summary[row.channel] = []
        health_summary[row.channel].append({
            "provider": row.provider_name,
            "success_rate": success_rate,
            "is_healthy": success_rate >= 90.0
        })

    return {
        "tenant_id": tenant_id,
        "provider_stats": provider_stats,
        "health_summary": health_summary,
        "timestamp": datetime.utcnow().isoformat()
    }


@router.get("/api/tenant-dashboard/tenant/{tenant_id}/deduplication-stats")
async def get_tenant_deduplication_stats(
    tenant_id: str,
    days: int = 30,
    tenant: Tenant = Depends(require_tenant_or_admin_path_access),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """Get deduplication statistics for a tenant."""
    since_date = datetime.utcnow() - timedelta(days=days)

    # If it's a marketing user, filter by their own ID
    owner_id_filter = None
    if hasattr(tenant, "current_user_role") and tenant.current_user_role == "marketing":
        owner_id_filter = tenant.current_user_id

    query_params = {"tenant_id": tenant_id, "since_date": since_date}
    owner_clause = ""
    if owner_id_filter:
        owner_clause = "AND owner_id = :owner_id"
        query_params["owner_id"] = owner_id_filter

    # Count notifications with idempotency keys
    idempotency_query = text(f"""
        SELECT
            COUNT(*) as total_with_idempotency,
            COUNT(DISTINCT idempotency_key) as unique_idempotency_keys
        FROM notifications
        WHERE tenant_id = :tenant_id
            AND idempotency_key IS NOT NULL
            AND created_at >= :since_date
            {owner_clause}
    """)

    result = await db.execute(idempotency_query, query_params)
    row = result.fetchone()

    # Count total notifications
    total_query = text(f"""
        SELECT COUNT(*) as total
        FROM notifications
        WHERE tenant_id = :tenant_id
            AND created_at >= :since_date
            {owner_clause}
    """)

    total_result = await db.execute(total_query, query_params)
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
    tenant: Tenant = Depends(require_tenant_or_admin_path_access),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """Get LLM routing decisions for a tenant."""
    # If it's a marketing user, filter by their own ID
    owner_id_filter = None
    if hasattr(tenant, "current_user_role") and tenant.current_user_role == "marketing":
        owner_id_filter = tenant.current_user_id

    query_params = {"tenant_id": tenant_id, "limit": limit}
    owner_clause = ""
    if owner_id_filter:
        owner_clause = "AND n.owner_id = :owner_id"
        query_params["owner_id"] = owner_id_filter

    decisions_query = text(f"""
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
            {owner_clause}
        GROUP BY n.id, n.type, n.priority, n.llm_decision, n.created_at
        ORDER BY n.created_at DESC
        LIMIT :limit
    """)

    result = await db.execute(decisions_query, query_params)
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


@router.get("/api/tenant-dashboard/tenant/{tenant_id}/marketing-activity")
async def get_marketing_combined_activity(
    tenant_id: str,
    limit: int = 50,
    tenant: Tenant = Depends(require_tenant_path_access),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """Get combined inbound and outbound activity for a marketing team member."""
    # This must be scoped to the current user (marketing member)
    owner_id = getattr(tenant, "current_user_id", None)
    if not owner_id:
        raise HTTPException(status_code=401, detail="User session required")

    # 1. Get outbound notifications owned by this user
    outbound_query = text("""
        SELECT
            n.id as id,
            'outbound' as direction,
            n.type as type,
            nc.channel as channel,
            nc.status as status,
            n.user_id as recipient,
            n.data->>'body' as content,
            n.created_at as timestamp
        FROM notifications n
        JOIN notification_channels nc ON nc.notification_id = n.id
        WHERE n.tenant_id = :tenant_id AND n.owner_id = :owner_id
        ORDER BY n.created_at DESC
        LIMIT :limit
    """)

    # 2. Get inbound messages owned by this user
    inbound_query = text("""
        SELECT
            m.id as id,
            'inbound' as direction,
            'reply' as type,
            m.channel as channel,
            p.status as status,
            m.sender_address as recipient,
            p.parsed_content as content,
            m.created_at as timestamp
        FROM inbound_messages_raw m
        LEFT JOIN inbound_messages_parsed p ON m.id = p.raw_message_id
        WHERE m.tenant_id = :tenant_id AND m.owner_id = :owner_id
        ORDER BY m.created_at DESC
        LIMIT :limit
    """)

    outbound_res = await db.execute(outbound_query, {"tenant_id": tenant_id, "owner_id": owner_id, "limit": limit})
    inbound_res = await db.execute(inbound_query, {"tenant_id": tenant_id, "owner_id": owner_id, "limit": limit})

    combined = []
    for row in outbound_res.fetchall():
        combined.append(dict(row._mapping))
    for row in inbound_res.fetchall():
        # Handle Enum serialization
        row_dict = dict(row._mapping)
        row_dict['channel'] = str(row_dict['channel'])
        row_dict['status'] = str(row_dict['status'])
        combined.append(row_dict)

    # Sort by timestamp DESC
    combined.sort(key=lambda x: x['timestamp'], reverse=True)
    
    # Trim to limit
    combined = combined[:limit]

    # Convert timestamps to ISO
    for item in combined:
        if isinstance(item['timestamp'], datetime):
            item['timestamp'] = item['timestamp'].isoformat()

    return {
        "tenant_id": tenant_id,
        "owner_id": str(owner_id),
        "activity": combined
    }


@router.get("/api/tenant-dashboard/tenant/{tenant_id}/marketing-threaded-activity")
async def get_marketing_threaded_activity(
    tenant_id: str,
    limit: int = 50,
    tenant: Tenant = Depends(require_tenant_or_admin_path_access),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """Get threaded activity (outbound + its direct reply) for marketing."""
    try:
        owner_id = getattr(tenant, "current_user_id", None)
        user_role = getattr(tenant, "current_user_role", "admin" if getattr(tenant, "is_platform_admin", False) else "marketing")

        # If marketing role, we filter outbound by their own ID
        # If admin/root, we show all activity for the tenant
        use_owner_filter = (user_role == "marketing")

        outbound_where = "n.tenant_id = :tenant_id"
        if use_owner_filter and owner_id:
            outbound_where += " AND n.owner_id = :owner_id"

        # This query pairs notifications with their most recent subsequent reply
        query = text(f"""
            WITH outbound_page AS (
                SELECT 
                    n.id as id,
                    n.created_at as timestamp,
                    n.user_id as recipient_id,
                    n.data->>'email' as recipient_email,
                    n.data->>'phone' as recipient_phone,
                    n.data->>'body' as content,
                    nc.channel as channel,
                    nc.status as status,
                    nc.opened_at as opened_at,
                    nc.clicked_at as clicked_at
                FROM notifications n
                JOIN notification_channels nc ON nc.notification_id = n.id
                WHERE {outbound_where}
                ORDER BY n.created_at DESC
                LIMIT :limit
            ),
            inbound_candidates AS (
                SELECT 
                    m.id as id,
                    m.created_at as timestamp,
                    m.sender_address as sender,
                    COALESCE(p.parsed_content, m.raw_payload->>'body', m.raw_payload->>'text', m.raw_payload->>'stripped-text') as content,
                    CAST(m.channel AS TEXT) as channel,
                    p.status as status,
                    m.tenant_id,
                    ii.intent as ai_intent,
                    ii.confidence as ai_confidence,
                    ii.rationale as ai_rationale
                FROM inbound_messages_raw m
                LEFT JOIN inbound_messages_parsed p ON m.id = p.raw_message_id
                LEFT JOIN inbound_intents ii ON p.id = ii.parsed_message_id
                WHERE m.tenant_id = :tenant_id
                -- Only consider inbound messages newer than the oldest outbound message on this page
                AND m.created_at >= (SELECT MIN(timestamp) FROM outbound_page)
            ),
            inbound_mapped AS (
                SELECT 
                    i.*,
                    (
                        SELECT n2.id
                        FROM notifications n2
                        JOIN notification_channels nc2 ON nc2.notification_id = n2.id
                        WHERE n2.tenant_id = :tenant_id
                        AND n2.created_at <= i.timestamp
                        AND n2.created_at >= i.timestamp - INTERVAL '30 days'
                        AND LOWER(CAST(nc2.channel AS TEXT)) = LOWER(CAST(i.channel AS TEXT))
                        AND (
                            (LOWER(CAST(i.channel AS TEXT)) = 'email' AND n2.data->>'email' = i.sender)
                            OR (LOWER(CAST(i.channel AS TEXT)) IN ('sms', 'whatsapp', 'voice') AND (n2.data->>'phone' = i.sender OR 'whatsapp:' || (n2.data->>'phone') = i.sender OR n2.data->>'phone' = REPLACE(i.sender, 'whatsapp:', '')))
                            OR n2.user_id = i.sender
                        )
                        ORDER BY n2.created_at DESC
                        LIMIT 1
                    ) as matched_out_id
                FROM inbound_candidates i
            )
            SELECT 
                o.id as out_id,
                o.timestamp as out_time,
                COALESCE(o.recipient_email, o.recipient_phone, o.recipient_id) as recipient,
                o.content as out_content,
                o.channel as channel,
                CASE 
                    WHEN o.clicked_at IS NOT NULL THEN 'CLICKED'
                    WHEN o.opened_at IS NOT NULL THEN 'OPENED'
                    ELSE CAST(o.status AS TEXT)
                END as out_status,
                i.id as in_id,
                i.timestamp as in_time,
                i.content as in_content,
                i.status as in_status,
                i.ai_intent,
                i.ai_confidence,
                i.ai_rationale
            FROM outbound_page o
            LEFT JOIN inbound_mapped i ON i.matched_out_id = o.id AND LOWER(CAST(i.channel AS TEXT)) = LOWER(CAST(o.channel AS TEXT))
            ORDER BY o.timestamp DESC
        """)

        params = {"tenant_id": tenant_id, "limit": limit}
        if use_owner_filter and owner_id:
            params["owner_id"] = owner_id

        result = await db.execute(query, params)
        rows = result.fetchall()

        activity = []
        for row in rows:
            try:
                item = {
                    "channel": str(row.channel),
                    "recipient": row.recipient,
                    "outbound": {
                        "id": str(row.out_id),
                        "timestamp": row.out_time.isoformat() if row.out_time else None,
                        "content": row.out_content,
                        "status": str(row.out_status)
                    },
                    "inbound": None
                }
                
                if row.in_id:
                    item["inbound"] = {
                        "id": str(row.in_id),
                        "timestamp": row.in_time.isoformat() if row.in_time else None,
                        "content": row.in_content,
                        "status": str(row.in_status),
                        "ai_intent": str(row.ai_intent) if row.ai_intent else None,
                        "ai_confidence": float(row.ai_confidence) if row.ai_confidence is not None else None,
                        "ai_rationale": row.ai_rationale
                    }
                activity.append(item)
            except Exception as row_err:
                logger.error(f"Error processing activity row: {row_err}")
                continue

        return {
            "tenant_id": tenant_id,
            "owner_id": str(owner_id) if owner_id else None,
            "role": user_role,
            "threads": activity
        }
    except Exception as e:
        logger.error(f"Failed to get threaded activity: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/tenant-dashboard/tenant/{tenant_id}/candidates")
async def get_tenant_candidates(
    tenant_id: str,
    tenant: Tenant = Depends(require_tenant_or_admin_path_access),
    db: AsyncSession = Depends(get_db)
) -> List[Dict[str, Any]]:
    """
    Get a list of unique notification recipients (candidates) for this tenant.
    Aggregates from recent notifications to find known users and their contact info.
    """
    # If it's a marketing user, filter by their own ID
    owner_id_filter = None
    if hasattr(tenant, "current_user_role") and tenant.current_user_role == "marketing":
        owner_id_filter = tenant.current_user_id

    query_params = {"tenant_id": tenant_id}
    owner_clause = ""
    if owner_id_filter:
        owner_clause = "AND tenant_id = :tenant_id AND owner_id = :owner_id"
        query_params["owner_id"] = owner_id_filter
    else:
        owner_clause = "AND tenant_id = :tenant_id"

    query = text(f"""
        WITH recent_recipients AS (
            SELECT 
                user_id,
                data->>'email' as email,
                data->>'phone' as phone,
                created_at,
                ROW_NUMBER() OVER(PARTITION BY user_id ORDER BY created_at DESC) as rn
            FROM notifications
            WHERE 1=1 {owner_clause}
        )
        SELECT user_id, email, phone
        FROM recent_recipients
        WHERE rn = 1
        ORDER BY created_at DESC
        LIMIT 100
    """)
    
    result = await db.execute(query, query_params)
    rows = result.fetchall()
    
    candidates = []
    for row in rows:
        candidates.append({
            "user_id": row.user_id,
            "email": row.email,
            "phone": row.phone
        })
    
    # If no real data, provide some mocks for a better UI experience
    if not candidates:
        candidates = [
            {"user_id": "cust_001", "email": "alex.smith@example.com", "phone": "+14155550101"},
            {"user_id": "cust_002", "email": "jordan.lee@test.org", "phone": "+14155550102"},
            {"user_id": "cust_003", "email": "sam.taylor@company.net", "phone": "+14155550103"},
            {"user_id": "cust_004", "email": "casey.morgan@web.com", "phone": "+14155550104"},
            {"user_id": "cust_005", "email": "riley.quinn@service.io", "phone": "+14155550105"},
        ]
        
    return candidates
