"""Static mapping helpers for department-level dashboards.

This file keeps template-to-department and role inbox mapping outside the database.
Update these dictionaries as tenant-specific templates are finalized.
"""

from __future__ import annotations

from typing import Any

DEPARTMENT_LABELS: dict[str, str] = {
    "hr": "HR",
    "it": "IT",
}

# Global template-id mapping across tenants.
DEFAULT_TEMPLATE_DEPARTMENT_MAP: dict[int, str] = {
    # 101: "hr",
    # 102: "it",
    # 103: "finance",
}

# Tenant-specific override mapping.
# Key is client_id, value is {template_id: department}.
CLIENT_TEMPLATE_DEPARTMENT_MAP: dict[int, dict[int, str]] = {
    # 1: {201: "hr", 202: "it", 203: "finance"},
}

# Tenant-specific role inboxes shown on the dashboard cards.
CLIENT_DEPARTMENT_ROLE_EMAILS: dict[int, dict[str, list[str]]] = {
    1: {
        "hr": ["prachikushwaha.dataalchemy@gmail.com", "+919893155055"],
        "it": ["prateekgaur.prateek.1609@gmail.com", "+918290942415"],
    },
}

DEPARTMENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "hr": (
        "hr",
        "human resource",
        "candidate",
        "onboarding",
        "joiner",
        "new joinee",
    ),
    "it": (
        "it",
        "resource setup",
        "laptop",
        "access",
        "credentials",
        "it team",
    ),
    "finance": (
        "finance",
        "attendance",
        "payroll",
        "payslip",
        "salary",
        "paycheck",
    ),
}


def resolve_template_department(
    client_id: int,
    template_id: Any,
    template_name: str | None,
    notification_type: str | None,
    template_category: str | None = None,
) -> str | None:
    """Resolve a department from template mapping first, then keyword fallback."""
    normalized_category = (template_category or "").strip().lower().replace("-", "_").replace(" ", "_")
    category_aliases = {
        "hr": "hr",
        "human_resources": "hr",
        "human_resource": "hr",
        "it": "it",
        "it_dept": "it",
        "finance": "finance",
        "fin": "finance",
    }
    if normalized_category in category_aliases:
        return category_aliases[normalized_category]

    template_pk: int | None
    try:
        template_pk = int(template_id) if template_id is not None else None
    except (ValueError, TypeError):
        template_pk = None

    client_map = CLIENT_TEMPLATE_DEPARTMENT_MAP.get(client_id, {})
    if template_pk is not None and template_pk in client_map:
        return client_map[template_pk]

    if template_pk is not None and template_pk in DEFAULT_TEMPLATE_DEPARTMENT_MAP:
        return DEFAULT_TEMPLATE_DEPARTMENT_MAP[template_pk]

    searchable = f"{template_name or ''} {notification_type or ''}".strip().lower()
    if not searchable:
        return None

    for department, keywords in DEPARTMENT_KEYWORDS.items():
        if any(keyword in searchable for keyword in keywords):
            return department
    return None


def get_department_role_emails(client_id: int) -> dict[str, list[str]]:
    """Return configured role inboxes for a tenant (static fallback)."""
    configured = CLIENT_DEPARTMENT_ROLE_EMAILS.get(client_id, {})
    return {
        "hr": configured.get("hr", []),
        "it": configured.get("it", []),
    }


async def fetch_department_role_emails(client_id: int) -> dict[str, list[str]]:
    """Fetch role emails from the users table in DB, keyed by role."""
    from src.core.supabase import supabase_client
    try:
        rows = await supabase_client.select(
            "users",
            "email,role",
            filters={"client_id": f"eq.{client_id}", "is_active": "eq.true"},
        )
    except Exception:
        return get_department_role_emails(client_id)

    result: dict[str, list[str]] = {"hr": [], "it": []}
    for row in rows:
        role = (row.get("role") or "").strip().lower()
        email = (row.get("email") or "").strip()
        if role in result and email:
            result[role].append(email)
    return result
