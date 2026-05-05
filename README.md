# Multi-Channel Notification Orchestration Platform

A multi-tenant notification platform for sending messages across WhatsApp, Email, SMS, Slack, and Voice from one API.

## What This Platform Does

- Single API for multi-channel notifications
- Tenant onboarding portal (signup/login/dashboard)
- Tenant-owned template management
- Delivery tracking and status visibility
- Channel capability discovery endpoint for client validation
- Batch and multi-channel sends

## Current Template Policy (Important)

| Channel | Template Required | Raw Body Allowed |
|---|---|---|
| `whatsapp` | Yes | No |
| `email` | No | Yes |
| `sms` | No | Yes |
| `slack` | No | Yes |
| `voice` | No | Yes |
<!-- | `push` | No | Yes |
| `inapp` | No | Yes | -->

Rule applies to both single send and bulk send flows.

## Key URLs

- Platform Home: `http://localhost:8000/`
- Tenant Signup: `http://localhost:8000/portal/signup`
- Tenant Login: `http://localhost:8000/portal/login`
- How To Use: `http://localhost:8000/portal/how-to-use`
- Channel Capabilities Page: `http://localhost:8000/channels`
- System Status Page: `http://localhost:8000/status`
- API Swagger: `http://localhost:8000/api/v1/docs`
- API ReDoc: `http://localhost:8000/api/v1/redoc`

## Quick Start

### Prerequisites

- Python 3.11+
- PostgreSQL
- Redis
- Provider credentials as needed (Twilio, Mailgun, Slack, etc.)

### Local Setup

```bash
python -m venv venv
# Windows
venv\Scripts\activate
# Linux/macOS
# source venv/bin/activate

pip install -r requirements.txt
alembic upgrade head
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
docker compose up --build -d
```

## Tenant Onboarding Flow

1. Go to `/portal/signup`.
2. Create tenant account.
3. Save API key securely (shown at signup response).
4. Use API key in backend integration (`X-API-Key` header).
5. Login from `/portal/login` for dashboard/template management.

## Core API Endpoints

- `POST /api/v1/notifications/send`
- `POST /api/v1/notifications/agentic`
- `POST /api/v1/notifications/batch`
- `POST /api/v1/notifications/batch-multichannel`
- `GET /api/v1/notifications/{notification_id}`
- `GET /api/v1/channels/capabilities`
- `POST /api/v1/tenant/auth/signup`
- `POST /api/v1/tenant/auth/login`
- `POST /api/v1/tenant/templates/`

## API Auth

Programmatic API calls require tenant API key:

```http
X-API-Key: your_tenant_api_key
```

Portal login uses username/password and returns JWT for portal pages.

## Usage Examples

### 1) Single Send: Email Raw Mode (Template Optional)

```bash
curl -X POST "http://localhost:8000/api/v1/notifications/send" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_tenant_api_key" \
  -d '{
    "recipient": {
      "user_id": "user_123",
      "email": "user@example.com"
    },
    "notification": {
      "type": "order_update",
      "priority": "high",
      "channels": ["email"],
      "subject": "Order Update",
      "body": "Your order has shipped",
      "data": {"order_id": "ORD-1001"},
      "idempotency_key": "ord-1001-email"
    }
  }'
```

### 2) Single Send: WhatsApp Template Mode (Template Required)

```bash
curl -X POST "http://localhost:8000/api/v1/notifications/send" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_tenant_api_key" \
  -d '{
    "recipient": {
      "user_id": "user_123",
      "phone": "+14155550123"
    },
    "notification": {
      "type": "order_update",
      "priority": "high",
      "channels": ["whatsapp"],
      "template_id": "wa_order_update",
      "data": {"name": "Alex", "order_id": "ORD-1001"},
      "idempotency_key": "ord-1001-whatsapp"
    }
  }'
```

### 3) Batch Send (Policy Same as Single Send)

- If batch includes `whatsapp`, include `template_id`.
- For other channels, template is optional.

```bash
curl -X POST "http://localhost:8000/api/v1/notifications/batch-multichannel" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_tenant_api_key" \
  -d '{
    "channels": ["email", "sms"],
    "subject": "Maintenance Notice",
    "body": "Planned maintenance at 02:00 UTC",
    "recipients": [
      {"user_id": "u1", "email": "u1@example.com", "phone": "+14155550111", "data": {"name": "A"}},
      {"user_id": "u2", "email": "u2@example.com", "phone": "+14155550112", "data": {"name": "B"}}
    ]
  }'
```

## Delivery Tracking

After send, use the returned `notification_id`:

```bash
curl -X GET "http://localhost:8000/api/v1/notifications/{notification_id}" \
  -H "X-API-Key: your_tenant_api_key"
```

Typical states: `queued`, `sent`, `delivered`, `failed`.

## Channel Capability Discovery

Use this endpoint before constructing payloads:

```bash
curl -X GET "http://localhost:8000/api/v1/channels/capabilities" \
  -H "X-API-Key: your_tenant_api_key"
```

Response includes template requirements, recipient-field requirements, and subject support per channel.

## Template Management

Tenant templates can be managed from:

- Portal UI (`/portal/{tenant_id}/templates`)
- API (`/api/v1/tenant/templates/*`)

Platform can internally map tenant templates to provider-native template references where needed.

## Architecture and Plans

- Architecture: [ARCHITECTURE.md](./ARCHITECTURE.md)
- Implementation details: [IMPLEMENTATION_PLAN.md](./IMPLEMENTATION_PLAN.md)

## Notes

- Provider-specific complexity is abstracted from tenant clients.
- Tenant users should focus on payload correctness and delivery outcomes.
- For detailed onboarding/tutorial, see `/portal/how-to-use`.
