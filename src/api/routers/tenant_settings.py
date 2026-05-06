"""
Tenant self-service settings API.

Provides:
- Profile view/update
- Developer settings (API key metadata + rotation)
- Tenant channel enable/disable preferences
"""

from datetime import datetime
from typing import Dict, Any, List, Tuple
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core import get_db
from src.api.dependencies import get_authenticated_tenant
from src.models import Tenant, TenantChannelPreference, TenantProviderConfig, TenantUser

router = APIRouter(prefix="/tenant/settings", tags=["tenant-settings"])

SUPPORTED_CHANNELS = ["email", "sms", "whatsapp", "slack", "voice"] #, "push", "inapp"]
SUPPORTED_DELIVERY_MODES = {"parallel_all", "sequential_failover"}


class TenantProfileResponse(BaseModel):
    tenant_id: str
    name: str
    admin_name: str | None = None
    admin_email: str | None = None
    status: str
    config: Dict[str, Any] | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class TenantProfileUpdateRequest(BaseModel):
    name: str | None = None
    admin_name: str | None = None
    admin_email: EmailStr | None = None
    config: Dict[str, Any] | None = None


class DeveloperSettingsResponse(BaseModel):
    tenant_id: str
    api_key_prefix: str
    note: str
    updated_at: datetime | None = None


class RotateApiKeyResponse(BaseModel):
    api_key: str
    api_key_prefix: str
    message: str


class ChannelPreferenceItem(BaseModel):
    channel: str
    enabled: bool
    available: bool = True
    availability_reason: str | None = None


class ChannelPreferencesResponse(BaseModel):
    tenant_id: str
    channels: List[ChannelPreferenceItem]


class ChannelPreferencesUpdateRequest(BaseModel):
    channels: List[ChannelPreferenceItem]


class ChannelPriorityResponse(BaseModel):
    tenant_id: str
    default_channel_priority: List[str]


class ChannelPriorityUpdateRequest(BaseModel):
    default_channel_priority: List[str]


class DeliveryModeResponse(BaseModel):
    tenant_id: str
    default_delivery_mode: str


class DeliveryModeUpdateRequest(BaseModel):
    default_delivery_mode: str


def _is_channel_sender_available(
    channel: str,
    provider_config_map: Dict[str, Dict[str, Any]],
) -> Tuple[bool, str | None]:
    """
    Channel availability based on tenant sender configuration.

    Rules:
    - email requires from_email/sender_email
    - sms/whatsapp/voice require from_number/sender_id
    - slack requires channel_id
    - push/inapp are always available from sender-identity perspective
    """
    cfg = provider_config_map.get(channel) or {}

    if channel == "email":
        if cfg.get("from_email") or cfg.get("sender_email"):
            return True, None
        return False, "Missing sender email"

    if channel in {"sms", "whatsapp", "voice"}:
        if cfg.get("from_number") or cfg.get("sender_id"):
            return True, None
        return False, "Missing sender number/caller ID"

    if channel == "slack":
        if cfg.get("channel_id"):
            return True, None
        return False, "Missing default Slack channel_id"

    return True, None


@router.get("/profile", response_model=TenantProfileResponse)
async def get_profile(
    tenant: Tenant = Depends(get_authenticated_tenant),
    db: AsyncSession = Depends(get_db)
):
    current = await db.get(Tenant, tenant.id)
    if not current:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    return TenantProfileResponse(
        tenant_id=current.id,
        name=current.name,
        admin_name=current.admin_name,
        admin_email=current.admin_email,
        status=current.status,
        config=current.config or {},
        created_at=current.created_at,
        updated_at=current.updated_at,
    )


