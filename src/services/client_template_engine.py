from __future__ import annotations

from typing import Any, Optional

from jinja2 import BaseLoader, Environment
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models import Channel, Template


class ClientTemplateEngine:
    """Resolve and render templates from the live Supabase schema."""

    def __init__(self):
        self.env = Environment(loader=BaseLoader(), autoescape=True)

    async def get_template(
        self,
        db: AsyncSession,
        client_id: int,
        template_key: str,
        channel: str,
        notification_type: Optional[str] = None,
        language: str = "en",
    ) -> Optional[Template]:
        query = (
            select(Template)
            .join(Channel, Template.channel_id == Channel.id)
            .options(selectinload(Template.channel_ref))
            .where(
                Template.client_id == client_id,
                Template.is_active == True,
                Channel.name == channel,
                Template.language == language,
            )
        )

        if str(template_key).isdigit():
            query = query.where(Template.id == int(template_key))
        else:
            query = query.where(Template.name == template_key)

        if notification_type:
            query = query.order_by((Template.notification_type == notification_type).desc(), Template.id.asc())

        result = await db.execute(query)
        template = result.scalars().first()
        if template:
            return template

        # If lookup by numeric ID found nothing (channel mismatch), try without channel filter
        if str(template_key).isdigit():
            result = await db.execute(
                select(Template)
                .options(selectinload(Template.channel_ref))
                .where(
                    Template.client_id == client_id,
                    Template.is_active == True,
                    Template.id == int(template_key),
                )
            )
            template = result.scalars().first()
            if template:
                return template

        if notification_type:
            result = await db.execute(
                select(Template)
                .join(Channel, Template.channel_id == Channel.id)
                .options(selectinload(Template.channel_ref))
                .where(
                    Template.client_id == client_id,
                    Template.is_active == True,
                    Channel.name == channel,
                    Template.language == language,
                    Template.notification_type == notification_type,
                )
                .order_by(Template.id.asc())
            )
            return result.scalars().first()

        return None

    async def render_template(
        self,
        db: AsyncSession,
        client_id: int,
        template_key: str,
        channel: str,
        data: dict[str, Any],
        notification_type: Optional[str] = None,
        language: str = "en",
    ) -> Optional[dict[str, Any]]:
        template = await self.get_template(
            db=db,
            client_id=client_id,
            template_key=template_key,
            channel=channel,
            notification_type=notification_type,
            language=language,
        )
        if not template:
            return None

        try:
            rendered_subject = None
            if template.subject:
                rendered_subject = self.env.from_string(template.subject).render(**data)
            rendered_body = self.env.from_string(template.content).render(**data)
            return {
                "template_id": template.id,
                "subject": rendered_subject,
                "body": rendered_body,
            }
        except Exception as exc:
            return {
                "template_id": template.id,
                "subject": template.subject,
                "body": f"[Template Error: {exc}]",
            }

    def render_string(self, template: str, data: dict[str, Any]) -> str:
        return self.env.from_string(template).render(**data)

    def validate_template(self, template: str) -> tuple[bool, Optional[str]]:
        try:
            self.env.from_string(template)
            return True, None
        except Exception as exc:
            return False, str(exc)

    async def list_available_templates(
        self,
        db: AsyncSession,
        client_id: int,
        channel: Optional[str] = None,
        language: str = "en",
    ) -> list[Template]:
        query = (
            select(Template)
            .join(Channel, Template.channel_id == Channel.id)
            .options(selectinload(Template.channel_ref))
            .where(
                Template.client_id == client_id,
                Template.language == language,
                Template.is_active == True,
            )
            .order_by(Template.id.asc())
        )
        if channel:
            query = query.where(Channel.name == channel)
        result = await db.execute(query)
        return list(result.scalars().all())
