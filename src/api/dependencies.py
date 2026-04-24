from fastapi import Depends, HTTPException, status, Header, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from redis.asyncio import Redis
from src.core import get_db, get_redis_client, verify_token
from src.config import settings
from src.models import Tenant
import hashlib
import time

security = HTTPBearer()


async def verify_api_key(x_api_key: Optional[str] = Header(None)) -> Optional[str]:
    """Verify API key from header."""
    # In debug mode, allow requests without API key
    if settings.debug and not x_api_key:
        return None

    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key"
        )

    # In production, verify against database
    # For now, check if key is provided
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key"
        )

    return x_api_key


async def get_authenticated_tenant(
    x_api_key: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db)
) -> Tenant:
    """
    Get authenticated tenant from API key, JWT token, or tenant ID (dev mode).

    Supports two authentication methods:
    1. API Key (X-API-Key header) - for programmatic access
    2. JWT Token (Authorization: Bearer) - for web portal access

    Validates credentials and returns the associated tenant object.
    Raises 401 if authentication fails or tenant is not active.
    """
    # Try JWT authentication first (Authorization header)
    if authorization and authorization.startswith("Bearer "):
        token = authorization.replace("Bearer ", "")
        payload = verify_token(token)

        if payload is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token"
            )

        tenant_id = payload.get("tenant_id")
        if not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload"
            )

        # Look up tenant by ID from JWT
        query = select(Tenant).where(
            Tenant.id == tenant_id,
            Tenant.status == "active",
            Tenant.deleted_at.is_(None)
        )
        result = await db.execute(query)
        tenant = result.scalar_one_or_none()

        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Tenant not found or not active"
            )

        return tenant

    # Try API key authentication (X-API-Key header)
    if x_api_key:
        # Hash the provided API key
        api_key_hash = Tenant.hash_api_key(x_api_key)

        # Look up tenant by hashed API key
        query = select(Tenant).where(
            Tenant.api_key_hash == api_key_hash,
            Tenant.status == "active",
            Tenant.deleted_at.is_(None)
        )
        result = await db.execute(query)
        tenant = result.scalar_one_or_none()

        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key or tenant not active"
            )

        return tenant

    # No authentication provided
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing authentication. Provide X-API-Key or Authorization Bearer token"
    )


async def require_admin_access(
    request: Request,
    x_admin_key: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None)
) -> bool:
    """
    Require admin key for admin-only endpoints.

    Accepts either:
    - X-Admin-Key: <secret>
    - Authorization: Bearer <secret>
    """
    # Legacy header support (x-admin-key / bearer secret)
    if x_admin_key and x_admin_key == settings.secret_key:
        return True

    bearer_token = None
    if authorization and authorization.startswith("Bearer "):
        bearer_token = authorization.replace("Bearer ", "").strip()

    if bearer_token:
        # Backward-compatible admin secret as bearer token
        if bearer_token == settings.secret_key:
            return True

        payload = verify_token(bearer_token)
        if (
            payload
            and payload.get("type") == "admin_access"
            and payload.get("role") in {"admin", "super_admin"}
        ):
            return True

    # Cookie-based admin portal session
    cookie_token = request.cookies.get("admin_access_token")
    if cookie_token:
        payload = verify_token(cookie_token)
        if (
            payload
            and payload.get("type") == "admin_access"
            and payload.get("role") in {"admin", "super_admin"}
        ):
            return True

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Admin authentication required"
    )


async def verify_jwt_token(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> dict:
    """Verify JWT token from Authorization header."""
    token = credentials.credentials
    payload = verify_token(token)

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )

    return payload


async def get_current_user(
    api_key: Optional[str] = Depends(verify_api_key)
) -> Optional[str]:
    """Get current authenticated user."""
    # In production, fetch user info from API key
    return api_key


class RateLimiter:
    """Rate limiter using Redis."""

    def __init__(self, requests: int, window: int):
        """
        Initialize rate limiter.

        Args:
            requests: Number of requests allowed
            window: Time window in seconds
        """
        self.requests = requests
        self.window = window

    async def __call__(
        self,
        request: Request,
        redis: Redis = Depends(get_redis_client),
        api_key: Optional[str] = Depends(verify_api_key)
    ):
        """Check rate limit."""
        # Skip rate limiting in debug mode when no API key is provided
        if settings.debug and not api_key:
            return True

        # Create unique key for this API key
        key = f"rate_limit:{api_key}:{int(time.time() / self.window)}"

        # Get current count
        count = await redis.get(key)

        if count is None:
            # First request in this window
            await redis.setex(key, self.window, 1)
            remaining = self.requests - 1
        else:
            count = int(count)
            if count >= self.requests:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Rate limit exceeded"
                )
            await redis.incr(key)
            remaining = self.requests - count - 1

        # Add rate limit headers to response
        request.state.rate_limit_remaining = remaining
        request.state.rate_limit_reset = int(time.time()) + self.window

        return True


# Rate limiter instances
user_rate_limiter = RateLimiter(
    requests=settings.rate_limit_per_user_hour,
    window=3600  # 1 hour
)

app_rate_limiter = RateLimiter(
    requests=settings.rate_limit_per_app_minute,
    window=60  # 1 minute
)
