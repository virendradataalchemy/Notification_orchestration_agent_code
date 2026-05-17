import asyncio
from sqlalchemy import text
from src.core.database import AsyncSessionLocal
import json

async def main():
    async with AsyncSessionLocal() as session:
        try:
            tenant_id = "demo_corp"
            query = text("""
            WITH outbound_page AS (
                SELECT 
                    n.id as id,
                    n.created_at as timestamp,
                    n.user_id as recipient_id,
                    n.data->>'email' as recipient_email,
                    n.data->>'phone' as recipient_phone,
                    COALESCE(
                        NULLIF(n.data->>'body', ''),
                        NULLIF(n.data->'channel_content_map'->CAST(nc.channel AS TEXT)->>'body', ''),
                        NULLIF(n.data->'channel_content_map'->CAST(nc.channel AS TEXT)->>'subject', ''),
                        NULLIF(n.data->>'subject', ''),
                        NULLIF(n.template_id, ''),
                        '(' || n.type || ')'
                    ) as content,
                    nc.channel as channel,
                    nc.status as status,
                    nc.opened_at as opened_at,
                    nc.clicked_at as clicked_at
                FROM notifications n
                JOIN notification_channels nc ON nc.notification_id = n.id
                WHERE n.tenant_id = :tenant_id
                ORDER BY n.created_at DESC
                LIMIT :limit
            ),
            inbound_candidates AS (
                SELECT 
                    m.id as id,
                    m.created_at as timestamp,
                    m.sender_address as sender,
                    COALESCE(p.parsed_content, m.raw_payload->>'body', m.raw_payload->>'text', m.raw_payload->>'stripped-text') as content,
                    CAST(m.channel AS TEXT) as channel,
                    p.status as status,
                    m.tenant_id,
                    ii.intent as ai_intent,
                    ii.confidence as ai_confidence,
                    ii.rationale as ai_rationale
                FROM inbound_messages_raw m
                LEFT JOIN inbound_messages_parsed p ON m.id = p.raw_message_id
                LEFT JOIN inbound_intents ii ON p.id = ii.parsed_message_id
                WHERE m.tenant_id = :tenant_id
                -- Only consider inbound messages newer than the oldest outbound message on this page
                -- REMOVED FOR TESTING: AND m.created_at >= COALESCE((SELECT MIN(timestamp) FROM outbound_page), '1970-01-01'::timestamp)
            ),
            inbound_mapped AS (
                SELECT 
                    i.*,
                    (
                        SELECT n2.id
                        FROM notifications n2
                        JOIN notification_channels nc2 ON nc2.notification_id = n2.id
                        WHERE n2.tenant_id = :tenant_id
                        -- RELAXED FOR TESTING: AND n2.created_at <= i.timestamp
                        -- AND n2.created_at >= i.timestamp - INTERVAL '30 days'
                        AND LOWER(CAST(nc2.channel AS TEXT)) = LOWER(CAST(i.channel AS TEXT))
                        AND (
                            (LOWER(CAST(i.channel AS TEXT)) = 'email' AND n2.data->>'email' = i.sender)
                            OR (LOWER(CAST(i.channel AS TEXT)) IN ('sms', 'whatsapp', 'voice') AND (n2.data->>'phone' = i.sender OR 'whatsapp:' || (n2.data->>'phone') = i.sender OR n2.data->>'phone' = REPLACE(i.sender, 'whatsapp:', '')))
                            OR n2.user_id = i.sender
                        )
                        ORDER BY n2.created_at DESC
                        LIMIT 1
                    ) as matched_out_id
                FROM inbound_candidates i
            )
            SELECT 
                o.id as out_id,
                o.timestamp as out_time,
                COALESCE(o.recipient_email, o.recipient_phone, o.recipient_id) as recipient,
                o.channel as channel,
                i.id as in_id,
                i.timestamp as in_time,
                i.content as in_content
            FROM outbound_page o
            LEFT JOIN inbound_mapped i ON i.matched_out_id = o.id AND LOWER(CAST(i.channel AS TEXT)) = LOWER(CAST(o.channel AS TEXT))
            ORDER BY o.timestamp DESC
            """)
            result = await session.execute(query, {"tenant_id": tenant_id, "limit": 50})
            rows = [dict(row._mapping) for row in result]
            for row in rows:
                row['out_id'] = str(row['out_id'])
                row['out_time'] = str(row['out_time'])
                if row['in_id']:
                    row['in_id'] = str(row['in_id'])
                    row['in_time'] = str(row['in_time'])
            
            with open("test_query_output.json", "w") as f:
                json.dump(rows, f, indent=2)
            print("Query executed successfully. Saved to test_query_output.json")
        except Exception as e:
            print(f"Error executing query: {e}")

if __name__ == "__main__":
    asyncio.run(main())