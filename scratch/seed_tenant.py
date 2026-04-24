
import asyncio
from src.core.database import AsyncSessionLocal
from src.models import Tenant
from src.config import settings

async def seed_test_tenant():
    async with AsyncSessionLocal() as db:
        tenant_id = "demo_corp"
        username = "admin"
        password = "Password123!"
        
        # Check if exists
        from sqlalchemy import select
        result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
        if result.scalar_one_or_none():
            print(f"Tenant {tenant_id} already exists.")
            return

        # Generate API key
        api_key, api_key_hash, api_key_prefix = Tenant.generate_api_key(tenant_id, env="live")
        
        # Use the key from demo script if possible, or just generate a new one
        # The demo script has: sk_live_demo_corp_m1UxVyIM67QKaSxTTGYqg244DObbChfZ78Te09o7Wy0
        # But Tenant.generate_api_key creates its own. 
        # Let's just create a standard one.

        tenant = Tenant(
            id=tenant_id,
            name="Demo Corporation",
            status="active",
            username=username,
            password_hash=Tenant.hash_password(password),
            api_key_hash=api_key_hash,
            api_key_prefix=api_key_prefix,
            admin_email="admin@demo.corp",
            admin_name="Demo Admin",
            config={"tier": "pro"},
        )
        
        db.add(tenant)
        await db.commit()
        
        print(f"Test Tenant Created!")
        print(f"Username: {username}")
        print(f"Password: {password}")
        print(f"Tenant ID: {tenant_id}")
        print(f"API Key: {api_key}")

if __name__ == "__main__":
    asyncio.run(seed_test_tenant())
