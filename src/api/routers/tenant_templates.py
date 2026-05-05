"""
Tenant-scoped template management API.

Allows tenants to:
- Create and manage their own templates
- Clone global templates for customization
- Preview templates with sample data
- List available templates (global + tenant-specific)
- Update and delete their templates

All operations are scoped to the authenticated tenant.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, func
from typing import List, Optional
from datetime import datetime
import uuid
import re

from src.core import get_db
from src.api.dependencies import get_authenticated_tenant
from src.api.schemas import (
    TenantTemplateCreate,
    TenantTemplateUpdate,
    TemplateResponse,
    TenantTemplateListResponse,
    TemplatePreviewRequest,
    TemplatePreviewResponse,
    TemplateCloneRequest,
    Channel,
    AITemplateGenerateRequest,
    AITemplateGenerateResponse,
    MultiChannelTemplateRequest,
    MultiChannelTemplateResponse
)
from src.models import Template, Tenant
from src.services.tenant_template_engine import TenantTemplateEngine
from src.services.llm_service import BedrockLLMService

router = APIRouter(prefix="/tenant/templates", tags=["tenant-templates"])
template_engine = TenantTemplateEngine()
llm_service = BedrockLLMService()


def _build_template_id(tenant_id: str, name: str, channel: str) -> str:
    """Build a DB-safe template id that fits templates.id (VARCHAR(50))."""
    safe_tenant = re.sub(r"[^a-zA-Z0-9_]+", "_", tenant_id)[:18]
    safe_name = re.sub(r"[^a-zA-Z0-9_]+", "_", name)[:12]
    safe_channel = re.sub(r"[^a-zA-Z0-9_]+", "_", channel)[:8]
    suffix = uuid.uuid4().hex[:8]
    return f"{safe_tenant}_{safe_name}_{safe_channel}_{suffix}"


@router.post(
    "/",
    response_model=TemplateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create tenant template",
    description="Create a new template for your tenant. You can only create templates for your own tenant."
)
async def create_tenant_template(
    template: TenantTemplateCreate,
    tenant: Tenant = Depends(get_authenticated_tenant),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new template for the authenticated tenant.

    - **name**: Template identifier (e.g., 'welcome_email', 'order_sms')
    - **channel**: Channel type (email, sms, slack, whatsapp)
    - **subject**: Subject line (required for email templates)
    - **body**: Template content with Jinja2 variables (e.g., {{user.name}})
    - **base_template_id**: Optional global template to inherit from
    """
    # Validate template syntax
    is_valid, error = template_engine.validate_template(template.body)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid template syntax: {error}"
        )

    if template.subject:
        is_valid, error = template_engine.validate_template(template.subject)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid subject template syntax: {error}"
            )

    # Check if template with same name/channel/language already exists for this tenant
    existing_query = select(Template).where(
        Template.tenant_id == tenant.id,
        Template.name == template.name,
        Template.channel == template.channel.value,
        Template.language == template.language
    )
    result = await db.execute(existing_query)
    existing = result.scalar_one_or_none()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Template '{template.name}' for channel '{template.channel.value}' and language '{template.language}' already exists for your tenant"
        )

    # Validate base_template_id if provided
    if template.base_template_id:
        base_query = select(Template).where(
            Template.id == template.base_template_id,
            Template.is_global == True,
            Template.active == True
        )
        base_result = await db.execute(base_query)
        base_template = base_result.scalar_one_or_none()

        if not base_template:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Global template '{template.base_template_id}' not found"
            )

    # Create template
    db_template = Template(
        id=_build_template_id(tenant.id, template.name, template.channel.value),
        tenant_id=tenant.id,
        name=template.name,
        channel=template.channel.value,
        language=template.language,
        subject=template.subject,
        body=template.body,
        base_template_id=template.base_template_id,
        provider_template_ref=template.provider_template_ref,
        provider_template_meta=template.provider_template_meta,
        is_global=False,
        active=True,
        version=1
    )

    db.add(db_template)
    await db.commit()
    await db.refresh(db_template)

    return db_template