@router.patch("/profile", response_model=TenantProfileResponse)
async def update_profile(
    payload: TenantProfileUpdateRequest,
    tenant: Tenant = Depends(get_authenticated_tenant),
    db: AsyncSession = Depends(get_db)
):
    current = await db.get(Tenant, tenant.id)
    if not current:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    print(f"Updating profile for tenant {tenant.id} with payload: {payload.dict(exclude_unset=True)}")
    if hasattr(tenant, "current_user_id"):
        print(f"Current user ID: {tenant.current_user_id}")
    else:
        print("No current_user_id found on tenant")

    if payload.name is not None:
        current.name = payload.name
    if payload.admin_name is not None:
        current.admin_name = payload.admin_name
    if payload.admin_email is not None:
        current.admin_email = str(payload.admin_email)

    if payload.config is not None:
        current.config = {**(current.config or {}), **payload.config}

    # Update the root user to keep the profile synced with team management
    if payload.admin_name is not None or payload.admin_email is not None:
        from sqlalchemy import update
        values = {}
        if payload.admin_name is not None:
            values['full_name'] = payload.admin_name
        if payload.admin_email is not None:
            values['email'] = str(payload.admin_email)
            
        print(f"Updating TenantUser table with values: {values} for tenant {current.id}")
            
        res1 = await db.execute(
            update(TenantUser)
            .where(TenantUser.tenant_id == current.id)
            .where(TenantUser.role == "root")
            .values(**values)
        )
        print(f"Updated {res1.rowcount} root users")
        
        # Also update the current user if they exist
        if hasattr(tenant, "current_user_id") and tenant.current_user_id:
            res2 = await db.execute(
                update(TenantUser)
                .where(TenantUser.id == tenant.current_user_id)
                .values(**values)
            )
            print(f"Updated {res2.rowcount} current user")
            
    current.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(current)

    return TenantProfileResponse(
        tenant_id=current.id,
        name=current.name,
        admin_name=current.admin_name,
        admin_email=current.admin_email,
        status=current.status,
        config=current.config or {},
        created_at=current.created_at,
        updated_at=current.updated_at,
    )


@router.get("/developer", response_model=DeveloperSettingsResponse)
async def get_developer_settings(
    tenant: Tenant = Depends(get_authenticated_tenant),
    db: AsyncSession = Depends(get_db)
):
    current = await db.get(Tenant, tenant.id)
    if not current:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    return DeveloperSettingsResponse(
        tenant_id=current.id,
        api_key_prefix=current.api_key_prefix,
        note="Full API key is only shown once at creation/rotation time.",
        updated_at=current.updated_at,
    )


@router.post("/developer/rotate-api-key", response_model=RotateApiKeyResponse)
async def rotate_api_key(
    tenant: Tenant = Depends(get_authenticated_tenant),
    db: AsyncSession = Depends(get_db)
):
    current = await db.get(Tenant, tenant.id)
    if not current:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    api_key, api_key_hash, api_key_prefix = Tenant.generate_api_key(current.id, env="live")
    current.api_key_hash = api_key_hash
    current.api_key_prefix = api_key_prefix
    current.updated_at = datetime.utcnow()
    await db.commit()

    return RotateApiKeyResponse(
        api_key=api_key,
        api_key_prefix=api_key_prefix,
        message="API key rotated successfully. Save it now; it will not be shown again."
    )


@router.get("/channels", response_model=ChannelPreferencesResponse)
async def get_channel_preferences(
    tenant: Tenant = Depends(get_authenticated_tenant),
    db: AsyncSession = Depends(get_db)
):
    query = select(TenantChannelPreference).where(TenantChannelPreference.tenant_id == tenant.id)
    result = await db.execute(query)
    rows = result.scalars().all()
    enabled_map = {row.channel: row.enabled for row in rows}

    provider_query = select(TenantProviderConfig).where(
        TenantProviderConfig.tenant_id == tenant.id,
        TenantProviderConfig.is_active == True
    )
    provider_result = await db.execute(provider_query)
    provider_rows = provider_result.scalars().all()
    provider_config_map = {row.provider: (row.config or {}) for row in provider_rows}

    channels: List[ChannelPreferenceItem] = []
    for channel in SUPPORTED_CHANNELS:
        available, reason = _is_channel_sender_available(channel, provider_config_map)
        channel_enabled = enabled_map.get(channel, True) if available else False
        channels.append(
            ChannelPreferenceItem(
                channel=channel,
                enabled=channel_enabled,
                available=available,
                availability_reason=reason,
            )
        )
    return ChannelPreferencesResponse(tenant_id=tenant.id, channels=channels)


