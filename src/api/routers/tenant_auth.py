"""
Tenant authentication endpoints for web portal.

Provides username/password login for tenant portal access.
Separate from API key authentication used for programmatic access.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from jose import JWTError, jwt
from pydantic import BaseModel, EmailStr, Field
import re

from src.core import get_db
from src.models import Tenant, UserPreference
from src.api.schemas import TenantLoginRequest, TenantLoginResponse
from src.core.security import create_access_token
from src.config import settings

router = APIRouter(prefix="/tenant/auth", tags=["tenant-auth"])


class TenantSignupRequest(BaseModel):
    tenant_name: str = Field(..., min_length=2, max_length=255)
    admin_email: EmailStr
    admin_name: Optional[str] = Field(default=None, max_length=255)
    username: Optional[str] = Field(default=None, min_length=3, max_length=100)
    password: str = Field(..., min_length=8, max_length=128)
    tenant_id: Optional[str] = Field(default=None, max_length=50)
    preference_user_id: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=50,
        description="Optional initial user/customer id for preference seed"
    )
    preferred_channels: Optional[Dict[str, List[str]]] = Field(
        default=None,
        description="Optional mapping like {'order_update':['email'],'default':['email','whatsapp']}"
    )
    quiet_hours: Optional[Dict[str, str]] = Field(default=None, description="Optional, e.g. {'start':'22:00','end':'08:00'}")
    language: Optional[str] = Field(default="en", max_length=10)
    timezone: Optional[str] = Field(default="UTC", max_length=50)


def _to_tenant_id(raw_name: str) -> str:
    """Create a safe tenant_id from provided name."""
    base = raw_name.strip().lower()
    base = re.sub(r"[^a-z0-9]+", "_", base)
    base = re.sub(r"_+", "_", base).strip("_")
    if not base:
        base = "tenant"
    return f"tenant_{base[:40]}"


# Dependency for JWT-based authentication (for portal)
async def get_authenticated_tenant_from_jwt(
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db)
) -> Tenant:
    """
    Get authenticated tenant from JWT token.

    Used for tenant portal authentication (username/password flow).
    Different from API key authentication used for programmatic access.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = authorization.replace("Bearer ", "")

    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm]
        )
        tenant_id: str = payload.get("tenant_id")

        if not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
                headers={"WWW-Authenticate": "Bearer"},
            )

    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Get tenant from database
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
            detail="Tenant not found or not active",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return tenant