@router.get(
    "/",
    response_model=TenantTemplateListResponse,
    summary="List tenant templates",
    description="List all templates available to your tenant (global + tenant-specific)"
)
async def list_tenant_templates(
    channel: Optional[Channel] = Query(None, description="Filter by channel"),
    language: str = Query("en", description="Filter by language"),
    include_global: bool = Query(True, description="Include global templates"),
    tenant: Tenant = Depends(get_authenticated_tenant),
    db: AsyncSession = Depends(get_db)
):
    """
    List all templates available to the authenticated tenant.

    Returns both:
    - Tenant-specific templates (created by you)
    - Global templates (platform defaults, if include_global=true)

    Tenant-specific templates override global templates with the same name.
    """
    # Build query
    conditions = [
        Template.active == True,
        Template.language == language
    ]

    if include_global:
        conditions.append(
            or_(
                Template.tenant_id == tenant.id,
                Template.tenant_id.is_(None)
            )
        )
    else:
        conditions.append(Template.tenant_id == tenant.id)

    if channel:
        conditions.append(Template.channel == channel.value)

    query = select(Template).where(*conditions).order_by(
        Template.tenant_id.desc(),  # Tenant templates first
        Template.channel,
        Template.name
    )

    result = await db.execute(query)
    templates = result.scalars().all()

    # Count global vs tenant templates
    global_count = sum(1 for t in templates if t.tenant_id is None)
    tenant_count = sum(1 for t in templates if t.tenant_id == tenant.id)

    return TenantTemplateListResponse(
        tenant_id=tenant.id,
        templates=templates,
        global_templates_count=global_count,
        tenant_templates_count=tenant_count
    )


@router.get(
    "/stats",
    summary="Get template usage statistics",
    description="Get statistics about your templates"
)
async def get_template_stats(
    tenant: Tenant = Depends(get_authenticated_tenant),
    db: AsyncSession = Depends(get_db)
):
    """
    Get statistics about template usage for your tenant.

    Shows:
    - Total templates created
    - Templates per channel
    - Most used templates
    """
    # Count tenant templates by channel
    channel_query = select(
        Template.channel,
        func.count(Template.id).label('count')
    ).where(
        Template.tenant_id == tenant.id,
        Template.active == True
    ).group_by(Template.channel)

    channel_result = await db.execute(channel_query)
    channel_counts = {row.channel: row.count for row in channel_result}

    # Total tenant templates
    total_query = select(func.count(Template.id)).where(
        Template.tenant_id == tenant.id,
        Template.active == True
    )
    total_result = await db.execute(total_query)
    total_templates = total_result.scalar() or 0

    # Count global templates available
    global_query = select(func.count(Template.id)).where(
        Template.tenant_id.is_(None),
        Template.is_global == True,
        Template.active == True
    )
    global_result = await db.execute(global_query)
    global_templates = global_result.scalar() or 0

    return {
        "tenant_id": tenant.id,
        "tenant_name": tenant.name,
        "total_tenant_templates": total_templates,
        "total_global_templates_available": global_templates,
        "templates_by_channel": channel_counts,
        "stats_generated_at": datetime.utcnow().isoformat()
    }


@router.get(
    "/{template_id}",
    response_model=TemplateResponse,
    summary="Get template details",
    description="Get a specific template by ID"
)
async def get_tenant_template(
    template_id: str,
    tenant: Tenant = Depends(get_authenticated_tenant),
    db: AsyncSession = Depends(get_db)
):
    """
    Get template details.

    You can access:
    - Your tenant-specific templates
    - Global templates (read-only)
    """
    query = select(Template).where(
        or_(
            Template.id == template_id,
            Template.name == template_id
        ),
        or_(
            Template.tenant_id == tenant.id,
            Template.tenant_id.is_(None)  # Global templates
        )
    )
    result = await db.execute(query)
    template = result.scalar_one_or_none()

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found or not accessible to your tenant"
        )

    return template


@router.put(
    "/{template_id}",
    response_model=TemplateResponse,
    summary="Update tenant template",
    description="Update an existing tenant-specific template"
)
async def update_tenant_template(
    template_id: str,
    update: TenantTemplateUpdate,
    tenant: Tenant = Depends(get_authenticated_tenant),
    db: AsyncSession = Depends(get_db)
):
    """
    Update a tenant-specific template.

    You can only update templates that belong to your tenant.
    Global templates cannot be modified.
    """
    # Find template
    query = select(Template).where(
        Template.id == template_id,
        Template.tenant_id == tenant.id  # Must be tenant's own template
    )
    result = await db.execute(query)
    db_template = result.scalar_one_or_none()

    if not db_template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found or you don't have permission to modify it"
        )

    # Validate new template syntax if body is being updated
    if update.body:
        is_valid, error = template_engine.validate_template(update.body)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid template syntax: {error}"
            )
        db_template.body = update.body

    if update.subject:
        is_valid, error = template_engine.validate_template(update.subject)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid subject template syntax: {error}"
            )
        db_template.subject = update.subject

    # Update other fields
    if update.name:
        db_template.name = update.name
    if update.active is not None:
        db_template.active = update.active
    if update.provider_template_ref is not None:
        db_template.provider_template_ref = update.provider_template_ref
    if update.provider_template_meta is not None:
        db_template.provider_template_meta = update.provider_template_meta

    # Increment version
    db_template.version += 1

    await db.commit()
    await db.refresh(db_template)

    return db_template


