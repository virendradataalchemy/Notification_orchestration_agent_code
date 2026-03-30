from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
import uuid
from datetime import datetime

from src.core import get_db
from src.api.schemas import (
    SendNotificationRequest,
    BatchNotificationRequest,
    NotificationResponse,
    BatchNotificationResponse,
    NotificationStatusResponse,
    NotificationStatus,
)
from src.api.dependencies import user_rate_limiter
from src.middleware import get_tenant_id
from src.models import Notification, NotificationChannel, Priority as DBPriority
from src.services.notification_service import NotificationService
from src.agents.sync_team import get_notification_team
import logging

router = APIRouter(prefix="/notifications", tags=["notifications"])
logger = logging.getLogger(__name__)


@router.post(
    "/send",
    response_model=NotificationResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(user_rate_limiter)]
)
async def send_notification(
    request: SendNotificationRequest,
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Depends(get_tenant_id)
):
    """
    Send a notification to a single recipient (LEGACY).

    This endpoint creates and queues a notification for delivery across specified channels.
    Supports intelligent routing, priority handling, and automatic failover.

    NOTE: This is the legacy endpoint. Use /notifications/agentic for self-learning routing.
    """
    service = NotificationService(db)
    notification = await service.send_notification(tenant_id, request)
    return notification


@router.post(
    "/agentic",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(user_rate_limiter)]
)
async def send_notification_agentic(
    request: SendNotificationRequest,
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Depends(get_tenant_id)
):
    """
    Send notification using self-learning Strands agents (RECOMMENDED).

    This endpoint uses a multi-agent system with:
    - Semantic deduplication via ChromaDB
    - Learning from past similar notifications
    - Intelligent channel routing using ML and memory
    - Asynchronous outcome tracking and continuous improvement

    Flow:
    1. Analyzer Agent (Haiku) - Fast duplicate check + user analysis
    2. Router Agent (Sonnet) - Smart channel selection using memory
    3. Returns immediately after sending
    4. Learning happens asynchronously via webhooks

    Benefits over /send:
    - 72% lower LLM costs (uses Haiku for analysis)
    - Learns from past decisions (ChromaDB memory)
    - Semantic duplicate detection (0.2 similarity threshold)
    - Self-improving over time
    """
    try:
        # Get notification team
        team = get_notification_team()

        # Process with agents
        result = await team.process_notification(
            tenant_id=tenant_id,
            user_id=request.user_id,
            notification_type=request.type,
            content=request.content,
            priority=request.priority.value if hasattr(request.priority, 'value') else request.priority,
            metadata=request.metadata or {}
        )

        return result

    except Exception as e:
        logger.error(f"Agentic notification failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Agentic processing failed: {str(e)}"
        )


@router.post(
    "/batch",
    response_model=BatchNotificationResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(user_rate_limiter)]
)
async def send_batch_notifications(
    request: BatchNotificationRequest,
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Depends(get_tenant_id)
):
    """
    Send notifications to multiple recipients in batch.

    Efficient for sending the same notification template to many users.
    Processing happens asynchronously.
    """
    service = NotificationService(db)
    batch = await service.send_batch_notifications(tenant_id, request)
    return batch


@router.get(
    "/{notification_id}",
    response_model=NotificationStatusResponse
)
async def get_notification_status(
    notification_id: str,
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Depends(get_tenant_id)
):
    """
    Get the current status of a notification.

    Returns detailed information about the notification including delivery status
    for each channel, timestamps, and any errors.
    """
    try:
        notification_uuid = uuid.UUID(notification_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid notification ID format"
        )

    # IMPORTANT: Filter by tenant_id to prevent cross-tenant data access
    query = select(Notification).where(
        Notification.id == notification_uuid,
        Notification.tenant_id == tenant_id
    )
    result = await db.execute(query)
    notification = result.scalar_one_or_none()

    if not notification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found"
        )

    # Get channel statuses
    channels = []
    for channel in notification.channels:
        channels.append({
            "channel": channel.channel,
            "provider": channel.provider,
            "message_id": channel.message_id,
            "status": channel.status.value,
            "delivered_at": channel.delivered_at,
            "opened_at": channel.opened_at,
            "clicked_at": channel.clicked_at,
        })

    return NotificationStatusResponse(
        notification_id=str(notification.id),
        user_id=notification.user_id,
        type=notification.type,
        priority=notification.priority,
        status=notification.status,
        channels=channels,
        attempts=sum(c.attempts for c in notification.channels),
        created_at=notification.created_at,
        updated_at=notification.updated_at,
    )


@router.get(
    "/user/{user_id}",
    response_model=List[NotificationStatusResponse]
)
async def get_user_notifications(
    user_id: str,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Depends(get_tenant_id)
):
    """
    Get all notifications for a specific user.

    Returns a paginated list of notifications ordered by creation time (newest first).
    """
    # IMPORTANT: Filter by tenant_id to prevent cross-tenant data access
    query = (
        select(Notification)
        .where(
            Notification.tenant_id == tenant_id,
            Notification.user_id == user_id
        )
        .order_by(Notification.created_at.desc())
        .limit(limit)
        .offset(offset)
    )

    result = await db.execute(query)
    notifications = result.scalars().all()

    response = []
    for notification in notifications:
        channels = [
            {
                "channel": c.channel,
                "provider": c.provider,
                "message_id": c.message_id,
                "status": c.status.value,
                "delivered_at": c.delivered_at,
                "opened_at": c.opened_at,
                "clicked_at": c.clicked_at,
            }
            for c in notification.channels
        ]

        response.append(
            NotificationStatusResponse(
                notification_id=str(notification.id),
                user_id=notification.user_id,
                type=notification.type,
                priority=notification.priority,
                status=notification.status,
                channels=channels,
                attempts=sum(c.attempts for c in notification.channels),
                created_at=notification.created_at,
                updated_at=notification.updated_at,
            )
        )

    return response
