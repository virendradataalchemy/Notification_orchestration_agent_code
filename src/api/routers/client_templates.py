"""
Client-scoped template management API.

Allows clients to:
- Create and manage their own templates
- Clone global templates for customization
- Preview templates with sample data
- List available templates (global + client-specific)
- Update and delete their templates

All operations are scoped to the authenticated client.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, func
from typing import List, Optional
from datetime import datetime
import uuid
import re

from src.core import get_db, get_db_optional, supabase_client
from src.api.dependencies import get_authenticated_client
from src.api.schemas import (
    ClientTemplateCreate,
    ClientTemplateUpdate,
    TemplateResponse,
    ClientTemplateListResponse,
    TemplatePreviewRequest,
    TemplatePreviewResponse,
    TemplateCloneRequest,
    Channel
)
from src.models import Template, Client
from src.models.channel import Channel as ChannelModel
from src.services.client_template_engine import ClientTemplateEngine

router = APIRouter(prefix="/client/templates", tags=["client-templates"])
template_engine = ClientTemplateEngine()


def _serialize_template(template: Template | dict) -> dict:
    if isinstance(template, dict):
        channel_name = template.get("channel")
        if not channel_name:
            channel_rel = template.get("channels")
            if isinstance(channel_rel, dict):
                channel_name = channel_rel.get("name")
            elif isinstance(channel_rel, list) and channel_rel:
                channel_name = channel_rel[0].get("name")
        return {
            "id": template.get("id"),
            "client_id": template.get("client_id"),
            "name": template.get("name"),
            "channel": channel_name or "unknown",
            "language": template.get("language") or "en",
            "subject": template.get("subject"),
            "body": template.get("content") or template.get("body") or "",
            "version": template.get("version") or 1,
            "active": template.get("is_active", template.get("active", True)),
            "is_global": template.get("client_id") is None,
            "base_template_id": template.get("base_template_id"),
            "created_at": template.get("created_at") or datetime.utcnow(),
        }

    return {
        "id": template.id,
        "client_id": template.client_id,
        "name": template.name,
        "channel": template.channel or "unknown",
        "language": template.language or "en",
        "subject": template.subject,
        "body": template.body,
        "version": template.version,
        "active": template.active,
        "is_global": template.is_global,
        "base_template_id": template.base_template_id,
        "created_at": template.created_at or datetime.utcnow(),
    }


async def _get_channel_lookup(db: AsyncSession | None) -> tuple[dict[str, int], dict[int, str]]:
    if db is not None:
        result = await db.execute(select(ChannelModel))
        channels = result.scalars().all()
        by_name = {channel.name.lower(): channel.id for channel in channels}
        by_id = {channel.id: channel.name.lower() for channel in channels}
        return by_name, by_id

    rows = await supabase_client.select("channels", "id,name", filters={"is_active": "eq.true"})
    by_name = {str(row["name"]).lower(): row["id"] for row in rows}
    by_id = {row["id"]: str(row["name"]).lower() for row in rows}
    return by_name, by_id


@router.post(
    "/",
    response_model=TemplateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create client template",
    description="Create a new template for your client. You can only create templates for your own client."
)
async def create_client_template(
    template: ClientTemplateCreate,
    client: Client = Depends(get_authenticated_client),
    db: AsyncSession | None = Depends(get_db_optional)
):
    """
    Create a new template for the authenticated client.

    - **name**: Template identifier (e.g., 'welcome_email', 'order_sms')
    - **channel**: Channel type (email, sms, slack, whatsapp, push)
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

    # Check if template with same name/channel/language already exists for this client
    if db is not None:
        existing_query = (
            select(Template)
            .join(ChannelModel, Template.channel_id == ChannelModel.id)
            .where(
                Template.client_id == client.id,
                Template.name == template.name,
                ChannelModel.name == template.channel.value,
                Template.language == template.language
            )
        )
        result = await db.execute(existing_query)
        existing = result.scalar_one_or_none()
    else:
        existing_rows = await supabase_client.select(
            "templates",
            "id",
            limit=1,
            filters={
                "client_id": f"eq.{client.id}",
                "name": f"eq.{template.name}",
                "language": f"eq.{template.language}",
            },
        )
        existing = existing_rows[0] if existing_rows else None

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Template '{template.name}' for channel '{template.channel.value}' and language '{template.language}' already exists for your client"
        )

    # Get all channels for lookup
    channels = await supabase_client.select("channels", "id,name")
    channel_by_name = {c["name"].lower(): c["id"] for c in channels}
    
    # Map 'inapp' enum to 'in_app' database name
    channel_name = template.channel.value.lower()
    if channel_name == "inapp":
        channel_name = "in_app"
        
    channel_id = channel_by_name.get(channel_name)
    if channel_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Channel '{template.channel.value}' is not configured"
        )

    if db is not None:
        db_template = Template(
            client_id=client.id,
            name=template.name,
            channel_id=channel_id,
            language=template.language,
            subject=template.subject,
            content=template.body,
            variable_schema={"description": template.description} if template.description else None,
            version=1,
            is_active=True,
            notification_type=template.name,
        )

        db.add(db_template)
        await db.commit()
        await db.refresh(db_template)
        return _serialize_template(db_template)

    rows = await supabase_client.insert(
        "templates",
        {
            "client_id": client.id,
            "name": template.name,
            "channel_id": channel_id,
            "language": template.language,
            "subject": template.subject,
            "content": template.body,
            "variable_schema": {"description": template.description} if template.description else None,
            "version": 1,
            "is_active": True,
            "notification_type": template.name,
        },
    )
    created = rows[0]
    created["channel"] = template.channel.value
    return _serialize_template(created)