@router.delete(
    "/{template_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete tenant template",
    description="Soft delete (deactivate) a tenant-specific template"
)
async def delete_tenant_template(
    template_id: str,
    tenant: Tenant = Depends(get_authenticated_tenant),
    db: AsyncSession = Depends(get_db)
):
    """
    Deactivate a tenant-specific template.

    You can only delete templates that belong to your tenant.
    Global templates cannot be deleted.
    """
    query = select(Template).where(
        Template.id == template_id,
        Template.tenant_id == tenant.id
    )
    result = await db.execute(query)
    template = result.scalar_one_or_none()

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found or you don't have permission to delete it"
        )

    # Soft delete
    template.active = False
    await db.commit()

    return None


@router.post(
    "/preview",
    response_model=TemplatePreviewResponse,
    summary="Preview template rendering",
    description="Preview how a template will render with sample data before saving"
)
async def preview_template(
    preview: TemplatePreviewRequest,
    tenant: Tenant = Depends(get_authenticated_tenant)
):
    """
    Preview template rendering with sample data.

    Use this to test your template before creating/updating it.
    """
    # Validate and render
    is_valid, error = template_engine.validate_template(preview.body)

    if not is_valid:
        return TemplatePreviewResponse(
            rendered_subject=None,
            rendered_body="",
            valid=False,
            error=error
        )

    # Render body
    rendered_body = template_engine.render_string(
        preview.body, 
        preview.sample_data, 
        wrap_variables=preview.wrap_variables
    )

    # Render subject if provided
    rendered_subject = None
    if preview.subject:
        is_valid, error = template_engine.validate_template(preview.subject)
        if not is_valid:
            return TemplatePreviewResponse(
                rendered_subject=None,
                rendered_body="",
                valid=False,
                error=f"Invalid subject: {error}"
            )
        rendered_subject = template_engine.render_string(preview.subject, preview.sample_data)

    # Extract variables used in template
    variables_used = extract_template_variables(preview.body)
    if preview.subject:
        variables_used.extend(extract_template_variables(preview.subject))
    variables_used = list(set(variables_used))  # Remove duplicates

    return TemplatePreviewResponse(
        rendered_subject=rendered_subject,
        rendered_body=rendered_body,
        valid=True,
        variables_used=variables_used
    )


@router.get(
    "/global",
    response_model=List[TemplateResponse],
    summary="List global templates",
    description="Browse global platform templates that you can clone and customize"
)
async def list_global_templates(
    channel: Optional[Channel] = Query(None, description="Filter by channel"),
    language: str = Query("en", description="Filter by language"),
    tenant: Tenant = Depends(get_authenticated_tenant),
    db: AsyncSession = Depends(get_db)
):
    """
    List all global templates available for cloning.

    Global templates are platform defaults that you can:
    - Use as-is (if not overridden)
    - Clone and customize for your tenant
    """
    query = select(Template).where(
        Template.tenant_id.is_(None),
        Template.is_global == True,
        Template.active == True,
        Template.language == language
    )

    if channel:
        query = query.where(Template.channel == channel.value)

    query = query.order_by(Template.channel, Template.name)

    result = await db.execute(query)
    templates = result.scalars().all()

    return templates


