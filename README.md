# Multi Tenant Orchestration System

This repository contains a multi-tenant communication orchestration platform with:

- a `FastAPI` backend for APIs, orchestration, authentication checks, admin endpoints, and provider integrations
- a `Next.js` frontend for the modern client portal and admin workspace
- `Supabase` as the main data/auth backend
- `Redis` for cache/runtime support

The current direction of the project is:

- `Next.js` is the primary frontend
- `FastAPI` provides backend APIs
- Supabase schema is treated as the source of truth
- some older Jinja templates still exist in the backend as legacy UI code and can be cleaned up in a later pass

## Architecture

### High-level structure

- `frontend/`
  - Next.js 16 app
  - client login/signup
  - admin login and admin workspace
  - client portal pages such as portal, templates, analytics, and demo flows

- `src/`
  - FastAPI application
  - REST/API routers
  - Supabase REST client
  - orchestration and provider services
  - middleware, models, and workers

- `supabase_tables/`
  - exported table snapshots used as schema reference during alignment work

- `tests/`
  - backend tests and test scaffolding

### Current frontend/backend split

The active UI is in `frontend/`.

The backend still contains some HTML/Jinja routes in `src/templates` and routers that return `TemplateResponse(...)`, but those are mostly legacy UI pieces. The modern portal and admin flow are now intended to run from Next.js.

## Tech Stack

### Frontend

- Next.js `16.2.2`
- React `19`
- TypeScript
- Tailwind CSS `4`
- Supabase JS client

### Backend

- FastAPI
- Uvicorn
- Pydantic / pydantic-settings
- SQLAlchemy
- httpx / aiohttp
- Redis
- Celery dependencies are present, but the worker is currently disabled

### Data and integrations

- Supabase REST API
- Supabase Auth
- Redis
- AWS SES / SQS / S3
- Twilio
- Slack
- Firebase
- optional LLM integrations

## Important Current Reality

This codebase has gone through a schema rename from older naming such as:

- `tenant` -> `client`
- `contact` -> `candidate`

The application is being aligned to the existing Supabase schema instead of renaming the database again.

Current important table names used by the app:

- `clients`
- `candidates`
- `communications`
- `client_preferences`
- `templates`
- `channels`
- `providers`
- `communication_attempts`
- `notification_events`
- `device_tokens`
- `admins`

## Repository Layout

### Backend

- [src/main.py](/c:/Users/PRATEEK%20G/Desktop/Notification_orchestration_agent_code/Notification_orchestration_agent_code/src/main.py)
  - FastAPI app entry point
  - router registration
  - middleware
  - lifespan initialization

- [src/core/supabase.py](/c:/Users/PRATEEK%20G/Desktop/Notification_orchestration_agent_code/Notification_orchestration_agent_code/src/core/supabase.py)
  - lightweight Supabase REST client
  - auth user lookup
  - admin user creation via Supabase Auth Admin API

- [src/api/routers/client_management.py](/c:/Users/PRATEEK%20G/Desktop/Notification_orchestration_agent_code/Notification_orchestration_agent_code/src/api/routers/client_management.py)
  - client profile management
  - client lookup by id, slug, or Supabase UID
  - signup-time client creation/update logic

- [src/api/routers/client_templates.py](/c:/Users/PRATEEK%20G/Desktop/Notification_orchestration_agent_code/Notification_orchestration_agent_code/src/api/routers/client_templates.py)
  - client-facing template CRUD APIs
  - global/shared template inclusion logic

- [src/api/routers/admin.py](/c:/Users/PRATEEK%20G/Desktop/Notification_orchestration_agent_code/Notification_orchestration_agent_code/src/api/routers/admin.py)
  - protected admin APIs
  - admin workspace data
  - admin creation flow

- [src/api/dependencies.py](/c:/Users/PRATEEK%20G/Desktop/Notification_orchestration_agent_code/Notification_orchestration_agent_code/src/api/dependencies.py)
  - authentication dependencies
  - admin access checks against the `admins` table

- [src/api/routers/client_dashboard.py](/c:/Users/PRATEEK%20G/Desktop/Notification_orchestration_agent_code/Notification_orchestration_agent_code/src/api/routers/client_dashboard.py)
  - analytics-style APIs used by the frontend client portal

### Frontend

- [frontend/src/app/page.tsx](/c:/Users/PRATEEK%20G/Desktop/Notification_orchestration_agent_code/Notification_orchestration_agent_code/frontend/src/app/page.tsx)
  - public landing page

