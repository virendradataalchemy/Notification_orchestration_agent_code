import asyncio
import json
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from src.api.routers.tenant_dashboard import get_marketing_threaded_activity
from sqlalchemy import text

async def main():
    engine = create_async_engine("postgresql+asyncpg://prateek:prateek@localhost:5432/notification_db")
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    class MockTenant:
        current_user_id = "00000000-0000-0000-0000-000000000000"
        current_user_role = "admin"
        is_platform_admin = False

    async with async_session() as db:
        try:
            result = await get_marketing_threaded_activity(
                tenant_id="demo_corp",
                tenant=MockTenant(),
                db=db,
                limit=50
            )
            # Find the ones with inbound
            matches = [t for t in result["threads"] if t.get("inbound")]
            print(f"Total threads: {len(result['threads'])}")
            print(f"Total matches: {len(matches)}")
            print("Matches:")
            print(json.dumps(matches, indent=2))
        except Exception as e:
            print("Error:", e)

if __name__ == "__main__":
    asyncio.run(main())