@router.get(
    "/",
    response_model=ClientTemplateListResponse,
    summary="List client templates",
    description="List all templates available to your client (global + client-specific)"
)
async def list_client_templates(
    channel: Optional[Channel] = Query(None, description="Filter by channel"),
    language: str = Query("en", description="Filter by language"),
    include_global: bool = Query(True, description="Include global templates"),
    client: Client = Depends(get_authenticated_client),
    db: AsyncSession | None = Depends(get_db_optional)
):
    """
    List all templates available to the authenticated client.

    Returns both:
    - Client-specific templates (created by you)
    - Global templates (platform defaults, if include_global=true)

    Client-specific templates override global templates with the same name.
    """
    if db is not None:
        conditions = [
            Template.active == True,
            Template.language == language
        ]

        if include_global:
            conditions.append(
                or_(
                    Template.client_id == client.id,
                    Template.client_id.is_(None)
                )
            )
        else:
            conditions.append(Template.client_id == client.id)

        query = select(Template).where(*conditions).order_by(
            Template.client_id.desc(),
            Template.name
        )
        if channel:
            query = query.join(ChannelModel, Template.channel_id == ChannelModel.id).where(ChannelModel.name == channel.value)

        result = await db.execute(query)
        templates = result.scalars().all()
        serialized_templates = [_serialize_template(template) for template in templates]
    else:
        _, channel_by_id = await _get_channel_lookup(db)
        filters = {
            "client_id": f"eq.{client.id}",
            "is_active": "eq.true",
            "language": f"eq.{language}",
        }
        rows = await supabase_client.select(
            "templates",
            "id,client_id,name,language,subject,content,version,is_active,notification_type,created_at,channel_id",
            filters=filters,
        )
        serialized_templates = []
        for row in rows:
            channel_name = channel_by_id.get(row.get("channel_id"), "unknown")
            if channel and channel_name != channel.value:
                continue
            row["channel"] = channel_name
            serialized_templates.append(_serialize_template(row))

    global_count = sum(1 for t in serialized_templates if t["client_id"] is None)
    client_count = sum(1 for t in serialized_templates if t["client_id"] == client.id)

    return ClientTemplateListResponse(
        client_id=client.id,
        client_name=client.name,
        templates=serialized_templates,
        global_templates_count=global_count,
        client_templates_count=client_count
    )


@router.get(
    "/stats",
    summary="Get template usage statistics",
    description="Get statistics about your templates"
)
async def get_template_stats(
    client: Client = Depends(get_authenticated_client),
    db: AsyncSession | None = Depends(get_db_optional)
):
    """
    Get statistics about template usage for your client.

    Shows:
    - Total templates created
    - Templates per channel
    - Most used templates
    """
    if db is not None:
        channel_query = (
            select(
                ChannelModel.name,
                func.count(Template.id).label('count')
            )
            .join(ChannelModel, Template.channel_id == ChannelModel.id)
            .where(
                Template.client_id == client.id,
                Template.active == True
            )
            .group_by(ChannelModel.name)
        )

        channel_result = await db.execute(channel_query)
        channel_counts = {row.name: row.count for row in channel_result}

        total_query = select(func.count(Template.id)).where(
            Template.client_id == client.id,
            Template.active == True
        )
        total_result = await db.execute(total_query)
        total_templates = total_result.scalar() or 0
        global_templates = 0
    else:
        _, channel_by_id = await _get_channel_lookup(db)
        rows = await supabase_client.select(
            "templates",
            "id,channel_id",
            filters={
                "client_id": f"eq.{client.id}",
                "is_active": "eq.true",
            },
        )
        channel_counts: dict[str, int] = {}
        for row in rows:
            name = channel_by_id.get(row.get("channel_id"), "unknown")
            channel_counts[name] = channel_counts.get(name, 0) + 1
        total_templates = len(rows)
        global_templates = 0

    return {
        "client_id": client.id,
        "client_name": client.name,
        "total_client_templates": total_templates,
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
async def get_client_template(
    template_id: str,
    client: Client = Depends(get_authenticated_client),
    db: AsyncSession | None = Depends(get_db_optional)
):
    """
    Get template details.

    You can access:
    - Your client-specific templates
    - Global templates (read-only)
    """
    if db is not None:
        query = select(Template).where(
            Template.id == int(template_id),
            or_(
                Template.client_id == client.id,
                Template.client_id.is_(None)
            )
        )
        result = await db.execute(query)
        template = result.scalar_one_or_none()
        serialized = _serialize_template(template) if template else None
    else:
        _, channel_by_id = await _get_channel_lookup(db)
        rows = await supabase_client.select(
            "templates",
            "id,client_id,name,language,subject,content,version,is_active,notification_type,created_at,channel_id",
            limit=1,
            filters={
                "id": f"eq.{template_id}",
                "client_id": f"eq.{client.id}",
            },
        )
        template = rows[0] if rows else None
        if template:
            template["channel"] = channel_by_id.get(template.get("channel_id"), "unknown")
        serialized = _serialize_template(template) if template else None

    if not serialized:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found or not accessible to your client"
        )

    return serialized


