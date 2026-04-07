from fastapi import APIRouter, Depends
from src.api.dependencies import get_authenticated_tenant
from src.models import Tenant
from src.providers.inapp_provider import get_user_notifications, mark_as_read, get_unread_count

router = APIRouter(prefix="/inapp", tags=["inapp"])


@router.get("/notifications/{user_id}")
async def get_notifications(
    user_id: str,
    limit: int = 20,
    tenant: Tenant = Depends(get_authenticated_tenant)
):
    """Get in-app notifications for a user."""
    notifications = await get_user_notifications(user_id, limit)
    unread_count = await get_unread_count(user_id)
    
    return {
        "notifications": notifications,
        "unread_count": unread_count,
        "total": len(notifications)
    }


@router.post("/notifications/{user_id}/{notification_id}/read")
async def mark_notification_read(
    user_id: str,
    notification_id: str,
    tenant: Tenant = Depends(get_authenticated_tenant)
):
    """Mark a notification as read."""
    success = await mark_as_read(user_id, notification_id)
    
    if success:
        return {"status": "success", "message": "Notification marked as read"}
    else:
        return {"status": "not_found", "message": "Notification not found"}


@router.get("/unread-count/{user_id}")
async def get_unread_count_endpoint(
    user_id: str,
    tenant: Tenant = Depends(get_authenticated_tenant)
):
    """Get unread notification count for a user."""
    count = await inapp_provider.get_unread_count(user_id)
    return {"user_id": user_id, "unread_count": count}
