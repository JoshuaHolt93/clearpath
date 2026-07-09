"""phase 3 planning: budgets, forecasts, goals, loans, insights

Revision ID: 0005_phase3_planning
Revises: 0004_phase2c_subscriptions
Create Date: 2026-07-09
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0005_phase3_planning"
down_revision = "0004_phase2c_subscriptions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fixed_expense_item",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("due_day", sa.Integer(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("frequency", sa.String(length=20), nullable=False),
        sa.Column("days_of_week", sa.String(length=30), nullable=True),
        sa.Column("second_date", sa.Date(), nullable=True),
        sa.Column("second_day_of_month", sa.Integer(), nullable=True),
        sa.Column("monthly_week_numbers", sa.String(length=20), nullable=True),
        sa.Column("monthly_weekday", sa.Integer(), nullable=True),
        sa.Column("category_label", sa.String(length=80), nullable=True),
        sa.Column("is_loan", sa.Boolean(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_fixed_expense_item_user_id", "fixed_expense_item", ["user_id"])
    op.create_index("ix_fixed_expense_user_category", "fixed_expense_item", ["user_id", "category_label"])
    op.create_index("ix_fixed_expense_user_frequency", "fixed_expense_item", ["user_id", "frequency"])

    op.create_table(
        "goal",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("goal_type", sa.String(length=20), nullable=False),
        sa.Column("target_amount", sa.Float(), nullable=False),
        sa.Column("current_amount", sa.Float(), nullable=False),
        sa.Column("monthly_contribution", sa.Float(), nullable=False),
        sa.Column("target_date", sa.Date(), nullable=True),
        sa.Column("fixed_expense_item_id", sa.Integer(), sa.ForeignKey("fixed_expense_item.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_goal_user_id", "goal", ["user_id"])
    op.create_index("ix_goal_user_type", "goal", ["user_id", "goal_type"])
    op.create_index("ix_goal_user_fixed_expense", "goal", ["user_id", "fixed_expense_item_id"])

    op.create_table(
        "monthly_plan",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("month", sa.Date(), nullable=False),
        sa.Column("income", sa.Float(), nullable=False),
        sa.Column("fixed_expenses", sa.Float(), nullable=False),
        sa.Column("planned_savings", sa.Float(), nullable=False),
        sa.Column("planned_debt_payment", sa.Float(), nullable=False),
        sa.Column("safe_to_spend_target", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_monthly_plan_user_id", "monthly_plan", ["user_id"])
    op.create_index("ix_monthly_plan_user_month", "monthly_plan", ["user_id", "month"])

    op.create_table(
        "monthly_budget_snapshot",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("month", sa.Date(), nullable=False),
        sa.Column("planned_income", sa.Float(), nullable=False),
        sa.Column("planned_fixed_expenses", sa.Float(), nullable=False),
        sa.Column("planned_variable_expenses", sa.Float(), nullable=False),
        sa.Column("planned_savings", sa.Float(), nullable=False),
        sa.Column("planned_debt_payment", sa.Float(), nullable=False),
        sa.Column("planned_taxes", sa.Float(), nullable=False),
        sa.Column("planned_retirement", sa.Float(), nullable=False),
        sa.Column("planned_safe_to_spend", sa.Float(), nullable=False),
        sa.Column("expected_cash_flow", sa.Float(), nullable=False),
        sa.Column("budget_remaining", sa.Float(), nullable=False),
        sa.Column("actual_income", sa.Float(), nullable=False),
        sa.Column("actual_fixed_expenses", sa.Float(), nullable=False),
        sa.Column("actual_variable_expenses", sa.Float(), nullable=False),
        sa.Column("actual_total_expenses", sa.Float(), nullable=False),
        sa.Column("net_cash_flow", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_monthly_budget_snapshot_user_id", "monthly_budget_snapshot", ["user_id"])
    op.create_index("ix_monthly_budget_snapshot_user_month", "monthly_budget_snapshot", ["user_id", "month"])

    op.create_table(
        "monthly_budget_category_snapshot",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("month", sa.Date(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=True),
        sa.Column("category_name", sa.String(length=80), nullable=False),
        sa.Column("category_kind", sa.String(length=20), nullable=False),
        sa.Column("planned", sa.Float(), nullable=False),
        sa.Column("actual", sa.Float(), nullable=False),
        sa.Column("group_key", sa.String(length=80), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=True),
        sa.Column("transaction_count", sa.Integer(), nullable=False),
        sa.Column("transaction_ids_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_monthly_budget_category_snapshot_user_id", "monthly_budget_category_snapshot", ["user_id"])
    op.create_index("ix_monthly_budget_category_snapshot_user_month", "monthly_budget_category_snapshot", ["user_id", "month"])
    op.create_index("ix_monthly_budget_category_snapshot_category", "monthly_budget_category_snapshot", ["category_id"])

    op.create_table(
        "insight",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("month", sa.Date(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("level", sa.String(length=20), nullable=False),
        sa.Column("insight_type", sa.String(length=40), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_insight_user_id", "insight", ["user_id"])
    op.create_index("ix_insight_user_month_active", "insight", ["user_id", "month", "is_active"])

    op.create_table(
        "forecast_item",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("item_date", sa.Date(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("item_type", sa.String(length=20), nullable=False),
        sa.Column("category_label", sa.String(length=80), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_forecast_item_user_id", "forecast_item", ["user_id"])
    op.create_index("ix_forecast_item_item_date", "forecast_item", ["item_date"])
    op.create_index("ix_forecast_item_user_date", "forecast_item", ["user_id", "item_date"])
    op.create_index("ix_forecast_item_user_type_date", "forecast_item", ["user_id", "item_type", "item_date"])

    op.create_table(
        "variable_expense_item",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("frequency", sa.String(length=20), nullable=False),
        sa.Column("use_specific_date", sa.Boolean(), nullable=False),
        sa.Column("specific_date", sa.Date(), nullable=True),
        sa.Column("days_of_week", sa.String(length=30), nullable=True),
        sa.Column("category_label", sa.String(length=80), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_variable_expense_item_user_id", "variable_expense_item", ["user_id"])
    op.create_index("ix_variable_expense_user_category", "variable_expense_item", ["user_id", "category_label"])
    op.create_index("ix_variable_expense_user_frequency", "variable_expense_item", ["user_id", "frequency"])

    op.create_table(
        "recurring_forecast_template",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("item_type", sa.String(length=20), nullable=False),
        sa.Column("frequency", sa.String(length=20), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("second_date", sa.Date(), nullable=True),
        sa.Column("days_of_week", sa.String(length=30), nullable=True),
        sa.Column("second_day_of_month", sa.Integer(), nullable=True),
        sa.Column("monthly_week_numbers", sa.String(length=20), nullable=True),
        sa.Column("monthly_weekday", sa.Integer(), nullable=True),
        sa.Column("category_label", sa.String(length=80), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("income_replacement", sa.Boolean(), nullable=False),
        sa.Column("income_basis", sa.String(length=20), nullable=True),
        sa.Column("income_type", sa.String(length=20), nullable=True),
        sa.Column("paycheck_cadence", sa.String(length=20), nullable=True),
        sa.Column("income_next_pay_date", sa.Date(), nullable=True),
        sa.Column("hourly_hours_per_week", sa.Float(), nullable=False),
        sa.Column("additional_income_amount", sa.Float(), nullable=False),
        sa.Column("additional_income_frequency", sa.String(length=20), nullable=False),
        sa.Column("tax_state", sa.String(length=2), nullable=True),
        sa.Column("tax_filing_status", sa.String(length=30), nullable=True),
        sa.Column("include_payroll_taxes", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_recurring_forecast_template_user_id", "recurring_forecast_template", ["user_id"])
    op.create_index("ix_recurring_forecast_user_type", "recurring_forecast_template", ["user_id", "item_type"])
    op.create_index("ix_recurring_forecast_user_frequency", "recurring_forecast_template", ["user_id", "frequency"])
    op.create_index("ix_recurring_forecast_user_type_start", "recurring_forecast_template", ["user_id", "item_type", "start_date"])
    op.create_index(
        "ix_recurring_forecast_user_income_replacement_start",
        "recurring_forecast_template",
        ["user_id", "income_replacement", "start_date"],
    )

    op.create_table(
        "cash_projection_recurring_ignore",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("detection_key", sa.String(length=64), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("frequency", sa.String(length=20), nullable=False),
        sa.Column("category_label", sa.String(length=80), nullable=True),
        sa.Column("last_seen", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_cash_projection_recurring_ignore_user_id", "cash_projection_recurring_ignore", ["user_id"])
    op.create_index(
        "ix_cash_projection_recurring_ignore_user_key",
        "cash_projection_recurring_ignore",
        ["user_id", "detection_key"],
        unique=True,
    )
    op.create_index(
        "ix_cash_projection_recurring_ignore_user_amount",
        "cash_projection_recurring_ignore",
        ["user_id", "amount"],
    )

    op.create_table(
        "loan_plan",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("fixed_expense_item_id", sa.Integer(), sa.ForeignKey("fixed_expense_item.id"), nullable=False, unique=True),
        sa.Column("loan_type", sa.String(length=30), nullable=False),
        sa.Column("principal_balance", sa.Float(), nullable=False),
        sa.Column("collateral_value", sa.Float(), nullable=False),
        sa.Column("annual_interest_rate", sa.Float(), nullable=False),
        sa.Column("term_months", sa.Integer(), nullable=False),
        sa.Column("term_unit_preference", sa.String(length=12), nullable=False),
        sa.Column("regular_payment", sa.Float(), nullable=False),
        sa.Column("extra_payment_one", sa.Float(), nullable=False),
        sa.Column("extra_payment_two", sa.Float(), nullable=False),
        sa.Column("selected_scenario", sa.String(length=20), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_loan_plan_user_id", "loan_plan", ["user_id"])
    op.create_index("ix_loan_plan_user_type", "loan_plan", ["user_id", "loan_type"])
    op.create_index("ix_loan_plan_user_fixed_expense", "loan_plan", ["user_id", "fixed_expense_item_id"])

    op.create_table(
        "ai_usage_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("feature", sa.String(length=80), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False),
        sa.Column("completion_tokens", sa.Integer(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("estimated_cost_cents", sa.Float(), nullable=False),
        sa.Column("provider_request_id", sa.String(length=160), nullable=True),
        sa.Column("limit_reason", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_ai_usage_log_user_id", "ai_usage_log", ["user_id"])
    op.create_index("ix_ai_usage_log_feature", "ai_usage_log", ["feature"])
    op.create_index("ix_ai_usage_log_provider", "ai_usage_log", ["provider"])
    op.create_index("ix_ai_usage_log_status", "ai_usage_log", ["status"])
    op.create_index("ix_ai_usage_log_user_created", "ai_usage_log", ["user_id", "created_at"])
    op.create_index("ix_ai_usage_log_user_feature_created", "ai_usage_log", ["user_id", "feature", "created_at"])
    op.create_index("ix_ai_usage_log_status_created", "ai_usage_log", ["status", "created_at"])


def downgrade() -> None:
    for table in [
        "ai_usage_log",
        "loan_plan",
        "cash_projection_recurring_ignore",
        "recurring_forecast_template",
        "variable_expense_item",
        "forecast_item",
        "insight",
        "monthly_budget_category_snapshot",
        "monthly_budget_snapshot",
        "monthly_plan",
        "goal",
        "fixed_expense_item",
    ]:
        op.drop_table(table)
