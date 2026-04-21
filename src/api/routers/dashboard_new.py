"""Dashboard API routes."""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse
import os

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/", response_class=HTMLResponse)
async def dashboard():
    """Serve the main notification dashboard."""
    dashboard_path = os.path.join(os.path.dirname(__file__), "..", "..", "templates", "dashboard.html")
    with open(dashboard_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())
