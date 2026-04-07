from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from contextlib import asynccontextmanager
import logging
from datetime import datetime

from src.config import settings
from src.core import init_db, init_redis, close_redis
from src.middleware import ClientAuthMiddleware
from src.services.usage_tracker import initialize_usage_tracker
from src.api.routers import (
    notifications_router,
    templates_router,
    preferences_router,
    webhooks_router,
    health_router,
    dashboard_router,
    admin_router,
    client_management_router,
    usage_router,
    client_dashboard_router,
    client_templates_router,
    client_portal_router,
    client_auth_router,
    tracking_router,
)
from src.api.routers.twilio_webhooks import router as twilio_webhooks_router
from src.api.routers.orchestration import router as orchestration_router
from src.api.routers.inapp import router as inapp_router
from src.api.routers.device_tokens import router as device_tokens_router

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


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
    description="Centralized multi-client platform for managing notifications across multiple channels",
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

# Client authentication middleware (disabled for development)
# app.add_middleware(ClientAuthMiddleware)


# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all HTTP requests."""
    start_time = datetime.utcnow()

    # Process request
    response = await call_next(request)

    # Calculate duration
    duration = (datetime.utcnow() - start_time).total_seconds()

    # Log request
    logger.info(
        f"{request.method} {request.url.path} - "
        f"Status: {response.status_code} - "
        f"Duration: {duration:.3f}s"
    )

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


@app.get("/", response_class=HTMLResponse)
async def landing_page():
    """Serve the authentication landing page."""
    import os
    landing_path = os.path.join(os.path.dirname(__file__), "templates", "landing.html")
    with open(landing_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


# Include routers
app.include_router(health_router)
app.include_router(dashboard_router)
app.include_router(admin_router)  # Admin dashboard (no auth required for demo)
app.include_router(client_dashboard_router)  # Multi-client dashboard
app.include_router(client_portal_router)  # Client self-service UI portal
app.include_router(client_auth_router, prefix=settings.api_prefix)  # Client portal authentication
app.include_router(orchestration_router)  # Intelligent orchestration agent
app.include_router(inapp_router, prefix=settings.api_prefix)  # In-app notifications
app.include_router(device_tokens_router, prefix=settings.api_prefix)  # Device tokens for push
app.include_router(notifications_router, prefix=settings.api_prefix)
app.include_router(templates_router, prefix=settings.api_prefix)
app.include_router(client_templates_router, prefix=settings.api_prefix)  # Client self-service templates
app.include_router(preferences_router, prefix=settings.api_prefix)
app.include_router(webhooks_router, prefix=settings.api_prefix)
app.include_router(twilio_webhooks_router)  # Twilio webhooks for call recording
app.include_router(client_management_router, prefix=settings.api_prefix)
app.include_router(usage_router, prefix=settings.api_prefix)
app.include_router(tracking_router, prefix=settings.api_prefix)  # Tracking, logs, and unsubscribe


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )
