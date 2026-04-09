"""
Multi-client dashboard API backed by Supabase REST and the exported live schema.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from src.core import supabase_client
from src.config.department_mapping import (
    DEPARTMENT_LABELS,
    get_department_role_emails,
    resolve_template_department,
)
from src.services.supabase_notification_service import SupabaseNotificationService

router = APIRouter(tags=["client-dashboard"])
templates = Jinja2Templates(directory="src/templates")
notification_service = SupabaseNotificationService()


class DepartmentSendEmailRequest(BaseModel):
    to_email: str
    from_email: str
    template_id: int | None = None
    subject: str | None = None
    body: str | None = None
    notification_type: str | None = None
    priority: str = "high"


def _parse_dt(value: Any):
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


async def _load_dashboard_data() -> dict[str, Any]:
    return {
        "clients": await supabase_client.select("clients", "id,name,is_active,created_at"),
        "channels": await supabase_client.select("channels", "id,name,priority,is_active"),
        "communications": await supabase_client.select(
            "communications",
            "id,client_id,candidate_id,notification_type,channel_id,priority,status,template_id,idempotency_key,created_at,sent_at,retry_count",
        ),
        "candidates": await supabase_client.select("candidates", "id,client_id,name,email,phone,whatsapp_number"),
        "templates": await supabase_client.select(
            "templates",
            "id,client_id,name,language,subject,content,version,is_active,notification_type,channel_id,created_at",
        ),
        "providers": await supabase_client.select("providers", "id,client_id,channel_id,name,priority,is_active,created_at,config_ref"),
        "events": await supabase_client.select("notification_events", "id,communication_id,event_type,channel_id,status,metadata,created_at"),
        "attempts": await supabase_client.select("communication_attempts", "id,communication_id,attempt_number,status,error_message,provider_id,created_at"),
        "slots": await supabase_client.select("slots", "id,client_id,label,slot_time,duration_mins,slot_type,offered_via_channel_id,created_at"),
    }


def _channel_name_map(data: dict[str, Any]) -> dict[int, str]:
    return {row["id"]: row["name"] for row in data["channels"]}


def _normalize_status(value: Any) -> str:
    return str(value or "unknown").strip().lower().replace("-", "_").replace(" ", "_")


async def _ensure_candidate_for_email(client_id: int, email: str, fallback_name: str = "Department Recipient") -> int:
    rows = await supabase_client.select(
        "candidates",
        "id,name,email",
        limit=1,
        filters={"client_id": f"eq.{client_id}", "email": f"eq.{email}"},
    )
    if rows:
        return int(rows[0]["id"])

    latest = await supabase_client.select("candidates", "id", limit=1, filters={"order": "id.desc"})
    next_id = int(latest[0]["id"]) + 1 if latest else 1
    now = datetime.utcnow().isoformat()
    inserted = await supabase_client.insert(
        "candidates",
        {
            "id": next_id,
            "client_id": client_id,
            "name": fallback_name,
            "email": email,
            "language": "en",
            "metadata": {"department_contact": True, "created_via": "department_dashboard"},
            "created_at": now,
            "updated_at": now,
        },
    )
    return int(inserted[0]["id"])


async def _load_template_categories() -> dict[int, str]:
    """Load template category mapping when the optional category column exists."""
    try:
        rows = await supabase_client.select("templates", "id,category")
    except Exception:
        return {}
    return {int(row["id"]): str(row.get("category") or "") for row in rows if row.get("id") is not None}


@router.get("/client-dashboard", response_class=HTMLResponse)
async def client_dashboard_page(request: Request):
    return templates.TemplateResponse(request, "client_dashboard.html")


@router.get("/client-detail/{client_id}", response_class=HTMLResponse)
async def client_detail_page(request: Request, client_id: str):
    return templates.TemplateResponse(request, "client_detail.html", {"client_id": client_id})


@router.get("/client-detail-enhanced/{client_id}", response_class=HTMLResponse)
async def client_detail_enhanced_page(request: Request, client_id: str):
    return templates.TemplateResponse(request, "client_detail_enhanced.html", {"client_id": client_id})


@router.get("/api/client-dashboard/stats")
async def get_client_dashboard_stats(days: int = 30) -> Dict[str, Any]:
    data = await _load_dashboard_data()
    since_date = datetime.utcnow() - timedelta(days=days)
    channels_by_id = _channel_name_map(data)
    clients = [client for client in data["clients"] if client.get("is_active", True)]

    client_stats = []
    for client in sorted(clients, key=lambda row: row.get("name", "")):
        client_comms = [
            comm for comm in data["communications"]
            if comm.get("client_id") == client["id"] and ((_parse_dt(comm.get("created_at")) or since_date) >= since_date)
        ]
        breakdown: dict[str, dict[str, Any]] = {}
        for comm in client_comms:
            channel_name = channels_by_id.get(comm.get("channel_id"), "unknown")
            stats = breakdown.setdefault(
                channel_name,
                {"channel": channel_name, "queued": 0, "sent": 0, "delivered": 0, "failed": 0, "ringing": 0, "initiated": 0, "total": 0, "success_rate": 0},
            )
            status = str(comm.get("status", "unknown")).lower()
            stats[status] = stats.get(status, 0) + 1
            stats["total"] += 1
        for stats in breakdown.values():
            successful = stats.get("sent", 0) + stats.get("delivered", 0)
            stats["success_rate"] = round((successful / stats["total"] * 100) if stats["total"] else 0, 1)

        total_notifications = sum(item["total"] for item in breakdown.values())
        total_successful = sum(item.get("sent", 0) + item.get("delivered", 0) for item in breakdown.values())
        total_failed = sum(item.get("failed", 0) for item in breakdown.values())
        client_stats.append(
            {
                "client_id": client["id"],
                "client_name": client.get("name"),
                "tier": "free",
                "status": "active" if client.get("is_active", True) else "inactive",
                "total_notifications": total_notifications,
                "total_channels": len(breakdown),
                "channels": list(breakdown.values()),
                "summary": {
                    "queued": sum(item.get("queued", 0) for item in breakdown.values()),
                    "sent": sum(item.get("sent", 0) for item in breakdown.values()),
                    "delivered": sum(item.get("delivered", 0) for item in breakdown.values()),
                    "failed": total_failed,
                    "total": total_notifications,
                    "success_rate": round((total_successful / total_notifications * 100) if total_notifications else 0, 1),
                },
                "created_at": client.get("created_at"),
            }
        )

    client_name_map = {row["id"]: row.get("name") for row in data["clients"]}
    candidate_map = {row["id"]: row for row in data["candidates"]}
    recent_activity = []
    for comm in sorted(data["communications"], key=lambda row: row.get("created_at") or "", reverse=True):
        created_at = _parse_dt(comm.get("created_at"))
        if created_at and created_at >= since_date:
            candidate = candidate_map.get(comm.get("candidate_id"))
            recent_activity.append(
                {
                    "client_id": comm.get("client_id"),
                    "client_name": client_name_map.get(comm.get("client_id")),
                    "type": comm.get("notification_type"),
                    "channel": channels_by_id.get(comm.get("channel_id"), "unknown"),
                    "status": str(comm.get("status", "unknown")).lower(),
                    "created_at": comm.get("created_at"),
                    "delivered_at": comm.get("sent_at"),
                    "error": None,
                    "recipient": (candidate or {}).get("email") or (candidate or {}).get("phone") or "N/A",
                }
            )
            if len(recent_activity) >= 50:
                break

    total_notifications = len([c for c in data["communications"] if (_parse_dt(c.get("created_at")) or since_date) >= since_date])
    successful = len([c for c in data["communications"] if (_parse_dt(c.get("created_at")) or since_date) >= since_date and str(c.get("status", "")).lower() in {"sent", "delivered"}])
    failed = len([c for c in data["communications"] if (_parse_dt(c.get("created_at")) or since_date) >= since_date and str(c.get("status", "")).lower() == "failed"])
    queued = len([c for c in data["communications"] if (_parse_dt(c.get("created_at")) or since_date) >= since_date and str(c.get("status", "")).lower() == "queued"])

    return {
        "period_days": days,
        "generated_at": datetime.utcnow().isoformat(),
        "platform_summary": {
            "active_clients": len(clients),
            "total_notifications": total_notifications,
            "total_channels": len(data["channels"]),
            "successful": successful,
            "failed": failed,
            "queued": queued,
            "success_rate": round((successful / total_notifications * 100) if total_notifications else 0, 1),
        },
        "clients": client_stats,
        "recent_activity": recent_activity,
    }


@router.get("/api/client-dashboard/client/{client_id}/overview")
async def get_client_overview(client_id: str, days: int = 30) -> Dict[str, Any]:
    data = await _load_dashboard_data()
    client_pk = int(client_id)
    client = next((row for row in data["clients"] if row["id"] == client_pk), None)
    if not client:
        return {"error": "Client not found"}

    since_date = datetime.utcnow() - timedelta(days=days)
    channels_by_id = _channel_name_map(data)
    comms = [c for c in data["communications"] if c.get("client_id") == client_pk and ((_parse_dt(c.get("created_at")) or since_date) >= since_date)]
    channels = {}
    for comm in comms:
        channel_name = channels_by_id.get(comm.get("channel_id"), "unknown")
        stats = channels.setdefault(channel_name, {"channel": channel_name, "queued": 0, "sent": 0, "delivered": 0, "failed": 0, "ringing": 0, "initiated": 0, "total": 0, "success_rate": 0})
        status = str(comm.get("status", "unknown")).lower()
        stats[status] = stats.get(status, 0) + 1
        stats["total"] += 1
    for stats in channels.values():
        successful = stats.get("sent", 0) + stats.get("delivered", 0)
        stats["success_rate"] = round((successful / stats["total"] * 100) if stats["total"] else 0, 1)

    return {
        "client_id": client["id"],
        "client_name": client.get("name"),
        "tier": "free",
        "status": "active" if client.get("is_active", True) else "inactive",
        "created_at": client.get("created_at"),
        "channels": list(channels.values()),
        "period_days": days,
    }


@router.get("/api/client-dashboard/client/{client_id}/channel/{channel_name}")
async def get_client_channel_data(client_id: str, channel_name: str, days: int = 30, limit: int = 50) -> Dict[str, Any]:
    data = await _load_dashboard_data()
    since_date = datetime.utcnow() - timedelta(days=days)
    client_pk = int(client_id)
    channels_by_id = _channel_name_map(data)
    candidates_by_id = {row["id"]: row for row in data["candidates"]}
    templates_by_id = {row["id"]: row for row in data["templates"]}
    notifications = []

    for comm in sorted(data["communications"], key=lambda row: row.get("created_at") or "", reverse=True):
        created_at = _parse_dt(comm.get("created_at"))
        if comm.get("client_id") != client_pk or channels_by_id.get(comm.get("channel_id")) != channel_name or not created_at or created_at < since_date:
            continue
        candidate = candidates_by_id.get(comm.get("candidate_id"), {})
        template = templates_by_id.get(comm.get("template_id"))
        notifications.append(
            {
                "id": str(comm["id"]),
                "type": comm.get("notification_type"),
                "priority": str(comm.get("priority", "medium")).lower(),
                "user_id": str(comm.get("candidate_id")),
                "status": str(comm.get("status", "unknown")).lower(),
                "message_id": None,
                "attempts": comm.get("retry_count", 0),
                "error_message": None,
                "recipient": candidate.get("email") or candidate.get("phone") or "N/A",
                "subject": template.get("subject") if template else "",
                "delivered_at": comm.get("sent_at"),
                "opened_at": None,
                "clicked_at": None,
                "created_at": comm.get("created_at"),
                "llm_decision": None,
            }
        )
        if len(notifications) >= limit:
            break

    statistics = {"queued": 0, "sent": 0, "delivered": 0, "failed": 0, "ringing": 0, "initiated": 0, "total": len(notifications)}
    for item in notifications:
        statistics[item["status"]] = statistics.get(item["status"], 0) + 1
    successful = statistics.get("sent", 0) + statistics.get("delivered", 0)
    statistics["success_rate"] = round((successful / statistics["total"] * 100) if statistics["total"] else 0, 1)
    return {"client_id": client_id, "channel": channel_name, "statistics": statistics, "notifications": notifications, "period_days": days}


@router.get("/api/client-dashboard/client/{client_id}/recent-notifications")
async def get_client_recent_notifications(client_id: str, limit: int = 20) -> List[Dict[str, Any]]:
    data = await _load_dashboard_data()
    client_pk = int(client_id)
    channels_by_id = _channel_name_map(data)
    templates_by_id = {row["id"]: row for row in data["templates"]}
    events_by_comm: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for event in data["events"]:
        events_by_comm[event.get("communication_id")].append(event)

    response = []
    for comm in sorted(data["communications"], key=lambda row: row.get("created_at") or "", reverse=True):
        if comm.get("client_id") != client_pk:
            continue
        template = templates_by_id.get(comm.get("template_id"))
        reasoning = None
        comm_events = events_by_comm.get(comm.get("id"), [])
        if comm_events:
            latest = sorted(comm_events, key=lambda row: row.get("created_at") or "", reverse=True)[0]
            reasoning = {
                "channel": channels_by_id.get(comm.get("channel_id"), "unknown"),
                "reasoning": latest.get("event_type"),
            }
        response.append(
            {
                "id": str(comm["id"]),
                "type": comm.get("notification_type"),
                "priority": str(comm.get("priority", "medium")).lower(),
                "user_id": str(comm.get("candidate_id")),
                "status": str(comm.get("status", "unknown")).lower(),
                "subject": (template or {}).get("subject") or ((template or {}).get("content", "").splitlines()[0] if template else ""),
                "body": (template or {}).get("content", "")[:180],
                "channels": [channels_by_id.get(comm.get("channel_id"), "unknown")],
                "channel_statuses": [str(comm.get("status", "unknown")).lower()],
                "llm_decision": reasoning,
                "created_at": comm.get("created_at"),
            }
        )
        if len(response) >= limit:
            break
    return response


@router.get("/api/client-dashboard/client/{client_id}/provider-health")
async def get_client_provider_health(client_id: str) -> Dict[str, Any]:
    data = await _load_dashboard_data()
    client_pk = int(client_id)
    channels_by_id = _channel_name_map(data)
    providers = [row for row in data["providers"] if row.get("client_id") in (None, client_pk) and row.get("is_active", True)]
    attempts = data["attempts"]
    provider_stats = []
    for provider in providers:
        provider_attempts = [a for a in attempts if a.get("provider_id") == provider["id"]]
        failures = len([a for a in provider_attempts if str(a.get("status", "")).lower() == "failed"])
        total = len(provider_attempts)
        provider_stats.append(
            {
                "provider": provider["name"],
                "channel": channels_by_id.get(provider.get("channel_id"), "unknown"),
                "priority": provider.get("priority", 1),
                "is_active": provider.get("is_active", True),
                "attempts": total,
                "failures": failures,
                "success_rate": round(((total - failures) / total * 100) if total else 100, 1),
            }
        )
    return {
        "client_id": client_id,
        "provider_stats": provider_stats,
        "health_summary": {
            "healthy": len([p for p in provider_stats if p["is_active"]]),
            "degraded": len([p for p in provider_stats if p["attempts"] and p["success_rate"] < 100]),
            "total": len(provider_stats),
        },
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get("/api/client-dashboard/client/{client_id}/departments")
async def get_client_departments_dashboard(client_id: str, limit: int = 20) -> Dict[str, Any]:
    """Build department cards and metrics from existing communication/event data."""
    data = await _load_dashboard_data()
    client_pk = int(client_id)
    client = next((row for row in data["clients"] if row["id"] == client_pk), None)
    if not client:
        return {"error": "Client not found"}

    channels_by_id = _channel_name_map(data)
    template_categories = await _load_template_categories()
    candidates_by_id = {row["id"]: row for row in data["candidates"] if row.get("client_id") == client_pk}
    templates_by_id = {
        row["id"]: row
        for row in data["templates"]
        if row.get("is_active", True) and row.get("client_id") in (None, client_pk)
    }

    events_by_comm: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for event in data["events"]:
        comm_id = event.get("communication_id")
        if comm_id is not None:
            events_by_comm[comm_id].append(event)

    role_emails = get_department_role_emails(client_pk)
    departments: dict[str, Dict[str, Any]] = {
        dept: {
            "department": dept,
            "label": label,
            "role_emails": role_emails.get(dept, []),
            "metrics": {
                "total": 0,
                "sent": 0,
                "received": 0,
                "opened": 0,
                "failed": 0,
                "in_progress": 0,
            },
            "templates": [],
            "recent_mails": [],
        }
        for dept, label in DEPARTMENT_LABELS.items()
    }

    # Build template catalog by department from mapping rules.
    for template in templates_by_id.values():
        department = resolve_template_department(
            client_pk,
            template.get("id"),
            template.get("name"),
            template.get("notification_type"),
            template_categories.get(int(template.get("id"))),
        )
        if department not in departments:
            continue
        departments[department]["templates"].append(
            {
                "id": template.get("id"),
                "name": template.get("name"),
                "notification_type": template.get("notification_type"),
                "category": template_categories.get(int(template.get("id"))),
                "channel": channels_by_id.get(template.get("channel_id"), "unknown"),
                "subject": template.get("subject"),
                "content": template.get("content"),
            }
        )

    communications = [row for row in data["communications"] if row.get("client_id") == client_pk]
    communications.sort(key=lambda row: row.get("created_at") or "", reverse=True)

    for comm in communications:
        template = templates_by_id.get(comm.get("template_id"))
        department = resolve_template_department(
            client_pk,
            comm.get("template_id"),
            (template or {}).get("name"),
            comm.get("notification_type"),
            template_categories.get(int(comm.get("template_id"))) if comm.get("template_id") is not None else None,
        )
        if department not in departments:
            continue

        item = departments[department]
        metrics = item["metrics"]
        metrics["total"] += 1

        status = _normalize_status(comm.get("status"))
        sent_statuses = {"sent", "delivered", "completed", "closed"}
        failed_statuses = {"failed", "error", "undelivered"}
        progress_statuses = {"queued", "opened", "in_progress", "ringing", "initiated"}

        if status in sent_statuses:
            metrics["sent"] += 1
        if status in failed_statuses:
            metrics["failed"] += 1
        if status in progress_statuses:
            metrics["in_progress"] += 1

        opened_at = None
        received = status in sent_statuses
        opened = False
        for event in events_by_comm.get(comm.get("id"), []):
            event_type = _normalize_status(event.get("event_type"))
            event_status = _normalize_status(event.get("status"))
            if event_type in {"sent", "delivered", "opened"} or event_status in {"sent", "delivered", "opened"}:
                received = True
            if event_type == "opened" or event_status == "opened":
                opened = True
                opened_at = event.get("created_at") or opened_at

        if received:
            metrics["received"] += 1
        if opened:
            metrics["opened"] += 1

        if len(item["recent_mails"]) < limit:
            candidate = candidates_by_id.get(comm.get("candidate_id"), {})
            item["recent_mails"].append(
                {
                    "communication_id": comm.get("id"),
                    "mail_type": comm.get("notification_type"),
                    "template_id": comm.get("template_id"),
                    "template_name": (template or {}).get("name"),
                    "template_category": template_categories.get(int(comm.get("template_id"))) if comm.get("template_id") is not None else None,
                    "channel": channels_by_id.get(comm.get("channel_id"), "unknown"),
                    "status": status,
                    "direction": "received" if received else "sent",
                    "recipient": candidate.get("email") or candidate.get("phone") or candidate.get("whatsapp_number") or "N/A",
                    "subject": (template or {}).get("subject"),
                    "created_at": comm.get("created_at"),
                    "opened_at": opened_at,
                }
            )

    for dept in departments.values():
        dept["templates"].sort(key=lambda row: (str(row.get("name") or "").lower(), row.get("id") or 0))

    return {
        "client_id": client_pk,
        "client_name": client.get("name"),
        "generated_at": datetime.utcnow().isoformat(),
        "departments": [departments["hr"], departments["it"], departments["finance"]],
        "use_cases": [
            {
                "key": "new_candidate_setup",
                "title": "Candidate Added -> HR informs IT",
                "description": "After candidate creation, HR triggers setup mail to IT for resource preparation.",
                "teams": ["HR", "IT"],
            },
            {
                "key": "attendance_payroll",
                "title": "Attendance Record -> HR to Finance",
                "description": "Attendance details are captured and forwarded so Finance can process paychecks.",
                "teams": ["IT", "HR", "Finance"],
            },
        ],
    }


@router.get("/api/client-dashboard/client/{client_id}/departments/{department_key}")
async def get_client_department_detail(client_id: str, department_key: str, limit: int = 30) -> Dict[str, Any]:
    """Return details for a single department card."""
    normalized = department_key.strip().lower()
    if normalized not in DEPARTMENT_LABELS:
        return {"error": "Department not found"}

    aggregate = await get_client_departments_dashboard(client_id=client_id, limit=limit)
    if aggregate.get("error"):
        return aggregate

    departments = aggregate.get("departments", [])
    selected = next((item for item in departments if item.get("department") == normalized), None)
    if not selected:
        return {"error": "Department not found"}

    return {
        "client_id": aggregate.get("client_id"),
        "client_name": aggregate.get("client_name"),
        "generated_at": aggregate.get("generated_at"),
        "department": selected,
        "use_cases": [
            item
            for item in aggregate.get("use_cases", [])
            if DEPARTMENT_LABELS[normalized] in item.get("teams", [])
        ],
    }


@router.post("/api/client-dashboard/client/{client_id}/departments/{department_key}/send-email")
async def send_department_email(client_id: str, department_key: str, payload: DepartmentSendEmailRequest) -> Dict[str, Any]:
    """Send internal department email directly from dashboard using configured providers."""
    normalized = department_key.strip().lower()
    if normalized not in DEPARTMENT_LABELS:
        raise HTTPException(status_code=404, detail="Department not found")

    client_pk = int(client_id)
    to_email = payload.to_email.strip().lower()
    if not to_email:
        raise HTTPException(status_code=400, detail="to_email is required")

    from_email = payload.from_email.strip().lower()
    fallback_name = to_email.split("@")[0].replace(".", " ").title() if "@" in to_email else "Department Recipient"
    candidate_id = await _ensure_candidate_for_email(client_pk, to_email, fallback_name=fallback_name)

    template_rows = []
    if payload.template_id is not None:
        template_rows = await supabase_client.select(
            "templates",
            "id,name,subject,content,notification_type,channel_id,category",
            limit=1,
            filters={"id": f"eq.{payload.template_id}"},
        )

    template = template_rows[0] if template_rows else None
    body = (payload.body or (template or {}).get("content") or "").strip()
    subject = (payload.subject or (template or {}).get("subject") or f"{DEPARTMENT_LABELS[normalized]} Update").strip()
    notification_type = (payload.notification_type or (template or {}).get("notification_type") or f"{normalized}_internal_mail").strip()

    if not body:
        raise HTTPException(status_code=400, detail="Email body is required")

    send_result = await notification_service.send_notification(
        client_pk,
        {
            "candidate_id": candidate_id,
            "email": to_email,
            "template_id": payload.template_id,
            "notification_type": notification_type,
            "priority": payload.priority,
            "channels": ["email"],
            "subject": subject,
            "body": body,
            "data": {
                "department": normalized,
                "from_email": from_email,
                "to_email": to_email,
                "source": "department_dashboard",
            },
        },
    )

    return {
        "status": "queued",
        "department": normalized,
        "to_email": to_email,
        "from_email": from_email,
        "result": send_result,
    }


@router.get("/api/client-dashboard/client/{client_id}/deduplication-stats")
async def get_client_deduplication_stats(client_id: str, days: int = 30) -> Dict[str, Any]:
    data = await _load_dashboard_data()
    client_pk = int(client_id)
    since_date = datetime.utcnow() - timedelta(days=days)
    comms = [c for c in data["communications"] if c.get("client_id") == client_pk and ((_parse_dt(c.get("created_at")) or since_date) >= since_date)]
    keyed = [c for c in comms if c.get("idempotency_key")]
    unique_keys = len(set(c.get("idempotency_key") for c in keyed))
    prevented = max(0, len(keyed) - unique_keys)
    return {
        "client_id": client_id,
        "period_days": days,
        "total_notifications": len(comms),
        "total_with_idempotency": len(keyed),
        "unique_idempotency_keys": unique_keys,
        "potential_duplicates_prevented": prevented,
        "deduplication_percentage": round((prevented / len(keyed) * 100) if keyed else 0, 1),
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get("/api/client-dashboard/client/{client_id}/llm-decisions")
async def get_client_llm_decisions(client_id: str, limit: int = 50) -> Dict[str, Any]:
    data = await _load_dashboard_data()
    client_pk = int(client_id)
    channel_map = _channel_name_map(data)
    comms = {row["id"]: row for row in data["communications"] if row.get("client_id") == client_pk}
    decisions = []
    for event in sorted(data["events"], key=lambda row: row.get("created_at") or "", reverse=True):
        communication = comms.get(event.get("communication_id"))
        if not communication:
            continue
        decisions.append(
            {
                "id": str(event.get("communication_id")),
                "type": event.get("event_type"),
                "priority": str(communication.get("priority", "medium")).lower(),
                "llm_channel": channel_map.get(event.get("channel_id")) if event.get("channel_id") else channel_map.get(communication.get("channel_id")),
                "llm_timing": None,
                "retry_strategy": None,
                "reasoning": event.get("event_type"),
                "channels_used": [channel_map.get(communication.get("channel_id"), "unknown")],
                "channel_statuses": [str(communication.get("status", "unknown")).lower()],
                "created_at": event.get("created_at"),
            }
        )
        if len(decisions) >= limit:
            break
    return {
        "client_id": client_id,
        "total_llm_decisions": len(decisions),
        "channel_distribution": dict(Counter(d["llm_channel"] for d in decisions if d["llm_channel"])),
        "timing_distribution": {},
        "decisions": decisions,
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get("/api/client-dashboard/client/{client_id}/service-showcase")
async def get_client_service_showcase(client_id: str) -> Dict[str, Any]:
    data = await _load_dashboard_data()
    client_pk = int(client_id)
    client = next((row for row in data["clients"] if row["id"] == client_pk), None)
    if not client:
        return {"error": "Client not found"}

    channels_by_id = {row["id"]: row for row in data["channels"]}
    client_templates = [row for row in data["templates"] if row.get("client_id") == client_pk and row.get("is_active", True)]
    client_providers = [row for row in data["providers"] if row.get("client_id") in (None, client_pk) and row.get("is_active", True)]
    client_slots = [row for row in data["slots"] if row.get("client_id") == client_pk]
    client_comms = [row for row in data["communications"] if row.get("client_id") == client_pk]
    dedup_keys = [row.get("idempotency_key") for row in client_comms if row.get("idempotency_key")]
    templates_by_channel = Counter(channels_by_id.get(row.get("channel_id"), {}).get("name", "unknown") for row in client_templates)

    # Get events for tracking metrics
    client_events = [row for row in data.get("events", []) if any(
        comm.get("id") == row.get("communication_id") for comm in client_comms
    )]
    
    services = []
    for channel_name in ["email", "sms", "whatsapp", "voice", "push", "in_app", "slack"]:
        channel = next((row for row in data["channels"] if row.get("name") == channel_name), None)
        if not channel:
            continue
        channel_templates = [row for row in client_templates if row.get("channel_id") == channel["id"]]
        channel_providers = [row["name"] for row in client_providers if row.get("channel_id") == channel["id"]]
        
        # Calculate metrics for this channel
        channel_comms = [row for row in client_comms if row.get("channel_id") == channel["id"]]
        channel_comm_ids = {row["id"] for row in channel_comms}
        
        sent_count = len([row for row in channel_comms if str(row.get("status", "")).lower() in {"sent", "delivered"}])
        delivered_count = len([row for row in channel_comms if str(row.get("status", "")).lower() == "delivered"])
        failed_count = len([row for row in channel_comms if str(row.get("status", "")).lower() == "failed"])
        
        # Track opened, clicked, unsubscribed from events
        channel_events = [row for row in client_events if row.get("communication_id") in channel_comm_ids]
        opened_count = len([row for row in channel_events if row.get("event_type") == "opened"])
        clicked_count = len([row for row in channel_events if row.get("event_type") == "clicked"])
        unsubscribed_count = len([row for row in channel_events if row.get("event_type") == "unsubscribed"])
        
        services.append(
            {
                "channel": channel_name,
                "enabled": channel.get("is_active", False),
                "priority": channel.get("priority"),
                "providers": channel_providers,
                "template_count": len(channel_templates),
                "sample_templates": [row.get("name") for row in channel_templates[:3]],
                "sent_count": sent_count,
                "delivered_count": delivered_count,
                "failed_count": failed_count,
                "opened_count": opened_count,
                "clicked_count": clicked_count,
                "unsubscribed_count": unsubscribed_count,
            }
        )

    return {
        "client_id": client_pk,
        "client_name": client.get("name"),
        "services": services,
        "routing": {
            "implemented": True,
            "available_channels": [row.get("name") for row in data["channels"] if row.get("is_active", True)],
            "provider_count": len(client_providers),
        },
        "deduplication": {
            "implemented": True,
            "communications_with_keys": len(dedup_keys),
            "potential_duplicates_prevented": max(0, len(dedup_keys) - len(set(dedup_keys))),
        },
        "templates": {
            "total": len(client_templates),
            "by_channel": dict(templates_by_channel),
        },
        "slots": {
            "total": len(client_slots),
            "types": dict(Counter(row.get("slot_type", "unknown") for row in client_slots)),
        },
        "activity": {
            "communications": len(client_comms),
            "statuses": dict(Counter(str(row.get("status", "unknown")).lower() for row in client_comms)),
        },
        "frontend_actions": {
            "templates": f"/portal/{client_pk}/templates",
            "create_template": f"/portal/{client_pk}/templates/create",
            "metrics": f"/client-detail/{client_pk}",
        },
    }
