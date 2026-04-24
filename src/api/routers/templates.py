from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List

from src.core import get_db
from src.api.schemas import TemplateCreate, TemplateResponse
from src.api.dependencies import verify_api_key
from src.models import Template

router = APIRouter(prefix="/templates", tags=["templates"])


@router.post(
    "/",
    response_model=TemplateResponse,
    status_code=status.HTTP_201_CREATED
)
async def create_template(
    template: TemplateCreate,
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(verify_api_key)
):
    """
    Create a new notification template.

    Templates support variable substitution using Jinja2 syntax.
    """
    # Check if template ID already exists
    query = select(Template).where(Template.id == template.id)
    result = await db.execute(query)
    existing = result.scalar_one_or_none()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Template with ID '{template.id}' already exists"
        )

    db_template = Template(
        id=template.id,
        name=template.name,
        channel=template.channel.value,
        language=template.language,
        subject=template.subject,
        body=template.body,
        version=template.version,
        active=True,
    )

    db.add(db_template)
    await db.commit()
    await db.refresh(db_template)

    return db_template


@router.get(
    "/{template_id}",
    response_model=TemplateResponse
)
async def get_template(
    template_id: str,
    language: str = "en",
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(verify_api_key)
):
    """
    Get a template by ID and language.
    """
    query = (
        select(Template)
        .where(Template.id == template_id)
        .where(Template.language == language)
        .where(Template.active == True)
    )
    result = await db.execute(query)
    template = result.scalar_one_or_none()

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found"
        )

    return template


@router.get(
    "/",
    response_model=List[TemplateResponse]
)
async def list_templates(
    channel: str = None,
    language: str = None,
    active: bool = True,
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(verify_api_key)
):
    """
    List all templates with optional filtering.
    """
    query = select(Template)

    if channel:
        query = query.where(Template.channel == channel)
    if language:
        query = query.where(Template.language == language)
    if active is not None:
        query = query.where(Template.active == active)

    result = await db.execute(query)
    templates = result.scalars().all()

    return templates


@router.put(
    "/{template_id}",
    response_model=TemplateResponse
)
async def update_template(
    template_id: str,
    template: TemplateCreate,
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(verify_api_key)
):
    """
    Update an existing template.
    """
    query = select(Template).where(Template.id == template_id)
    result = await db.execute(query)
    db_template = result.scalar_one_or_none()

    if not db_template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found"
        )

    db_template.name = template.name
    db_template.subject = template.subject
    db_template.body = template.body
    db_template.version += 1

    await db.commit()
    await db.refresh(db_template)

    return db_template


@router.delete(
    "/{template_id}",
    status_code=status.HTTP_204_NO_CONTENT
)
async def delete_template(
    template_id: str,
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(verify_api_key)
):
    """
    Deactivate a template (soft delete).
    """
    query = select(Template).where(Template.id == template_id)
    result = await db.execute(query)
    template = result.scalar_one_or_none()

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found"
        )

    template.active = False
    await db.commit()

    return None
