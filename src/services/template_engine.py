from jinja2 import Environment, BaseLoader, TemplateNotFound
from typing import Dict, Any


class TemplateEngine:
    """Template rendering engine using Jinja2."""

    def __init__(self):
        self.env = Environment(loader=BaseLoader(), autoescape=True)

    def render(self, template: str, data: Dict[str, Any]) -> str:
        """
        Render a template with provided data.

        Args:
            template: Template string with Jinja2 syntax
            data: Dictionary of variables to substitute

        Returns:
            Rendered template string

        Example:
            >>> engine = TemplateEngine()
            >>> template = "Hello {{user.first_name}}, your order #{{order.id}} is confirmed!"
            >>> data = {"user": {"first_name": "John"}, "order": {"id": "12345"}}
            >>> engine.render(template, data)
            "Hello John, your order #12345 is confirmed!"
        """
        try:
            jinja_template = self.env.from_string(template)
            return jinja_template.render(**data)
        except Exception as e:
            # Return template with error indication
            return f"[Template Error: {str(e)}]"

    def render_with_fallback(
        self, template: str, data: Dict[str, Any], default_values: Dict[str, Any] = None
    ) -> str:
        """
        Render template with fallback values for missing variables.

        Args:
            template: Template string
            data: Primary data dictionary
            default_values: Fallback values for missing keys

        Returns:
            Rendered template string
        """
        # Merge data with defaults
        merged_data = {**(default_values or {}), **data}

        return self.render(template, merged_data)

    def validate_template(self, template: str) -> bool:
        """
        Validate template syntax.

        Args:
            template: Template string to validate

        Returns:
            True if template is valid, False otherwise
        """
        try:
            self.env.from_string(template)
            return True
        except Exception:
            return False
