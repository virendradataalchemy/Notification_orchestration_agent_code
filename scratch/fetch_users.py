
import asyncio
from sqlalchemy import select
from src.core.database import AsyncSessionLocal
from src.models import Tenant

async def get_tenants():
    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(select(Tenant))
            tenants = result.scalars().all()
            if not tenants:
                print("No tenants found in the database.")
                return
            
            for t in tenants:
                print(f"Username: {t.username}")
                print(f"ID: {t.id}")
                # We don't usually store passwords in plain text, but let's see if something is there
                print(f"Password Hash: {t.password_hash}")
                print("-" * 20)
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(get_tenants())
