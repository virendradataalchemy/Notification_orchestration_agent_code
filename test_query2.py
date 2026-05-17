import asyncio
from sqlalchemy import text
from src.core.database import AsyncSessionLocal

async def main():
    async with AsyncSessionLocal() as session:
        try:
            query = text("""
            SELECT NULL::jsonb->'channel_content_map'->'email'->>'body'
            """)
            await session.execute(query)
            print("Query executed successfully")
        except Exception as e:
            print(f"Error executing query: {e}")

if __name__ == "__main__":
    asyncio.run(main())