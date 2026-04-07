from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy import select
from typing import Optional
import logging

from src.models import Client
from src.core import get_db

logger = logging.getLogger(__name__)


class ClientAuthMiddleware(BaseHTTPMiddleware):
    """
    Middleware to authenticate clients via API key and inject client context.

    API Key format: sk_{env}_{client_id}_{random}
    Header: Authorization: Bearer sk_live_acme_xyz...
    """

    # Routes that don't require client authentication
    EXEMPT_PATHS = [
        "/docs",
        "/redoc",
        "/openapi.json",
        "/health",
        "/api/v1/health",
        "/admin",  # Admin dashboard
    ]

    async def dispatch(self, request: Request, call_next):
        """Process each request for client authentication."""

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

        # Authenticate client
        client = await self._authenticate_client(api_key)

        if not client:
            logger.warning(f"Failed authentication attempt with API key: {api_key[:20]}...")
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={
                    "error": "Invalid API key",
                    "message": "The provided API key is invalid or has been revoked"
                }
            )

        # Check client status
        if not client.is_active:
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={
                    "error": "Client suspended",
                    "message": "This client is inactive. Please candidate support."
                }
            )

        # Inject client into request state
        request.state.client_id = client.id
        request.state.client = client

        logger.debug(f"Authenticated client: {client.id} ({client.name})")

        # Proceed with request
        response = await call_next(request)

        # Add client ID to response headers for debugging
        response.headers["X-Client-ID"] = client.id

        return response

    async def _authenticate_client(self, api_key: str) -> Optional[Client]:
        """
        Authenticate a client by API key.

        Args:
            api_key: The API key from the Authorization header

        Returns:
            Client object if authenticated, None otherwise
        """
        logger.warning("API-key client auth is not supported by the live Supabase schema")
        return None


def get_client_id(request: Request) -> str:
    """
    Dependency to extract client_id from request state.

    Usage in route:
        @app.get("/notifications")
        async def get_notifications(client_id: str = Depends(get_client_id)):
            ...
    """
    # Development fallback: use X-Client-ID header
    client_id = request.headers.get("X-Client-ID") or request.headers.get("x-client-id")
    if client_id:
        try:
            int(client_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="X-Client-ID must be an integer"
            ) from exc
        logger.debug(f"Using X-Client-ID header: {client_id}")
        return client_id

    # Check request state (set by middleware)
    if hasattr(request.state, "client_id"):
        return request.state.client_id

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing API key"
    )


def get_client(request: Request) -> Client:
    """
    Dependency to extract full client object from request state.

    Usage in route:
        @app.get("/notifications")
        async def get_notifications(client: Client = Depends(get_client)):
            ...
    """
    if not hasattr(request.state, "client"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Client authentication required"
        )
    return request.state.client
