"""Dashboard routes - Supabase REST based."""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse
import os

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/", response_class=HTMLResponse)
async def dashboard():
    """Serve the main notification dashboard."""
    dashboard_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "templates", "dashboard.html"
    )
    with open(dashboard_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@router.get("/api/failures")
async def get_failed_notifications(limit: int = 20):
    """Get failed communications from Supabase."""
    from src.core.supabase import supabase_client
    rows = await supabase_client.select(
        "communications",
        "id,client_id,candidate_id,notification_type,channel_id,status,retry_count,created_at,updated_at",
        filters={"status": "eq.failed"},
    )
    return rows[:limit]


@router.get("/api/channel-health")
async def get_channel_health():
    """Get channel health summary from Supabase."""
    from src.core.supabase import supabase_client
    from collections import Counter

    comms = await supabase_client.select(
        "communications", "channel_id,status"
    )
    channels = await supabase_client.select("channels", "id,name")
    ch_map = {c["id"]: c["name"] for c in channels}

    health: dict = {}
    for comm in comms:
        name = ch_map.get(comm.get("channel_id"), "unknown")
        if name not in health:
            health[name] = {"total": 0, "delivered": 0, "failed": 0, "pending": 0, "success_rate": 0}
        health[name]["total"] += 1
        s = str(comm.get("status", "")).lower()
        if s in ("sent", "delivered"):
            health[name]["delivered"] += 1
        elif s == "failed":
            health[name]["failed"] += 1
        else:
            health[name]["pending"] += 1

    for ch in health.values():
        total = ch["total"]
        ch["success_rate"] = round((ch["delivered"] / total * 100), 2) if total else 0

    return health
