"""
Tenant portal web UI routes.

Serves HTML pages for tenant self-service template management.
Tenant-specific URLs require valid tenant portal session cookie.
"""

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.core import get_db, verify_token
from src.models import Tenant, TenantUser

router = APIRouter(prefix="/portal", tags=["tenant-portal-ui"])

# Templates directory
TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates" / "tenant_portal"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


async def _get_portal_tenant_from_cookie(
    request: Request,
    db: AsyncSession
) -> Tenant | None:
    """Validate tenant portal JWT from cookie and return active tenant."""
    token = request.cookies.get("tenant_access_token")
    if not token:
        return None

    payload = verify_token(token)
    if not payload:
        return None

    tenant_id = payload.get("tenant_id")
    user_id = payload.get("user_id")
    if not tenant_id or not user_id:
        return None

    # Verify user
    user_query = select(TenantUser).where(
        TenantUser.id == user_id,
        TenantUser.tenant_id == tenant_id,
        TenantUser.is_active == True
    )
    user_result = await db.execute(user_query)
    user = user_result.scalar_one_or_none()
    if not user:
        return None

    query = select(Tenant).where(
        Tenant.id == tenant_id,
        Tenant.status == "active",
        Tenant.deleted_at.is_(None)
    )
    result = await db.execute(query)
    tenant = result.scalar_one_or_none()
    if tenant:
        tenant.current_user_role = user.role
        tenant.current_user_id = user.id
    return tenant


@router.get("/", include_in_schema=False)
async def portal_root():
    """Redirect portal root to login page."""
    return RedirectResponse(url="/portal/login", status_code=303)


@router.get("/assets/{asset_name}", include_in_schema=False)
async def portal_assets(asset_name: str):
    """Serve shared tenant portal assets."""
    allowed_assets = {"portal_shared.css", "portal_auth.js"}
    if asset_name not in allowed_assets:
        raise HTTPException(status_code=404, detail="Asset not found")

    asset_path = TEMPLATES_DIR / "assets" / asset_name
    if not asset_path.exists():
        raise HTTPException(status_code=404, detail="Asset not found")
    return FileResponse(str(asset_path))


@router.get("/login", response_class=HTMLResponse)
async def tenant_login_page(request: Request, db: AsyncSession = Depends(get_db)):
    """Tenant portal login page."""
    tenant = await _get_portal_tenant_from_cookie(request, db)
    if tenant:
        return RedirectResponse(url=f"/portal/{tenant.id}/dashboard", status_code=303)
    return templates.TemplateResponse("login.html", {
        "request": request
    })


@router.get("/signup", response_class=HTMLResponse)
async def tenant_signup_page(request: Request):
    """Tenant portal signup page."""
    return templates.TemplateResponse("signup.html", {
        "request": request
    })


@router.get("/accept-invite", response_class=HTMLResponse)
async def accept_invite_page(request: Request, token: str):
    """Page to set up account after receiving invitation."""
    return templates.TemplateResponse("accept_invite.html", {
        "request": request,
        "token": token
    })


@router.get("/how-to-use", response_class=HTMLResponse)
async def how_to_use_page(request: Request):
    """Product usage guide page."""
    return templates.TemplateResponse("how_to_use.html", {
        "request": request
    })


