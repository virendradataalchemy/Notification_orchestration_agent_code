"""Tenant portal web UI routes - serves HTML pages only."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

router = APIRouter(prefix="/portal", tags=["tenant-portal-ui"])
TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@router.get("/{tenant_id}/dashboard", response_class=HTMLResponse)
async def tenant_dashboard_page(request: Request, tenant_id: str):
    return templates.TemplateResponse(request, "tenant_portal/dashboard.html", {"tenant_id": tenant_id})


@router.get("/{tenant_id}/templates", response_class=HTMLResponse)
async def templates_list_page(request: Request, tenant_id: str):
    return templates.TemplateResponse(request, "tenant_portal/templates.html", {"tenant_id": tenant_id})


@router.get("/{tenant_id}/templates/create", response_class=HTMLResponse)
async def template_create_page(request: Request, tenant_id: str):
    return templates.TemplateResponse(request, "tenant_portal/template_create.html", {"tenant_id": tenant_id})


@router.get("/{tenant_id}/send-demo", response_class=HTMLResponse)
async def notification_demo_page(request: Request, tenant_id: str):
    return templates.TemplateResponse(request, "tenant_portal/send_demo.html", {"tenant_id": tenant_id})


@router.get("/{tenant_id}/templates/edit/{template_id}", response_class=HTMLResponse)
async def template_edit_page(request: Request, tenant_id: str, template_id: str):
    return templates.TemplateResponse(request, "tenant_portal/template_create.html",
                                      {"tenant_id": tenant_id, "template_id": template_id, "mode": "edit"})


@router.get("/{tenant_id}/templates/view/{template_id}", response_class=HTMLResponse)
async def template_view_page(request: Request, tenant_id: str, template_id: str):
    return templates.TemplateResponse(request, "tenant_portal/template_create.html",
                                      {"tenant_id": tenant_id, "template_id": template_id, "mode": "view"})


@router.get("/tenant/new", response_class=HTMLResponse)
async def create_tenant_page(request: Request):
    """Full page for creating a new tenant."""
    return templates.TemplateResponse(request, "tenant_create.html", {})
