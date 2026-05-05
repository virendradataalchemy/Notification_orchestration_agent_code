import os
import asyncio
import asyncpg
from dotenv import load_dotenv

# Load from .env file
load_dotenv()

async def test_conn():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("Error: DATABASE_URL not found in .env")
        return

    print(f"Attempting to connect to: {db_url.split('@')[-1]}") # Print host/db only for security
    
    try:
        # Convert sqlalchemy style to asyncpg style if needed
        # (Though we already have asyncpg in the URL)
        conn = await asyncpg.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
        try:
            version = await conn.fetchval("SELECT version()")
            print(f"Success! Database Version: {version}")
            
            # Check for existing tables
            tables = await conn.fetch("SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname = 'public'")
            print(f"Tables currently in 'public' schema: {[t['tablename'] for t in tables]}")
            
        finally:
            await conn.close()
    except Exception as e:
        print(f"Connection failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_conn())
