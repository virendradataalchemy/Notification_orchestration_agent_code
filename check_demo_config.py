import asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.core import init_db, engine
from src.models import TenantProviderConfig

async def check_config():
    await init_db()
    async with AsyncSession(engine) as db:
        query = select(TenantProviderConfig).where(TenantProviderConfig.tenant_id == "demo_corp")
        result = await db.execute(query)
        rows = result.scalars().all()
        print(f"Configs for demo_corp: {len(rows)}")
        for row in rows:
            print(f"Provider: {row.provider}, Active: {row.is_active}, Config: {row.config}")

if __name__ == "__main__":
    asyncio.run(check_config())
