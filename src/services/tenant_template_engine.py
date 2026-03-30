"""
Tenant-aware template engine with inheritance support.

Supports:
- Global templates (tenant_id = NULL)
- Tenant-specific templates
- Template inheritance (tenant templates can override global templates)
- Variable substitution with Jinja2
"""

from jinja2 import Environment, BaseLoader
from typing import Dict, Any, Optional
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Template


class TenantTemplateEngine:
    """Template engine with tenant-aware template resolution and inheritance."""

    def __init__(self):
        self.env = Environment(loader=BaseLoader(), autoescape=True)

    async def get_template(
        self,
        db: AsyncSession,
        tenant_id: str,
        template_name: str,
        channel: str,
        language: str = "en"
    ) -> Optional[Template]:
        """
        Get template with tenant-specific override support.

        Resolution order:
        1. Check for tenant-specific template
        2. Fall back to global template (tenant_id = NULL)

        Args:
            db: Database session
            tenant_id: Tenant identifier
            template_name: Name of template
            channel: Channel (email, sms, etc.)
            language: Language code

        Returns:
            Template object or None
        """
        # Query for both tenant-specific and global templates
        query = (
            select(Template)
            .where(
                Template.name == template_name,
                Template.channel == channel,
                Template.language == language,
                Template.active == True,
                or_(
                    Template.tenant_id == tenant_id,
                    Template.tenant_id.is_(None)
                )
            )
            .order_by(
                # Tenant-specific templates take precedence
                Template.tenant_id.desc()
            )
        )

        result = await db.execute(query)
        templates = result.scalars().all()

        if not templates:
            return None

        # First template is either tenant-specific or global
        tenant_template = templates[0]

        # If it's a tenant override with base_template_id, we could merge them
        # For now, we just return the most specific template
        return tenant_template

    async def render_template(
        self,
        db: AsyncSession,
        tenant_id: str,
        template_name: str,
        channel: str,
        data: Dict[str, Any],
        language: str = "en"
    ) -> Optional[Dict[str, str]]:
        """
        Render template with tenant-specific overrides.

        Args:
            db: Database session
            tenant_id: Tenant identifier
            template_name: Name of template
            channel: Channel type
            data: Variables for template substitution
            language: Language code

        Returns:
            Dict with 'subject' and 'body' or None if template not found
        """
        # Get template (tenant-specific or global)
        template = await self.get_template(
            db, tenant_id, template_name, channel, language
        )

        if not template:
            return None

        # Render subject and body
        try:
            rendered_subject = None
            if template.subject:
                subject_template = self.env.from_string(template.subject)
                rendered_subject = subject_template.render(**data)

            body_template = self.env.from_string(template.body)
            rendered_body = body_template.render(**data)

            return {
                'subject': rendered_subject,
                'body': rendered_body,
                'template_id': template.id
            }

        except Exception as e:
            # Log error but return template with error indication
            return {
                'subject': f"[Template Error: {str(e)}]",
                'body': f"[Template Error: {str(e)}]",
                'template_id': template.id
            }

    async def render_with_inheritance(
        self,
        db: AsyncSession,
        tenant_id: str,
        template_name: str,
        channel: str,
        data: Dict[str, Any],
        language: str = "en"
    ) -> Optional[Dict[str, str]]:
        """
        Render template with full inheritance chain.

        If tenant template has base_template_id, merges with base template:
        - Uses tenant template's subject if present, else base template's
        - Uses tenant template's body if present, else base template's
        - Variables from both templates are available

        Args:
            db: Database session
            tenant_id: Tenant identifier
            template_name: Name of template
            channel: Channel type
            data: Variables for template substitution
            language: Language code

        Returns:
            Dict with 'subject' and 'body' or None
        """
        # Get tenant-specific template
        tenant_template = await self.get_template(
            db, tenant_id, template_name, channel, language
        )

        if not tenant_template:
            return None

        # Check if it has a base template
        base_template = None
        if tenant_template.base_template_id:
            query = select(Template).where(
                Template.id == tenant_template.base_template_id,
                Template.active == True
            )
            result = await db.execute(query)
            base_template = result.scalar_one_or_none()

        # Determine which subject and body to use
        subject_text = tenant_template.subject
        if not subject_text and base_template:
            subject_text = base_template.subject

        body_text = tenant_template.body
        if not body_text and base_template:
            body_text = base_template.body

        # Render
        try:
            rendered_subject = None
            if subject_text:
                subject_template = self.env.from_string(subject_text)
                rendered_subject = subject_template.render(**data)

            if body_text:
                body_template = self.env.from_string(body_text)
                rendered_body = body_template.render(**data)
            else:
                rendered_body = ""

            return {
                'subject': rendered_subject,
                'body': rendered_body,
                'template_id': tenant_template.id,
                'base_template_id': tenant_template.base_template_id
            }

        except Exception as e:
            return {
                'subject': f"[Template Error: {str(e)}]",
                'body': f"[Template Error: {str(e)}]",
                'template_id': tenant_template.id
            }

    def render_string(self, template: str, data: Dict[str, Any]) -> str:
        """
        Render a template string with data.

        Args:
            template: Template string with Jinja2 syntax
            data: Dictionary of variables

        Returns:
            Rendered string
        """
        try:
            jinja_template = self.env.from_string(template)
            return jinja_template.render(**data)
        except Exception as e:
            return f"[Template Error: {str(e)}]"

    def validate_template(self, template: str) -> tuple[bool, Optional[str]]:
        """
        Validate template syntax.

        Args:
            template: Template string to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            self.env.from_string(template)
            return True, None
        except Exception as e:
            return False, str(e)

    async def list_available_templates(
        self,
        db: AsyncSession,
        tenant_id: str,
        channel: Optional[str] = None,
        language: str = "en"
    ) -> list[Template]:
        """
        List all available templates for a tenant (including global).

        Args:
            db: Database session
            tenant_id: Tenant identifier
            channel: Optional channel filter
            language: Language code

        Returns:
            List of Template objects
        """
        query = select(Template).where(
            Template.language == language,
            Template.active == True,
            or_(
                Template.tenant_id == tenant_id,
                Template.tenant_id.is_(None),
                Template.is_global == True
            )
        )

        if channel:
            query = query.where(Template.channel == channel)

        query = query.order_by(
            Template.tenant_id.desc(),  # Tenant-specific first
            Template.name
        )

        result = await db.execute(query)
        return result.scalars().all()

    async def create_tenant_template(
        self,
        db: AsyncSession,
        tenant_id: str,
        name: str,
        channel: str,
        subject: Optional[str],
        body: str,
        language: str = "en",
        base_template_id: Optional[str] = None
    ) -> Template:
        """
        Create a tenant-specific template.

        Args:
            db: Database session
            tenant_id: Tenant identifier
            name: Template name
            channel: Channel type
            subject: Email subject (optional for non-email)
            body: Template body
            language: Language code
            base_template_id: Base template to inherit from (optional)

        Returns:
            Created Template object
        """
        import uuid

        template = Template(
            id=f"{tenant_id}_{name}_{channel}_{uuid.uuid4().hex[:8]}",
            tenant_id=tenant_id,
            name=name,
            channel=channel,
            language=language,
            subject=subject,
            body=body,
            base_template_id=base_template_id,
            is_global=False,
            active=True,
            version=1
        )

        db.add(template)
        await db.commit()
        await db.refresh(template)

        return template
