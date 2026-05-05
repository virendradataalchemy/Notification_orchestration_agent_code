import asyncio
import os
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from dotenv import load_dotenv

load_dotenv()
db_url = os.getenv("DATABASE_URL")
if "?prepared_statement_cache_size=" not in db_url:
    db_url += "?prepared_statement_cache_size=0"

async def test():
    engine = create_async_engine(db_url)
    async with engine.connect() as conn:
        res = await conn.execute(text("SELECT id, tenant_id, email, username, is_active FROM tenant_users WHERE email = 'gaur.prateek.1609@gmail.com'"))
        rows = res.fetchall()
        print("Users:")
        for row in rows:
            print(dict(row._mapping))
            
        res2 = await conn.execute(text("SELECT id, tenant_id, email, status FROM tenant_invitations WHERE email = 'gaur.prateek.1609@gmail.com'"))
        rows2 = res2.fetchall()
        print("\nInvitations:")
        for row in rows2:
            print(dict(row._mapping))

asyncio.run(test())