@router.post(
    "/clone",
    response_model=TemplateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Clone global template",
    description="Clone a global template and customize it for your tenant"
)
async def clone_global_template(
    clone_request: TemplateCloneRequest,
    tenant: Tenant = Depends(get_authenticated_tenant),
    db: AsyncSession = Depends(get_db)
):
    """
    Clone a global template to create a tenant-specific version.

    This creates a copy of a global template that you can then customize.
    The new template will override the global one for your tenant.
    """
    # Find global template
    global_query = select(Template).where(
        Template.id == clone_request.global_template_id,
        Template.is_global == True,
        Template.active == True
    )
    global_result = await db.execute(global_query)
    global_template = global_result.scalar_one_or_none()

    if not global_template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Global template not found"
        )

    # Check if tenant already has a template with this name/channel
    existing_query = select(Template).where(
        Template.tenant_id == tenant.id,
        Template.name == global_template.name,
        Template.channel == global_template.channel,
        Template.language == global_template.language
    )
    existing_result = await db.execute(existing_query)
    existing = existing_result.scalar_one_or_none()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"You already have a template named '{global_template.name}' for {global_template.channel}"
        )

    # Apply customizations
    subject = global_template.subject
    body = global_template.body
    name = clone_request.new_name or global_template.name

    if clone_request.customizations:
        if "subject" in clone_request.customizations:
            subject = clone_request.customizations["subject"]
        if "body" in clone_request.customizations:
            body = clone_request.customizations["body"]
        if "name" in clone_request.customizations:
            name = clone_request.customizations["name"]

    # Validate customized template
    is_valid, error = template_engine.validate_template(body)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid customized template syntax: {error}"
        )

    # Create tenant template
    tenant_template = Template(
        id=_build_template_id(tenant.id, name, global_template.channel),
        tenant_id=tenant.id,
        name=name,
        channel=global_template.channel,
        language=global_template.language,
        subject=subject,
        body=body,
        base_template_id=global_template.id,  # Track inheritance
        provider_template_ref=global_template.provider_template_ref,
        provider_template_meta=global_template.provider_template_meta,
        is_global=False,
        active=True,
        version=1
    )

    db.add(tenant_template)
    await db.commit()
    await db.refresh(tenant_template)

    return tenant_template


@router.post(
    "/validate",
    summary="Validate template syntax",
    description="Validate Jinja2 template syntax without saving"
)
async def validate_template_syntax(
    body: str,
    subject: Optional[str] = None,
    tenant: Tenant = Depends(get_authenticated_tenant)
):
    """
    Validate template syntax without creating it.

    Useful for real-time validation in template editors.
    """
    # Validate body
    is_valid, error = template_engine.validate_template(body)

    if not is_valid:
        return {
            "valid": False,
            "error": error,
            "field": "body"
        }

    # Validate subject if provided
    if subject:
        is_valid, error = template_engine.validate_template(subject)
        if not is_valid:
            return {
                "valid": False,
                "error": error,
                "field": "subject"
            }

    # Extract variables
    variables_body = extract_template_variables(body)
    variables_subject = extract_template_variables(subject) if subject else []
    all_variables = list(set(variables_body + variables_subject))

    return {
        "valid": True,
        "variables_found": all_variables,
        "variables_count": len(all_variables)
    }


@router.post(
    "/ai-generate",
    response_model=AITemplateGenerateResponse,
    summary="Generate template using AI",
    description="Use AI to generate a professional template based on raw content"
)
async def ai_generate_template(
    request: AITemplateGenerateRequest,
    tenant: Tenant = Depends(get_authenticated_tenant)
):
    """
    Generate a professional template using AI.
    """
    generated = await llm_service.generate_template(
        content=request.content,
        channel=request.channel.value
    )
    return generated


@router.post(
    "/ai-generate-multi",
    response_model=MultiChannelTemplateResponse,
    summary="Generate templates for multiple channels using AI",
    description="Use AI to generate professional templates for multiple channels at once"
)
async def ai_generate_multi_templates(
    request: MultiChannelTemplateRequest,
    tenant: Tenant = Depends(get_authenticated_tenant)
):
    """
    Generate professional templates for multiple channels using AI.
    """
    channels = [c.value for c in request.channels]
    result = await llm_service.generate_multi_channel_templates(
        content=request.content,
        channels=channels
    )
    
    # Format response
    templates = {}
    for channel_str, template_data in result.get("templates", {}).items():
        try:
            channel_enum = Channel(channel_str)
            templates[channel_enum] = AITemplateGenerateResponse(
                name=template_data.get("name"),
                subject=template_data.get("subject"),
                body=template_data.get("body"),
                description=template_data.get("description", f"AI generated {channel_str} template")
            )
        except ValueError:
            continue
            
    return MultiChannelTemplateResponse(templates=templates)


# Helper functions

def extract_template_variables(template: str) -> List[str]:
    """
    Extract Jinja2 variables from template.

    Finds patterns like: {{user.name}}, {{order.id}}, {{message}}
    """
    pattern = r'\{\{[\s]*([a-zA-Z0-9_\.]+)[\s]*\}\}'
    matches = re.findall(pattern, template)
    return list(set(matches))
