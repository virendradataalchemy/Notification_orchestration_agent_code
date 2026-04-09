"""add template departments and seed department templates

Revision ID: 20260409162723
Revises: 20260409154340
Create Date: 2026-04-09 16:27:23
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260409162723"
down_revision = "20260409154340"
branch_labels = None
depends_on = None


template_departments = sa.table(
    "template_departments",
    sa.column("template_id", sa.Integer),
    sa.column("department", sa.String),
)


EXISTING_TEMPLATE_DEPARTMENTS = [
    {"template_id": 1, "department": "hr"},
    {"template_id": 2, "department": "hr"},
    {"template_id": 3, "department": "finance"},
    {"template_id": 4, "department": "hr"},
    {"template_id": 5, "department": "hr"},
    {"template_id": 6, "department": "general"},
    {"template_id": 6, "department": "hr"},
    {"template_id": 7, "department": "hr"},
    {"template_id": 8, "department": "general"},
    {"template_id": 8, "department": "hr"},
    {"template_id": 9, "department": "general"},
    {"template_id": 9, "department": "hr"},
    {"template_id": 10, "department": "hr"},
    {"template_id": 11, "department": "finance"},
    {"template_id": 12, "department": "general"},
    {"template_id": 12, "department": "hr"},
    {"template_id": 13, "department": "hr"},
    {"template_id": 14, "department": "hr"},
    {"template_id": 15, "department": "general"},
    {"template_id": 15, "department": "hr"},
    {"template_id": 16, "department": "hr"},
    {"template_id": 17, "department": "general"},
    {"template_id": 17, "department": "hr"},
    {"template_id": 18, "department": "hr"},
    {"template_id": 19, "department": "hr"},
    {"template_id": 20, "department": "general"},
]


SEEDED_NOTIFICATION_TYPES = (
    "onboarding_checklist",
    "policy_update",
    "document_reminder",
    "password_reset_notice",
    "system_maintenance_alert",
    "access_request_approved",
    "invoice_reminder",
    "reimbursement_status",
    "budget_approval_notice",
)


def upgrade() -> None:
    op.create_table(
        "template_departments",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("template_id", sa.Integer(), sa.ForeignKey("templates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("department", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("department IN ('general', 'hr', 'it', 'finance')", name="ck_template_departments_department"),
        sa.UniqueConstraint("template_id", "department", name="uq_template_departments_template_department"),
    )
    op.create_index("ix_template_departments_template_id", "template_departments", ["template_id"], unique=False)
    op.create_index("ix_template_departments_department", "template_departments", ["department"], unique=False)

    op.execute(
        """
        UPDATE templates
        SET name = CASE id
            WHEN 1 THEN 'Selection'
            WHEN 2 THEN 'Interview Reminder'
            WHEN 3 THEN 'Payslip'
            WHEN 4 THEN 'Leave Approval'
            WHEN 5 THEN 'Interview Confirmation'
            WHEN 6 THEN 'Welcome'
            WHEN 7 THEN 'Interview'
            WHEN 8 THEN 'Appointment Confirmation'
            WHEN 9 THEN 'Welcome'
            WHEN 10 THEN 'Interview'
            WHEN 11 THEN 'Payslip'
            WHEN 12 THEN 'Welcome'
            WHEN 13 THEN 'Interview Scheduling'
            WHEN 14 THEN 'Interview Confirmation'
            WHEN 15 THEN 'Welcome'
            WHEN 16 THEN 'Interview Scheduling'
            WHEN 17 THEN 'Welcome'
            WHEN 18 THEN 'Interview'
            WHEN 19 THEN 'Rejection'
            WHEN 20 THEN 'Demo'
            ELSE name
        END,
        department = CASE id
            WHEN 3 THEN 'finance'
            WHEN 11 THEN 'finance'
            WHEN 20 THEN 'general'
            ELSE 'hr'
        END,
        updated_at = NOW()
        WHERE id BETWEEN 1 AND 20
        """
    )

    op.bulk_insert(template_departments, EXISTING_TEMPLATE_DEPARTMENTS)

    op.execute(
        """
        WITH new_templates AS (
            SELECT
                (SELECT COALESCE(MAX(id), 0) FROM templates) + row_number() OVER () AS id,
                1 AS client_id,
                name,
                5 AS channel_id,
                'en' AS language,
                subject,
                content,
                1 AS version,
                TRUE AS is_active,
                notification_type,
                primary_department AS department,
                'public' AS visibility,
                NOW() AS created_at,
                NOW() AS updated_at
            FROM (
                VALUES
                    ('Onboarding Checklist', 'Onboarding Checklist', 'Hi {{name}}, please complete your onboarding checklist for {{company}} before your start date.', 'onboarding_checklist', 'hr'),
                    ('Policy Update', 'Policy Update', 'Hi {{name}}, a new policy update is available for review. Please read it before {{due_date}}.', 'policy_update', 'general'),
                    ('Document Reminder', 'Document Reminder', 'Hi {{name}}, please submit the pending document {{document_name}} by {{due_date}}.', 'document_reminder', 'general'),
                    ('Password Reset Notice', 'Password Reset Notice', 'Hi {{name}}, your password reset request has been received. Use the secure reset link sent by IT.', 'password_reset_notice', 'it'),
                    ('System Maintenance Alert', 'System Maintenance Alert', 'Hi {{name}}, scheduled system maintenance will run from {{start_time}} to {{end_time}}. Please save your work.', 'system_maintenance_alert', 'general'),
                    ('Access Request Approved', 'Access Request Approved', 'Hi {{name}}, your access request for {{system_name}} has been approved.', 'access_request_approved', 'it'),
                    ('Invoice Reminder', 'Invoice Reminder', 'Hi {{name}}, invoice {{invoice_number}} is pending. Please complete payment by {{due_date}}.', 'invoice_reminder', 'finance'),
                    ('Reimbursement Status', 'Reimbursement Status', 'Hi {{name}}, your reimbursement request {{request_id}} is now {{status}}.', 'reimbursement_status', 'finance'),
                    ('Budget Approval Notice', 'Budget Approval Notice', 'Hi {{name}}, the budget request for {{project_name}} has been approved.', 'budget_approval_notice', 'finance')
            ) AS seed(name, subject, content, notification_type, primary_department)
        )
        INSERT INTO templates (
            id, client_id, name, channel_id, language, subject, content, version,
            is_active, notification_type, department, visibility, created_at, updated_at
        )
        SELECT
            id, client_id, name, channel_id, language, subject, content, version,
            is_active, notification_type, department, visibility, created_at, updated_at
        FROM new_templates
        """
    )

    op.execute(
        """
        INSERT INTO template_departments (template_id, department)
        SELECT t.id, seed.department
        FROM templates t
        JOIN (
            VALUES
                ('onboarding_checklist', 'hr'),
                ('policy_update', 'general'),
                ('policy_update', 'hr'),
                ('policy_update', 'it'),
                ('policy_update', 'finance'),
                ('document_reminder', 'general'),
                ('document_reminder', 'hr'),
                ('password_reset_notice', 'it'),
                ('system_maintenance_alert', 'general'),
                ('system_maintenance_alert', 'it'),
                ('access_request_approved', 'it'),
                ('invoice_reminder', 'finance'),
                ('reimbursement_status', 'finance'),
                ('budget_approval_notice', 'finance')
        ) AS seed(notification_type, department)
        ON seed.notification_type = t.notification_type
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM templates
        WHERE notification_type IN (
            'onboarding_checklist',
            'policy_update',
            'document_reminder',
            'password_reset_notice',
            'system_maintenance_alert',
            'access_request_approved',
            'invoice_reminder',
            'reimbursement_status',
            'budget_approval_notice'
        )
        """
    )
    op.drop_index("ix_template_departments_department", table_name="template_departments")
    op.drop_index("ix_template_departments_template_id", table_name="template_departments")
    op.drop_table("template_departments")
    op.execute(
        """
        UPDATE templates
        SET department = NULL,
            updated_at = NOW()
        WHERE id BETWEEN 1 AND 20
        """
    )
