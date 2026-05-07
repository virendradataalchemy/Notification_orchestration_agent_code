# Notification SDK

This SDK lets another Python service call the notification pipeline directly without running the FastAPI server.

The SDK is a thin facade over the existing orchestration code in this repo. It validates inputs, opens a database session, calls the notification service, and returns typed response objects.

## When to use this

Use this SDK when:

- your team wants to import Python functions directly
- you do not want to call `POST /api/v1/notifications/*`
- you do not want to run `uvicorn`
- you still want to reuse the existing notification pipeline, templates, routing, and delivery flow

Do not use this SDK from frontend/browser code. It is for Python backend services only.

## What still needs to be running

The SDK removes the HTTP API layer, but it does not remove the platform runtime dependencies.

Required runtime:

- Supabase Postgres reachable through `DATABASE_URL`
- Redis reachable through `REDIS_URL`
- Celery worker for queued delivery execution
- provider credentials/config needed by your enabled channels

Not required:

- FastAPI server
- API routes
- `uvicorn`

## Import path

```python
from src.sdk import (
    process_inbound_reply,
    detect_reply_intent,
    get_inbound_conversation,
    send_notification_pipeline,
    send_batch_notification_pipeline,
    send_batch_multichannel_notification_pipeline,
    get_notification_status,
)
```

Async variants are also available:

```python
from src.sdk import (
    process_inbound_reply_async,
    detect_reply_intent_async,
    get_inbound_conversation_async,
    send_notification_pipeline_async,
    send_batch_notification_pipeline_async,
    send_batch_multichannel_notification_pipeline_async,
    get_notification_status_async,
)
```

## Public functions

The SDK now exposes both:

- outbound notification functions
- inbound reply and intent-detection functions

### `send_notification_pipeline(...)`

Send one notification to one recipient.

Signature:

```python
send_notification_pipeline(
    tenant_id,
    recipient,
    notification,
    options=None,
    *,
    owner_id=None,
    session=None,
    session_factory=None,
)
```

Parameters:

- `tenant_id: str`
  - required
  - tenant identifier already present in your platform data
- `recipient: dict | RecipientInfo`
  - required
  - recipient identity fields
- `notification: dict | NotificationData`
  - required
  - notification content and routing preferences
- `options: dict | NotificationOptions | None`
  - optional
  - idempotency and tracking options
- `owner_id: str | None`
  - optional
  - pass a user/team member ID if you want attribution in created records
- `session`
  - optional
  - pass an existing async SQLAlchemy session if your app already manages DB transactions
- `session_factory`
  - optional
  - pass a custom async session factory if you do not want to use the default DB session creator

Returns:

- `NotificationResponse`

Example:

```python
from src.sdk import send_notification_pipeline

result = send_notification_pipeline(
    tenant_id="tenant_acme",
    recipient={
        "user_id": "user_123",
        "email": "user@example.com",
    },
    notification={
        "type": "order_update",
        "priority": "high",
        "channels": ["email"],
        "subject": "Order Update",
        "body": "Your order has shipped.",
        "data": {"order_id": "ORD-1001"},
    },
    options={
        "idempotency_key": "ord-1001-email",
    },
)

print(result.notification_id)
print(result.status)
```

### `send_batch_notification_pipeline(...)`

Send one channel to many recipients using the batch flow.

Signature:

```python
send_batch_notification_pipeline(
    tenant_id,
    request,
    *,
    owner_id=None,
    session=None,
    session_factory=None,
)
```

Parameters:

- `tenant_id: str`
- `request: dict | BatchNotificationRequest`

Returns:

- `BatchNotificationResponse`

Example:

```python
from src.sdk import send_batch_notification_pipeline

result = send_batch_notification_pipeline(
    tenant_id="tenant_acme",
    request={
        "channel": "email",
        "subject": "Weekly Update",
        "body": "Hello {{user.name}}, your weekly summary is ready.",
        "data": {"campaign": "weekly_update"},
        "recipients": [
            {"user_id": "u1", "email": "u1@example.com", "data": {"user": {"name": "A"}}},
            {"user_id": "u2", "email": "u2@example.com", "data": {"user": {"name": "B"}}},
        ],
    },
)

print(result.batch_id)
print(result.total_recipients)
```

### `send_batch_multichannel_notification_pipeline(...)`

