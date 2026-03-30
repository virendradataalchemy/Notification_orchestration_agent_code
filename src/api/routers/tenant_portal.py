"""
Tenant portal web UI routes.

Serves HTML pages for tenant self-service template management.
Tenant-specific URLs (no authentication required for dev).
"""

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pathlib import Path

from src.core import get_db
from src.models import Tenant

router = APIRouter(prefix="/portal", tags=["tenant-portal-ui"])

# Templates directory
TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates" / "tenant_portal"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


async def get_tenant_by_id(tenant_id: str, db: AsyncSession):
    """Get tenant by ID."""
    query = select(Tenant).where(Tenant.id == tenant_id)
    result = await db.execute(query)
    tenant = result.scalar_one_or_none()
    return tenant


@router.get("/{tenant_id}/dashboard", response_class=HTMLResponse)
async def tenant_dashboard_page(request: Request, tenant_id: str):
    """Main tenant dashboard."""
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "tenant_id": tenant_id
    })


@router.get("/{tenant_id}/templates", response_class=HTMLResponse)
async def templates_list_page(request: Request, tenant_id: str):
    """List all templates (tenant + global)."""
    return templates.TemplateResponse("templates.html", {
        "request": request,
        "tenant_id": tenant_id
    })


@router.get("/{tenant_id}/templates/create", response_class=HTMLResponse)
async def template_create_page(request: Request, tenant_id: str):
    """Create new template form."""
    return templates.TemplateResponse("template_create.html", {
        "request": request,
        "tenant_id": tenant_id
    })


@router.get("/{tenant_id}/templates/edit/{template_id}", response_class=HTMLResponse)
async def template_edit_page(request: Request, tenant_id: str, template_id: str):
    """Edit existing template."""
    return templates.TemplateResponse("template_create.html", {
        "request": request,
        "tenant_id": tenant_id,
        "template_id": template_id,
        "mode": "edit"
    })


@router.get("/{tenant_id}/templates/view/{template_id}", response_class=HTMLResponse)
async def template_view_page(request: Request, tenant_id: str, template_id: str):
    """View template details (read-only)."""
    return templates.TemplateResponse("template_create.html", {
        "request": request,
        "tenant_id": tenant_id,
        "template_id": template_id,
        "mode": "view"
    })
