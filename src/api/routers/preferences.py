"""User preferences API - Supabase REST based."""

from fastapi import APIRouter, Depends, HTTPException, status
from typing import Optional, Dict, Any

from src.api.dependencies import get_authenticated_client, verify_api_key
from src.api.schemas import UserPreferenceUpdate, UserPreferenceResponse
from src.core.supabase import supabase_client
from src.models import Client

router = APIRouter(prefix="/preferences", tags=["preferences"])


async def _get_or_none(user_id: str, client_id: int) -> Optional[Dict[str, Any]]:
    rows = await supabase_client.select(
        "user_preferences",
        "id,user_id,client_id,preferred_channels,quiet_hours,unsubscribed,language,timezone",
        limit=1,
        filters={"user_id": f"eq.{user_id}", "client_id": f"eq.{client_id}"},
    )
    return rows[0] if rows else None


def _default_prefs(user_id: str) -> Dict[str, Any]:
    return {
        "user_id": user_id,
        "preferred_channels": None,
        "quiet_hours": None,
        "unsubscribed": None,
        "language": "en",
        "timezone": "UTC",
    }


@router.get("/{user_id}", response_model=UserPreferenceResponse)
async def get_user_preferences(
    user_id: str,
    client: Client = Depends(get_authenticated_client),
):
    row = await _get_or_none(user_id, client.id)
    if not row:
        return UserPreferenceResponse(**_default_prefs(user_id))
    return UserPreferenceResponse(
        user_id=row["user_id"],
        preferred_channels=row.get("preferred_channels"),
        quiet_hours=row.get("quiet_hours"),
        unsubscribed=row.get("unsubscribed"),
        language=row.get("language") or "en",
        timezone=row.get("timezone") or "UTC",
    )


@router.put("/{user_id}", response_model=UserPreferenceResponse)
async def update_user_preferences(
    user_id: str,
    preferences: UserPreferenceUpdate,
    client: Client = Depends(get_authenticated_client),
):
    existing = await _get_or_none(user_id, client.id)
    update_data: Dict[str, Any] = {}
    if preferences.preferred_channels is not None:
        update_data["preferred_channels"] = preferences.preferred_channels
    if preferences.quiet_hours is not None:
        update_data["quiet_hours"] = preferences.quiet_hours
    if preferences.unsubscribed is not None:
        update_data["unsubscribed"] = preferences.unsubscribed
    if preferences.language is not None:
        update_data["language"] = preferences.language
    if preferences.timezone is not None:
        update_data["timezone"] = preferences.timezone

    if existing:
        rows = await supabase_client.update(
            "user_preferences", update_data, filters={"id": f"eq.{existing['id']}"}
        )
        row = rows[0] if rows else {**existing, **update_data}
    else:
        latest = await supabase_client.select("user_preferences", "id", limit=1, filters={"order": "id.desc"})
        next_id = int(latest[0]["id"]) + 1 if latest else 1
        rows = await supabase_client.insert("user_preferences", {
            "id": next_id,
            "user_id": user_id,
            "client_id": client.id,
            "preferred_channels": preferences.preferred_channels,
            "quiet_hours": preferences.quiet_hours,
            "unsubscribed": preferences.unsubscribed,
            "language": preferences.language or "en",
            "timezone": preferences.timezone or "UTC",
        })
        row = rows[0]

    return UserPreferenceResponse(
        user_id=row.get("user_id", user_id),
        preferred_channels=row.get("preferred_channels"),
        quiet_hours=row.get("quiet_hours"),
        unsubscribed=row.get("unsubscribed"),
        language=row.get("language") or "en",
        timezone=row.get("timezone") or "UTC",
    )


@router.post("/{user_id}/unsubscribe/{notification_type}", response_model=UserPreferenceResponse)
async def unsubscribe_notification_type(
    user_id: str,
    notification_type: str,
    client: Client = Depends(get_authenticated_client),
):
    existing = await _get_or_none(user_id, client.id)
    current_unsub = (existing or {}).get("unsubscribed") or []
    if notification_type not in current_unsub:
        current_unsub = current_unsub + [notification_type]

    if existing:
        rows = await supabase_client.update(
            "user_preferences", {"unsubscribed": current_unsub}, filters={"id": f"eq.{existing['id']}"}
        )
        row = rows[0] if rows else {**existing, "unsubscribed": current_unsub}
    else:
        latest = await supabase_client.select("user_preferences", "id", limit=1, filters={"order": "id.desc"})
        next_id = int(latest[0]["id"]) + 1 if latest else 1
        rows = await supabase_client.insert("user_preferences", {
            "id": next_id, "user_id": user_id, "client_id": client.id,
            "unsubscribed": current_unsub, "language": "en", "timezone": "UTC",
        })
        row = rows[0]

    return UserPreferenceResponse(
        user_id=row.get("user_id", user_id),
        preferred_channels=row.get("preferred_channels"),
        quiet_hours=row.get("quiet_hours"),
        unsubscribed=row.get("unsubscribed"),
        language=row.get("language") or "en",
        timezone=row.get("timezone") or "UTC",
    )


@router.delete("/{user_id}/unsubscribe/{notification_type}", response_model=UserPreferenceResponse)
async def resubscribe_notification_type(
    user_id: str,
    notification_type: str,
    client: Client = Depends(get_authenticated_client),
):
    existing = await _get_or_none(user_id, client.id)
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User preferences not found")

    current_unsub = existing.get("unsubscribed") or []
    new_unsub = [t for t in current_unsub if t != notification_type]
    rows = await supabase_client.update(
        "user_preferences", {"unsubscribed": new_unsub}, filters={"id": f"eq.{existing['id']}"}
    )
    row = rows[0] if rows else {**existing, "unsubscribed": new_unsub}

    return UserPreferenceResponse(
        user_id=row.get("user_id", user_id),
        preferred_channels=row.get("preferred_channels"),
        quiet_hours=row.get("quiet_hours"),
        unsubscribed=row.get("unsubscribed"),
        language=row.get("language") or "en",
        timezone=row.get("timezone") or "UTC",
    )
