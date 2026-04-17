from .notifications import router as notifications_router
from .templates import router as templates_router
from .preferences import router as preferences_router
from .webhooks import router as webhooks_router
from .health import router as health_router
from .dashboard import router as dashboard_router
from .admin import router as admin_router
from .client_management import router as client_management_router
from .usage import router as usage_router
from .client_dashboard import router as client_dashboard_router
from .client_templates import router as client_templates_router
from .client_portal import router as client_portal_router
from .client_auth import router as client_auth_router
from .tracking import router as tracking_router
from .integration import router as integration_router

__all__ = [
    "notifications_router",
    "templates_router",
    "preferences_router",
    "webhooks_router",
    "health_router",
    "dashboard_router",
    "admin_router",
    "client_management_router",
    "usage_router",
    "client_dashboard_router",
    "client_templates_router",
    "client_portal_router",
    "client_auth_router",
    "tracking_router",
    "integration_router",
]
