"""
Tenant management API endpoints.

Provides CRUD operations for tenant management, API key rotation,
provider configuration, and tenant settings.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, EmailStr
from datetime import datetime
import uuid

from src.core import get_db
from src.models import Tenant, TenantProviderConfig
from src.api.dependencies import get_authenticated_tenant, require_admin_access

router = APIRouter(prefix="/tenants", tags=["tenant-management"])


# Request/Response Schemas
class CreateTenantRequest(BaseModel):
    tenant_id: str
    name: str
    admin_email: EmailStr
    admin_name: Optional[str] = None
    config: Optional[Dict[str, Any]] = {}


class TenantResponse(BaseModel):
    id: str
    name: str
    status: str
    admin_email: Optional[str]
    admin_name: Optional[str]
    api_key_prefix: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class APIKeyResponse(BaseModel):
    api_key: str
    api_key_prefix: str
    message: str


class ProviderConfigRequest(BaseModel):
    provider: str
    config: Dict[str, Any]
    is_active: bool = True
    notes: Optional[str] = None


class ProviderConfigResponse(BaseModel):
    id: str
    provider: str
    config: Dict[str, Any]
    is_active: bool
    notes: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class UpdateTenantRequest(BaseModel):
    name: Optional[str] = None
    admin_email: Optional[EmailStr] = None
    admin_name: Optional[str] = None
    config: Optional[Dict[str, Any]] = None


# Endpoints

@router.post("/", response_model=APIKeyResponse, status_code=status.HTTP_201_CREATED)
async def create_tenant(
    request: CreateTenantRequest,
    _: bool = Depends(require_admin_access),
    db: AsyncSession = Depends(get_db)
) -> APIKeyResponse:
    """
    Create a new tenant.

    Generates API key and creates tenant record.

    **⚠️ Security**: This endpoint should be protected with admin authentication in production.
    """
    # Check if tenant already exists
    existing = await db.get(Tenant, request.tenant_id)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Tenant '{request.tenant_id}' already exists"
        )

    # Generate API key
    api_key, api_key_hash, api_key_prefix = Tenant.generate_api_key(
        request.tenant_id, env="live"
    )

    # Create tenant
    tenant = Tenant(
        id=request.tenant_id,
        name=request.name,
        status="active",
        api_key_hash=api_key_hash,
        api_key_prefix=api_key_prefix,
        admin_email=request.admin_email,
        admin_name=request.admin_name or request.name,
        config=request.config,
        tenant_metadata={"created_via": "api"}
    )

    db.add(tenant)
    await db.commit()

    return APIKeyResponse(
        api_key=api_key,
        api_key_prefix=api_key_prefix,
        message=f"Tenant '{request.tenant_id}' created successfully. Save this API key - it won't be shown again!"
    )


@router.get("/me", response_model=TenantResponse)
async def get_current_tenant(
    tenant: Tenant = Depends(get_authenticated_tenant),
    db: AsyncSession = Depends(get_db)
) -> TenantResponse:
    """
    Get current tenant information.

    Uses the authenticated tenant from the API key.
    """
    current_tenant = await db.get(Tenant, tenant.id)
    if not current_tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found"
        )

    return TenantResponse.from_orm(current_tenant)


@router.get("/{tenant_id}", response_model=TenantResponse)
async def get_tenant(
    tenant_id: str,
    _: bool = Depends(require_admin_access),
    db: AsyncSession = Depends(get_db)
) -> TenantResponse:
    """
    Get tenant by ID.

    **⚠️ Security**: Should be admin-only in production.
    """
    tenant = await db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant '{tenant_id}' not found"
        )

    return TenantResponse.from_orm(tenant)


@router.patch("/me", response_model=TenantResponse)
async def update_current_tenant(
    request: UpdateTenantRequest,
    tenant: Tenant = Depends(get_authenticated_tenant),
    db: AsyncSession = Depends(get_db)
) -> TenantResponse:
    """
    Update current tenant information.

    Allows tenant to update their own information.
    """
    current_tenant = await db.get(Tenant, tenant.id)
    if not current_tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found"
        )

    # Update fields
    if request.name is not None:
        current_tenant.name = request.name
    if request.admin_email is not None:
        current_tenant.admin_email = request.admin_email
    if request.admin_name is not None:
        current_tenant.admin_name = request.admin_name
    if request.config is not None:
        current_tenant.config = {**(current_tenant.config or {}), **request.config}

    current_tenant.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(current_tenant)

    return TenantResponse.from_orm(current_tenant)


@router.post("/me/rotate-api-key", response_model=APIKeyResponse)
async def rotate_api_key(
    tenant: Tenant = Depends(get_authenticated_tenant),
    db: AsyncSession = Depends(get_db)
) -> APIKeyResponse:
    """
    Rotate tenant's API key.

    Generates new API key and invalidates the old one.
    """
    current_tenant = await db.get(Tenant, tenant.id)
    if not current_tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found"
        )

    # Generate new API key
    api_key, api_key_hash, api_key_prefix = Tenant.generate_api_key(
        tenant.id, env="live"
    )

    # Update tenant
    current_tenant.api_key_hash = api_key_hash
    current_tenant.api_key_prefix = api_key_prefix
    current_tenant.updated_at = datetime.utcnow()

    await db.commit()

    return APIKeyResponse(
        api_key=api_key,
        api_key_prefix=api_key_prefix,
        message="API key rotated successfully. Update your application with the new key immediately!"
    )


@router.delete("/me", status_code=status.HTTP_200_OK)
async def delete_current_tenant(
    tenant: Tenant = Depends(get_authenticated_tenant),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, str]:
    """
    Delete (soft delete) current tenant.

    Marks tenant as deleted and blocks API access.
    """
    current_tenant = await db.get(Tenant, tenant.id)
    if not current_tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found"
        )

    # Soft delete
    current_tenant.status = "deleted"
    current_tenant.deleted_at = datetime.utcnow()

    await db.commit()

    return {
        "message": f"Tenant '{tenant.id}' has been deleted. API access is now blocked."
    }


# Provider Configuration Endpoints

@router.post("/me/providers", response_model=ProviderConfigResponse, status_code=status.HTTP_201_CREATED)
async def add_provider_config(
    request: ProviderConfigRequest,
    tenant: Tenant = Depends(get_authenticated_tenant),
    db: AsyncSession = Depends(get_db)
) -> ProviderConfigResponse:
    """
    Add or update provider configuration for current tenant.

    Examples:
    - Slack: {"channel_id": "#notifications", "webhook_url": "https://..."}
    - Email: {"from_name": "Company Name", "reply_to": "support@company.com"}
    - SMS: {"sender_id": "COMPANY"}
    - Template refs (internal->provider): {"template_refs": {"order_update": "HXXXXXXXXXXXXXXXX"}}
    """
    # Check if config already exists
    query = select(TenantProviderConfig).where(
        TenantProviderConfig.tenant_id == tenant.id,
        TenantProviderConfig.provider == request.provider
    )
    result = await db.execute(query)
    existing = result.scalar_one_or_none()

    if existing:
        # Update existing
        existing.config = request.config
        existing.is_active = request.is_active
        existing.notes = request.notes
        existing.updated_at = datetime.utcnow()
        config = existing
    else:
        # Create new
        config = TenantProviderConfig(
            id=f"{tenant.id}_{request.provider}_{uuid.uuid4().hex[:8]}",
            tenant_id=tenant.id,
            provider=request.provider,
            config=request.config,
            is_active=request.is_active,
            notes=request.notes
        )
        db.add(config)

    await db.commit()
    await db.refresh(config)

    return ProviderConfigResponse.from_orm(config)


@router.get("/me/providers", response_model=List[ProviderConfigResponse])
async def list_provider_configs(
    tenant: Tenant = Depends(get_authenticated_tenant),
    db: AsyncSession = Depends(get_db)
) -> List[ProviderConfigResponse]:
    """
    List all provider configurations for current tenant.
    """
    query = select(TenantProviderConfig).where(
        TenantProviderConfig.tenant_id == tenant.id
    ).order_by(TenantProviderConfig.provider)

    result = await db.execute(query)
    configs = result.scalars().all()

    return [ProviderConfigResponse.from_orm(c) for c in configs]


@router.get("/me/providers/{provider}", response_model=ProviderConfigResponse)
async def get_provider_config(
    provider: str,
    tenant: Tenant = Depends(get_authenticated_tenant),
    db: AsyncSession = Depends(get_db)
) -> ProviderConfigResponse:
    """
    Get specific provider configuration.
    """
    query = select(TenantProviderConfig).where(
        TenantProviderConfig.tenant_id == tenant.id,
        TenantProviderConfig.provider == provider
    )
    result = await db.execute(query)
    config = result.scalar_one_or_none()

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider configuration '{provider}' not found"
        )

    return ProviderConfigResponse.from_orm(config)


@router.delete("/me/providers/{provider}", status_code=status.HTTP_200_OK)
async def delete_provider_config(
    provider: str,
    tenant: Tenant = Depends(get_authenticated_tenant),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, str]:
    """
    Delete provider configuration.
    """
    query = select(TenantProviderConfig).where(
        TenantProviderConfig.tenant_id == tenant.id,
        TenantProviderConfig.provider == provider
    )
    result = await db.execute(query)
    config = result.scalar_one_or_none()

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider configuration '{provider}' not found"
        )

    await db.delete(config)
    await db.commit()

    return {
        "message": f"Provider configuration '{provider}' deleted successfully"
    }
