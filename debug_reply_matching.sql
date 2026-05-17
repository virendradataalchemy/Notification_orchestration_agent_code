-- Debug query to check reply matching
-- Run this on your AWS database to see what's happening

-- 1. Check recent outbound notifications
SELECT 
    n.id as notification_id,
    n.created_at as sent_time,
    n.user_id as recipient_id,
    n.data->>'email' as recipient_email,
    n.data->>'phone' as recipient_phone,
    nc.channel,
    nc.status
FROM notifications n
JOIN notification_channels nc ON nc.notification_id = n.id
WHERE n.tenant_id = 'YOUR_TENANT_ID'  -- Replace with your tenant ID
ORDER BY n.created_at DESC
LIMIT 10;

-- 2. Check recent inbound messages
SELECT 
    m.id as message_id,
    m.created_at as received_time,
    m.sender_address,
    m.channel,
    p.parsed_content,
    p.status,
    ii.intent as ai_intent
FROM inbound_messages_raw m
LEFT JOIN inbound_messages_parsed p ON m.id = p.raw_message_id
LEFT JOIN inbound_intents ii ON p.id = ii.parsed_message_id
WHERE m.tenant_id = 'YOUR_TENANT_ID'  -- Replace with your tenant ID
ORDER BY m.created_at DESC
LIMIT 10;

-- 3. Test the matching logic for a specific outbound
-- Replace the notification ID with one from query #1
WITH test_outbound AS (
    SELECT 
        n.id,
        n.created_at as timestamp,
        n.data->>'email' as recipient_email,
        n.data->>'phone' as recipient_phone,
        nc.channel
    FROM notifications n
    JOIN notification_channels nc ON nc.notification_id = n.id
    WHERE n.id = 'NOTIFICATION_ID_HERE'  -- Replace with actual notification ID
    LIMIT 1
)
SELECT 
    m.id as inbound_id,
    m.created_at as inbound_time,
    m.sender_address,
    m.channel,
    o.timestamp as outbound_time,
    o.recipient_email,
    o.recipient_phone,
    CASE 
        WHEN m.created_at > o.timestamp THEN 'AFTER'
        ELSE 'BEFORE'
    END as timing,
    EXTRACT(EPOCH FROM (m.created_at - o.timestamp)) / 86400 as days_diff
FROM test_outbound o
CROSS JOIN inbound_messages_raw m
WHERE m.tenant_id = 'YOUR_TENANT_ID'  -- Replace with your tenant ID
AND LOWER(CAST(m.channel AS TEXT)) = LOWER(CAST(o.channel AS TEXT))
AND (
    (o.recipient_email IS NOT NULL AND LOWER(TRIM(m.sender_address)) = LOWER(TRIM(o.recipient_email)))
    OR (o.recipient_phone IS NOT NULL AND (
        m.sender_address = o.recipient_phone
        OR m.sender_address = 'whatsapp:' || o.recipient_phone
        OR REPLACE(m.sender_address, 'whatsapp:', '') = o.recipient_phone
    ))
)
ORDER BY m.created_at DESC;
