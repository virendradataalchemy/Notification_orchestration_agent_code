from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from redis.asyncio import Redis
from datetime import datetime
from pathlib import Path

from src.core import get_db, get_redis_client
from src.api.schemas import HealthResponse
from src.config import settings

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health_check(
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis_client)
):
    """
    Health check endpoint.

    Returns the status of the application and its dependencies.
    """
    services = {}

    # Check database
    try:
        await db.execute(text("SELECT 1"))
        services["database"] = "healthy"
    except Exception as e:
        services["database"] = f"unhealthy: {str(e)}"

    # Check Redis
    try:
        await redis.ping()
        services["redis"] = "healthy"
    except Exception as e:
        services["redis"] = f"unhealthy: {str(e)}"

    # Overall status
    overall_status = "healthy" if all(
        s == "healthy" for s in services.values()
    ) else "degraded"

    return HealthResponse(
        status=overall_status,
        timestamp=datetime.utcnow(),
        version=settings.api_version,
        services=services,
    )


@router.get("/")
async def root():
    """Platform landing page."""
    template_path = Path(__file__).parent.parent.parent / "templates" / "platform_home.html"
    with open(template_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@router.get("/status", response_class=HTMLResponse)
async def status_page():
    """Human-friendly health status page."""
    template_path = Path(__file__).parent.parent.parent / "templates" / "platform_status.html"
    with open(template_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@router.get("/channels", response_class=HTMLResponse)
async def channels_page():
    """Human-friendly channel capabilities page."""
    template_path = Path(__file__).parent.parent.parent / "templates" / "platform_channels.html"
    with open(template_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())
