import asyncio
from sqlalchemy import text
from src.core.database import AsyncSessionLocal
import json

async def main():
    async with AsyncSessionLocal() as session:
        try:
            print("Fetching inbound messages...")
            query = text("""
            SELECT m.id, m.created_at, m.sender_address, m.channel, m.tenant_id, p.parsed_content 
            FROM inbound_messages_raw m
            LEFT JOIN inbound_messages_parsed p ON m.id = p.raw_message_id
            ORDER BY m.created_at DESC LIMIT 5
            """)
            result = await session.execute(query)
            inbound = [dict(row._mapping) for row in result]
            for row in inbound:
                row['id'] = str(row['id'])
                row['created_at'] = str(row['created_at'])
            
            print("Fetching outbound messages...")
            query2 = text("""
            SELECT n.id, n.created_at, n.data, nc.channel, n.tenant_id
            FROM notifications n
            JOIN notification_channels nc ON nc.notification_id = n.id
            ORDER BY n.created_at DESC LIMIT 5
            """)
            result2 = await session.execute(query2)
            outbound = [dict(row._mapping) for row in result2]
            for row in outbound:
                row['id'] = str(row['id'])
                row['created_at'] = str(row['created_at'])
                
            with open("test_db_output.json", "w") as f:
                json.dump({"inbound": inbound, "outbound": outbound}, f, indent=2)
            print("Success. Saved to test_db_output.json")
        except Exception as e:
            print(f"Error executing query: {e}")

if __name__ == "__main__":
    asyncio.run(main())