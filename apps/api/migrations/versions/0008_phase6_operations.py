"""phase 6 operational tables

Revision ID: 0008_phase6_operations
Revises: 0007_tax_percentage_fields
Create Date: 2026-07-18

Ports the Flask operational models at 92ccdbc: privileged-access audit log,
compliance control evaluations, security incidents (8c9f0bf), Stripe webhook
idempotency ledger, and product feedback.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0008_phase6_operations"
down_revision = "0007_tax_percentage_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "privileged_access_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("action", sa.String(length=120), nullable=False),
        sa.Column("resource", sa.String(length=255), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_privileged_access_log_user_id", "privileged_access_log", ["user_id"])
    op.create_index("ix_privileged_access_log_success", "privileged_access_log", ["success"])
    op.create_index("ix_privileged_access_log_user_created", "privileged_access_log", ["user_id", "created_at"])
    op.create_index("ix_privileged_access_log_success_created", "privileged_access_log", ["success", "created_at"])

    op.create_table(
        "control_evaluation",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("control_id", sa.String(length=80), nullable=False),
        sa.Column("control_name", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("evidence", sa.Text(), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_control_evaluation_control_id", "control_evaluation", ["control_id"])
    op.create_index("ix_control_evaluation_status", "control_evaluation", ["status"])
    op.create_index("ix_control_evaluation_evaluated_at", "control_evaluation", ["evaluated_at"])
    op.create_index("ix_control_evaluation_control_evaluated", "control_evaluation", ["control_id", "evaluated_at"])
    op.create_index("ix_control_evaluation_status_evaluated", "control_evaluation", ["status", "evaluated_at"])

    op.create_table(
        "security_incident",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("incident_type", sa.String(length=80), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("source", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("detected_at", sa.DateTime(), nullable=False),
        sa.Column("report_deadline_at", sa.DateTime(), nullable=False),
        sa.Column("reported_at", sa.DateTime(), nullable=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("audit_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_security_incident_incident_type", "security_incident", ["incident_type"])
    op.create_index("ix_security_incident_severity", "security_incident", ["severity"])
    op.create_index("ix_security_incident_status", "security_incident", ["status"])
    op.create_index("ix_security_incident_detected_at", "security_incident", ["detected_at"])
    op.create_index("ix_security_incident_report_deadline_at", "security_incident", ["report_deadline_at"])
    op.create_index("ix_security_incident_user_id", "security_incident", ["user_id"])
    op.create_index("ix_security_incident_status_deadline", "security_incident", ["status", "report_deadline_at"])
    op.create_index("ix_security_incident_type_detected", "security_incident", ["incident_type", "detected_at"])
    op.create_index("ix_security_incident_user_detected", "security_incident", ["user_id", "detected_at"])

    op.create_table(
        "stripe_webhook_event",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("stripe_event_id", sa.String(length=160), nullable=False),
        sa.Column("event_type", sa.String(length=120), nullable=False),
        sa.Column("event_created", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("processed_at", sa.DateTime(), nullable=True),
        sa.Column("raw_event_json", sa.Text(), nullable=True),
        sa.Column("payload_hash", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_stripe_webhook_event_stripe_event_id", "stripe_webhook_event", ["stripe_event_id"], unique=True)
    op.create_index("ix_stripe_webhook_event_event_type", "stripe_webhook_event", ["event_type"])
    op.create_index("ix_stripe_webhook_event_event_created", "stripe_webhook_event", ["event_created"])
    op.create_index("ix_stripe_webhook_event_status", "stripe_webhook_event", ["status"])
    op.create_index("ix_stripe_webhook_event_payload_hash", "stripe_webhook_event", ["payload_hash"])
    op.create_index("ix_stripe_webhook_event_status_created", "stripe_webhook_event", ["status", "event_created"])
    op.create_index("ix_stripe_webhook_event_type_created", "stripe_webhook_event", ["event_type", "event_created"])

    op.create_table(
        "product_feedback",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("feedback_type", sa.String(length=40), nullable=False),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("reason", sa.String(length=80), nullable=False),
        sa.Column("feature_expectation_reason", sa.String(length=80), nullable=True),
        sa.Column("broken_features", sa.Text(), nullable=True),
        sa.Column("notify_when_addressed", sa.Boolean(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("selected_plan", sa.String(length=40), nullable=True),
        sa.Column("billing_status", sa.String(length=40), nullable=True),
        sa.Column("stripe_customer_id", sa.String(length=120), nullable=True),
        sa.Column("stripe_subscription_id", sa.String(length=120), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_product_feedback_user_id", "product_feedback", ["user_id"])
    op.create_index("ix_product_feedback_feedback_type", "product_feedback", ["feedback_type"])
    op.create_index("ix_product_feedback_source", "product_feedback", ["source"])
    op.create_index("ix_product_feedback_reason", "product_feedback", ["reason"])
    op.create_index("ix_product_feedback_status", "product_feedback", ["status"])
    op.create_index("ix_product_feedback_user_type_created", "product_feedback", ["user_id", "feedback_type", "created_at"])
    op.create_index("ix_product_feedback_reason_created", "product_feedback", ["reason", "created_at"])


def downgrade() -> None:
    op.drop_table("product_feedback")
    op.drop_table("stripe_webhook_event")
    op.drop_table("security_incident")
    op.drop_table("control_evaluation")
    op.drop_table("privileged_access_log")