@router.post(
    "/login",
    response_model=TenantLoginResponse,
    summary="Tenant portal login",
    description="Login to tenant portal with username and password"
)
async def tenant_login(
    credentials: TenantLoginRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Authenticate tenant user with username and password.

    Returns a JWT token for accessing the tenant portal.
    This token is different from the API key used for programmatic access.

    - **username**: Tenant username (e.g., 'acme.corp')
    - **password**: Tenant password

    Returns JWT token valid for 8 hours.
    """
    # Find tenant by username
    query = select(Tenant).where(
        Tenant.username == credentials.username.lower(),
        Tenant.status == "active",
        Tenant.deleted_at.is_(None)
    )
    result = await db.execute(query)
    tenant = result.scalar_one_or_none()

    # Check if tenant exists
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Verify password
    if not tenant.password_hash:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Password authentication not configured for this tenant",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not Tenant.verify_password(credentials.password, tenant.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Create JWT token
    token_expiration = 8 * 60 * 60  # 8 hours in seconds
    access_token = create_access_token(
        data={
            "sub": tenant.id,
            "tenant_id": tenant.id,
            "tenant_name": tenant.name,
            "type": "portal_access"
        },
        expires_delta=timedelta(seconds=token_expiration)
    )

    return TenantLoginResponse(
        access_token=access_token,
        token_type="bearer",
        tenant_id=tenant.id,
        tenant_name=tenant.name,
        expires_in=token_expiration
    )


@router.post(
    "/signup",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
    summary="Tenant signup",
    description="Create a new tenant account with portal credentials and API key."
)
async def tenant_signup(
    payload: TenantSignupRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Public tenant signup flow for portal onboarding.

    Creates:
    - Tenant record
    - Username/password credentials for portal login
    - API key for programmatic access
    - Immediate JWT access token
    - Optional initial user preference seed (if provided)
    """
    if not settings.allow_public_tenant_signup:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Public signup is currently disabled"
        )

    tenant_id = (payload.tenant_id or _to_tenant_id(payload.tenant_name)).lower()
    username = (payload.username or Tenant.generate_username(tenant_id)).lower()

    # Validate tenant_id characters
    if not re.match(r"^[a-z0-9_]{3,50}$", tenant_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid tenant_id. Use lowercase letters, numbers, and underscores only."
        )

    # Validate username characters
    if not re.match(r"^[a-z0-9._-]{3,100}$", username):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid username. Use lowercase letters, numbers, dot, underscore, or hyphen."
        )

    # Enforce strong-ish password policy
    if (
        not re.search(r"[A-Z]", payload.password)
        or not re.search(r"[a-z]", payload.password)
        or not re.search(r"[0-9]", payload.password)
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must contain at least one uppercase letter, one lowercase letter, and one number."
        )

    # Validate optional preference seed payload
    valid_channels = {"email", "sms", "whatsapp", "slack", "push", "voice", "inapp"}
    has_preference_user = bool(payload.preference_user_id)
    has_preferred_channels = bool(payload.preferred_channels)

    if has_preference_user != has_preferred_channels:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="To seed initial preferences, provide both preference_user_id and preferred_channels. "
                   "Otherwise omit both."
        )

    if has_preferred_channels:
        for notif_type, channels in payload.preferred_channels.items():
            if not isinstance(channels, list) or len(channels) == 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"preferred_channels['{notif_type}'] must be a non-empty list"
                )
            invalid = [ch for ch in channels if ch not in valid_channels]
            if invalid:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid channels for '{notif_type}': {invalid}"
                )

    # Uniqueness checks
    existing_tenant = await db.get(Tenant, tenant_id)
    if existing_tenant:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Tenant ID '{tenant_id}' is already in use"
        )

    username_query = select(Tenant).where(Tenant.username == username)
    username_result = await db.execute(username_query)
    if username_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Username '{username}' is already in use"
        )

    # Generate API key
    api_key, api_key_hash, api_key_prefix = Tenant.generate_api_key(tenant_id, env="live")

    # Create tenant
    tenant = Tenant(
        id=tenant_id,
        name=payload.tenant_name,
        status="active",
        username=username,
        password_hash=Tenant.hash_password(payload.password),
        api_key_hash=api_key_hash,
        api_key_prefix=api_key_prefix,
        admin_email=str(payload.admin_email),
        admin_name=payload.admin_name or payload.tenant_name,
        config={"tier": "free"},
        tenant_metadata={"created_via": "portal_signup", "created_at": datetime.utcnow().isoformat()}
    )
    db.add(tenant)

    # Optional initial user/channel preference seed
    if has_preference_user and has_preferred_channels:
        initial_pref = UserPreference(
            tenant_id=tenant_id,
            user_id=payload.preference_user_id,
            preferred_channels=payload.preferred_channels,
            quiet_hours=payload.quiet_hours or {"start": "22:00", "end": "08:00"},
            language=payload.language or "en",
            timezone=payload.timezone or "UTC",
        )
        db.add(initial_pref)

    await db.commit()

    # Auto-login token
    token_expiration = 8 * 60 * 60
    access_token = create_access_token(
        data={
            "sub": tenant.id,
            "tenant_id": tenant.id,
            "tenant_name": tenant.name,
            "type": "portal_access"
        },
        expires_delta=timedelta(seconds=token_expiration)
    )

    return {
        "message": "Tenant account created successfully",
        "tenant_id": tenant.id,
        "tenant_name": tenant.name,
        "username": tenant.username,
        "api_key": api_key,
        "api_key_prefix": api_key_prefix,
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": token_expiration,
        "initial_preference_user_id": payload.preference_user_id if has_preference_user else None
    }


@router.post(
    "/logout",
    summary="Tenant portal logout",
    description="Logout from tenant portal (client-side only)"
)
async def tenant_logout():
    """
    Logout endpoint (for consistency).

    JWT tokens are stateless, so logout is handled client-side
    by removing the token from localStorage.
    """
    return {
        "message": "Logged out successfully",
        "action": "Remove token from client storage"
    }


@router.post(
    "/refresh",
    response_model=TenantLoginResponse,
    summary="Refresh access token",
    description="Get a new access token before expiration"
)
async def refresh_token(
    current_tenant: Tenant = Depends(get_authenticated_tenant_from_jwt),
    db: AsyncSession = Depends(get_db)
):
    """
    Refresh the access token.

    Use this endpoint before token expiration to get a new token
    without requiring username/password again.
    """
    # Check tenant is still active
    if current_tenant.status != "active" or current_tenant.deleted_at:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tenant account is not active"
        )

    # Generate new token
    token_expiration = 8 * 60 * 60  # 8 hours
    access_token = create_access_token(
        data={
            "sub": current_tenant.id,
            "tenant_id": current_tenant.id,
            "tenant_name": current_tenant.name,
            "type": "portal_access"
        },
        expires_delta=timedelta(seconds=token_expiration)
    )

    return TenantLoginResponse(
        access_token=access_token,
        token_type="bearer",
        tenant_id=current_tenant.id,
        tenant_name=current_tenant.name,
        expires_in=token_expiration
    )
