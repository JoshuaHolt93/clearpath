"""phase 1 auth and household foundation

Revision ID: 0001_phase1_auth_households
Revises:
Create Date: 2026-07-01
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0001_phase1_auth_households"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=True),
        sa.Column("household_name", sa.Text(), nullable=True),
        sa.Column("is_admin", sa.Boolean(), nullable=False),
        sa.Column("ethics_acknowledged_at", sa.DateTime(), nullable=True),
        sa.Column("ethics_policy_version", sa.String(length=40), nullable=True),
        sa.Column("mfa_secret", sa.Text(), nullable=True),
        sa.Column("mfa_enabled", sa.Boolean(), nullable=False),
        sa.Column("mfa_confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("mfa_recovery_codes", sa.Text(), nullable=True),
        sa.Column("mfa_push_enabled", sa.Boolean(), nullable=False),
        sa.Column("mfa_preferred_method", sa.String(length=20), nullable=False),
        sa.Column("stripe_customer_id", sa.String(length=120), nullable=True),
        sa.Column("stripe_subscription_id", sa.String(length=120), nullable=True),
        sa.Column("billing_status", sa.String(length=40), nullable=False),
        sa.Column("billing_price_id", sa.String(length=120), nullable=True),
        sa.Column("selected_plan", sa.String(length=40), nullable=False),
        sa.Column("stripe_current_period_end", sa.DateTime(), nullable=True),
        sa.Column("ai_provider", sa.String(length=40), nullable=False),
        sa.Column("ai_model", sa.String(length=120), nullable=False),
        sa.Column("ai_guidance_snapshot", sa.Text(), nullable=True),
        sa.Column("ai_guidance_generated_at", sa.DateTime(), nullable=True),
        sa.Column("cash_projection_calendar_token", sa.Text(), nullable=True),
        sa.Column("cash_projection_calendar_token_hash", sa.String(length=64), nullable=True),
        sa.Column("cash_projection_calendar_enabled", sa.Boolean(), nullable=False),
        sa.Column("cash_projection_calendar_generated_at", sa.DateTime(), nullable=True),
        sa.Column("cash_projection_default_horizon", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_user_email", "user", ["email"], unique=True)
    op.create_index("ix_user_stripe_customer_id", "user", ["stripe_customer_id"])
    op.create_index("ix_user_stripe_subscription_id", "user", ["stripe_subscription_id"])
    op.create_index("ix_user_billing_status", "user", ["billing_status"])
    op.create_index("ix_user_selected_plan", "user", ["selected_plan"])
    op.create_index("ix_user_cash_projection_calendar_token_hash", "user", ["cash_projection_calendar_token_hash"], unique=True)

    op.create_table(
        "household_member",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("invited_by_user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=True),
        sa.Column("mfa_secret", sa.Text(), nullable=True),
        sa.Column("mfa_enabled", sa.Boolean(), nullable=False),
        sa.Column("mfa_confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("mfa_recovery_codes", sa.Text(), nullable=True),
        sa.Column("mfa_push_enabled", sa.Boolean(), nullable=False),
        sa.Column("mfa_preferred_method", sa.String(length=20), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("accepted_at", sa.DateTime(), nullable=True),
        sa.Column("last_login_at", sa.DateTime(), nullable=True),
        sa.Column("policy_version", sa.String(length=40), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_household_member_owner_user_id", "household_member", ["owner_user_id"])
    op.create_index("ix_household_member_invited_by_user_id", "household_member", ["invited_by_user_id"])
    op.create_index("ix_household_member_email", "household_member", ["email"], unique=True)
    op.create_index("ix_household_member_status", "household_member", ["status"])
    op.create_index("ix_household_member_owner_status", "household_member", ["owner_user_id", "status"])
    op.create_index("ix_household_member_owner_role", "household_member", ["owner_user_id", "role"])

    op.create_table(
        "household_invite",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("invited_by_user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("accepted_member_id", sa.Integer(), sa.ForeignKey("household_member.id"), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("accepted_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_household_invite_owner_user_id", "household_invite", ["owner_user_id"])
    op.create_index("ix_household_invite_invited_by_user_id", "household_invite", ["invited_by_user_id"])
    op.create_index("ix_household_invite_accepted_member_id", "household_invite", ["accepted_member_id"])
    op.create_index("ix_household_invite_email", "household_invite", ["email"])
    op.create_index("ix_household_invite_token_hash", "household_invite", ["token_hash"], unique=True)
    op.create_index("ix_household_invite_status", "household_invite", ["status"])
    op.create_index("ix_household_invite_owner_status", "household_invite", ["owner_user_id", "status"])
    op.create_index("ix_household_invite_email_status", "household_invite", ["email", "status"])

    op.create_table(
        "login_attempt",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(length=255), nullable=False),
        sa.Column("attempted_at", sa.DateTime(), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_login_attempt_key_attempted_at", "login_attempt", ["key", "attempted_at"])

    op.create_table(
        "onboarding_profile",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False, unique=True),
        sa.Column("income_amount", sa.Float(), nullable=False),
        sa.Column("income_basis", sa.String(length=20), nullable=False),
        sa.Column("income_type", sa.String(length=20), nullable=False),
        sa.Column("income_frequency", sa.String(length=20), nullable=False),
        sa.Column("paycheck_cadence", sa.String(length=20), nullable=False),
        sa.Column("next_pay_date", sa.Date(), nullable=True),
        sa.Column("paycheck_second_date", sa.Date(), nullable=True),
        sa.Column("paycheck_days_of_week", sa.String(length=30), nullable=True),
        sa.Column("paycheck_second_day_of_month", sa.Integer(), nullable=True),
        sa.Column("paycheck_monthly_week_numbers", sa.String(length=20), nullable=True),
        sa.Column("paycheck_monthly_weekday", sa.Integer(), nullable=True),
        sa.Column("hourly_hours_per_week", sa.Float(), nullable=False),
        sa.Column("monthly_income", sa.Float(), nullable=False),
        sa.Column("fixed_expenses", sa.Float(), nullable=False),
        sa.Column("variable_expenses", sa.Float(), nullable=False),
        sa.Column("additional_income_amount", sa.Float(), nullable=False),
        sa.Column("additional_income_frequency", sa.String(length=20), nullable=False),
        sa.Column("planned_savings_contribution", sa.Float(), nullable=False),
        sa.Column("planned_debt_payment", sa.Float(), nullable=False),
        sa.Column("target_investment_contribution", sa.Float(), nullable=False),
        sa.Column("tax_state", sa.String(length=2), nullable=True),
        sa.Column("tax_filing_status", sa.String(length=30), nullable=False),
        sa.Column("tax_gross_annual_income", sa.Float(), nullable=False),
        sa.Column("tax_state_effective_rate", sa.Float(), nullable=False),
        sa.Column("include_payroll_taxes", sa.Boolean(), nullable=False),
        sa.Column("retirement_enabled", sa.Boolean(), nullable=False),
        sa.Column("retirement_has_employer_plan", sa.Boolean(), nullable=False),
        sa.Column("retirement_employer_withheld", sa.Boolean(), nullable=False),
        sa.Column("retirement_has_personal_plan", sa.Boolean(), nullable=False),
        sa.Column("retirement_monthly_contribution", sa.Float(), nullable=False),
        sa.Column("retirement_personal_monthly_contribution", sa.Float(), nullable=False),
        sa.Column("retirement_lifestyle_notes", sa.Text(), nullable=True),
        sa.Column("retirement_location_notes", sa.Text(), nullable=True),
        sa.Column("retirement_healthcare_notes", sa.Text(), nullable=True),
        sa.Column("retirement_income_notes", sa.Text(), nullable=True),
        sa.Column("retirement_debt_notes", sa.Text(), nullable=True),
        sa.Column("retirement_family_notes", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("onboarding_profile")
    op.drop_index("ix_login_attempt_key_attempted_at", table_name="login_attempt")
    op.drop_table("login_attempt")
    op.drop_index("ix_household_invite_email_status", table_name="household_invite")
    op.drop_index("ix_household_invite_owner_status", table_name="household_invite")
    op.drop_index("ix_household_invite_status", table_name="household_invite")
    op.drop_index("ix_household_invite_token_hash", table_name="household_invite")
    op.drop_index("ix_household_invite_email", table_name="household_invite")
    op.drop_index("ix_household_invite_accepted_member_id", table_name="household_invite")
    op.drop_index("ix_household_invite_invited_by_user_id", table_name="household_invite")
    op.drop_index("ix_household_invite_owner_user_id", table_name="household_invite")
    op.drop_table("household_invite")
    op.drop_index("ix_household_member_owner_role", table_name="household_member")
    op.drop_index("ix_household_member_owner_status", table_name="household_member")
    op.drop_index("ix_household_member_status", table_name="household_member")
    op.drop_index("ix_household_member_email", table_name="household_member")
    op.drop_index("ix_household_member_invited_by_user_id", table_name="household_member")
    op.drop_index("ix_household_member_owner_user_id", table_name="household_member")
    op.drop_table("household_member")
    op.drop_index("ix_user_cash_projection_calendar_token_hash", table_name="user")
    op.drop_index("ix_user_selected_plan", table_name="user")
    op.drop_index("ix_user_billing_status", table_name="user")
    op.drop_index("ix_user_stripe_subscription_id", table_name="user")
    op.drop_index("ix_user_stripe_customer_id", table_name="user")
    op.drop_index("ix_user_email", table_name="user")
    op.drop_table("user")
