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
from src.agents.sync_team import get_notification_team
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

    NOTE: This is the legacy endpoint. Use /notifications/agentic for self-learning routing.
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
        body_text = request.notification.body or ""
        if not body_text:
            # Keep agent pipeline usable even when only subject/template metadata is provided.
            body_text = request.notification.subject or request.notification.type

        # Get notification team
        team = get_notification_team()

        # Pass current user ID as owner if available
        owner_id = getattr(tenant, "current_user_id", None)

        # Process with agents
        result = await team.process_notification(
            tenant_id=tenant.id,
            user_id=request.recipient.user_id,
            notification_type=request.notification.type,
            content=body_text,
            priority=(
                request.notification.priority.value
                if hasattr(request.notification.priority, "value")
                else str(request.notification.priority)
            ),
            owner_id=owner_id,
            metadata={
                **(request.notification.data or {}),
                **(request.options.model_dump() if request.options else {}),
                "channels": [c.value for c in request.notification.channels],
                "recipient": request.recipient.model_dump(),
                "template_id": request.notification.template_id,
                "subject": request.notification.subject,
                "body": request.notification.body,
            }
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
