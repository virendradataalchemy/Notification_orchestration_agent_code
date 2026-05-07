import asyncio
from src.core.database import AsyncSessionLocal
from src.models import TenantUser
from sqlalchemy import select

async def check():
    async with AsyncSessionLocal() as db:
        res = await db.execute(select(TenantUser).where(TenantUser.tenant_id == 'demo_corp'))
        users = res.scalars().all()
        for u in users:
            print(f"User: {u.username}, Role: {u.role}, Email: {u.email}")

if __name__ == "__main__":
    asyncio.run(check())
