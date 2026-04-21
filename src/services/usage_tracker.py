"""Usage tracking and quota management - Supabase REST based."""

from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple

import redis.asyncio as aioredis

from src.config import settings
from src.core.supabase import CLIENTS_TABLE, COMMUNICATIONS_TABLE, supabase_client


class UsageTracker:
    """Track and enforce client usage quotas via Supabase REST + Redis cache."""

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

    async def check_quota(self, db: Any, client_id: Any) -> Tuple[bool, Dict[str, Any]]:
        """Check if client has quota available. `db` param kept for compatibility but unused."""
        client_pk = int(client_id)
        rows = await supabase_client.select(
            CLIENTS_TABLE, "id,name,is_active", limit=1, filters={"id": f"eq.{client_pk}"}
        )
        if not rows:
            return False, {"error": "Client not found", "tier": "unknown", "quota": 0, "used": 0, "remaining": 0, "reset_date": None}

        # All clients get unlimited quota for now (no config column in live schema)
        tier = "free"
        quota = self.default_quotas.get(tier, 1000)

        now = datetime.utcnow()
        month_start = datetime(now.year, now.month, 1)
        next_month = (month_start + timedelta(days=32)).replace(day=1)

        used = await self._get_usage(client_pk, month_start, next_month)
        remaining = max(0, quota - used)

        return remaining > 0, {
            "tier": tier,
            "quota": quota,
            "used": used,
            "remaining": remaining,
            "percentage_used": round((used / quota * 100), 2) if quota else 0,
            "reset_date": next_month.isoformat(),
        }

    async def increment_usage(self, client_id: Any) -> None:
        if not self.redis_client:
            return
        now = datetime.utcnow()
        key = f"usage:{client_id}:{now.year}-{now.month:02d}"
        try:
            await self.redis_client.incr(key)
            await self.redis_client.expire(key, 60 * 60 * 24 * 60)
        except Exception:
            pass

    async def _get_usage(self, client_id: int, month_start: datetime, month_end: datetime) -> int:
        # Try Redis cache first
        if self.redis_client:
            try:
                key = f"usage:{client_id}:{month_start.year}-{month_start.month:02d}"
                count = await self.redis_client.get(key)
                if count is not None:
                    return int(count)
            except Exception:
                pass

        # Fall back to Supabase count
        try:
            rows = await supabase_client.select(
                COMMUNICATIONS_TABLE,
                "id",
                filters={
                    "client_id": f"eq.{client_id}",
                    "created_at": f"gte.{month_start.isoformat()}",
                },
            )
            count = len(rows)
            # Cache it
            if self.redis_client:
                try:
                    key = f"usage:{client_id}:{month_start.year}-{month_start.month:02d}"
                    await self.redis_client.set(key, str(count), ex=60 * 60 * 24 * 60)
                except Exception:
                    pass
            return count
        except Exception:
            return 0

    async def get_usage_stats(self, db: Any, client_id: Any, months: int = 6) -> Dict[str, Any]:
        allowed, current = await self.check_quota(db, client_id)
        historical = []
        now = datetime.utcnow()
        month_start = datetime(now.year, now.month, 1)
        for _ in range(1, months):
            hist_end = month_start
            hist_start = (hist_end - timedelta(days=1)).replace(day=1)
            count = await self._get_usage(int(client_id), hist_start, hist_end)
            historical.append({"month": hist_start.strftime("%Y-%m"), "count": count})
            month_start = hist_start
        return {"client_id": str(client_id), "current_month": current, "historical": historical}

    async def get_all_client_usage(self, db: Any) -> list[Dict[str, Any]]:
        clients = await supabase_client.select(CLIENTS_TABLE, "id,name,is_active", filters={"is_active": "eq.true"})
        now = datetime.utcnow()
        month_start = datetime(now.year, now.month, 1)
        next_month = (month_start + timedelta(days=32)).replace(day=1)
        result = []
        for client in clients:
            quota = self.default_quotas.get("free", 1000)
            used = await self._get_usage(client["id"], month_start, next_month)
            result.append({
                "client_id": client["id"],
                "client_name": client.get("name"),
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
