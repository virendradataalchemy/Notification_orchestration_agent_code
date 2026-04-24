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
from src.models import Tenant

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
    if not tenant_id:
        return None

    query = select(Tenant).where(
        Tenant.id == tenant_id,
        Tenant.status == "active",
        Tenant.deleted_at.is_(None)
    )
    result = await db.execute(query)
    return result.scalar_one_or_none()


@router.get("/", include_in_schema=False)
async def portal_root():
    """Redirect portal root to login page."""
    return RedirectResponse(url="/portal/login")


@router.get("/assets/{asset_name}", include_in_schema=False)
async def portal_assets(asset_name: str):
    """Serve shared tenant portal assets."""
    allowed_assets = {"portal_shared.css"}
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
        return RedirectResponse(url=f"/portal/{tenant.id}/dashboard")
    return templates.TemplateResponse("login.html", {
        "request": request
    })


@router.get("/signup", response_class=HTMLResponse)
async def tenant_signup_page(request: Request):
    """Tenant portal signup page."""
    return templates.TemplateResponse("signup.html", {
        "request": request
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
        return RedirectResponse(url="/portal/login")
    if tenant.id != tenant_id:
        return RedirectResponse(url=f"/portal/{tenant.id}/dashboard")

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
        return RedirectResponse(url="/portal/login")
    if tenant.id != tenant_id:
        return RedirectResponse(url=f"/portal/{tenant.id}/templates")

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
        return RedirectResponse(url="/portal/login")
    if tenant.id != tenant_id:
        return RedirectResponse(url=f"/portal/{tenant.id}/templates/create")

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
        return RedirectResponse(url="/portal/login")
    if tenant.id != tenant_id:
        return RedirectResponse(url=f"/portal/{tenant.id}/templates/edit/{template_id}")

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
        return RedirectResponse(url="/portal/login")
    if tenant.id != tenant_id:
        return RedirectResponse(url=f"/portal/{tenant.id}/templates/view/{template_id}")

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
        return RedirectResponse(url="/portal/login")
    if tenant.id != tenant_id:
        return RedirectResponse(url=f"/portal/{tenant.id}/profile")

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
        return RedirectResponse(url="/portal/login")
    if tenant.id != tenant_id:
        return RedirectResponse(url=f"/portal/{tenant.id}/developer")

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
        return RedirectResponse(url="/portal/login")
    if tenant.id != tenant_id:
        return RedirectResponse(url=f"/portal/{tenant.id}/channels")

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
        return RedirectResponse(url="/portal/login")
    if tenant.id != tenant_id:
        return RedirectResponse(url=f"/portal/{tenant.id}/analytics")

    return templates.TemplateResponse("analytics.html", {"request": request, "tenant_id": tenant_id})
