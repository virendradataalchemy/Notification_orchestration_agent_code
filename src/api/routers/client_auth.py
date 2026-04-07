"""Client portal authentication - Supabase REST based."""

from fastapi import APIRouter, HTTPException, status, Header
from typing import Optional
from datetime import timedelta
from jose import JWTError, jwt

from src.api.schemas import ClientLoginRequest, ClientLoginResponse
from src.core.security import create_access_token
from src.core.supabase import supabase_client
from src.config import settings

router = APIRouter(prefix="/client/auth", tags=["client-auth"])


@router.post("/login", response_model=ClientLoginResponse)
async def client_login(credentials: ClientLoginRequest):
    """
    Dev-mode login: accepts client_id as username, any password.
    In production, replace with real credential verification.
    """
    # Try to find client by id (username = client_id for dev) or name
    try:
        client_pk = int(credentials.username)
        filters = {"id": f"eq.{client_pk}", "is_active": "eq.true"}
    except ValueError:
        filters = {"name": f"ilike.*{credentials.username}*", "is_active": "eq.true"}

    rows = await supabase_client.select(
        "clients", "id,name,is_active",
        limit=1, filters=filters,
    )
    if not rows:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    client = rows[0]
    token_expiration = 8 * 60 * 60  # 8 hours
    access_token = create_access_token(
        data={"sub": str(client["id"]), "client_id": client["id"], "client_name": client["name"]},
        expires_delta=timedelta(seconds=token_expiration),
    )
    return ClientLoginResponse(
        access_token=access_token,
        token_type="bearer",
        client_id=client["id"],
        client_name=client["name"],
        expires_in=token_expiration,
    )


@router.post("/logout")
async def client_logout():
    return {"message": "Logged out successfully"}


@router.post("/refresh", response_model=ClientLoginResponse)
async def refresh_token(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = authorization.replace("Bearer ", "")
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        client_id = payload.get("client_id")
        if not client_id:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Could not validate credentials")

    rows = await supabase_client.select(
        "clients", "id,name,is_active",
        limit=1, filters={"id": f"eq.{client_id}", "is_active": "eq.true"},
    )
    if not rows:
        raise HTTPException(status_code=401, detail="Client not found or not active")

    client = rows[0]
    token_expiration = 8 * 60 * 60
    access_token = create_access_token(
        data={"sub": str(client["id"]), "client_id": client["id"], "client_name": client["name"]},
        expires_delta=timedelta(seconds=token_expiration),
    )
    return ClientLoginResponse(
        access_token=access_token,
        token_type="bearer",
        client_id=client["id"],
        client_name=client["name"],
        expires_in=token_expiration,
    )