@router.put("/channels", response_model=ChannelPreferencesResponse)
async def update_channel_preferences(
    payload: ChannelPreferencesUpdateRequest,
    tenant: Tenant = Depends(get_authenticated_tenant),
    db: AsyncSession = Depends(get_db)
):
    invalid = [item.channel for item in payload.channels if item.channel not in SUPPORTED_CHANNELS]
    if invalid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported channels: {invalid}"
        )

    existing_query = select(TenantChannelPreference).where(
        TenantChannelPreference.tenant_id == tenant.id
    )
    existing_result = await db.execute(existing_query)
    existing_rows = existing_result.scalars().all()
    existing_map = {row.channel: row for row in existing_rows}

    provider_query = select(TenantProviderConfig).where(
        TenantProviderConfig.tenant_id == tenant.id,
        TenantProviderConfig.is_active == True
    )
    provider_result = await db.execute(provider_query)
    provider_rows = provider_result.scalars().all()
    provider_config_map = {row.provider: (row.config or {}) for row in provider_rows}

    unavailable_enabled = []
    for item in payload.channels:
        available, _ = _is_channel_sender_available(item.channel, provider_config_map)
        if item.enabled and not available:
            unavailable_enabled.append(item.channel)
    if unavailable_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Cannot enable channels without sender configuration: "
                f"{unavailable_enabled}. Set sender identity first in Developer Settings."
            )
        )

    for item in payload.channels:
        current = existing_map.get(item.channel)
        if current:
            current.enabled = item.enabled
            current.updated_at = datetime.utcnow()
        else:
            db.add(
                TenantChannelPreference(
                    id=uuid.uuid4().hex[:32],
                    tenant_id=tenant.id,
                    channel=item.channel,
                    enabled=item.enabled,
                )
            )

    # Keep stored default channel priority aligned with active channels only.
    current_tenant = await db.get(Tenant, tenant.id)
    if current_tenant:
        enabled_after = {ch: True for ch in SUPPORTED_CHANNELS}
        for row in existing_rows:
            enabled_after[row.channel] = row.enabled
        for item in payload.channels:
            enabled_after[item.channel] = item.enabled

        active_channels = [
            ch for ch in SUPPORTED_CHANNELS
            if enabled_after.get(ch, True)
            and _is_channel_sender_available(ch, provider_config_map)[0]
        ]

        cfg = current_tenant.config or {}
        stored_priority = cfg.get("default_channel_priority") or []
        pruned_priority = [ch for ch in stored_priority if ch in active_channels]
        if pruned_priority != stored_priority:
            current_tenant.config = {
                **cfg,
                "default_channel_priority": pruned_priority
            }
            current_tenant.updated_at = datetime.utcnow()

    await db.commit()

    return await get_channel_preferences(tenant=tenant, db=db)


