import os
import sqlalchemy
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

db_url = os.getenv("DATABASE_URL").replace("postgresql+asyncpg", "postgresql")

engine = create_engine(db_url)
with engine.begin() as conn:
    print("\n--- Failed Inbound Parsed Messages Details ---")
    res = conn.execute(text("SELECT id, raw_message_id, status, failure_reason FROM inbound_messages_parsed WHERE status = 'FAILED' ORDER BY created_at DESC LIMIT 5"))
    for row in res.mappings():
        print(dict(row))
