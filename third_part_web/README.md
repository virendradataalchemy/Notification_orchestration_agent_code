# Third Party Web

This folder contains a fully isolated test web app that behaves like an external product using the notification orchestration API.

## What it does

- stores API settings in browser local storage
- stores test candidates in browser local storage
- sends message content through the existing integration trigger endpoint
- does not depend on the main frontend code

## Important design choice

This app does not create candidates in the main backend, and it does not target backend-saved candidate IDs.

Why:
- you asked to keep it completely isolated
- the current public integration API is for triggering notifications, not full candidate management
- local candidate storage makes this app act like a separate third-party client without changing the main product

Every send uses the locally stored candidate contact fields through `to.email`, `to.phone`, and `to.whatsapp_number`.

## Files

- `index.html`
- `styles.css`
- `app.js`
- `.env`

## Run locally

You can serve it with any static server. For example:

```powershell
cd third_part_web
python -m http.server 5500
```

Then open:

```text
http://127.0.0.1:5500
```

## Optional `.env` preload

When served from `third_part_web`, the app will try to load `./.env` on page boot and prefill settings from it.

Supported keys:

- `API_KEY`
- `INTEGRATION_BASE_URL` or `BASE_URL`
- `AUTH_MODE`
- `CLIENT_ID`

If the same setting is already saved in browser local storage, the browser-saved value wins.

## Default API URL

The app defaults to:

```text
http://127.0.0.1:8000/api/v1/integration
```

That matches the current route wiring in this repo.

## Auth modes

- `Bearer API Key`
- `Dev Client Id`

Use `Dev Client Id` for local debug flows if API key auth is not available in your current environment.
