import asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.core import init_db, engine
from src.models import NotificationChannel

async def check():
    await init_db()
    async with AsyncSession(engine) as db:
        print("--- EMAIL STATUS ---")
        q_email = select(NotificationChannel).where(NotificationChannel.channel == 'email').order_by(NotificationChannel.created_at.desc()).limit(2)
        res_email = await db.execute(q_email)
        for r in res_email.scalars().all():
            print(f"ID: {r.id}, Status: {r.status}, Error: {r.error_message}")
            
        print("\n--- VOICE STATUS ---")
        q_voice = select(NotificationChannel).where(NotificationChannel.channel == 'voice').order_by(NotificationChannel.created_at.desc()).limit(2)
        res_voice = await db.execute(q_voice)
        for r in res_voice.scalars().all():
            print(f"ID: {r.id}, Status: {r.status}, Error: {r.error_message}")

if __name__ == "__main__":
    asyncio.run(check())