Send many recipients across multiple channels in one request.

Signature:

```python
send_batch_multichannel_notification_pipeline(
    tenant_id,
    request,
    *,
    owner_id=None,
    session=None,
    session_factory=None,
)
```

Parameters:

- `tenant_id: str`
- `request: dict | BatchMultiChannelNotificationRequest`

Returns:

- `BatchMultiChannelNotificationResponse`

Example:

```python
from src.sdk import send_batch_multichannel_notification_pipeline

result = send_batch_multichannel_notification_pipeline(
    tenant_id="tenant_acme",
    request={
        "channels": ["email", "sms"],
        "subject": "Maintenance Notice",
        "body": "Planned maintenance at 02:00 UTC",
        "recipients": [
            {
                "user_id": "u1",
                "email": "u1@example.com",
                "phone": "+14155550111",
                "data": {"user": {"name": "A"}},
            },
            {
                "user_id": "u2",
                "email": "u2@example.com",
                "phone": "+14155550112",
                "data": {"user": {"name": "B"}},
            },
        ],
    },
)

print(result.batch_id)
print(result.channels)
```

### `get_notification_status(...)`

Fetch the stored status for one notification.

Signature:

```python
get_notification_status(
    tenant_id,
    notification_id,
    *,
    session=None,
    session_factory=None,
)
```

Parameters:

- `tenant_id: str`
- `notification_id: str`

Returns:

- `NotificationStatusResponse`

Example:

```python
from src.sdk import get_notification_status

status = get_notification_status(
    tenant_id="tenant_acme",
    notification_id="0f8fad5b-d9cb-469f-a165-70867728950e",
)

print(status.status)
print(status.channels)
```

### `process_inbound_reply(...)`

Store an inbound reply, parse it, detect intent, and return the processed result without using the FastAPI webhook route.

Signature:

```python
process_inbound_reply(
    inbound_message,
    *,
    enqueue=False,
    broadcast=False,
    session=None,
    session_factory=None,
)
```

Parameters:

- `inbound_message: dict | InboundMessageCanonical`
  - required
  - canonical inbound payload
  - valid inbound `channel` values are `email`, `sms`, `whatsapp`, and `chat`
- `enqueue: bool`
  - optional
  - if `False`, processing happens immediately in-process
  - if `True`, the raw inbound message is stored and the Celery inbound task is queued
- `broadcast: bool`
  - optional
  - if `True`, sends the same WebSocket-style tenant broadcast used by the existing server flow
- `session`
  - optional existing async SQLAlchemy session
- `session_factory`
  - optional custom async session factory

Returns:

- `dict` with:
  - `status`
  - `raw_message`
  - `parsed_message`
  - `intent`

Example:

```python
from src.sdk import process_inbound_reply

result = process_inbound_reply(
    {
        "tenant_id": "demo_corp",
        "channel": "sms",
        "sender_address": "+918290942415",
        "provider_message_id": "SM_TEST_001",
        "raw_payload": {
            "Body": "Yes, I am interested."
        },
        "candidate_id": "candidate_001",
    }
)

print(result["status"])
print(result["parsed_message"]["parsed_content"])
print(result["intent"])
```

### `detect_reply_intent(...)`

Convenience wrapper that runs inbound parsing + intent detection and returns only the detected intent payload.

Signature:

```python
detect_reply_intent(
    inbound_message,
    *,
    broadcast=False,
    session=None,
    session_factory=None,
)
```

Returns:

- `dict` with:
  - `intent`
  - `confidence`
  - `detection_method`
  - `rationale`
  - `needs_review`

Example:

```python
from src.sdk import detect_reply_intent

intent = detect_reply_intent(
    {
        "tenant_id": "demo_corp",
        "channel": "email",
        "sender_address": "candidate@example.com",
        "provider_message_id": "MAILGUN_TEST_001",
        "raw_payload": {
            "stripped-text": "Can you reschedule this interview?"
        },
    }
)

print(intent["intent"])
print(intent["confidence"])
```

### `get_inbound_conversation(...)`

Fetch stored inbound replies and their parsed/intent data for a tenant.

Signature:

```python
get_inbound_conversation(
    tenant_id,
    *,
    sender_address=None,
    candidate_id=None,
    reference_id=None,
    limit=50,
    session=None,
    session_factory=None,
)
```

