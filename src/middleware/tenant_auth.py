from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
import logging

from src.models import Tenant
from src.core import get_db

logger = logging.getLogger(__name__)


class TenantAuthMiddleware(BaseHTTPMiddleware):
    """
    Middleware to authenticate tenants via API key and inject tenant context.

    API Key format: sk_{env}_{tenant_id}_{random}
    Header: Authorization: Bearer sk_live_acme_xyz...
    """

    # Routes that don't require tenant authentication
    EXEMPT_PATHS = [
        "/docs",
        "/redoc",
        "/openapi.json",
        "/health",
        "/api/v1/health",
        "/admin",  # Admin dashboard
        "/webhooks",  # Mailgun/Twilio provider callbacks
    ]

    async def dispatch(self, request: Request, call_next):
        """Process each request for tenant authentication."""

        # Skip authentication for exempt paths
        if any(request.url.path.startswith(path) for path in self.EXEMPT_PATHS):
            return await call_next(request)

        # Extract API key from Authorization header
        auth_header = request.headers.get("Authorization", "")

        if not auth_header:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={
                    "error": "Authentication required",
                    "message": "Missing Authorization header. Use: Authorization: Bearer sk_live_..."
                }
            )

        # Parse Bearer token
        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={
                    "error": "Invalid authorization format",
                    "message": "Use: Authorization: Bearer sk_live_..."
                }
            )

        api_key = parts[1]

        # Validate API key format
        if not api_key.startswith("sk_"):
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={
                    "error": "Invalid API key format",
                    "message": "API key must start with 'sk_'"
                }
            )

        # Authenticate tenant
        tenant = await self._authenticate_tenant(api_key)

        if not tenant:
            logger.warning(f"Failed authentication attempt with API key: {api_key[:20]}...")
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={
                    "error": "Invalid API key",
                    "message": "The provided API key is invalid or has been revoked"
                }
            )

        # Check tenant status
        if tenant.status != "active":
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={
                    "error": "Tenant suspended",
                    "message": f"Your account is {tenant.status}. Please contact support."
                }
            )

        # Inject tenant into request state
        request.state.tenant_id = tenant.id
        request.state.tenant = tenant

        logger.debug(f"Authenticated tenant: {tenant.id} ({tenant.name})")

        # Proceed with request
        response = await call_next(request)

        # Add tenant ID to response headers for debugging
        response.headers["X-Tenant-ID"] = tenant.id

        return response

    async def _authenticate_tenant(self, api_key: str) -> Optional[Tenant]:
        """
        Authenticate a tenant by API key.

        Args:
            api_key: The API key from the Authorization header

        Returns:
            Tenant object if authenticated, None otherwise
        """
        # Hash the API key
        api_key_hash = Tenant.hash_api_key(api_key)

        # Query database for tenant
        try:
            async for session in get_db():
                result = await session.execute(
                    select(Tenant).where(Tenant.api_key_hash == api_key_hash)
                )
                tenant = result.scalar_one_or_none()
                return tenant
        except Exception as e:
            logger.error(f"Error authenticating tenant: {e}")
            return None


def get_tenant_id(request: Request) -> str:
    """
    Dependency to extract tenant_id from request state.

    Usage in route:
        @app.get("/notifications")
        async def get_notifications(tenant_id: str = Depends(get_tenant_id)):
            ...
    """
    # Check request state (set by middleware)
    if hasattr(request.state, "tenant_id"):
        return request.state.tenant_id

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Tenant authentication required"
    )


def get_tenant(request: Request) -> Tenant:
    """
    Dependency to extract full tenant object from request state.

    Usage in route:
        @app.get("/notifications")
        async def get_notifications(tenant: Tenant = Depends(get_tenant)):
            ...
    """
    if not hasattr(request.state, "tenant"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tenant authentication required"
        )
    return request.state.tenant
