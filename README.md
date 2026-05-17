# Multi-Channel Notification Orchestration Platform

A multi-tenant notification platform for sending messages across WhatsApp, Email, SMS, Slack, and Voice from one API.

## What This Platform Does

- Single API for multi-channel notifications
- Tenant onboarding portal (signup/login/dashboard)
- Tenant-owned template management
- Automatic email branding footer support
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

## Current Scope

This repo currently works best as an internal notification module for one company:

- send notifications across email, SMS, WhatsApp, Slack, and voice
- receive inbound replies through provider webhooks
- classify reply intent and show it back in the dashboard
- apply tenant/company-owned templates and branding

The self-learning ML/agentic layer is preserved in the repo for future use, but it is not part of the active runtime path right now.

## Core Runtime Flow

1. Client sends a notification request to the API or SDK.
2. Notification is stored and queued.
3. Redis brokers the job to Celery.
4. Celery sends through the selected channel/provider with retry and failover logic.
5. Provider webhooks update delivery state.
6. Inbound replies are captured through webhook endpoints.
7. Replies are parsed, intent is detected, and live dashboard updates are pushed over WebSocket/Redis pub-sub.

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
cp .env.example .env
# Windows PowerShell:
# Copy-Item .env.example .env
#
# Then fill in your own secrets in .env before continuing.
```

Install Python dependencies for local non-Docker runs:

```bash
python -m venv venv
# Windows
venv\Scripts\activate
# Linux/macOS
# source venv/bin/activate

pip install -r requirements.txt
alembic upgrade head
```

### Run Modes

#### 1. Local API via `uvicorn` + Docker for Redis/Celery/ngrok

Use this for the fastest local development loop.

```bash
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
docker compose up -d --build
```

This local Docker stack starts:

- `redis`
- `celery_worker`
- `celery_beat`
- `ngrok`

#### 2. Local Full Docker Mode

Use this when you want the API to run in Docker too.

```bash
docker compose -f docker-compose.aws.yml up -d --build
```

This uses:

- `Dockerfile` for the API container
- `Dockerfile.celery` for the Celery worker
- `redis` in Docker

It does not start `ngrok`, so it is better for container parity than local inbound webhook testing.

#### 3. AWS / Containerized Deployment

Use the AWS compose file on the server:

```bash
docker compose -f docker-compose.aws.yml up -d --build
```

This uses:

- `Dockerfile` for the API container
- `Dockerfile.celery` for the Celery worker

For teammates pulling fresh code, the safest restart is:

```bash
docker compose down
docker compose up -d --build
```

If you are using full Docker mode or AWS compose, use the matching compose file:

```bash
docker compose -f docker-compose.aws.yml down
docker compose -f docker-compose.aws.yml up -d --build
```

The local Celery worker bind-mounts the repo, so after `git pull` it reads the latest code from the working tree instead of silently running stale baked-in worker code from an older image.

This matters for reliability:

- `celery_beat` runs the stuck-message recovery schedule automatically
- the worker performs a recovery sweep on startup after laptop or Docker restarts
- Celery containers now run as a non-root user
- beat stores its schedule file under `/tmp/celery` instead of writing into the repo mount

### Clone Checklist

After cloning on a new laptop:

1. Copy `.env.example` to `.env`
2. Add your own credentials and secrets
3. If using a reserved `ngrok` URL, make sure no other laptop is currently using that same URL
4. Choose a run mode:
   local `uvicorn` mode: start `uvicorn` and then `docker compose up -d --build`
   full Docker mode: run `docker compose -f docker-compose.aws.yml up -d --build`
5. Run the local stack checker:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\manual\check_local_stack.ps1
```

The checker verifies:

- Docker is available
- `redis` is running
- `celery_worker` is running
- `celery_beat` is running
- `ngrok` is running
- API `/health` responds

## Email Branding

Email branding is built into the active send flow.

What it does:

- appends a tenant/company branding footer to outgoing emails
- works for both template-based emails and raw-body emails
- applies in single-send, batch, and batch-multichannel email flows
- supports a default generated footer or custom footer HTML

How it works:

- branding is stored in `tenant_branding`
- email template rendering uses [src/services/tenant_template_engine.py](</c:/Users/PRATEEK G/Desktop/Notification-orchestration-prateek-dev/Notification_orchestration_agent_code/src/services/tenant_template_engine.py:23>)
- raw email bodies also go through branding-aware rendering
- notification send paths call the branding-aware renderer from [src/services/notification_service.py](</c:/Users/PRATEEK G/Desktop/Notification-orchestration-prateek-dev/Notification_orchestration_agent_code/src/services/notification_service.py:435>)

Branding can include:

- company logo URL
- company name
- theme/accent color
- contact email
- contact phone
- website
- optional custom footer HTML

Relevant endpoints:

- `POST /api/v1/branding`
- `POST /api/v1/branding/from-template`
- `GET /api/v1/branding`
- `DELETE /api/v1/branding`
- `POST /api/v1/branding/preview`

Operational notes:

- branding is email-focused; it is not appended to SMS/WhatsApp/voice bodies
- if no branding is configured, email still sends normally
- if custom footer HTML is provided, it replaces the default footer layout

Production recommendations for email branding:

- set up SPF, DKIM, and DMARC properly
- use a real Mailgun/custom sending domain instead of a sandbox domain
- host logos on a stable public URL or CDN
- keep logo size optimized for email clients

### Local ngrok vs AWS

- Local Docker uses `docker-compose.yml` and can start the `ngrok` container.
- AWS uses `docker-compose.aws.yml` and does not start any `ngrok` service.
- For local development, keep these in your local `.env`:

```env
APP_ENV=development
APP_BASE_URL=
NGROK_URL=https://your-subdomain.ngrok-free.app
NGROK_AUTHTOKEN=your-ngrok-token
```

- For AWS, set a real public host and do not rely on ngrok:

```env
APP_ENV=production
APP_BASE_URL=https://your-aws-domain-or-alb
```

In production, the app now only falls back to `NGROK_URL` when `APP_ENV` is `development` or `local`.

## Repo Layout

- `src/`: application code, services, SDK, tasks, models, and templates
- `tests/`: automated `pytest` coverage only
- `scripts/manual/`: manual smoke tests, DB checks, and diagnostics
- `tenant_demo_app/`: demo UI for tenant-side flows

## Tenant Onboarding Flow

1. Go to `/portal/signup`.
2. Create tenant account.
3. Save API key securely (shown at signup response).
4. Use API key in backend integration (`X-API-Key` header).
5. Login from `/portal/login` for dashboard/template management.

## Core API Endpoints

- `POST /api/v1/notifications/send`
- `POST /api/v1/notifications/batch`
- `POST /api/v1/notifications/batch-multichannel`
- `GET /api/v1/notifications/{notification_id}`
- `GET /api/v1/channels/capabilities`
- `POST /webhooks/inbound/mailgun`
- `POST /webhooks/inbound/twilio`
- `POST /webhooks/mailgun/delivery`
- `POST /webhooks/twilio`
- `POST /api/v1/tenant/auth/signup`
- `POST /api/v1/tenant/auth/login`
- `POST /api/v1/tenant/templates/`

Optional future route retained but intentionally disabled right now:

- `POST /api/v1/notifications/agentic`

## Direct Python Module Usage

Teams that do not want to run the FastAPI server can import the pipeline directly and connect to the same Supabase-backed database using the configured `DATABASE_URL`.

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
        "body": "Your order has shipped",
        "data": {"order_id": "ORD-1001"},
    },
)

print(result.notification_id)
```

This direct-import path does not require `uvicorn` or the HTTP API layer, but it still expects the supporting runtime to exist:

- Supabase Postgres reachable through `DATABASE_URL`
- Redis for idempotency/rate-limit style features
- Celery worker for queued delivery execution

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

Template + branding behavior:

- `email` can use template or raw body
- `sms`, `slack`, and `voice` can use template or raw body
- `whatsapp` requires a template
- email branding footer can be attached whether the email body came from a template or raw content

## Architecture and Plans

- Architecture: [ARCHITECTURE.md](./ARCHITECTURE.md)
- Implementation details: [IMPLEMENTATION_PLAN.md](./IMPLEMENTATION_PLAN.md)

## Notes

- Provider-specific complexity is abstracted from tenant clients.
- Tenant users should focus on payload correctness and delivery outcomes.
- Redis, Celery, and webhook processing are part of the active runtime and are required for reliable asynchronous delivery and inbound reply handling.
- For detailed onboarding/tutorial, see `/portal/how-to-use`.
