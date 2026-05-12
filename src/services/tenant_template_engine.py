"""
Tenant-aware template engine with inheritance support.

Supports:
- Global templates (tenant_id = NULL)
- Tenant-specific templates
- Template inheritance (tenant templates can override global templates)
- Variable substitution with Jinja2
- Email branding footer (default or custom Jinja2 HTML) appended after body
"""

import html as html_module

from jinja2 import Environment, BaseLoader
from typing import Dict, Any, Optional
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Template


class TenantTemplateEngine:
    """Template engine with tenant-aware template resolution and inheritance."""

    def __init__(self):
        self.env = Environment(loader=BaseLoader(), autoescape=True)

    def render_branding_footer_html(self, branding: Dict[str, Any], data: Dict[str, Any]) -> str:
        """
        Build the email branding block that is appended after the main template body.

        If ``footer_html`` is set, render it as Jinja2 with ``data`` (including ``branding``).
        Otherwise render a default signature-style footer (logo + contact lines).
        """
        if not branding or not isinstance(branding, dict):
            return ""
        b = dict(branding)
        custom = (b.get("footer_html") or "").strip()
        ctx = {**data, "branding": b}
        try:
            if custom:
                tpl = self.env.from_string(custom)
                return tpl.render(**ctx)
            return self._default_email_branding_footer(b)
        except Exception as e:
            return (
                '<div style="padding:12px;color:#b91c1c;font-size:13px;border:1px solid #fecaca;'
                'border-radius:8px;margin-top:16px;">[Branding footer error: '
                f"{html_module.escape(str(e))}]</div>"
            )

    def _default_email_branding_footer(self, b: Dict[str, Any]) -> str:
        """Outlook-style horizontal rules + two-column logo | contacts."""
        theme = (b.get("theme_color") or "#1d4ed8").strip()
        logo = (b.get("logo_url") or "").strip()
        company = (b.get("company_name") or "").strip()
        phone = (b.get("contact_phone") or "").strip()
        email_c = (b.get("contact_email") or "").strip()
        web = (b.get("website") or "").strip()
        if not any([logo, company, phone, email_c, web]):
            return ""

        def esc(x: str) -> str:
            return html_module.escape(x, quote=True)

        contact_rows = []
        if phone:
            contact_rows.append(
                f'<p style="margin:6px 0;font-size:14px;line-height:1.4;">'
                f'<strong style="color:{esc(theme)};">M:</strong> '
                f'<span style="color:#0f172a;">{esc(phone)}</span></p>'
            )
        if email_c:
            contact_rows.append(
                f'<p style="margin:6px 0;font-size:14px;line-height:1.4;">'
                f'<strong style="color:{esc(theme)};">E:</strong> '
                f'<span style="color:#0f172a;">{esc(email_c)}</span></p>'
            )
        if web:
            contact_rows.append(
                f'<p style="margin:6px 0;font-size:14px;line-height:1.4;">'
                f'<strong style="color:{esc(theme)};">W:</strong> '
                f'<span style="color:#0f172a;">{esc(web)}</span></p>'
            )

        logo_cell = ""
        if logo:
            logo_cell = (
                f'<td style="vertical-align:top;padding-right:20px;width:1%;">'
                f'<img src="{esc(logo)}" alt="" width="120" '
                'style="display:block;max-width:120px;height:auto;border:0;outline:none;" />'
                f"</td>"
            )
        else:
            logo_cell = '<td style="width:1%;"></td>'

        title_html = ""
        if company:
            title_html = (
                f'<p style="margin:0 0 10px 0;font-size:16px;font-weight:700;color:#0f172a;'
                f'white-space:pre-line;">'
                f"{esc(company)}</p>"
            )

        contacts_html = "".join(contact_rows)
        inner = f"{title_html}{contacts_html}" if (title_html or contacts_html) else ""

        return (
            '<div class="notification-branding-footer" style="margin-top:28px;">'
            '<hr style="border:none;border-top:1px solid #e2e8f0;margin:0 0 20px 0;" />'
            '<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
            'style="width:100%;max-width:560px;border-collapse:collapse;">'
            "<tr>"
            f"{logo_cell}"
            f'<td style="vertical-align:top;">{inner}</td>'
            "</tr>"
            "</table>"
            '<hr style="border:none;border-top:1px solid #e2e8f0;margin:20px 0 0 0;" />'
            "</div>"
        )

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
        # Query for both tenant-specific and global templates.
        # Accept either logical template name or concrete template id.
        query = (
            select(Template)
            .where(
                or_(
                    Template.name == template_name,
                    Template.id == template_name
                ),
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

        # Extract branding into data context if available and not already provided
        meta = template.provider_template_meta or {}
        if "branding" in meta and "branding" not in data:
            data = {**data, "branding": meta["branding"]}

        # Render subject and body
        try:
            rendered_subject = None
            if template.subject:
                subject_template = self.env.from_string(template.subject)
                rendered_subject = subject_template.render(**data)

            body_template = self.env.from_string(template.body)
            rendered_body = body_template.render(**data)

            if channel == "email":
                branding_block = meta.get("branding")
                if branding_block and isinstance(branding_block, dict):
                    footer = self.render_branding_footer_html(branding_block, data)
                    if footer:
                        rendered_body = rendered_body + footer

            return {
                'subject': rendered_subject,
                'body': rendered_body,
                'template_id': template.id,
                'provider_template_ref': template.provider_template_ref,
                'provider_template_meta': template.provider_template_meta or {},
            }

        except Exception as e:
            # Log error but return template with error indication
            return {
                'subject': f"[Template Error: {str(e)}]",
                'body': f"[Template Error: {str(e)}]",
                'template_id': template.id,
                'provider_template_ref': template.provider_template_ref,
                'provider_template_meta': template.provider_template_meta or {},
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

        # Extract branding into data context if available and not already provided
        meta = tenant_template.provider_template_meta or {}
        if "branding" in meta and "branding" not in data:
            data = {**data, "branding": meta["branding"]}

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

            if channel == "email":
                branding_block = meta.get("branding")
                if branding_block and isinstance(branding_block, dict):
                    footer = self.render_branding_footer_html(branding_block, data)
                    if footer:
                        rendered_body = rendered_body + footer

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

    def render_string(self, template: str, data: Dict[str, Any], wrap_variables: bool = False) -> str:
        """
        Render a template string with data.

        Args:
            template: Template string with Jinja2 syntax
            data: Dictionary of variables
            wrap_variables: If True, wraps rendered variables in a span for visual editing

        Returns:
            Rendered string
        """
        try:
            if wrap_variables:
                # Wrap {{ var }} with <span class="jinja-var" data-raw="{{var}}">value</span>
                import re
                
                # First, find all {{ variables }}
                vars_found = re.findall(r'(\{\{[\s]*[a-zA-Z0-9_\.]+[\s]*\}\})', template)
                
                # Replace each one with a wrapped version temporarily
                # Note: This is a bit naive but works for simple cases
                wrapped_template = template
                for var_raw in set(vars_found):
                    # We need to render the value to put inside the span
                    jinja_var = self.env.from_string(var_raw)
                    try:
                        val = jinja_var.render(**data)
                    except:
                        val = var_raw
                    
                    # Escape the raw var for the data-raw attribute
                    safe_raw = var_raw.replace('"', '&quot;')
                    wrapped_template = wrapped_template.replace(
                        var_raw, 
                        f'<span class="jinja-var" data-raw="{safe_raw}" style="background: #eef2ff; border-bottom: 1px dashed #6366f1; color: #4338ca; cursor: help;" title="Variable: {safe_raw}">{val}</span>'
                    )
                
                # Now render the whole thing (to handle any other logic like % if %)
                # But since we already replaced the variables, we should just return it
                # unless there are conditions.
                # For conditions, this approach might be slightly broken, but for simple templates it works.
                return wrapped_template

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
