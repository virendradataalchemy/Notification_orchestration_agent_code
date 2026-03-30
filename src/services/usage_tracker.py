"""
Usage tracking and quota management for multi-tenant system.

Tracks notification usage per tenant and enforces quotas.
"""

from datetime import datetime, timedelta
from typing import Dict, Optional
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis

from src.models import Notification, Tenant
from src.config import settings


class UsageTracker:
    """Track and enforce tenant usage quotas."""

    def __init__(self):
        self.redis_client: Optional[aioredis.Redis] = None

        # Default quotas by tier (notifications per month)
        self.default_quotas = {
            "free": 1000,
            "basic": 10000,
            "pro": 50000,
            "enterprise": None  # Unlimited
        }

    async def initialize(self):
        """Initialize Redis connection for rate limiting."""
        try:
            self.redis_client = await aioredis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True
            )
        except Exception:
            # Redis is optional, will fall back to database
            self.redis_client = None

    async def check_quota(
        self,
        db: AsyncSession,
        tenant_id: str
    ) -> tuple[bool, Dict[str, any]]:
        """
        Check if tenant has quota available.

        Args:
            db: Database session
            tenant_id: Tenant identifier

        Returns:
            Tuple of (allowed, usage_info)
            - allowed: bool, whether tenant can send more notifications
            - usage_info: dict with usage statistics
        """
        # Get tenant
        tenant = await db.get(Tenant, tenant_id)
        if not tenant:
            return False, {
                "error": "Tenant not found",
                "tier": "unknown",
                "quota": 0,
                "used": 0,
                "remaining": 0,
                "reset_date": None
            }

        # Get tenant's tier/quota from config
        config = tenant.config or {}
        tier = config.get("tier", "free")
        custom_quota = config.get("monthly_quota")

        # Determine quota
        quota = custom_quota if custom_quota is not None else self.default_quotas.get(tier)

        # Enterprise tier (unlimited)
        if quota is None:
            return True, {
                "tier": tier,
                "quota": "unlimited",
                "used": 0,
                "remaining": "unlimited",
                "reset_date": None
            }

        # Get usage for current month
        now = datetime.utcnow()
        month_start = datetime(now.year, now.month, 1)
        next_month = (month_start + timedelta(days=32)).replace(day=1)

        # Try Redis first (faster)
        if self.redis_client:
            try:
                used = await self._get_usage_from_redis(tenant_id, month_start)
            except Exception:
                used = await self._get_usage_from_db(db, tenant_id, month_start, next_month)
        else:
            used = await self._get_usage_from_db(db, tenant_id, month_start, next_month)

        remaining = max(0, quota - used)
        allowed = remaining > 0

        return allowed, {
            "tier": tier,
            "quota": quota,
            "used": used,
            "remaining": remaining,
            "percentage_used": round((used / quota * 100), 2) if quota > 0 else 0,
            "reset_date": next_month.isoformat()
        }

    async def increment_usage(
        self,
        tenant_id: str
    ):
        """
        Increment tenant's usage counter.

        Args:
            tenant_id: Tenant identifier
        """
        if not self.redis_client:
            return  # Will be counted from database

        now = datetime.utcnow()
        month_key = f"{now.year}-{now.month:02d}"
        redis_key = f"usage:{tenant_id}:{month_key}"

        try:
            # Increment counter
            await self.redis_client.incr(redis_key)

            # Set expiry (2 months from now to be safe)
            await self.redis_client.expire(redis_key, 60 * 60 * 24 * 60)
        except Exception:
            pass  # Fail silently, will fall back to database

    async def _get_usage_from_redis(
        self,
        tenant_id: str,
        month_start: datetime
    ) -> int:
        """Get usage count from Redis cache."""
        month_key = f"{month_start.year}-{month_start.month:02d}"
        redis_key = f"usage:{tenant_id}:{month_key}"

        count = await self.redis_client.get(redis_key)
        return int(count) if count else 0

    async def _get_usage_from_db(
        self,
        db: AsyncSession,
        tenant_id: str,
        month_start: datetime,
        month_end: datetime
    ) -> int:
        """Get usage count from database."""
        query = select(func.count(Notification.id)).where(
            and_(
                Notification.tenant_id == tenant_id,
                Notification.created_at >= month_start,
                Notification.created_at < month_end
            )
        )

        result = await db.execute(query)
        count = result.scalar()

        # Cache in Redis for future queries
        if self.redis_client and count is not None:
            try:
                month_key = f"{month_start.year}-{month_start.month:02d}"
                redis_key = f"usage:{tenant_id}:{month_key}"
                await self.redis_client.set(redis_key, str(count), ex=60 * 60 * 24 * 60)
            except Exception:
                pass

        return count or 0

    async def get_usage_stats(
        self,
        db: AsyncSession,
        tenant_id: str,
        months: int = 6
    ) -> Dict[str, any]:
        """
        Get detailed usage statistics for tenant.

        Args:
            db: Database session
            tenant_id: Tenant identifier
            months: Number of months to include

        Returns:
            Dict with usage statistics
        """
        now = datetime.utcnow()
        stats = {
            "tenant_id": tenant_id,
            "current_month": {},
            "historical": []
        }

        # Current month
        month_start = datetime(now.year, now.month, 1)
        next_month = (month_start + timedelta(days=32)).replace(day=1)

        allowed, usage_info = await self.check_quota(db, tenant_id)
        stats["current_month"] = usage_info

        # Historical data
        for i in range(1, months):
            hist_end = month_start
            hist_start = (hist_end - timedelta(days=1)).replace(day=1)

            count = await self._get_usage_from_db(db, tenant_id, hist_start, hist_end)

            stats["historical"].append({
                "month": hist_start.strftime("%Y-%m"),
                "count": count
            })

            month_start = hist_start

        return stats

    async def set_tenant_quota(
        self,
        db: AsyncSession,
        tenant_id: str,
        quota: Optional[int],
        tier: Optional[str] = None
    ):
        """
        Set custom quota for tenant.

        Args:
            db: Database session
            tenant_id: Tenant identifier
            quota: Monthly quota (None for unlimited)
            tier: Tier name (optional)
        """
        tenant = await db.get(Tenant, tenant_id)
        if not tenant:
            raise ValueError(f"Tenant {tenant_id} not found")

        config = tenant.config or {}
        config["monthly_quota"] = quota

        if tier:
            config["tier"] = tier

        tenant.config = config
        tenant.updated_at = datetime.utcnow()

        await db.commit()

    async def get_all_tenant_usage(
        self,
        db: AsyncSession
    ) -> list[Dict[str, any]]:
        """
        Get usage statistics for all tenants (admin function).

        Returns:
            List of tenant usage stats
        """
        # Get all active tenants
        query = select(Tenant).where(Tenant.status == "active")
        result = await db.execute(query)
        tenants = result.scalars().all()

        now = datetime.utcnow()
        month_start = datetime(now.year, now.month, 1)
        next_month = (month_start + timedelta(days=32)).replace(day=1)

        usage_list = []

        for tenant in tenants:
            config = tenant.config or {}
            tier = config.get("tier", "free")
            quota = config.get("monthly_quota") or self.default_quotas.get(tier)

            # Get usage
            used = await self._get_usage_from_db(db, tenant.id, month_start, next_month)

            remaining = None
            if quota is not None:
                remaining = max(0, quota - used)

            usage_list.append({
                "tenant_id": tenant.id,
                "tenant_name": tenant.name,
                "tier": tier,
                "quota": quota if quota is not None else "unlimited",
                "used": used,
                "remaining": remaining if remaining is not None else "unlimited",
                "percentage": round((used / quota * 100), 2) if quota else 0
            })

        return usage_list


# Singleton instance
usage_tracker = UsageTracker()


async def initialize_usage_tracker():
    """Initialize the usage tracker."""
    await usage_tracker.initialize()
