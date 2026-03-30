"""
Tenant authentication endpoints for web portal.

Provides username/password login for tenant portal access.
Separate from API key authentication used for programmatic access.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt

from src.core import get_db
from src.models import Tenant
from src.api.schemas import TenantLoginRequest, TenantLoginResponse
from src.core.security import create_access_token
from src.config import settings

router = APIRouter(prefix="/tenant/auth", tags=["tenant-auth"])


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