@router.get("/{tenant_id}/dashboard", response_class=HTMLResponse)
async def tenant_dashboard_page(
    request: Request,
    tenant_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Main tenant dashboard."""
    tenant = await _get_portal_tenant_from_cookie(request, db)
    if not tenant:
        return RedirectResponse(url="/portal/login?error=unauthorized", status_code=303)
    if tenant.id != tenant_id:
        return RedirectResponse(url=f"/portal/{tenant.id}/dashboard", status_code=303)

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "tenant_id": tenant_id
    })


@router.get("/{tenant_id}/templates", response_class=HTMLResponse)
async def templates_list_page(
    request: Request,
    tenant_id: str,
    db: AsyncSession = Depends(get_db)
):
    """List all templates (tenant + global)."""
    tenant = await _get_portal_tenant_from_cookie(request, db)
    if not tenant:
        return RedirectResponse(url="/portal/login?error=unauthorized", status_code=303)
    if tenant.id != tenant_id:
        return RedirectResponse(url=f"/portal/{tenant.id}/templates", status_code=303)

    return templates.TemplateResponse("templates.html", {
        "request": request,
        "tenant_id": tenant_id
    })


@router.get("/{tenant_id}/templates/create", response_class=HTMLResponse)
async def template_create_page(
    request: Request,
    tenant_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Create new template form."""
    tenant = await _get_portal_tenant_from_cookie(request, db)
    if not tenant:
        return RedirectResponse(url="/portal/login?error=unauthorized", status_code=303)
    if tenant.id != tenant_id:
        return RedirectResponse(url=f"/portal/{tenant.id}/templates/create", status_code=303)

    return templates.TemplateResponse("template_create.html", {
        "request": request,
        "tenant_id": tenant_id
    })


@router.get("/{tenant_id}/templates/edit/{template_id}", response_class=HTMLResponse)
async def template_edit_page(
    request: Request,
    tenant_id: str,
    template_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Edit existing template."""
    tenant = await _get_portal_tenant_from_cookie(request, db)
    if not tenant:
        return RedirectResponse(url="/portal/login?error=unauthorized", status_code=303)
    if tenant.id != tenant_id:
        return RedirectResponse(url=f"/portal/{tenant.id}/templates/edit/{template_id}", status_code=303)

    return templates.TemplateResponse("template_create.html", {
        "request": request,
        "tenant_id": tenant_id,
        "template_id": template_id,
        "mode": "edit"
    })


@router.get("/{tenant_id}/templates/view/{template_id}", response_class=HTMLResponse)
async def template_view_page(
    request: Request,
    tenant_id: str,
    template_id: str,
    db: AsyncSession = Depends(get_db)
):
    """View template details (read-only)."""
    tenant = await _get_portal_tenant_from_cookie(request, db)
    if not tenant:
        return RedirectResponse(url="/portal/login?error=unauthorized", status_code=303)
    if tenant.id != tenant_id:
        return RedirectResponse(url=f"/portal/{tenant.id}/templates/view/{template_id}", status_code=303)

    return templates.TemplateResponse("template_create.html", {
        "request": request,
        "tenant_id": tenant_id,
        "template_id": template_id,
        "mode": "view"
    })


@router.get("/{tenant_id}/profile", response_class=HTMLResponse)
async def profile_page(
    request: Request,
    tenant_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Tenant profile page."""
    tenant = await _get_portal_tenant_from_cookie(request, db)
    if not tenant:
        return RedirectResponse(url="/portal/login?error=unauthorized", status_code=303)
    if tenant.id != tenant_id:
        return RedirectResponse(url=f"/portal/{tenant.id}/profile", status_code=303)

    return templates.TemplateResponse("profile.html", {"request": request, "tenant_id": tenant_id})


@router.get("/{tenant_id}/developer", response_class=HTMLResponse)
async def developer_page(
    request: Request,
    tenant_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Tenant developer settings page."""
    tenant = await _get_portal_tenant_from_cookie(request, db)
    if not tenant:
        return RedirectResponse(url="/portal/login?error=unauthorized", status_code=303)
    if tenant.id != tenant_id:
        return RedirectResponse(url=f"/portal/{tenant.id}/developer", status_code=303)

    return templates.TemplateResponse("developer.html", {"request": request, "tenant_id": tenant_id})


@router.get("/{tenant_id}/channels", response_class=HTMLResponse)
async def channel_settings_page(
    request: Request,
    tenant_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Tenant channel settings page."""
    tenant = await _get_portal_tenant_from_cookie(request, db)
    if not tenant:
        return RedirectResponse(url="/portal/login?error=unauthorized", status_code=303)
    if tenant.id != tenant_id:
        return RedirectResponse(url=f"/portal/{tenant.id}/channels", status_code=303)

    return templates.TemplateResponse("channel_settings.html", {"request": request, "tenant_id": tenant_id})


@router.get("/{tenant_id}/analytics", response_class=HTMLResponse)
async def analytics_page(
    request: Request,
    tenant_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Tenant analytics dashboard page."""
    tenant = await _get_portal_tenant_from_cookie(request, db)
    if not tenant:
        return RedirectResponse(url="/portal/login?error=unauthorized", status_code=303)
    if tenant.id != tenant_id:
        return RedirectResponse(url=f"/portal/{tenant.id}/analytics", status_code=303)

    return templates.TemplateResponse("analytics.html", {"request": request, "tenant_id": tenant_id})


@router.get("/{tenant_id}/marketing", response_class=HTMLResponse)
async def marketing_dashboard_page(
    request: Request,
    tenant_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Marketing team dashboard."""
    tenant = await _get_portal_tenant_from_cookie(request, db)
    if not tenant:
        return RedirectResponse(url="/portal/login?error=unauthorized", status_code=303)
    if tenant.id != tenant_id:
        return RedirectResponse(url=f"/portal/{tenant.id}/marketing", status_code=303)

    return templates.TemplateResponse("marketing.html", {
        "request": request,
        "tenant_id": tenant_id,
        "tenant_name": tenant.name
    })


@router.get("/{tenant_id}/marketing-dashboard", response_class=HTMLResponse)
async def marketing_detailed_dashboard_page(
    request: Request,
    tenant_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Detailed activity dashboard for marketing."""
    tenant = await _get_portal_tenant_from_cookie(request, db)
    if not tenant:
        return RedirectResponse(url="/portal/login?error=unauthorized", status_code=303)
    if tenant.id != tenant_id:
        return RedirectResponse(url=f"/portal/{tenant.id}/marketing-dashboard", status_code=303)

    return templates.TemplateResponse("marketing_dashboard.html", {
        "request": request,
        "tenant_id": tenant_id,
        "tenant_name": tenant.name
    })


@router.get("/{tenant_id}/team", response_class=HTMLResponse)
async def team_management_page(
    request: Request,
    tenant_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Team management page (Admin only)."""
    tenant = await _get_portal_tenant_from_cookie(request, db)
    if not tenant:
        return RedirectResponse(url="/portal/login?error=unauthorized", status_code=303)
    if tenant.id != tenant_id:
        return RedirectResponse(url=f"/portal/{tenant.id}/team", status_code=303)
    
    # Check permissions
    if tenant.current_user_role not in ["root", "admin"]:
        # Redirect to dashboard if not admin
        return RedirectResponse(url=f"/portal/{tenant.id}/dashboard", status_code=303)

    return templates.TemplateResponse("team.html", {
        "request": request,
        "tenant_id": tenant_id,
        "tenant_name": tenant.name,
        "user_role": tenant.current_user_role
    })
