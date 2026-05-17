# Notification SDK - Functions Overview

**Version:** 1.0  
**Date:** May 2026

---

## Table of Contents

1. [Overview](#overview)
2. [Setup & Requirements](#setup--requirements)
3. [Core Functions](#core-functions)
4. [Error Handling](#error-handling)
5. [Best Practices](#best-practices)
6. [Quick Reference](#quick-reference)

---

## Overview

The Notification SDK provides a Python interface to integrate notification capabilities directly into your application without running a separate API server.

### Key Features

- **Outbound Notifications**: Email, SMS, WhatsApp, Voice, Slack, Push
- **Inbound Processing**: Reply detection and AI-powered intent classification
- **Batch Operations**: Send to multiple recipients efficiently
- **Template Support**: Use pre-configured templates for consistent messaging
- **Async Support**: Both sync and async function variants available

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

- FastAPI server
- Uvicorn
- API routes

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

**Use Cases:**
- Order confirmations
- Account alerts
- Password resets
- Transactional notifications

---

### 2. Send Batch Notification

**Function:** `send_batch_notification_pipeline(tenant_id, request, owner_id)`

**Purpose:** Send the same notification to multiple recipients through a single channel.

**Key Request Fields:**

| Field | Required | Description |
|-------|----------|-------------|
| `channel` | Yes | Single channel (email, sms, whatsapp, etc.) |
| `template_id` | No* | Template ID (*Required for WhatsApp) |
| `subject` | No | Email subject |
| `body` | No | Message body |
| `data` | No | Shared template variables |
| `recipients` | Yes | List of recipient objects |

**Use Cases:**
- Email campaigns
- SMS broadcasts
- Newsletter distribution
- Promotional messages

---

### 3. Send Batch Multichannel

**Function:** `send_batch_multichannel_notification_pipeline(tenant_id, request, owner_id)`

**Purpose:** Send notifications to multiple recipients across multiple channels simultaneously.

**Key Request Fields:**

| Field | Required | Description |
|-------|----------|-------------|
| `channels` | Yes | List of channels |
| `template_id` | No | Shared template for all channels |
| `channel_template_map` | No | Different template per channel |
| `recipients` | Yes | List of recipient objects |
| `delivery_mode` | No | parallel_all, sequential, fallback |

**Use Cases:**
- System maintenance alerts
- Critical announcements
- Multi-channel marketing campaigns
- Emergency notifications

---

### 4. Get Notification Status

**Function:** `get_notification_status(tenant_id, notification_id)`

**Purpose:** Retrieve the current delivery status of a notification.

**Returns:**
- Notification ID and status
- Per-channel delivery status
- Provider information
- Delivery timestamps
- Attempt count

**Status Values:**
- `queued` - Queued for delivery
- `processing` - Currently being processed
- `delivered` - Successfully delivered
- `failed` - Delivery failed
- `partial` - Some channels succeeded, others failed

**Use Cases:**
- Delivery confirmation
- Debugging failed notifications
- Analytics and reporting
- Retry logic

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

**Intent Categories:**
- `ACCEPT` - Customer accepts/agrees
- `REJECT` - Customer declines/refuses
- `QUERY` - Customer has questions
- `REQUEST` - Customer requests action
- `UNKNOWN` - Intent unclear

**Detection Methods:**
- `RULES` - Regex pattern matching (100% confidence)
- `LLM` - AI-powered classification (variable confidence)

**Use Cases:**
- Customer service automation
- Lead qualification
- Survey response processing
- Appointment confirmations

---

### 6. Detect Reply Intent

**Function:** `detect_reply_intent(inbound_message, broadcast)`

**Purpose:** Simplified function that only returns the detected intent without full message processing details.

**Returns:**
- Intent category
- Confidence score (0.0 - 1.0)
- Detection method (RULES or LLM)
- Rationale explanation
- Review flag

**Use Cases:**
- Quick intent classification
- Routing decisions
- Automated response triggers
- Sentiment analysis

---

### 7. Get Conversation History

**Function:** `get_inbound_conversation(tenant_id, sender_address, candidate_id, reference_id, limit)`

**Purpose:** Retrieve all inbound messages and their intents for a specific customer or conversation.

**Lookup Options:**
- By `sender_address` (email or phone)
- By `candidate_id` (customer ID)
- By `reference_id` (tracking ID)

*At least one lookup parameter is required*

**Returns:**
- List of messages with parsed content
- Intent for each message
- Confidence scores
- Timestamps
- Channel information

**Use Cases:**
- Customer service dashboards
- Conversation analytics
- Lead scoring
- Automated follow-up triggers

---

## Error Handling

### Exception Types

| Exception | Description | Common Causes |
|-----------|-------------|---------------|
| `ValidationError` | Invalid input or missing required fields | Missing tenant_id, invalid payload, missing recipient fields |
| `ConfigurationError` | Runtime or infrastructure issues | Database connection failure, Redis unavailable, missing provider credentials |
| `NotFoundError` | Requested resource doesn't exist | Invalid notification ID, wrong tenant |
| `NotificationPipelineError` | Base exception for all SDK errors | Generic SDK errors |

### Error Handling Pattern

```python
from src.sdk import send_notification_pipeline, ValidationError, ConfigurationError

try:
    result = send_notification_pipeline(...)
    return {"success": True, "id": result.notification_id}
except ValidationError as e:
    return {"success": False, "error": "invalid_input"}
except ConfigurationError as e:
    return {"success": False, "error": "service_unavailable"}
```

---

## Best Practices

### 1. Use Idempotency Keys
Always provide idempotency keys for critical notifications to prevent duplicates.

### 2. Use Async Functions in Async Context
If your application is async, use the `_async` variants of SDK functions.

### 3. Batch Operations for Multiple Recipients
Use batch functions instead of loops for better performance and efficiency.

### 4. Handle Errors Gracefully
Always wrap SDK calls in try-except blocks with appropriate error handling.

### 5. Use Templates for Consistent Messaging
Define templates for frequently sent notifications to ensure consistency.

### 6. Monitor Notification Status
Check delivery status for critical notifications and implement retry logic.

### 7. Process Inbound Replies Asynchronously
For high-volume inbound processing, use `enqueue=True` option.

---

## Quick Reference

### Supported Channels

| Channel | Description | Template Required |
|---------|-------------|-------------------|
| `email` | Email notifications | No |
| `sms` | SMS text messages | No |
| `whatsapp` | WhatsApp messages | Yes |
| `voice` | Voice calls | No |
| `slack` | Slack messages | No |
| `push` | Push notifications | No |

### Priority Levels

| Priority | Description | Use Case |
|----------|-------------|----------|
| `critical` | Highest priority, immediate delivery | Security alerts, system failures |
| `high` | High priority | Order confirmations, payment receipts |
| `medium` | Normal priority (default) | General notifications |
| `low` | Low priority, can be delayed | Marketing emails, newsletters |

### Delivery Modes

| Mode | Description | Use Case |
|------|-------------|----------|
| `parallel_all` | Send to all channels simultaneously (default) | Maximum reach |
| `sequential` | Send to channels one by one | Ordered delivery |
| `fallback` | Try channels in order until one succeeds | Guaranteed delivery |

### Template Requirements

| Channel | Template Required | Notes |
|---------|-------------------|-------|
| WhatsApp | **Yes** | Must use pre-approved templates |
| Email | No | Can use template or raw body |
| SMS | No | Can use template or raw body |
| Voice | No | Can use template or raw body |
| Slack | No | Can use template or raw body |

---

## Function Summary

| Function | Purpose | Async Variant Available |
|----------|---------|-------------------------|
| `send_notification_pipeline` | Send single notification | ✓ |
| `send_batch_notification_pipeline` | Batch single channel | ✓ |
| `send_batch_multichannel_notification_pipeline` | Batch multiple channels | ✓ |
| `get_notification_status` | Check delivery status | ✓ |
| `process_inbound_reply` | Process inbound message | ✓ |
| `detect_reply_intent` | Detect intent only | ✓ |
| `get_inbound_conversation` | Get conversation history | ✓ |

---

## Support & Documentation

For additional help:

- **Full Documentation**: See `src/sdk/README.md`
- **Detailed Examples**: See `src/sdk/SDK_FUNCTIONS_GUIDE.md`
- **API Reference**: Check function docstrings
- **Test Examples**: See `src/sdk/tests/` directory
- **Issues**: Contact your integration team

---

**Document Version:** 1.0  
**Last Updated:** May 13, 2026  
**SDK Version:** 1.0.0
