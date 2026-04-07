from .notifications import router as notifications_router
from .templates import router as templates_router
from .preferences import router as preferences_router
from .webhooks import router as webhooks_router
from .health import router as health_router
from .dashboard import router as dashboard_router
from .admin import router as admin_router
from .tenant_management import router as tenant_management_router
from .usage import router as usage_router
from .tenant_dashboard import router as tenant_dashboard_router
from .tenant_templates import router as tenant_templates_router
from .tenant_portal import router as tenant_portal_router
from .tenant_auth import router as tenant_auth_router
from .tracking import router as tracking_router

__all__ = [
    "notifications_router",
    "templates_router",
    "preferences_router",
    "webhooks_router",
    "health_router",
    "dashboard_router",
    "admin_router",
    "tenant_management_router",
    "usage_router",
    "tenant_dashboard_router",
    "tenant_templates_router",
    "tenant_portal_router",
    "tenant_auth_router",
    "tracking_router",
]
