from fastapi import Depends, HTTPException, status, Header, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from redis.asyncio import Redis
from src.core import get_db, get_db_optional, get_redis_client, verify_token, supabase_client
from src.core.supabase import ADMINS_TABLE, CLIENTS_TABLE
from src.config import settings
from src.models import Client
import time

security = HTTPBearer()


def _client_from_row(row: dict) -> Client:
    return Client(
        id=row["id"],
        name=row["name"],
        default_language=row.get("default_language"),
        logo_url=row.get("logo_url"),
        brand_color=row.get("brand_color"),
        is_active=row.get("is_active", True),
        client_slug=row.get("client_slug"),
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
    )


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


async def get_authenticated_client(
    x_api_key: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
    x_client_id: Optional[str] = Header(None),
    db: AsyncSession | None = Depends(get_db_optional)
) -> Client:
    """
    Get authenticated client from API key, JWT token, or client ID (dev mode).

    Supports three authentication methods:
    1. API Key (X-API-Key header) - for programmatic access
    2. JWT Token (Authorization: Bearer) - for web portal access
    3. Client ID (X-Client-Id header) - for dev mode (no authentication)

    Validates credentials and returns the associated client object.
    Raises 401 if authentication fails or client is not active.
    """
    # Dev mode: Accept client ID directly (no authentication)
    if x_client_id and settings.debug:
        try:
            client_pk = int(x_client_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="X-Client-Id must be an integer",
            ) from exc
        client = None
        if db is not None:
            query = select(Client).where(
                Client.id == client_pk,
                Client.is_active == True
            )
            result = await db.execute(query)
            client = result.scalar_one_or_none()
        elif supabase_client.configured:
            rows = await supabase_client.select(
                CLIENTS_TABLE,
                "id,name,default_language,logo_url,brand_color,is_active,client_slug,created_at,updated_at",
                limit=1,
                filters={
                    "id": f"eq.{client_pk}",
                    "is_active": "eq.true",
                },
            )
            client = _client_from_row(rows[0]) if rows else None

        if not client:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Client '{x_client_id}' not found"
            )

        return client

    # Try JWT authentication first (Authorization header)
    if authorization and authorization.startswith("Bearer "):
        token = authorization.replace("Bearer ", "")
        payload = verify_token(token)

        if payload is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token"
            )

        client_id = payload.get("client_id")
        if not client_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload"
            )
        try:
            client_pk = int(client_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid client ID in token"
            ) from exc

        # Look up client by ID from JWT
        client = None
        if db is not None:
            query = select(Client).where(
                Client.id == client_pk,
                Client.is_active == True
            )
            result = await db.execute(query)
            client = result.scalar_one_or_none()
        elif supabase_client.configured:
            rows = await supabase_client.select(
                CLIENTS_TABLE,
                "id,name,default_language,logo_url,brand_color,is_active,client_slug,created_at,updated_at",
                limit=1,
                filters={
                    "id": f"eq.{client_pk}",
                    "is_active": "eq.true",
                },
            )
            client = _client_from_row(rows[0]) if rows else None

        if not client:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Client not found or not active"
            )

        return client

    # Try API key authentication (X-API-Key header)
    if x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key authentication is not available for the live Supabase client schema"
        )

    # No authentication provided
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing authentication. Provide X-Client-Id (dev), X-API-Key, or Authorization Bearer token"
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


async def get_authenticated_admin(
    authorization: Optional[str] = Header(None),
) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing admin authentication token",
        )

    access_token = authorization.replace("Bearer ", "", 1)

    try:
        auth_user = await supabase_client.get_auth_user(access_token)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired admin session",
        ) from exc

    user_id = auth_user.get("id")
    email = auth_user.get("email")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin session is missing a user id",
        )

    rows = await supabase_client.select(
        ADMINS_TABLE,
        "id,supabase_uid,email,name,is_active,created_at,updated_at",
        limit=1,
        filters={"supabase_uid": f"eq.{user_id}", "is_active": "eq.true"},
    )
    if not rows and email:
        rows = await supabase_client.select(
            ADMINS_TABLE,
            "id,supabase_uid,email,name,is_active,created_at,updated_at",
            limit=1,
            filters={"email": f"eq.{email}", "is_active": "eq.true"},
        )

    if not rows:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account is not authorized as an admin",
        )

    return rows[0]


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