@router.put(
    "/{template_id}",
    response_model=TemplateResponse,
    summary="Update client template",
    description="Update an existing client-specific template"
)
async def update_client_template(
    template_id: str,
    update: ClientTemplateUpdate,
    client: Client = Depends(get_authenticated_client),
    db: AsyncSession | None = Depends(get_db_optional)
):
    """
    Update a client-specific template.

    You can only update templates that belong to your client.
    Global templates cannot be modified.
    """
    # Find template
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Template updates are not available in Supabase REST mode yet"
        )

    query = select(Template).where(
        Template.id == int(template_id),
        Template.client_id == client.id
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

    # Increment version
    db_template.version += 1

    await db.commit()
    await db.refresh(db_template)

    return _serialize_template(db_template)


@router.delete(
    "/{template_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete client template",
    description="Soft delete (deactivate) a client-specific template"
)
async def delete_client_template(
    template_id: str,
    client: Client = Depends(get_authenticated_client),
    db: AsyncSession | None = Depends(get_db_optional)
):
    """
    Deactivate a client-specific template.

    You can only delete templates that belong to your client.
    Global templates cannot be deleted.
    """
    if db is not None:
        query = select(Template).where(
            Template.id == int(template_id),
            Template.client_id == client.id
        )
        result = await db.execute(query)
        template = result.scalar_one_or_none()

        if not template:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Template not found or you don't have permission to delete it"
            )

        template.active = False
        await db.commit()
        return None

    rows = await supabase_client.update(
        "templates",
        {"is_active": False},
        filters={
            "id": f"eq.{template_id}",
            "client_id": f"eq.{client.id}",
        },
    )
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found or you don't have permission to delete it"
        )
    return None


@router.post(
    "/preview",
    response_model=TemplatePreviewResponse,
    summary="Preview template rendering",
    description="Preview how a template will render with sample data before saving"
)
async def preview_template(
    preview: TemplatePreviewRequest,
    client: Client = Depends(get_authenticated_client)
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
    rendered_body = template_engine.render_string(preview.body, preview.sample_data)

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
    client: Client = Depends(get_authenticated_client),
    db: AsyncSession = Depends(get_db)
):
    """
    List all global templates available for cloning.

    Global templates are platform defaults that you can:
    - Use as-is (if not overridden)
    - Clone and customize for your client
    """
    query = select(Template).where(
        Template.client_id.is_(None),
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
    description="Clone a global template and customize it for your client"
)
async def clone_global_template(
    clone_request: TemplateCloneRequest,
    client: Client = Depends(get_authenticated_client),
    db: AsyncSession = Depends(get_db)
):
    """
    Clone a global template to create a client-specific version.

    This creates a copy of a global template that you can then customize.
    The new template will override the global one for your client.
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

    # Check if client already has a template with this name/channel
    existing_query = select(Template).where(
        Template.client_id == client.id,
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

    # Create client template
    client_template = Template(
        id=f"{client.id}_{name}_{global_template.channel}_{uuid.uuid4().hex[:8]}",
        client_id=client.id,
        name=name,
        channel=global_template.channel,
        language=global_template.language,
        subject=subject,
        body=body,
        base_template_id=global_template.id,  # Track inheritance
        is_global=False,
        active=True,
        version=1
    )

    db.add(client_template)
    await db.commit()
    await db.refresh(client_template)

    return client_template


@router.post(
    "/validate",
    summary="Validate template syntax",
    description="Validate Jinja2 template syntax without saving"
)
async def validate_template_syntax(
    body: str,
    subject: Optional[str] = None,
    client: Client = Depends(get_authenticated_client)
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


# Helper functions

def extract_template_variables(template: str) -> List[str]:
    """
    Extract Jinja2 variables from template.

    Finds patterns like: {{user.name}}, {{order.id}}, {{message}}
    """
    pattern = r'\{\{[\s]*([a-zA-Z0-9_\.]+)[\s]*\}\}'
    matches = re.findall(pattern, template)
    return list(set(matches))
