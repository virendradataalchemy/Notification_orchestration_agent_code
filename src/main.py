from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import logging
from datetime import datetime

from src.config import settings
from src.core import init_db, init_redis, close_redis
from src.middleware import TenantAuthMiddleware
from src.services.usage_tracker import initialize_usage_tracker
from src.utils.logger import configure_logging
from src.api.routers import (
    notifications_router,
    templates_router,
    preferences_router,
    webhooks_router,
    health_router,
    dashboard_router,
    admin_router,
    tenant_management_router,
    usage_router,
    tenant_dashboard_router,
    tenant_templates_router,
    tenant_portal_router,
    tenant_auth_router,
    channels_router,
    tenant_settings_router,
    admin_auth_router,
    admin_auth_portal_router,
    tenant_team_router,
    websocket_router,
    compliance_router,
    branding_router,
)

# Configure logging
configure_logging(settings.log_level)
logger = logging.getLogger(__name__)

QUIET_PATHS = {
    "/health",
    f"{settings.api_prefix}/docs",
    f"{settings.api_prefix}/redoc",
    f"{settings.api_prefix}/openapi.json",
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    logger.info("Starting notification orchestration application...")

    # Initialize database
    try:
        await init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")

    # Initialize Redis
    try:
        await init_redis()
        logger.info("Redis initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize Redis: {e}")

    # Initialize usage tracker
    try:
        await initialize_usage_tracker()
        logger.info("Usage tracker initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize usage tracker: {e}")

    yield

    # Cleanup
    logger.info("Shutting down notification orchestration application...")
    await close_redis()


# Create FastAPI app
app = FastAPI(
    title="Multi-Channel Notification Orchestration Platform",
    description="Centralized multi-tenant platform for managing notifications across multiple channels",
    version=settings.api_version,
    docs_url=f"{settings.api_prefix}/docs",
    redoc_url=f"{settings.api_prefix}/redoc",
    openapi_url=f"{settings.api_prefix}/openapi.json",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Tenant authentication middleware (disabled for development)
# app.add_middleware(TenantAuthMiddleware)


# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log only important HTTP requests."""
    start_time = datetime.utcnow()

    try:
        response = await call_next(request)
    except Exception:
        duration = (datetime.utcnow() - start_time).total_seconds()
        logger.error(
            f"{request.method} {request.url.path} failed after {duration:.3f}s",
            exc_info=True,
        )
        raise

    duration = (datetime.utcnow() - start_time).total_seconds()
    path = request.url.path
    should_log = (
        path not in QUIET_PATHS
        and not path.startswith("/static/")
        and (
            response.status_code >= 400
            or duration >= 1.0
            or request.method in {"POST", "PUT", "PATCH", "DELETE"}
        )
    )

    if should_log:
        message = f"{request.method} {path} -> {response.status_code} in {duration:.3f}s"
        if response.status_code >= 500:
            logger.error(message)
        elif response.status_code >= 400:
            logger.warning(message)
        else:
            logger.info(message)

    # Add rate limit headers if present
    if hasattr(request.state, 'rate_limit_remaining'):
        response.headers['X-RateLimit-Remaining'] = str(request.state.rate_limit_remaining)
        response.headers['X-RateLimit-Reset'] = str(request.state.rate_limit_reset)

    return response


# Exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Internal server error",
            "message": str(exc) if settings.debug else "An error occurred processing your request",
            "timestamp": datetime.utcnow().isoformat(),
        }
    )


# Include routers
app.include_router(health_router)
app.include_router(dashboard_router)
app.include_router(admin_router)  # Admin dashboard (no auth required for demo)
app.include_router(tenant_dashboard_router)  # Multi-tenant dashboard
app.include_router(tenant_portal_router)  # Tenant self-service UI portal
app.include_router(tenant_auth_router, prefix=settings.api_prefix)  # Tenant portal authentication
app.include_router(notifications_router, prefix=settings.api_prefix)
app.include_router(templates_router, prefix=settings.api_prefix)
app.include_router(tenant_templates_router, prefix=settings.api_prefix)  # Tenant self-service templates
app.include_router(branding_router, prefix=settings.api_prefix)  # Tenant branding management
app.include_router(preferences_router, prefix=settings.api_prefix)
# Mount webhooks without api_prefix so external providers can hit them directly at /webhooks
app.include_router(webhooks_router)
app.include_router(tenant_management_router, prefix=settings.api_prefix)
app.include_router(usage_router, prefix=settings.api_prefix)
app.include_router(channels_router, prefix=settings.api_prefix)
app.include_router(tenant_settings_router, prefix=settings.api_prefix)
app.include_router(tenant_team_router, prefix=settings.api_prefix)
app.include_router(admin_auth_router, prefix=settings.api_prefix)
app.include_router(admin_auth_portal_router)
app.include_router(websocket_router)
app.include_router(compliance_router, prefix=settings.api_prefix)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
        access_log=False,
        log_config=None,
    )