Lookup rules:

- you must provide at least one of:
  - `sender_address`
  - `candidate_id`
  - `reference_id`

Returns:

- `dict` with:
  - `tenant_id`
  - lookup filters used
  - `messages`

Each message includes:

- `raw_message`
- `parsed_message`
- `intent`

Example:

```python
from src.sdk import get_inbound_conversation

conversation = get_inbound_conversation(
    "demo_corp",
    sender_address="+918290942415",
    limit=10,
)

for message in conversation["messages"]:
    print(message["raw_message"]["sender_address"])
    print(message["parsed_message"])
    print(message["intent"])
```

## Async usage

If your service is already async, use the async SDK functions directly.

```python
from src.sdk import send_notification_pipeline_async

result = await send_notification_pipeline_async(
    tenant_id="tenant_acme",
    recipient={
        "user_id": "user_123",
        "email": "user@example.com",
    },
    notification={
        "type": "order_update",
        "priority": "high",
        "channels": ["email"],
        "subject": "Order Update",
        "body": "Your order has shipped.",
    },
)
```

The sync functions are just wrappers around the async implementation.

Inbound async example:

```python
from src.sdk import process_inbound_reply_async

result = await process_inbound_reply_async(
    {
        "tenant_id": "demo_corp",
        "channel": "sms",
        "sender_address": "+918290942415",
        "provider_message_id": "SM_TEST_002",
        "raw_payload": {
            "Body": "No, please stop."
        },
    }
)
```

## Payload structure

The SDK accepts either:

- existing Pydantic models from `src.api.schemas`
- plain Python dictionaries

### Inbound canonical payload

For inbound SDK functions, the expected canonical message shape is:

```python
{
    "tenant_id": "demo_corp",
    "channel": "sms",
    "sender_address": "+918290942415",
    "provider_message_id": "SM_TEST_001",
    "raw_payload": {
        "Body": "Yes, I am interested."
    },
    "candidate_id": "candidate_001",
    "owner_id": None,
    "retention_date": None,
    "metadata": {
        "to": "+14155550123"
    },
}
```

Important fields:

- `tenant_id` is required
- `channel` is required
- `sender_address` is required
- `provider_message_id` is required
- `raw_payload` is required

Supported inbound channels today:

- `email`
- `sms`
- `whatsapp`
- `chat`

### Recipient payload

Supported fields:

```python
{
    "user_id": "user_123",
    "email": "user@example.com",
    "phone": "+14155550123",
    "device_tokens": ["token_1", "token_2"],
    "slack_id": "U12345678",
}
```

At minimum:

- `user_id` is required
- at least one delivery-specific identifier should be present for the selected channel

Examples:

- for `email`, provide `email`
- for `sms`, `whatsapp`, or `voice`, provide `phone`
- for `slack`, provide `slack_id`

### Single notification payload

Common fields:

```python
{
    "type": "order_update",
    "priority": "high",
    "channels": ["email"],
    "subject": "Order Update",
    "body": "Your order has shipped.",
    "template_id": None,
    "data": {"order_id": "ORD-1001"},
    "idempotency_key": "ord-1001-email",
    "delivery_mode": "parallel_all",
    "strict_client_priority": True,
    "ai_fallback_enabled": True,
    "ai_on_no_channel_preference": True,
}
```

Important notes:

- `type` is required
- `priority` can be `critical`, `high`, `medium`, or `low`
- `channels` is a list such as `["email"]`, `["sms"]`, or `["email", "sms"]`
- `template_id` is required for `whatsapp`
- `subject` is mainly relevant for email
- `data` is passed as template variables and metadata

Template-based single-send example:

```python
from src.sdk import send_notification_pipeline

result = send_notification_pipeline(
    tenant_id="tenant_acme",
    recipient={
        "user_id": "user_123",
        "phone": "+14155550123",
    },
    notification={
        "type": "order_update",
        "priority": "high",
        "channels": ["whatsapp"],
        "template_id": "wa_order_update",
        "data": {
            "name": "Alex",
            "order_id": "ORD-1001",
        },
    },
)
```

### Batch notification payload

For `send_batch_notification_pipeline(...)`:

