"""
Admin authentication routes.

Provides:
- Admin login page
- Admin login/logout/refresh APIs
"""

from datetime import timedelta
from pathlib import Path
from fastapi import APIRouter, HTTPException, status, Response, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field

from src.config import settings
from src.core.security import create_access_token
from src.api.dependencies import require_admin_access


portal_router = APIRouter(tags=["admin-auth"])
api_router = APIRouter(prefix="/admin/auth", tags=["admin-auth"])


class AdminLoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=1, max_length=255)


class AdminLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str = "super_admin"
    expires_in: int


def _issue_admin_token() -> tuple[str, int]:
    expires_seconds = int(settings.admin_session_hours * 60 * 60)
    token = create_access_token(
        data={
            "sub": "admin",
            "type": "admin_access",
            "role": "super_admin",
            "username": settings.admin_username,
        },
        expires_delta=timedelta(seconds=expires_seconds),
    )
    return token, expires_seconds


@portal_router.get("/admin/login", response_class=HTMLResponse)
async def admin_login_page():
    template_path = Path(__file__).parent.parent.parent / "templates" / "admin_login.html"
    with open(template_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@portal_router.get("/admin/logout")
async def admin_logout_page():
    response = RedirectResponse(url="/admin/login")
    response.delete_cookie("admin_access_token", path="/", samesite="lax")
    return response


@api_router.post("/login", response_model=AdminLoginResponse)
async def admin_login(payload: AdminLoginRequest, response: Response):
    expected_username = settings.admin_username
    expected_password = settings.admin_password or settings.secret_key

    if payload.username != expected_username or payload.password != expected_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin credentials"
        )

    token, expires_seconds = _issue_admin_token()
    response.set_cookie(
        key="admin_access_token",
        value=token,
        max_age=expires_seconds,
        httponly=True,
        secure=False,  # Set True behind HTTPS reverse proxy in production
        samesite="lax",
        path="/",
    )

    return AdminLoginResponse(
        access_token=token,
        token_type="bearer",
        role="super_admin",
        expires_in=expires_seconds,
    )


@api_router.post("/logout")
async def admin_logout(response: Response):
    response.delete_cookie("admin_access_token", path="/", samesite="lax")
    return {"message": "Logged out successfully"}


@api_router.post("/refresh", response_model=AdminLoginResponse)
async def admin_refresh(
    response: Response,
    _: bool = Depends(require_admin_access)
):
    token, expires_seconds = _issue_admin_token()
    response.set_cookie(
        key="admin_access_token",
        value=token,
        max_age=expires_seconds,
        httponly=True,
        secure=False,
        samesite="lax",
        path="/",
    )
    return AdminLoginResponse(
        access_token=token,
        token_type="bearer",
        role="super_admin",
        expires_in=expires_seconds,
    )
