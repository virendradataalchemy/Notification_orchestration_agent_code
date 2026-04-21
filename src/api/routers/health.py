from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from redis.asyncio import Redis
from datetime import datetime

from src.core import get_db_optional, get_redis_client, supabase_client
from src.api.schemas import HealthResponse
from src.config import settings

router = APIRouter(tags=["health"])
templates = Jinja2Templates(directory="src/templates")


@router.get("/health", response_model=HealthResponse)
async def health_check(
    db: AsyncSession | None = Depends(get_db_optional),
    redis: Redis = Depends(get_redis_client)
):
    """
    Health check endpoint.

    Returns the status of the application and its dependencies.
    """
    services = {}

    # Check database
    try:
        if supabase_client.configured:
            await supabase_client.health_check()
            services["database"] = "healthy (supabase-rest)"
        else:
            if db is None:
                raise RuntimeError("Direct database session is unavailable")
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


@router.get("/", response_class=HTMLResponse)
@router.get("/app", response_class=HTMLResponse)
async def root(request: Request):
    """Main landing page - User Dashboard with client grid."""
    return templates.TemplateResponse(request, "user_dashboard.html")