@router.get("/channel-priority", response_model=ChannelPriorityResponse)
async def get_default_channel_priority(
    tenant: Tenant = Depends(get_authenticated_tenant),
    db: AsyncSession = Depends(get_db)
):
    current = await db.get(Tenant, tenant.id)
    if not current:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    prefs_query = select(TenantChannelPreference).where(TenantChannelPreference.tenant_id == tenant.id)
    prefs_result = await db.execute(prefs_query)
    prefs_rows = prefs_result.scalars().all()
    enabled_map = {row.channel: row.enabled for row in prefs_rows}

    provider_query = select(TenantProviderConfig).where(
        TenantProviderConfig.tenant_id == tenant.id,
        TenantProviderConfig.is_active == True
    )
    provider_result = await db.execute(provider_query)
    provider_rows = provider_result.scalars().all()
    provider_config_map = {row.provider: (row.config or {}) for row in provider_rows}

    active_channels = [
        ch for ch in SUPPORTED_CHANNELS
        if enabled_map.get(ch, True)
        and _is_channel_sender_available(ch, provider_config_map)[0]
    ]

    config = current.config or {}
    stored_priority = config.get("default_channel_priority") or []
    filtered = [ch for ch in stored_priority if ch in active_channels]
    missing_active = [ch for ch in active_channels if ch not in filtered]
    effective_priority = filtered + missing_active
    return ChannelPriorityResponse(tenant_id=current.id, default_channel_priority=effective_priority)


@router.put("/channel-priority", response_model=ChannelPriorityResponse)
async def update_default_channel_priority(
    payload: ChannelPriorityUpdateRequest,
    tenant: Tenant = Depends(get_authenticated_tenant),
    db: AsyncSession = Depends(get_db)
):
    current = await db.get(Tenant, tenant.id)
    if not current:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    invalid = [ch for ch in payload.default_channel_priority if ch not in SUPPORTED_CHANNELS]
    if invalid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported channels in default_channel_priority: {invalid}"
        )

    prefs_query = select(TenantChannelPreference).where(TenantChannelPreference.tenant_id == tenant.id)
    prefs_result = await db.execute(prefs_query)
    prefs_rows = prefs_result.scalars().all()
    enabled_map = {row.channel: row.enabled for row in prefs_rows}

    provider_query = select(TenantProviderConfig).where(
        TenantProviderConfig.tenant_id == tenant.id,
        TenantProviderConfig.is_active == True
    )
    provider_result = await db.execute(provider_query)
    provider_rows = provider_result.scalars().all()
    provider_config_map = {row.provider: (row.config or {}) for row in provider_rows}

    inactive = [
        ch for ch in payload.default_channel_priority
        if (
            not enabled_map.get(ch, True)
            or not _is_channel_sender_available(ch, provider_config_map)[0]
        )
    ]
    if inactive:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Cannot prioritize inactive channels (disabled or unavailable): "
                f"{inactive}"
            )
        )

    deduped = list(dict.fromkeys(payload.default_channel_priority))
    current.config = {**(current.config or {}), "default_channel_priority": deduped}
    current.updated_at = datetime.utcnow()
    await db.commit()

    return ChannelPriorityResponse(tenant_id=current.id, default_channel_priority=deduped)


@router.get("/delivery-mode", response_model=DeliveryModeResponse)
async def get_default_delivery_mode(
    tenant: Tenant = Depends(get_authenticated_tenant),
    db: AsyncSession = Depends(get_db)
):
    current = await db.get(Tenant, tenant.id)
    if not current:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    config = current.config or {}
    mode = config.get("default_delivery_mode") or "parallel_all"
    if mode not in SUPPORTED_DELIVERY_MODES:
        mode = "parallel_all"
    return DeliveryModeResponse(tenant_id=current.id, default_delivery_mode=mode)


@router.put("/delivery-mode", response_model=DeliveryModeResponse)
async def update_default_delivery_mode(
    payload: DeliveryModeUpdateRequest,
    tenant: Tenant = Depends(get_authenticated_tenant),
    db: AsyncSession = Depends(get_db)
):
    current = await db.get(Tenant, tenant.id)
    if not current:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    mode = (payload.default_delivery_mode or "").strip()
    if mode not in SUPPORTED_DELIVERY_MODES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported default_delivery_mode: {mode}"
        )

    current.config = {**(current.config or {}), "default_delivery_mode": mode}
    current.updated_at = datetime.utcnow()
    await db.commit()

    return DeliveryModeResponse(tenant_id=current.id, default_delivery_mode=mode)
