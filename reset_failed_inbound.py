import os
import sqlalchemy
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

db_url = os.getenv("DATABASE_URL").replace("postgresql+asyncpg", "postgresql")

engine = create_engine(db_url)
with engine.begin() as conn:
    print("--- Queueing Failed Messages for Retry ---")
    res = conn.execute(text("SELECT r.id, p.id as parsed_id FROM inbound_messages_raw r LEFT JOIN inbound_messages_parsed p ON r.id = p.raw_message_id WHERE p.status = 'FAILED'"))
    
    # Delete the failed parsed records so the pipeline recreates them cleanly
    conn.execute(text("DELETE FROM inbound_messages_parsed WHERE status = 'FAILED'"))
    print("Deleted failed parsed records.")
