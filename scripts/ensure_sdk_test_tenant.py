"""
Create or update the `demo_corp` row (same id as ``scripts/seed_tenant.py``).

Sets tier to **pro** and clears a zero ``monthly_quota`` so development sends work.

Run from repo root (after .env is configured):

    python scripts/ensure_sdk_test_tenant.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Repo root on path for `src` imports
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
except ImportError:
    pass
else:
    load_dotenv(ROOT / ".env")
    load_dotenv(ROOT / ".env.local", override=True)

from sqlalchemy import select

from src.core.database import AsyncSessionLocal
from src.models import Tenant


TENANT_ID = "demo_corp"


async def main() -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Tenant).where(Tenant.id == TENANT_ID))
        tenant = result.scalar_one_or_none()

        if tenant is None:
            api_key, api_key_hash, api_key_prefix = Tenant.generate_api_key(TENANT_ID, env="live")
            tenant = Tenant(
                id=TENANT_ID,
                name="Demo Corporation",
                status="active",
                username="admin",
                password_hash=Tenant.hash_password("Password123!"),
                api_key_hash=api_key_hash,
                api_key_prefix=api_key_prefix,
                admin_email="admin@demo.corp",
                admin_name="Demo Admin",
                config={
                    "tier": "pro",
                },
            )
            db.add(tenant)
            await db.commit()
            print(f"Created tenant {TENANT_ID} (tier=pro). API key (save it): {api_key}")
            return

        cfg = dict(tenant.config or {})
        cfg["tier"] = "pro"
        # Drop zero / stale cap so development Pro-unlimited applies
        if cfg.get("monthly_quota") in (0, "0"):
            cfg.pop("monthly_quota", None)
        tenant.config = cfg
        tenant.status = "active"
        await db.commit()
        print(f"Updated tenant {TENANT_ID} to tier=pro (cleared monthly_quota if it was 0).")
        print("Existing API key unchanged; create a new key from the admin UI if needed.")


if __name__ == "__main__":
    asyncio.run(main())
