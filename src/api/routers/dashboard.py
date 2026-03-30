from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from typing import Dict, List
from datetime import datetime, timedelta

from src.core import get_db
from src.models import Notification, NotificationChannel, NotificationStatus, ChannelStatus

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/", response_class=HTMLResponse)
async def dashboard_home():
    """Render the enhanced dashboard HTML page with tabs."""
    with open("src/api/routers/dashboard_enhanced.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@router.get("/api/stats")
async def get_dashboard_stats(
    db: AsyncSession = Depends(get_db)
):
    """
    Get overall statistics for the dashboard.

    Returns:
    - Total notifications
    - Status breakdown
    - Channel breakdown
    - Recent activity
    """
    # Total notifications
    total_query = select(func.count(Notification.id))
    total_result = await db.execute(total_query)
    total_notifications = total_result.scalar() or 0

    # Status breakdown
    status_query = select(
        Notification.status,
        func.count(Notification.id)
    ).group_by(Notification.status)
    status_result = await db.execute(status_query)
    status_breakdown = {
        status.value: count
        for status, count in status_result.all()
    }

    # Channel breakdown
    channel_query = select(
        NotificationChannel.channel,
        func.count(NotificationChannel.id)
    ).group_by(NotificationChannel.channel)
    channel_result = await db.execute(channel_query)
    channel_breakdown = {
        channel: count
        for channel, count in channel_result.all()
    }

    # Channel status breakdown
    channel_status_query = select(
        NotificationChannel.channel,
        NotificationChannel.status,
        func.count(NotificationChannel.id)
    ).group_by(NotificationChannel.channel, NotificationChannel.status)
    channel_status_result = await db.execute(channel_status_query)
    channel_status_breakdown = {}
    for channel, status, count in channel_status_result.all():
        if channel not in channel_status_breakdown:
            channel_status_breakdown[channel] = {}
        channel_status_breakdown[channel][status.value] = count

    # Last 24 hours activity
    yesterday = datetime.utcnow() - timedelta(days=1)
    recent_query = select(
        func.date_trunc('hour', Notification.created_at).label('hour'),
        func.count(Notification.id)
    ).where(
        Notification.created_at >= yesterday
    ).group_by('hour').order_by('hour')
    recent_result = await db.execute(recent_query)
    hourly_activity = [
        {
            "hour": hour.isoformat() if hour else None,
            "count": count
        }
        for hour, count in recent_result.all()
    ]

    # Success rate
    delivered_query = select(func.count(Notification.id)).where(
        Notification.status == NotificationStatus.DELIVERED
    )
    delivered_result = await db.execute(delivered_query)
    delivered_count = delivered_result.scalar() or 0
    success_rate = (delivered_count / total_notifications * 100) if total_notifications > 0 else 0

    return {
        "total_notifications": total_notifications,
        "status_breakdown": status_breakdown,
        "channel_breakdown": channel_breakdown,
        "channel_status_breakdown": channel_status_breakdown,
        "hourly_activity": hourly_activity,
        "success_rate": round(success_rate, 2),
        "delivered_count": delivered_count,
    }


@router.get("/api/recent")
async def get_recent_notifications(
    limit: int = 20,
    db: AsyncSession = Depends(get_db)
):
    """Get recent notifications with their status."""
    query = (
        select(Notification)
        .options(selectinload(Notification.channels))
        .order_by(Notification.created_at.desc())
        .limit(limit)
    )

    result = await db.execute(query)
    notifications = result.scalars().all()

    response = []
    for notification in notifications:
        channels_info = []
        for channel in notification.channels:
            channels_info.append({
                "channel": channel.channel,
                "status": channel.status.value,
                "provider": channel.provider,
                "attempts": channel.attempts,
                "delivered_at": channel.delivered_at.isoformat() if channel.delivered_at else None,
                "error_message": channel.error_message,
            })

        response.append({
            "id": str(notification.id),
            "user_id": notification.user_id,
            "type": notification.type,
            "priority": notification.priority.value,
            "status": notification.status.value,
            "channels": channels_info,
            "created_at": notification.created_at.isoformat(),
            "updated_at": notification.updated_at.isoformat(),
        })

    return response


@router.get("/api/failures")
async def get_failed_notifications(
    limit: int = 20,
    db: AsyncSession = Depends(get_db)
):
    """Get failed notifications for troubleshooting."""
    query = (
        select(NotificationChannel)
        .where(NotificationChannel.status.in_([ChannelStatus.FAILED, ChannelStatus.BOUNCED]))
        .order_by(NotificationChannel.updated_at.desc())
        .limit(limit)
    )

    result = await db.execute(query)
    failures = result.scalars().all()

    response = []
    for failure in failures:
        response.append({
            "id": str(failure.id),
            "notification_id": str(failure.notification_id),
            "channel": failure.channel,
            "provider": failure.provider,
            "status": failure.status.value,
            "attempts": failure.attempts,
            "error_code": failure.error_code,
            "error_message": failure.error_message,
            "created_at": failure.created_at.isoformat(),
            "updated_at": failure.updated_at.isoformat(),
        })

    return response


@router.get("/api/channel-health")
async def get_channel_health(
    db: AsyncSession = Depends(get_db)
):
    """Get health metrics for each channel."""
    # Last hour stats per channel
    one_hour_ago = datetime.utcnow() - timedelta(hours=1)

    query = select(
        NotificationChannel.channel,
        NotificationChannel.status,
        func.count(NotificationChannel.id)
    ).where(
        NotificationChannel.created_at >= one_hour_ago
    ).group_by(
        NotificationChannel.channel,
        NotificationChannel.status
    )

    result = await db.execute(query)

    channel_health = {}
    for channel, status, count in result.all():
        if channel not in channel_health:
            channel_health[channel] = {
                "total": 0,
                "delivered": 0,
                "failed": 0,
                "pending": 0,
                "success_rate": 0
            }

        channel_health[channel]["total"] += count

        if status in [ChannelStatus.DELIVERED]:
            channel_health[channel]["delivered"] += count
        elif status in [ChannelStatus.FAILED, ChannelStatus.BOUNCED]:
            channel_health[channel]["failed"] += count
        elif status in [ChannelStatus.QUEUED, ChannelStatus.SENT]:
            channel_health[channel]["pending"] += count

    # Calculate success rates
    for channel in channel_health:
        total = channel_health[channel]["total"]
        delivered = channel_health[channel]["delivered"]
        if total > 0:
            channel_health[channel]["success_rate"] = round((delivered / total) * 100, 2)

    return channel_health