```python
{
    "channel": "email",
    "template_id": None,
    "subject": "Weekly Update",
    "body": "Hello {{user.name}}",
    "data": {"campaign": "weekly_update"},
    "recipients": [
        {
            "user_id": "u1",
            "email": "u1@example.com",
            "data": {"user": {"name": "A"}},
        }
    ],
    "schedule_at": None,
}
```

Template-based batch example:

```python
from src.sdk import send_batch_notification_pipeline

result = send_batch_notification_pipeline(
    tenant_id="tenant_acme",
    request={
        "channel": "whatsapp",
        "template_id": "wa_order_update",
        "data": {"company": {"name": "Acme"}},
        "recipients": [
            {
                "user_id": "u1",
                "phone": "+14155550111",
                "data": {"name": "A", "order_id": "ORD-1001"},
            },
            {
                "user_id": "u2",
                "phone": "+14155550112",
                "data": {"name": "B", "order_id": "ORD-1002"},
            },
        ],
    },
)
```

### Batch multichannel payload

For `send_batch_multichannel_notification_pipeline(...)`:

```python
{
    "template_id": None,
    "subject": "Maintenance Notice",
    "body": "Planned maintenance at 02:00 UTC",
    "data": {"campaign": "ops_notice"},
    "recipients": [
        {
            "user_id": "u1",
            "email": "u1@example.com",
            "phone": "+14155550111",
            "data": {"user": {"name": "A"}},
        }
    ],
    "channels": ["email", "sms"],
    "delivery_mode": "parallel_all",
    "strict_client_priority": True,
    "ai_fallback_enabled": True,
    "ai_on_no_channel_preference": True,
    "schedule_at": None,
}
```

Optional per-channel overrides are also supported:

- `channel_template_map`
- `channel_subject_map`
- `channel_body_map`

Template-based multichannel example:

```python
from src.sdk import send_batch_multichannel_notification_pipeline

result = send_batch_multichannel_notification_pipeline(
    tenant_id="tenant_acme",
    request={
        "channels": ["whatsapp", "email"],
        "template_id": "shared_order_update",
        "channel_template_map": {
            "whatsapp": "wa_order_update",
            "email": "email_order_update",
        },
        "recipients": [
            {
                "user_id": "u1",
                "email": "u1@example.com",
                "phone": "+14155550111",
                "data": {"name": "A", "order_id": "ORD-1001"},
            }
        ],
    },
)
```

## Template support

Yes, the SDK supports template-based sending.

Supported template fields:

- `template_id`
  - supported in single send
  - supported in batch send
  - supported in multichannel batch send
- `channel_template_map`
  - supported in multichannel batch send
  - lets you choose a different template per channel
- `data`
  - used as template variables
  - merged with recipient-level `data` in batch flows

Current template rules:

- `whatsapp` requires a `template_id`
- `email`, `sms`, `slack`, and `voice` can use either:
  - `template_id`
  - raw `body`
- for multichannel requests, you can use:
  - one shared `template_id` for all channels
  - or `channel_template_map` for per-channel templates

## Return types

The SDK returns the same response models used by the API layer.

Inbound SDK functions return plain dictionaries instead of Pydantic response models.

### `NotificationResponse`

Important fields:

- `notification_id`
- `status`
- `channels`
- `estimated_delivery`
- `created_at`

### `BatchNotificationResponse`

Important fields:

- `batch_id`
- `status`
- `total_recipients`
- `estimated_completion`

### `BatchMultiChannelNotificationResponse`

Important fields:

- `batch_id`
- `status`
- `total_recipients`
- `total_notifications`
- `total_channel_records`
- `channels`

### `NotificationStatusResponse`

Important fields:

- `notification_id`
- `user_id`
- `type`
- `priority`
- `status`
- `channels`
- `attempts`
- `created_at`
- `updated_at`

### Inbound processing result

`process_inbound_reply(...)` returns:

```python
{
    "status": "processed|queued",
    "raw_message": {...},
    "parsed_message": {...} | None,
    "intent": {...} | None,
}
```

Important inbound result fields:

- `raw_message.id`
- `raw_message.channel`
- `raw_message.sender_address`
- `parsed_message.parsed_content`
- `parsed_message.status`
- `intent.intent`
- `intent.confidence`
- `intent.detection_method`
- `intent.needs_review`

## Exceptions

