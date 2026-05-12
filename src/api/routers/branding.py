"""API endpoints for tenant branding management."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, Field
from typing import Optional
import uuid

from src.core.database import get_db
from src.models import TenantBranding, Tenant
from src.api.dependencies import get_current_tenant
from src.services.tenant_template_engine import TenantTemplateEngine

router = APIRouter(prefix="/branding", tags=["branding"])


class BrandingRequest(BaseModel):
    """Request model for creating/updating branding."""
    logo_url: Optional[str] = Field(None, description="Logo URL (public URL or base64 data URI)")
    company_name: Optional[str] = Field(None, max_length=200, description="Company name")
    theme_color: Optional[str] = Field("#1d4ed8", max_length=20, description="Theme color (hex code)")
    contact_email: Optional[str] = Field(None, max_length=200, description="Contact email")
    contact_phone: Optional[str] = Field(None, max_length=50, description="Contact phone")
    website: Optional[str] = Field(None, max_length=200, description="Website URL")
    footer_html: Optional[str] = Field(None, description="Custom footer HTML (Jinja2 template)")
    enabled: bool = Field(True, description="Enable/disable branding")
    apply_to_all_channels: bool = Field(False, description="Apply to all channels (future)")


class BrandingResponse(BaseModel):
    """Response model for branding."""
    id: str
    tenant_id: str
    logo_url: Optional[str]
    company_name: Optional[str]
    theme_color: Optional[str]
    contact_email: Optional[str]
    contact_phone: Optional[str]
    website: Optional[str]
    footer_html: Optional[str]
    enabled: bool
    apply_to_all_channels: bool
    created_at: str
    updated_at: str


class BrandingPreviewRequest(BaseModel):
    """Request model for previewing branding."""
    subject: Optional[str] = Field("Test Email Subject", description="Email subject")
    body: str = Field(..., description="Email body content (HTML or plain text)")
    template_variables: dict = Field(default_factory=dict, description="Variables for Jinja2 rendering")


class BrandingPreviewResponse(BaseModel):
    """Response model for branding preview."""
    subject: Optional[str]
    body: str
    body_with_branding: str


@router.post(
    "",
    response_model=BrandingResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create or update tenant branding"
)
async def create_or_update_branding(
    request: BrandingRequest,
    tenant_id: str = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    """
    Create or update tenant branding configuration.
    
    This branding will automatically apply to all emails sent by the tenant,
    whether using templates or raw content.
    """
    # Check if branding already exists
    result = await db.execute(
        select(TenantBranding).where(TenantBranding.tenant_id == tenant_id)
    )
    branding = result.scalar_one_or_none()
    
    if branding:
        # Update existing branding
        branding.logo_url = request.logo_url
        branding.company_name = request.company_name
        branding.theme_color = request.theme_color or "#1d4ed8"
        branding.contact_email = request.contact_email
        branding.contact_phone = request.contact_phone
        branding.website = request.website
        branding.footer_html = request.footer_html
        branding.enabled = request.enabled
        branding.apply_to_all_channels = request.apply_to_all_channels
    else:
        # Create new branding
        branding = TenantBranding(
            id=f"branding_{uuid.uuid4().hex[:12]}",
            tenant_id=tenant_id,
            logo_url=request.logo_url,
            company_name=request.company_name,
            theme_color=request.theme_color or "#1d4ed8",
            contact_email=request.contact_email,
            contact_phone=request.contact_phone,
            website=request.website,
            footer_html=request.footer_html,
            enabled=request.enabled,
            apply_to_all_channels=request.apply_to_all_channels
        )
        db.add(branding)
    
    await db.commit()
    await db.refresh(branding)
    
    return BrandingResponse(
        id=branding.id,
        tenant_id=branding.tenant_id,
        logo_url=branding.logo_url,
        company_name=branding.company_name,
        theme_color=branding.theme_color,
        contact_email=branding.contact_email,
        contact_phone=branding.contact_phone,
        website=branding.website,
        footer_html=branding.footer_html,
        enabled=branding.enabled,
        apply_to_all_channels=branding.apply_to_all_channels,
        created_at=branding.created_at.isoformat(),
        updated_at=branding.updated_at.isoformat()
    )


@router.post(
    "/from-template",
    response_model=BrandingResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Save branding from template editor"
)
async def save_branding_from_template(
    request: BrandingRequest,
    tenant_id: str = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    """
    Save branding globally from the template editor.
    
    This allows users to save branding configuration while creating/editing templates,
    and it will automatically apply to all future emails.
    """
    return await create_or_update_branding(request, tenant_id, db)


@router.get("", response_model=BrandingResponse)
async def get_branding(
    tenant_id: str = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    """Get tenant branding configuration."""
    result = await db.execute(
        select(TenantBranding).where(TenantBranding.tenant_id == tenant_id)
    )
    branding = result.scalar_one_or_none()
    
    if not branding:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Branding not configured for this tenant"
        )
    
    return BrandingResponse(
        id=branding.id,
        tenant_id=branding.tenant_id,
        logo_url=branding.logo_url,
        company_name=branding.company_name,
        theme_color=branding.theme_color,
        contact_email=branding.contact_email,
        contact_phone=branding.contact_phone,
        website=branding.website,
        footer_html=branding.footer_html,
        enabled=branding.enabled,
        apply_to_all_channels=branding.apply_to_all_channels,
        created_at=branding.created_at.isoformat(),
        updated_at=branding.updated_at.isoformat()
    )


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_branding(
    tenant_id: str = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    """Delete tenant branding configuration."""
    result = await db.execute(
        select(TenantBranding).where(TenantBranding.tenant_id == tenant_id)
    )
    branding = result.scalar_one_or_none()
    
    if not branding:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Branding not found"
        )
    
    await db.delete(branding)
    await db.commit()


@router.post("/preview", response_model=BrandingPreviewResponse)
async def preview_branding(
    request: BrandingPreviewRequest,
    tenant_id: str = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db)
):
    """
    Preview how branding will look with the provided email content.
    
    This endpoint renders the email body with the tenant's branding footer
    so you can see the final result before sending.
    """
    engine = TenantTemplateEngine()
    
    # Render content with branding
    rendered = await engine.render_raw_content(
        db=db,
        tenant_id=tenant_id,
        subject=request.subject,
        body=request.body,
        channel="email",
        data=request.template_variables
    )
    
    return BrandingPreviewResponse(
        subject=rendered.get('subject'),
        body=request.body,  # Original body without branding
        body_with_branding=rendered.get('body')  # Body with branding footer
    )
