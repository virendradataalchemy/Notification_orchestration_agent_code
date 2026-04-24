import asyncio
import os
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

async def cleanup():
    print(f"Cleaning database: {DATABASE_URL}")
    engine = create_async_engine(DATABASE_URL)
    
    async with engine.begin() as conn:
        # asyncpg requires multiple commands to be executed separately
        commands = [
            "DROP SCHEMA public CASCADE",
            "CREATE SCHEMA public",
            "GRANT ALL ON SCHEMA public TO postgres",
            "GRANT ALL ON SCHEMA public TO public"
        ]
        for cmd in commands:
            await conn.execute(text(cmd))
            print(f"Executed: {cmd}")
            
        print("Dropped and recreated 'public' schema.")
    
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(cleanup())