Catch SDK exceptions from `src.sdk.exceptions` or directly from `src.sdk`.

```python
from src.sdk import (
    NotificationPipelineError,
    ValidationError,
    ConfigurationError,
    NotFoundError,
)
```

### `ValidationError`

Raised for caller-side problems such as:

- missing `tenant_id`
- invalid payload shape
- invalid `notification_id`
- invalid inbound message ID
- missing inbound lookup filters for conversation fetch
- channel/template policy failures
- missing required recipient fields

### `ConfigurationError`

Raised for environment/runtime failures such as:

- DB session creation failure
- infrastructure/configuration issues
- internal errors mapped from the service layer

### `NotFoundError`

Raised when requested data is not found, such as:

- notification ID does not exist for that tenant
- inbound message ID does not exist

### `NotificationPipelineError`

Base exception for all SDK-specific errors.

Example:

```python
from src.sdk import send_notification_pipeline, ValidationError, ConfigurationError

try:
    result = send_notification_pipeline(
        tenant_id="tenant_acme",
        recipient={"user_id": "u1", "email": "u1@example.com"},
        notification={
            "type": "order_update",
            "priority": "high",
            "channels": ["email"],
            "subject": "Order Update",
            "body": "Your order has shipped.",
        },
    )
except ValidationError as exc:
    print("Bad request:", exc)
except ConfigurationError as exc:
    print("Runtime/config issue:", exc)
```

## Session management

By default, the SDK creates its own async DB session using the repo's configured `AsyncSessionLocal`.

That is enough for most integrations.

### Default mode

Use this when your service just wants to call the pipeline:

```python
result = send_notification_pipeline(
    tenant_id="tenant_acme",
    recipient={...},
    notification={...},
)
```

Inbound equivalent:

```python
result = process_inbound_reply(
    {
        "tenant_id": "demo_corp",
        "channel": "sms",
        "sender_address": "+918290942415",
        "provider_message_id": "SM_TEST_003",
        "raw_payload": {"Body": "Please send more details."},
    }
)
```

### Existing session mode

If your app already has an async SQLAlchemy session:

```python
result = await send_notification_pipeline_async(
    tenant_id="tenant_acme",
    recipient={...},
    notification={...},
    session=db_session,
)
```

### Custom session factory mode

If you want to control session creation:

```python
result = send_notification_pipeline(
    tenant_id="tenant_acme",
    recipient={...},
    notification={...},
    session_factory=my_async_session_factory,
)
```

Use either:

- `session`
- `session_factory`

If both are omitted, the SDK uses the repo default DB session factory.

## Current limitations

- This SDK is internal to this repo; it is not yet packaged as a standalone pip distribution.
- It still depends on the existing backend runtime pieces like Redis and Celery.
- It is not a frontend-safe client.
- It does not replace provider setup, tenant setup, or template setup.
- inbound SDK processing is DB-backed and not a stateless pure parser
- inbound LLM fallback still depends on the configured Bedrock/Qwen setup when regex rules do not match

## Recommended integration pattern

For another backend team, the simplest pattern is:

1. Add this repo/package to the Python environment.
2. Configure env vars such as `DATABASE_URL`, `REDIS_URL`, and provider secrets.
3. Ensure Redis and Celery worker are running.
4. Call `send_notification_pipeline(...)` from application code.
5. Store `notification_id` if later status tracking is needed.

Inbound direct-import pattern:

1. Receive inbound provider payload in your own backend app.
2. Convert it into the canonical inbound shape.
3. Call `process_inbound_reply(...)` directly.
4. Read `intent` from the returned result.
5. Use `get_inbound_conversation(...)` if you later need the stored history.

## Quick copy-paste example

```python
from src.sdk import send_notification_pipeline, get_notification_status

send_result = send_notification_pipeline(
    tenant_id="tenant_acme",
    recipient={
        "user_id": "user_123",
        "email": "user@example.com",
    },
    notification={
        "type": "welcome_email",
        "priority": "medium",
        "channels": ["email"],
        "subject": "Welcome",
        "body": "Welcome to our platform.",
        "data": {"first_name": "Alex"},
    },
)

print("Queued notification:", send_result.notification_id)

status_result = get_notification_status(
    tenant_id="tenant_acme",
    notification_id=send_result.notification_id,
)

print("Current status:", status_result.status)
```