- [frontend/src/app/login/page.tsx](/c:/Users/PRATEEK%20G/Desktop/Notification_orchestration_agent_code/Notification_orchestration_agent_code/frontend/src/app/login/page.tsx)
  - client sign-in

- [frontend/src/app/signup/page.tsx](/c:/Users/PRATEEK%20G/Desktop/Notification_orchestration_agent_code/Notification_orchestration_agent_code/frontend/src/app/signup/page.tsx)
  - client signup and provisioning flow

- [frontend/src/app/admin/page.tsx](/c:/Users/PRATEEK%20G/Desktop/Notification_orchestration_agent_code/Notification_orchestration_agent_code/frontend/src/app/admin/page.tsx)
  - admin login
  - admin workspace
  - create-admin form

- [frontend/src/app/clients/[slug]](/c:/Users/PRATEEK%20G/Desktop/Notification_orchestration_agent_code/Notification_orchestration_agent_code/frontend/src/app/clients/[slug])
  - canonical client route group

- [frontend/src/components/client-portal-shell.tsx](/c:/Users/PRATEEK%20G/Desktop/Notification_orchestration_agent_code/Notification_orchestration_agent_code/frontend/src/components/client-portal-shell.tsx)
  - shared client portal shell/navigation

- [frontend/src/lib/client-routes.ts](/c:/Users/PRATEEK%20G/Desktop/Notification_orchestration_agent_code/Notification_orchestration_agent_code/frontend/src/lib/client-routes.ts)
  - route helper functions

- [frontend/src/lib/clientProvisioning.ts](/c:/Users/PRATEEK%20G/Desktop/Notification_orchestration_agent_code/Notification_orchestration_agent_code/frontend/src/lib/clientProvisioning.ts)
  - ensures client profile exists after auth

## Prerequisites

Install and configure:

- Python `3.11+` recommended
- Node.js `18+` recommended
- npm
- Redis
- a Supabase project

## Environment Variables

Settings are loaded from `.env` through [src/config/settings.py](/c:/Users/PRATEEK%20G/Desktop/Notification_orchestration_agent_code/Notification_orchestration_agent_code/src/config/settings.py).

### Minimum backend variables

These are the core variables you should set to run the app locally:

```env
REDIS_URL=redis://localhost:6379/0
SECRET_KEY=change-me
JWT_SECRET_KEY=change-me-too
AWS_SES_FROM_EMAIL=no-reply@example.com

SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-anon-or-api-key
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
```

### Common optional variables

```env
APP_ENV=development
DEBUG=true
LOG_LEVEL=INFO
HOST=0.0.0.0
PORT=8000

TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_PHONE_NUMBER=
TWILIO_WHATSAPP_NUMBER=

SLACK_BOT_TOKEN=
SLACK_SIGNING_SECRET=
SLACK_WEBHOOK_URL=

FIREBASE_CREDENTIALS_PATH=
QWEN_API_KEY=
MISTRAL_API_KEY=
```

### Frontend variables

The frontend uses `.env.local` inside `frontend/`. Typical values are:

```env
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-anon-key
```

## Installation

### 1. Backend setup

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Frontend setup

```powershell
cd frontend
npm install
```

## Running Locally

### Start the backend

From the repository root:

```powershell
uvicorn src.main:app --reload
```

Backend default URL:

- `http://127.0.0.1:8000`

API docs:

- `http://127.0.0.1:8000/api/v1/docs`

### Start the frontend

From `frontend/`:

```powershell
npm run dev
```

Frontend default URL:

- `http://localhost:3000`

If port `3000` is already in use, Next may move to another port such as `3001`.

## Authentication Flows

### Client flow

Client signup and login are handled through Supabase Auth plus a matching row in `clients`.

The frontend provisioning flow:

1. user signs up or logs in through Supabase Auth
2. frontend calls backend client profile endpoints
3. backend creates or updates the matching `clients` row
4. client enters the frontend client portal

### Admin flow

Admins are not created from the public client signup flow.

Admin access works like this:

1. user signs in with Supabase Auth
2. backend checks that the authenticated user exists in `public.admins`
3. only then is `/admin` access granted

## Admin Table SQL

Create the `admins` table in Supabase SQL Editor:

```sql
create table if not exists public.admins (
  id bigint generated by default as identity primary key,
  supabase_uid uuid not null unique,
  email text not null unique,
  name text,
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_admins_supabase_uid on public.admins (supabase_uid);
create index if not exists idx_admins_email on public.admins (email);

create or replace function public.set_admins_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists trg_admins_updated_at on public.admins;

create trigger trg_admins_updated_at
before update on public.admins
for each row
execute function public.set_admins_updated_at();

alter table public.admins enable row level security;
```

### First admin bootstrap

To create the first admin:

1. create the user manually in Supabase Auth
2. copy the Auth user UUID
3. insert it into `public.admins`

Example:

```sql
insert into public.admins (supabase_uid, email, name, is_active)
values (
  'PUT_AUTH_USER_UUID_HERE',
  'admin@example.com',
  'Platform Admin',
  true
);
```

After that, the admin can log in at `/admin` and create more admins from the UI.

## Routing

### Public routes

- `/`
- `/login`
- `/signup`
- `/admin`

### Canonical client routes

- `/clients/:slug/portal`
- `/clients/:slug/templates`
- `/clients/:slug/templates/new`
- `/clients/:slug/notifications/demo`
- `/clients/:slug/analytics`

### Notes on client route identity

The app supports client `slug` when present and may still fall back to numeric client id in some compatibility paths.

Current recommended rule:

- use `client_slug` when it exists
- use `client.id` only as a fallback for older records

If you want fully slug-only URLs, backfill `client_slug` for all existing rows first and then remove the id fallback safely.

## Supabase Notes

The app uses a lightweight REST wrapper rather than a full ORM-first Supabase integration. See [src/core/supabase.py](/c:/Users/PRATEEK%20G/Desktop/Notification_orchestration_agent_code/Notification_orchestration_agent_code/src/core/supabase.py).

Important points:

- backend talks to Supabase through `rest/v1`
- admin auth creation uses Supabase Auth Admin API
- many reads/writes were aligned against the exported CSV schema in `supabase_tables/`

## Legacy Jinja Templates

The repo still includes Jinja templates and HTML routes under:

- `src/templates/`
- several backend routers returning `TemplateResponse(...)`

These are mostly legacy UI code now that the active portal moved to Next.js.

Do not remove them blindly yet if:

- a backend HTML page is still being used manually
- a route still mixes HTML and API behavior

Safe cleanup strategy:

1. keep API endpoints that the frontend still calls
2. remove or redirect old HTML-only routes
3. delete unused templates after confirming there are no active links to them

## Worker Status

Background worker support is present in the repo, but [run_worker.py](/c:/Users/PRATEEK%20G/Desktop/Notification_orchestration_agent_code/Notification_orchestration_agent_code/run_worker.py) is currently disabled.

Right now:

- notifications are sent directly through the API process
- no separate worker process is required for local development

## Useful Commands

### Backend

```powershell
uvicorn src.main:app --reload
```

### Frontend

```powershell
cd frontend
npm run dev
```

### TypeScript check

```powershell
frontend\node_modules\.bin\tsc -p frontend\tsconfig.json --noEmit
```

### Python compile check

```powershell
@'
import py_compile
py_compile.compile(r"src/main.py", doraise=True)
print("ok")
'@ | python -
```

## Common Issues

### Next.js dev server says another server is already running

Stop the previous process and restart:

```powershell
Stop-Process -Id <PID> -Force
cd frontend
npm run dev
```

### Supabase Auth user exists but client row is missing

The project includes client profile provisioning logic, but if data is partially created you may need to:

- verify the `clients` row exists
- verify `supabase_uid` is set correctly
- verify `client_preferences` row matches the actual schema

### Hydration mismatch warnings in development

If the warning mentions extra attributes such as extension-added attributes, test in:

- incognito mode
- a browser session with extensions disabled

Some earlier warnings were caused by browser extensions mutating the DOM before hydration.

## Development Notes

- Treat the Supabase schema as the source of truth
- Prefer updating the code to match the existing database
- Be careful with older `tenant` and `contact` naming still present in legacy files
- The frontend is now the primary UI surface
- Some compatibility routes remain intentionally while migration is still in progress

## Next Recommended Cleanup Items

- backfill and stabilize `client_slug`
- remove legacy Jinja UI routes once fully unused
- consolidate remaining old `client/[id]` implementation paths if desired
- document exact Supabase SQL for all current production tables

## License

No license file is currently present in the repository. Add one if this project will be shared or published.
