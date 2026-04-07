"""Usage tracking and quota management - Supabase REST based."""

from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple

import redis.asyncio as aioredis

from src.config import settings
from src.core.supabase import supabase_client


class UsageTracker:
    """Track and enforce tenant usage quotas via Supabase REST + Redis cache."""

    def __init__(self):
        self.redis_client: Optional[aioredis.Redis] = None
        self.default_quotas = {
            "free": 1000,
            "basic": 10000,
            "pro": 50000,
            "enterprise": None,  # unlimited
        }

    async def initialize(self):
        try:
            self.redis_client = await aioredis.from_url(
                settings.redis_url, encoding="utf-8", decode_responses=True
            )
        except Exception:
            self.redis_client = None

    async def check_quota(self, db: Any, tenant_id: Any) -> Tuple[bool, Dict[str, Any]]:
        """Check if tenant has quota available. `db` param kept for compatibility but unused."""
        tenant_pk = int(tenant_id)
        rows = await supabase_client.select(
            "tenants", "id,name,is_active", limit=1, filters={"id": f"eq.{tenant_pk}"}
        )
        if not rows:
            return False, {"error": "Tenant not found", "tier": "unknown", "quota": 0, "used": 0, "remaining": 0, "reset_date": None}

        # All tenants get unlimited quota for now (no config column in live schema)
        tier = "free"
        quota = self.default_quotas.get(tier, 1000)

        now = datetime.utcnow()
        month_start = datetime(now.year, now.month, 1)
        next_month = (month_start + timedelta(days=32)).replace(day=1)

        used = await self._get_usage(tenant_pk, month_start, next_month)
        remaining = max(0, quota - used)

        return remaining > 0, {
            "tier": tier,
            "quota": quota,
            "used": used,
            "remaining": remaining,
            "percentage_used": round((used / quota * 100), 2) if quota else 0,
            "reset_date": next_month.isoformat(),
        }

    async def increment_usage(self, tenant_id: Any) -> None:
        if not self.redis_client:
            return
        now = datetime.utcnow()
        key = f"usage:{tenant_id}:{now.year}-{now.month:02d}"
        try:
            await self.redis_client.incr(key)
            await self.redis_client.expire(key, 60 * 60 * 24 * 60)
        except Exception:
            pass

    async def _get_usage(self, tenant_id: int, month_start: datetime, month_end: datetime) -> int:
        # Try Redis cache first
        if self.redis_client:
            try:
                key = f"usage:{tenant_id}:{month_start.year}-{month_start.month:02d}"
                count = await self.redis_client.get(key)
                if count is not None:
                    return int(count)
            except Exception:
                pass

        # Fall back to Supabase count
        try:
            rows = await supabase_client.select(
                "communications",
                "id",
                filters={
                    "tenant_id": f"eq.{tenant_id}",
                    "created_at": f"gte.{month_start.isoformat()}",
                },
            )
            count = len(rows)
            # Cache it
            if self.redis_client:
                try:
                    key = f"usage:{tenant_id}:{month_start.year}-{month_start.month:02d}"
                    await self.redis_client.set(key, str(count), ex=60 * 60 * 24 * 60)
                except Exception:
                    pass
            return count
        except Exception:
            return 0

    async def get_usage_stats(self, db: Any, tenant_id: Any, months: int = 6) -> Dict[str, Any]:
        allowed, current = await self.check_quota(db, tenant_id)
        historical = []
        now = datetime.utcnow()
        month_start = datetime(now.year, now.month, 1)
        for _ in range(1, months):
            hist_end = month_start
            hist_start = (hist_end - timedelta(days=1)).replace(day=1)
            count = await self._get_usage(int(tenant_id), hist_start, hist_end)
            historical.append({"month": hist_start.strftime("%Y-%m"), "count": count})
            month_start = hist_start
        return {"tenant_id": str(tenant_id), "current_month": current, "historical": historical}

    async def get_all_tenant_usage(self, db: Any) -> list[Dict[str, Any]]:
        tenants = await supabase_client.select("tenants", "id,name,is_active", filters={"is_active": "eq.true"})
        now = datetime.utcnow()
        month_start = datetime(now.year, now.month, 1)
        next_month = (month_start + timedelta(days=32)).replace(day=1)
        result = []
        for tenant in tenants:
            quota = self.default_quotas.get("free", 1000)
            used = await self._get_usage(tenant["id"], month_start, next_month)
            result.append({
                "tenant_id": tenant["id"],
                "tenant_name": tenant.get("name"),
                "tier": "free",
                "quota": quota,
                "used": used,
                "remaining": max(0, quota - used),
                "percentage": round((used / quota * 100), 2) if quota else 0,
            })
        return result


usage_tracker = UsageTracker()


async def initialize_usage_tracker():
    await usage_tracker.initialize()
