import asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.core import init_db, engine
from src.models import NotificationChannel

async def check():
    await init_db()
    async with AsyncSession(engine) as db:
        q = select(NotificationChannel).where(NotificationChannel.channel == 'email').order_by(NotificationChannel.created_at.desc()).limit(2)
        res = await db.execute(q)
        rows = res.scalars().all()
        print(f"Found {len(rows)} email records")
        for r in rows:
            print(f"ID: {r.id}, Status: {r.status}, Error: {r.error_message}, Created: {r.created_at}")

if __name__ == "__main__":
    asyncio.run(check())
