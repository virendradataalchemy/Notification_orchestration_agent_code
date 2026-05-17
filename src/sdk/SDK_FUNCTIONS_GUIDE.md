# Notification SDK - Functions Guide

**Version:** 1.0  
**Date:** May 2026

---

## Table of Contents

1. [Overview](#overview)
2. [Setup & Requirements](#setup--requirements)
3. [Core Functions](#core-functions)
4. [Error Handling](#error-handling)
5. [Best Practices](#best-practices)

---

## Overview

The Notification SDK provides a Python interface to integrate notification capabilities directly into your application without running a separate API server.

### Key Features

- **Outbound Notifications**: Email, SMS, WhatsApp, Voice, Slack, Push
- **Inbound Processing**: Reply detection and AI-powered intent classification
- **Batch Operations**: Send to multiple recipients efficiently
- **Template Support**: Use pre-configured templates for consistent messaging

---

## Setup & Requirements

### Installation

```python
from src.sdk import (
    send_notification_pipeline,
    send_batch_notification_pipeline,
    send_batch_multichannel_notification_pipeline,
    get_notification_status,
    process_inbound_reply,
    detect_reply_intent,
    get_inbound_conversation,
)
```

### Required Runtime

- **Database**: Supabase Postgres (via `DATABASE_URL`)
- **Cache**: Redis (via `REDIS_URL`)
- **Worker**: Celery worker for async delivery
- **Credentials**: Provider API keys (Twilio, SendGrid, Mailgun, etc.)

### Not Required

- FastAPI server, Uvicorn, API routes

---

## Core Functions

### 1. Send Single Notification

**Function:** `send_notification_pipeline(tenant_id, recipient, notification, options, owner_id)`

**Purpose:** Send a notification to a single recipient through one or more channels.

**Key Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `tenant_id` | str | Yes | Your tenant identifier |
| `recipient` | dict | Yes | Recipient info (user_id, email, phone, etc.) |
| `notification` | dict | Yes | Notification content and routing |
| `options` | dict | No | Idempotency and tracking options |

**Notification Fields:**

| Field | Required | Description |
|-------|----------|-------------|
| `type` | Yes | Notification type identifier |
| `priority` | Yes | critical, high, medium, low |
| `channels` | Yes | List: email, sms, whatsapp, voice, slack, push |
| `template_id` | No* | Template ID (*Required for WhatsApp) |
| `subject` | No | Email subject line |
| `body` | No | Message body (not needed with template) |
| `data` | No | Template variables and metadata |

**Examples:**

```python
# Email notification
result = send_notification_pipeline(
    tenant_id="acme_corp",
    recipient={"user_id": "user_123", "email": "john@example.com"},
    notification={
        "type": "order_confirmation",
        "priority": "high",
        "channels": ["email"],
        "subject": "Order Confirmed - #12345",
        "body": "Thank you for your order!",
        "data": {"order_id": "12345"}
    },
    options={"idempotency_key": "order-12345-confirmation"}
)

# WhatsApp with template (template_id required)
result = send_notification_pipeline(
    tenant_id="acme_corp",
    recipient={"user_id": "user_999", "phone": "+14155551234"},
    notification={
        "type": "order_shipped",
        "priority": "high",
        "channels": ["whatsapp"],
        "template_id": "order_shipped_template",
        "data": {
            "customer_name": "John Doe",
            "order_id": "ORD-12345",
            "tracking_number": "TRK-ABC123"
        }
    }
)

# Multi-channel notification
result = send_notification_pipeline(
    tenant_id="acme_corp",
    recipient={
        "user_id": "user_789",
        "email": "jane@example.com",
        "phone": "+14155559876"
    },
    notification={
        "type": "urgent_alert",
        "priority": "critical",
        "channels": ["email", "sms"],
        "subject": "Security Alert",
        "body": "Unusual login detected from new device.",
        "delivery_mode": "parallel_all"
    }
)
```

---

### 2. Send Batch Notification

**Function:** `send_batch_notification_pipeline(tenant_id, request, owner_id)`

**Purpose:** Send the same notification to multiple recipients through a single channel.

**Request Fields:**

| Field | Required | Description |
|-------|----------|-------------|
| `channel` | Yes | Single channel (email, sms, whatsapp, etc.) |
| `template_id` | No* | Template ID (*Required for WhatsApp) |
| `subject` | No | Email subject |
| `body` | No | Message body |
| `data` | No | Shared template variables |
| `recipients` | Yes | List of recipient objects |

**Examples:**

```python
# Email campaign
result = send_batch_notification_pipeline(
    tenant_id="acme_corp",
    request={
        "channel": "email",
        "subject": "Weekly Newsletter - May 2026",
        "body": "Hello {{name}}, here's your weekly update...",
        "recipients": [
            {"user_id": "u1", "email": "alice@example.com", "data": {"name": "Alice"}},
            {"user_id": "u2", "email": "bob@example.com", "data": {"name": "Bob"}},
            {"user_id": "u3", "email": "charlie@example.com", "data": {"name": "Charlie"}}
        ]
    }
)

# WhatsApp batch with template
result = send_batch_notification_pipeline(
    tenant_id="acme_corp",
    request={
        "channel": "whatsapp",
        "template_id": "appointment_reminder",
        "data": {"clinic_name": "Acme Health Center"},
        "recipients": [
            {
                "user_id": "p1",
                "phone": "+14155551111",
                "data": {"patient_name": "John", "appointment_date": "May 15"}
            },
            {
                "user_id": "p2",
                "phone": "+14155552222",
                "data": {"patient_name": "Jane", "appointment_date": "May 16"}
            }
        ]
    }
)
```

---

### 3. Send Batch Multichannel

**Function:** `send_batch_multichannel_notification_pipeline(tenant_id, request, owner_id)`

**Purpose:** Send notifications to multiple recipients across multiple channels simultaneously.

**Request Fields:**

| Field | Required | Description |
|-------|----------|-------------|
| `channels` | Yes | List of channels |
| `template_id` | No | Shared template for all channels |
| `channel_template_map` | No | Different template per channel |
| `subject` | No | Email subject |
| `body` | No | Message body |
| `data` | No | Shared template variables |
| `recipients` | Yes | List of recipient objects |
| `delivery_mode` | No | parallel_all, sequential, fallback |

**Examples:**

```python
# System maintenance alert
result = send_batch_multichannel_notification_pipeline(
    tenant_id="acme_corp",
    request={
        "channels": ["email", "sms"],
        "subject": "Scheduled Maintenance - May 15, 2026",
        "body": "System maintenance on May 15 from 2:00-4:00 AM UTC.",
        "recipients": [
            {
                "user_id": "admin_001",
                "email": "admin1@example.com",
                "phone": "+14155551111"
            }
        ],
        "delivery_mode": "parallel_all"
    }
)

# Marketing campaign with channel-specific templates
result = send_batch_multichannel_notification_pipeline(
    tenant_id="acme_corp",
    request={
        "channels": ["email", "whatsapp"],
        "channel_template_map": {
            "email": "promo_email_template",
            "whatsapp": "promo_wa_template"
        },
        "data": {"promo_code": "SAVE30", "expiry": "May 20, 2026"},
        "recipients": [
            {
                "user_id": "c1",
                "email": "customer1@example.com",
                "phone": "+14155551234"
            }
        ]
    }
)
```

---

### 4. Get Notification Status

**Function:** `get_notification_status(tenant_id, notification_id)`

**Purpose:** Retrieve the current delivery status of a notification.

**Example:**

```python
status = get_notification_status(
    tenant_id="acme_corp",
    notification_id="550e8400-e29b-41d4-a716-446655440000"
)

print(f"Status: {status.status}")
print(f"Channels: {status.channels}")

# Check individual channel status
for channel_name, channel_info in status.channels.items():
    print(f"{channel_name}: {channel_info['status']}")
```

**Status Values:** `queued`, `processing`, `delivered`, `failed`, `partial`

---

### 5. Process Inbound Reply

**Function:** `process_inbound_reply(inbound_message, enqueue, broadcast)`

**Purpose:** Process incoming messages from customers and detect their intent using AI.

**Key Parameters:**

| Parameter | Required | Description |
|-----------|----------|-------------|
| `inbound_message` | Yes | Canonical inbound message payload |
| `enqueue` | No | If True, process asynchronously via Celery |
| `broadcast` | No | If True, send WebSocket notification |

**Inbound Message Fields:**

| Field | Required | Description |
|-------|----------|-------------|
| `tenant_id` | Yes | Your tenant identifier |
| `channel` | Yes | email, sms, whatsapp, chat |
| `sender_address` | Yes | Email or phone number |
| `provider_message_id` | Yes | Provider's message ID |
| `raw_payload` | Yes | Original message data |

**Intent Categories:** `ACCEPT`, `REJECT`, `QUERY`, `REQUEST`, `UNKNOWN`

**Examples:**

```python
# Email reply
result = process_inbound_reply(
    inbound_message={
        "tenant_id": "acme_corp",
        "channel": "email",
        "sender_address": "customer@example.com",
        "provider_message_id": "msg_email_001",
        "raw_payload": {
            "stripped-text": "Yes, I'm interested in the premium plan."
        },
        "candidate_id": "cust_123"
    }
)

print(f"Intent: {result['intent']['intent']}")  # Output: "ACCEPT"
print(f"Confidence: {result['intent']['confidence']}")  # Output: 0.95

# SMS reply
result = process_inbound_reply(
    inbound_message={
        "tenant_id": "acme_corp",
        "channel": "sms",
        "sender_address": "+14155551234",
        "provider_message_id": "SM_abc123",
        "raw_payload": {"Body": "No thanks, not interested"}
    }
)

print(f"Intent: {result['intent']['intent']}")  # Output: "REJECT"
```

---

### 6. Detect Reply Intent

**Function:** `detect_reply_intent(inbound_message, broadcast)`

**Purpose:** Simplified function that only returns the detected intent.

**Example:**

```python
intent = detect_reply_intent(
    inbound_message={
        "tenant_id": "acme_corp",
        "channel": "sms",
        "sender_address": "+14155559999",
        "provider_message_id": "SM_xyz789",
        "raw_payload": {"Body": "Can you reschedule my appointment?"}
    }
)

print(f"Intent: {intent['intent']}")  # Output: "REQUEST"
print(f"Confidence: {intent['confidence']}")
print(f"Method: {intent['detection_method']}")  # RULES or LLM
```

---

### 7. Get Conversation History

**Function:** `get_inbound_conversation(tenant_id, sender_address, candidate_id, reference_id, limit)`

**Purpose:** Retrieve all inbound messages and their intents for a specific customer.

**Lookup Options:** At least one required: `sender_address`, `candidate_id`, or `reference_id`

**Example:**

```python
conversation = get_inbound_conversation(
    tenant_id="acme_corp",
    sender_address="customer@example.com",
    limit=10
)

for msg in conversation['messages']:
    print(f"Content: {msg['parsed_message']['parsed_content']}")
    print(f"Intent: {msg['intent']['intent']}")
    print(f"Confidence: {msg['intent']['confidence']}")
```

---

## Error Handling

### Exception Types

```python
from src.sdk import (
    ValidationError,        # Invalid input or missing fields
    ConfigurationError,     # Runtime or infrastructure issues
    NotFoundError,          # Resource doesn't exist
    NotificationPipelineError  # Base exception
)
```

### Error Handling Pattern

```python
from src.sdk import send_notification_pipeline, ValidationError, ConfigurationError

try:
    result = send_notification_pipeline(...)
    return {"success": True, "id": result.notification_id}
    
except ValidationError as e:
    # Bad input - missing tenant_id, invalid payload, etc.
    return {"success": False, "error": "invalid_input", "message": str(e)}
    
except ConfigurationError as e:
    # Infrastructure issue - DB connection, Redis, provider credentials
    return {"success": False, "error": "service_unavailable"}
    
except NotFoundError as e:
    # Resource not found
    return {"success": False, "error": "not_found"}
```

---

## Best Practices

### 1. Use Idempotency Keys

Always provide idempotency keys for critical notifications to prevent duplicates.

```python
result = send_notification_pipeline(
    tenant_id="acme_corp",
    recipient={"user_id": "u1", "email": "user@example.com"},
    notification={
        "type": "payment_receipt",
        "channels": ["email"],
        "body": "Payment received"
    },
    options={"idempotency_key": f"payment-{payment_id}-receipt"}
)
```

### 2. Use Async Functions in Async Context

```python
async def send_welcome_email(user_id, email):
    from src.sdk import send_notification_pipeline_async
    
    result = await send_notification_pipeline_async(
        tenant_id="acme_corp",
        recipient={"user_id": user_id, "email": email},
        notification={
            "type": "welcome",
            "channels": ["email"],
            "subject": "Welcome!",
            "body": "Welcome to our platform"
        }
    )
    return result
```

### 3. Batch Operations for Multiple Recipients

Use batch functions instead of loops for better performance.

```python
# Good - Batch operation
result = send_batch_notification_pipeline(
    tenant_id="acme_corp",
    request={
        "channel": "email",
        "subject": "Newsletter",
        "body": "Monthly update...",
        "recipients": [
            {"user_id": "u1", "email": "user1@example.com"},
            {"user_id": "u2", "email": "user2@example.com"}
        ]
    }
)

# Bad - Loop with individual sends (slow, inefficient)
for user in users:
    send_notification_pipeline(...)
```

### 4. Use Templates for Consistent Messaging

```python
# Good - Template-based
result = send_notification_pipeline(
    tenant_id="acme_corp",
    recipient={"user_id": "u1", "phone": "+14155551234"},
    notification={
        "type": "order_update",
        "channels": ["whatsapp"],
        "template_id": "wa_order_shipped",
        "data": {"order_id": "12345", "tracking_url": "https://track.me/abc"}
    }
)
```

### 5. Monitor Notification Status

```python
# Send notification
result = send_notification_pipeline(...)
notification_id = result.notification_id

# Check status
status = get_notification_status(
    tenant_id="acme_corp",
    notification_id=notification_id
)

if status.status == "failed":
    logger.error(f"Notification {notification_id} failed")
```

### 6. Process Inbound Replies Asynchronously

For high-volume inbound processing, use the enqueue option.

```python
result = process_inbound_reply(
    inbound_message={...},
    enqueue=True  # Process via Celery worker
)
```

---

## Quick Reference

### Supported Channels

| Channel | Template Required | Description |
|---------|-------------------|-------------|
| `email` | No | Email notifications |
| `sms` | No | SMS text messages |
| `whatsapp` | **Yes** | WhatsApp messages |
| `voice` | No | Voice calls |
| `slack` | No | Slack messages |
| `push` | No | Push notifications |

### Priority Levels

- `critical` - Highest priority, immediate delivery
- `high` - High priority
- `medium` - Normal priority (default)
- `low` - Low priority, can be delayed

### Delivery Modes

- `parallel_all` - Send to all channels simultaneously (default)
- `sequential` - Send to channels one by one
- `fallback` - Try channels in order until one succeeds

---

## Support & Documentation

For additional help:

- **Full Documentation**: See `src/sdk/README.md`
- **Overview**: See `src/sdk/SDK_FUNCTIONS_OVERVIEW.md`
- **API Reference**: Check function docstrings
- **Issues**: Contact your integration team

---

**Document Version:** 1.0  
**Last Updated:** May 13, 2026  
**SDK Version:** 1.0.0
