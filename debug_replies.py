"""
Debug script to check why replies aren't showing in the dashboard.
Run this on AWS: python3 debug_replies.py
"""
import asyncio
from sqlalchemy import text
from src.core.database import AsyncSessionLocal

async def debug_replies():
    async with AsyncSessionLocal() as db:
        # Get your tenant_id - replace with actual tenant ID
        tenant_id = input("Enter your tenant_id: ").strip()
        
        print("\n" + "="*80)
        print("1. CHECKING RECENT OUTBOUND NOTIFICATIONS")
        print("="*80)
        
        outbound_query = text("""
            SELECT 
                n.id::text as notification_id,
                n.created_at,
                n.data->>'email' as recipient_email,
                n.data->>'phone' as recipient_phone,
                nc.channel,
                nc.status
            FROM notifications n
            JOIN notification_channels nc ON nc.notification_id = n.id
            WHERE n.tenant_id = :tenant_id
            ORDER BY n.created_at DESC
            LIMIT 5
        """)
        
        result = await db.execute(outbound_query, {"tenant_id": tenant_id})
        outbound_rows = result.fetchall()
        
        if not outbound_rows:
            print("❌ No outbound notifications found!")
            return
        
        for row in outbound_rows:
            print(f"\n📤 Notification: {row.notification_id[:8]}...")
            print(f"   Sent: {row.created_at}")
            print(f"   Email: {row.recipient_email}")
            print(f"   Phone: {row.recipient_phone}")
            print(f"   Channel: {row.channel}")
            print(f"   Status: {row.status}")
        
        print("\n" + "="*80)
        print("2. CHECKING RECENT INBOUND MESSAGES")
        print("="*80)
        
        inbound_query = text("""
            SELECT 
                m.id::text as message_id,
                m.created_at,
                m.sender_address,
                m.channel,
                p.parsed_content,
                ii.intent
            FROM inbound_messages_raw m
            LEFT JOIN inbound_messages_parsed p ON m.id = p.raw_message_id
            LEFT JOIN inbound_intents ii ON p.id = ii.parsed_message_id
            WHERE m.tenant_id = :tenant_id
            ORDER BY m.created_at DESC
            LIMIT 5
        """)
        
        result = await db.execute(inbound_query, {"tenant_id": tenant_id})
        inbound_rows = result.fetchall()
        
        if not inbound_rows:
            print("❌ No inbound messages found!")
            print("\nThis is why replies aren't showing - no replies have been received yet.")
            return
        
        for row in inbound_rows:
            print(f"\n📥 Message: {row.message_id[:8]}...")
            print(f"   Received: {row.created_at}")
            print(f"   From: {row.sender_address}")
            print(f"   Channel: {row.channel}")
            print(f"   Content: {(row.parsed_content or '')[:50]}...")
            print(f"   Intent: {row.intent}")
        
        print("\n" + "="*80)
        print("3. TESTING REPLY MATCHING FOR FIRST OUTBOUND")
        print("="*80)
        
        first_outbound = outbound_rows[0]
        
        match_query = text("""
            SELECT 
                m.id::text as message_id,
                m.created_at as inbound_time,
                m.sender_address,
                m.channel as inbound_channel,
                CASE 
                    WHEN m.created_at > :outbound_time THEN 'AFTER'
                    ELSE 'BEFORE'
                END as timing,
                EXTRACT(EPOCH FROM (m.created_at - :outbound_time)) / 3600 as hours_diff,
                CASE
                    WHEN :recipient_email IS NOT NULL 
                         AND LOWER(TRIM(m.sender_address)) = LOWER(TRIM(:recipient_email))
                    THEN 'EMAIL_MATCH'
                    WHEN :recipient_phone IS NOT NULL 
                         AND (m.sender_address = :recipient_phone
                              OR m.sender_address = 'whatsapp:' || :recipient_phone
                              OR REPLACE(m.sender_address, 'whatsapp:', '') = :recipient_phone)
                    THEN 'PHONE_MATCH'
                    ELSE 'NO_MATCH'
                END as match_type
            FROM inbound_messages_raw m
            WHERE m.tenant_id = :tenant_id
            AND LOWER(CAST(m.channel AS TEXT)) = LOWER(CAST(:outbound_channel AS TEXT))
            ORDER BY m.created_at DESC
            LIMIT 10
        """)
        
        result = await db.execute(match_query, {
            "tenant_id": tenant_id,
            "outbound_time": first_outbound.created_at,
            "outbound_channel": first_outbound.channel,
            "recipient_email": first_outbound.recipient_email,
            "recipient_phone": first_outbound.recipient_phone
        })
        
        match_rows = result.fetchall()
        
        print(f"\nTesting matches for outbound {first_outbound.notification_id[:8]}...")
        print(f"Sent at: {first_outbound.created_at}")
        print(f"Channel: {first_outbound.channel}")
        print(f"Email: {first_outbound.recipient_email}")
        print(f"Phone: {first_outbound.recipient_phone}")
        print(f"\nFound {len(match_rows)} inbound messages on same channel:")
        
        for row in match_rows:
            print(f"\n  📨 {row.message_id[:8]}... | {row.timing} | {row.hours_diff:.1f}h diff")
            print(f"     From: {row.sender_address}")
            print(f"     Match: {row.match_type}")
            print(f"     Time: {row.inbound_time}")
        
        # Check if any would match our current query
        matching_after = [r for r in match_rows 
                         if r.timing == 'AFTER' 
                         and r.match_type in ('EMAIL_MATCH', 'PHONE_MATCH')
                         and r.hours_diff <= 720]  # 30 days
        
        print(f"\n" + "="*80)
        print("4. DIAGNOSIS")
        print("="*80)
        
        if matching_after:
            print(f"✅ Found {len(matching_after)} matching replies AFTER send!")
            print(f"   First match: {matching_after[0].message_id[:8]}...")
            print(f"   This SHOULD show in the dashboard.")
            print(f"\n   If it's not showing, the issue is in the frontend rendering.")
        else:
            print("❌ No matching replies found AFTER the outbound was sent.")
            print("\nPossible reasons:")
            print("  1. No replies have been received yet")
            print("  2. Replies came BEFORE the outbound (wrong order)")
            print("  3. Sender address doesn't match recipient address")
            print("  4. Channel mismatch")
            
            if any(r.timing == 'BEFORE' and r.match_type in ('EMAIL_MATCH', 'PHONE_MATCH') 
                   for r in match_rows):
                print("\n⚠️  Found replies BEFORE the outbound - this is unusual!")
                print("   Check if timestamps are correct.")

if __name__ == "__main__":
    asyncio.run(debug_replies())
