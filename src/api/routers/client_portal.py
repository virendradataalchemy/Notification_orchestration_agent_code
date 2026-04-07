"""Client portal web UI routes - serves HTML pages only."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

router = APIRouter(prefix="/portal", tags=["client-portal-ui"])
TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@router.get("/{client_id}/dashboard", response_class=HTMLResponse)
async def client_dashboard_page(request: Request, client_id: str):
    return templates.TemplateResponse(request, "client_portal/dashboard.html", {"client_id": client_id})


@router.get("/{client_id}/templates", response_class=HTMLResponse)
async def templates_list_page(request: Request, client_id: str):
    return templates.TemplateResponse(request, "client_portal/templates.html", {"client_id": client_id})


@router.get("/{client_id}/templates/create", response_class=HTMLResponse)
async def template_create_page(request: Request, client_id: str):
    return templates.TemplateResponse(request, "client_portal/template_create.html", {"client_id": client_id})


@router.get("/{client_id}/send-demo", response_class=HTMLResponse)
async def notification_demo_page(request: Request, client_id: str):
    return templates.TemplateResponse(request, "client_portal/send_demo.html", {"client_id": client_id})


@router.get("/{client_id}/templates/edit/{template_id}", response_class=HTMLResponse)
async def template_edit_page(request: Request, client_id: str, template_id: str):
    return templates.TemplateResponse(request, "client_portal/template_create.html",
                                      {"client_id": client_id, "template_id": template_id, "mode": "edit"})


@router.get("/{client_id}/templates/view/{template_id}", response_class=HTMLResponse)
async def template_view_page(request: Request, client_id: str, template_id: str):
    return templates.TemplateResponse(request, "client_portal/template_create.html",
                                      {"client_id": client_id, "template_id": template_id, "mode": "view"})


@router.get("/client/new", response_class=HTMLResponse)
async def create_client_page(request: Request):
    """Full page for creating a new client."""
    return templates.TemplateResponse(request, "client_create.html", {})
