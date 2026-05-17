from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from src.core import get_db
from src.api.schemas import (
    SendNotificationRequest,
    BatchNotificationRequest,
    BatchMultiChannelNotificationRequest,
    NotificationResponse,
    BatchNotificationResponse,
    BatchMultiChannelNotificationResponse,
    NotificationStatusResponse,
)
from src.api.dependencies import user_rate_limiter
from src.api.dependencies import get_authenticated_tenant
from src.models import Tenant
from src.sdk import (
    NotificationPipelineError,
    get_notification_status_async,
    send_batch_multichannel_notification_pipeline_async,
    send_batch_notification_pipeline_async,
    send_notification_pipeline_async,
)
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
    tenant: Tenant = Depends(get_authenticated_tenant)
):
    """
    Send a notification to a single recipient (LEGACY).

    This endpoint creates and queues a notification for delivery across specified channels.
    Supports intelligent routing, priority handling, and automatic failover.

    """
    owner_id = getattr(tenant, "current_user_id", None)
    try:
        return await send_notification_pipeline_async(
            tenant.id,
            request.recipient,
            request.notification,
            request.options,
            owner_id=owner_id,
            session=db,
        )
    except NotificationPipelineError as exc:
        raise exc.to_http_exception() from exc


@router.post(
    "/agentic",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(user_rate_limiter)]
)
async def send_notification_agentic(
    request: SendNotificationRequest,
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_authenticated_tenant)
):
    """
    Agentic self-learning routing is disabled for the current internal-module
    deployment.

    The endpoint is intentionally kept in place so the older agentic code path
    can be re-enabled later without rediscovering the API contract.
    """
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail=(
            "Agentic notification routing is disabled in this deployment. "
            "Use /notifications/send for the active send flow."
        ),
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
    tenant: Tenant = Depends(get_authenticated_tenant)
):
    """
    Send notifications to multiple recipients in batch.

    Efficient for sending the same notification template to many users.
    Processing happens asynchronously.
    """
    owner_id = getattr(tenant, "current_user_id", None)
    try:
        return await send_batch_notification_pipeline_async(
            tenant.id,
            request,
            owner_id=owner_id,
            session=db,
        )
    except NotificationPipelineError as exc:
        raise exc.to_http_exception() from exc


@router.post(
    "/batch-multichannel",
    response_model=BatchMultiChannelNotificationResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(user_rate_limiter)]
)
async def send_batch_notifications_multichannel(
    request: BatchMultiChannelNotificationRequest,
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_authenticated_tenant)
):
    """
    Send notifications to multiple recipients across multiple channels in one request.
    """
    owner_id = getattr(tenant, "current_user_id", None)
    try:
        return await send_batch_multichannel_notification_pipeline_async(
            tenant.id,
            request,
            owner_id=owner_id,
            session=db,
        )
    except NotificationPipelineError as exc:
        raise exc.to_http_exception() from exc


@router.get(
    "/{notification_id}",
    response_model=NotificationStatusResponse
)
async def get_notification_status(
    notification_id: str,
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_authenticated_tenant)
):
    """
    Get the current status of a notification.

    Returns detailed information about the notification including delivery status
    for each channel, timestamps, and any errors.
    """
    try:
        return await get_notification_status_async(
            tenant.id,
            notification_id,
            session=db,
        )
    except NotificationPipelineError as exc:
        raise exc.to_http_exception() from exc


@router.get(
    "/user/{user_id}",
    response_model=List[NotificationStatusResponse]
)
async def get_user_notifications(
    user_id: str,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_authenticated_tenant)
):
    """
    Get all notifications for a specific user.

    Returns a paginated list of notifications ordered by creation time (newest first).
    """
    # IMPORTANT: Filter by tenant_id to prevent cross-tenant data access
    query = (
        select(Notification)
        .options(selectinload(Notification.channels))
        .where(
            Notification.tenant_id == tenant.id,
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
