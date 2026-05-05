import asyncio
from src.core.database import AsyncSessionLocal
from src.models import Tenant
from sqlalchemy import select

async def update_api_key():
    async with AsyncSessionLocal() as db:
        tenant_id = "demo_corp"
        result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
        tenant = result.scalar_one_or_none()
        if not tenant:
            print("Tenant not found.")
            return

        api_key, api_key_hash, api_key_prefix = Tenant.generate_api_key(tenant_id, env="live")
        tenant.api_key_hash = api_key_hash
        tenant.api_key_prefix = api_key_prefix
        
        db.add(tenant)
        await db.commit()
        print(f"NEW_API_KEY={api_key}")

if __name__ == "__main__":
    asyncio.run(update_api_key())
