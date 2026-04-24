# Tenant Demo App

This folder contains a single browser-based demo client (`index.html`) for manual tenant testing.

## Run

```powershell
python -m http.server 8088
```

Open:

```text
http://127.0.0.1:8088
```

## What you can test

1. Single notification send (`POST /api/v1/notifications/send`)
2. Multi-channel bulk send (`POST /api/v1/notifications/batch-multichannel`)
3. Notification status lookup (`GET /api/v1/notifications/{notification_id}`)

## Current payload behavior in demo app

1. Platform base URL (default `http://127.0.0.1:8000`)
2. Tenant API key (from tenant portal developer settings)
3. Channels are user-selectable via checkboxes, filtered by tenant availability from `/api/v1/tenant/settings/channels`
4. Templates can be used for all channels; `template_id` is mandatory only when `whatsapp` is included
5. For non-WhatsApp channels, `template_id` is optional and raw `body` is allowed
6. Single send supports `Template Variables JSON` -> sent as `notification.data`
7. Bulk send supports `Bulk Template Variables JSON`, merged into each recipient `data`
8. One-click presets are available for common flows (email/sms/voice raw, WhatsApp template, Slack template, and bulk presets)
