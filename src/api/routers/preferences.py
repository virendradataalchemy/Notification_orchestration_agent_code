from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.core import get_db
from src.api.schemas import UserPreferenceUpdate, UserPreferenceResponse
from src.api.dependencies import get_authenticated_tenant
from src.models import UserPreference, Tenant

router = APIRouter(prefix="/preferences", tags=["preferences"])


@router.get(
    "/{user_id}",
    response_model=UserPreferenceResponse
)
async def get_user_preferences(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_authenticated_tenant)
):
    """
    Get notification preferences for a user.
    """
    query = select(UserPreference).where(
        UserPreference.tenant_id == tenant.id,
        UserPreference.user_id == user_id
    )
    result = await db.execute(query)
    preference = result.scalar_one_or_none()

    if not preference:
        # Return default preferences
        return UserPreferenceResponse(
            user_id=user_id,
            preferred_channels=None,
            quiet_hours=None,
            unsubscribed=None,
            language="en",
            timezone="UTC",
        )

    return preference


@router.put(
    "/{user_id}",
    response_model=UserPreferenceResponse
)
async def update_user_preferences(
    user_id: str,
    preferences: UserPreferenceUpdate,
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_authenticated_tenant)
):
    """
    Update notification preferences for a user.
    """
    query = select(UserPreference).where(
        UserPreference.tenant_id == tenant.id,
        UserPreference.user_id == user_id
    )
    result = await db.execute(query)
    db_preference = result.scalar_one_or_none()

    if not db_preference:
        # Create new preferences
        db_preference = UserPreference(
            tenant_id=tenant.id,
            user_id=user_id,
            preferred_channels=preferences.preferred_channels,
            quiet_hours=preferences.quiet_hours,
            unsubscribed=preferences.unsubscribed,
            language=preferences.language or "en",
            timezone=preferences.timezone or "UTC",
        )
        db.add(db_preference)
    else:
        # Update existing preferences
        if preferences.preferred_channels is not None:
            db_preference.preferred_channels = preferences.preferred_channels
        if preferences.quiet_hours is not None:
            db_preference.quiet_hours = preferences.quiet_hours
        if preferences.unsubscribed is not None:
            db_preference.unsubscribed = preferences.unsubscribed
        if preferences.language is not None:
            db_preference.language = preferences.language
        if preferences.timezone is not None:
            db_preference.timezone = preferences.timezone

    await db.commit()
    await db.refresh(db_preference)

    return db_preference


@router.post(
    "/{user_id}/unsubscribe/{notification_type}",
    response_model=UserPreferenceResponse
)
async def unsubscribe_notification_type(
    user_id: str,
    notification_type: str,
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_authenticated_tenant)
):
    """
    Unsubscribe user from a specific notification type.
    """
    query = select(UserPreference).where(
        UserPreference.tenant_id == tenant.id,
        UserPreference.user_id == user_id
    )
    result = await db.execute(query)
    db_preference = result.scalar_one_or_none()

    if not db_preference:
        db_preference = UserPreference(
            tenant_id=tenant.id,
            user_id=user_id,
            unsubscribed=[notification_type],
            language="en",
            timezone="UTC",
        )
        db.add(db_preference)
    else:
        if db_preference.unsubscribed is None:
            db_preference.unsubscribed = []
        if notification_type not in db_preference.unsubscribed:
            db_preference.unsubscribed.append(notification_type)

    await db.commit()
    await db.refresh(db_preference)

    return db_preference


@router.delete(
    "/{user_id}/unsubscribe/{notification_type}",
    response_model=UserPreferenceResponse
)
async def resubscribe_notification_type(
    user_id: str,
    notification_type: str,
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_authenticated_tenant)
):
    """
    Re-subscribe user to a specific notification type.
    """
    query = select(UserPreference).where(
        UserPreference.tenant_id == tenant.id,
        UserPreference.user_id == user_id
    )
    result = await db.execute(query)
    db_preference = result.scalar_one_or_none()

    if not db_preference:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User preferences not found"
        )

    if db_preference.unsubscribed and notification_type in db_preference.unsubscribed:
        db_preference.unsubscribed.remove(notification_type)
        await db.commit()
        await db.refresh(db_preference)

    return db_preference
