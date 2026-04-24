"""
Usage tracking and quota management API endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, List, Any
from pydantic import BaseModel

from src.core import get_db
from src.api.dependencies import get_authenticated_tenant, require_admin_access
from src.models import Tenant
from src.services.usage_tracker import usage_tracker

router = APIRouter(prefix="/usage", tags=["usage"])


class UsageResponse(BaseModel):
    tier: str
    quota: Any  # Can be int or "unlimited"
    used: int
    remaining: Any  # Can be int or "unlimited"
    percentage_used: float
    reset_date: str


class UsageStatsResponse(BaseModel):
    tenant_id: str
    current_month: Dict[str, Any]
    historical: List[Dict[str, Any]]


@router.get("/me", response_model=UsageResponse)
async def get_current_usage(
    tenant: Tenant = Depends(get_authenticated_tenant),
    db: AsyncSession = Depends(get_db)
) -> UsageResponse:
    """
    Get current tenant's usage and quota information.

    Returns:
    - Current tier
    - Monthly quota
    - Notifications used this month
    - Remaining quota
    - Usage percentage
    - Reset date (start of next month)
    """
    allowed, usage_info = await usage_tracker.check_quota(db, tenant.id)

    if "error" in usage_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=usage_info["error"]
        )

    return UsageResponse(**usage_info)


@router.get("/me/stats", response_model=UsageStatsResponse)
async def get_usage_stats(
    months: int = 6,
    tenant: Tenant = Depends(get_authenticated_tenant),
    db: AsyncSession = Depends(get_db)
) -> UsageStatsResponse:
    """
    Get detailed usage statistics for current tenant.

    Query parameters:
    - months: Number of historical months to include (default: 6, max: 12)

    Returns:
    - Current month usage
    - Historical usage for past N months
    """
    if months > 12:
        months = 12

    stats = await usage_tracker.get_usage_stats(db, tenant.id, months)

    return UsageStatsResponse(**stats)


@router.get("/me/check", response_model=Dict[str, bool])
async def check_quota_available(
    tenant: Tenant = Depends(get_authenticated_tenant),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, bool]:
    """
    Quick check if tenant has quota available.

    Returns:
    - allowed: True if tenant can send more notifications
    """
    allowed, _ = await usage_tracker.check_quota(db, tenant.id)

    return {"allowed": allowed}


@router.get("/all", response_model=List[Dict[str, Any]])
async def get_all_tenant_usage(
    _: bool = Depends(require_admin_access),
    db: AsyncSession = Depends(get_db)
) -> List[Dict[str, Any]]:
    """
    Get usage statistics for all tenants.

    **⚠️ Admin only** - This endpoint should be protected with admin authentication.

    Returns list of all tenants with their usage statistics.
    """
    usage_list = await usage_tracker.get_all_tenant_usage(db)

    return usage_list
