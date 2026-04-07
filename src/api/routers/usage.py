"""Usage tracking API - Supabase REST based."""

from fastapi import APIRouter, Depends
from typing import Dict, List, Any
from pydantic import BaseModel

from src.api.dependencies import get_authenticated_tenant
from src.core.supabase import supabase_client
from src.models import Tenant
from src.services.usage_tracker import usage_tracker

router = APIRouter(prefix="/usage", tags=["usage"])


class UsageResponse(BaseModel):
    tier: str
    quota: Any
    used: int
    remaining: Any
    percentage_used: float
    reset_date: str


@router.get("/me", response_model=UsageResponse)
async def get_current_usage(tenant: Tenant = Depends(get_authenticated_tenant)):
    _, usage_info = await usage_tracker.check_quota(None, tenant.id)
    return UsageResponse(**usage_info)


@router.get("/me/stats")
async def get_usage_stats(months: int = 6, tenant: Tenant = Depends(get_authenticated_tenant)):
    return await usage_tracker.get_usage_stats(None, tenant.id, months)


@router.get("/me/check")
async def check_quota_available(tenant: Tenant = Depends(get_authenticated_tenant)):
    allowed, _ = await usage_tracker.check_quota(None, tenant.id)
    return {"allowed": allowed}


@router.get("/all")
async def get_all_tenant_usage():
    return await usage_tracker.get_all_tenant_usage(None)
