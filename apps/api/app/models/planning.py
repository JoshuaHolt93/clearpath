from __future__ import annotations

from datetime import date

from sqlalchemy import Boolean, Date, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.crypto import EncryptedText
from app.models.base import Base, TimestampMixin


class FixedExpenseItem(TimestampMixin, Base):
    __tablename__ = "fixed_expense_item"
    __table_args__ = (
        Index("ix_fixed_expense_user_category", "user_id", "category_label"),
        Index("ix_fixed_expense_user_frequency", "user_id", "frequency"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(EncryptedText(), nullable=False)
    amount: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    due_day: Mapped[int | None] = mapped_column(Integer)
    start_date: Mapped[date] = mapped_column(Date, default=date.today, nullable=False)
    frequency: Mapped[str] = mapped_column(String(20), default="monthly", nullable=False)
    days_of_week: Mapped[str | None] = mapped_column(String(30))
    second_date: Mapped[date | None] = mapped_column(Date)
    second_day_of_month: Mapped[int | None] = mapped_column(Integer)
    monthly_week_numbers: Mapped[str | None] = mapped_column(String(20))
    monthly_weekday: Mapped[int | None] = mapped_column(Integer)
    category_label: Mapped[str | None] = mapped_column(String(80))
    is_loan: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[str | None] = mapped_column(EncryptedText())


class Goal(TimestampMixin, Base):
    __tablename__ = "goal"
    __table_args__ = (
        Index("ix_goal_user_type", "user_id", "goal_type"),
        Index("ix_goal_user_fixed_expense", "user_id", "fixed_expense_item_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(EncryptedText(), nullable=False)
    goal_type: Mapped[str] = mapped_column(String(20), nullable=False)
    target_amount: Mapped[float] = mapped_column(Float, nullable=False)
    current_amount: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    monthly_contribution: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    target_date: Mapped[date | None] = mapped_column(Date)
    fixed_expense_item_id: Mapped[int | None] = mapped_column(ForeignKey("fixed_expense_item.id"))

    user: Mapped["User"] = relationship("User", back_populates="goals")
    fixed_expense_item: Mapped[FixedExpenseItem | None] = relationship("FixedExpenseItem")


class MonthlyPlan(TimestampMixin, Base):
    __tablename__ = "monthly_plan"
    __table_args__ = (
        Index("ix_monthly_plan_user_month", "user_id", "month"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False, index=True)
    month: Mapped[date] = mapped_column(Date, default=date.today, nullable=False)
    income: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    fixed_expenses: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    planned_savings: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    planned_debt_payment: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    safe_to_spend_target: Mapped[float] = mapped_column(Float, default=0, nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="monthly_plans")


class MonthlyBudgetSnapshot(TimestampMixin, Base):
    __tablename__ = "monthly_budget_snapshot"
    __table_args__ = (
        Index("ix_monthly_budget_snapshot_user_month", "user_id", "month"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False, index=True)
    month: Mapped[date] = mapped_column(Date, nullable=False)
    planned_income: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    planned_fixed_expenses: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    planned_variable_expenses: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    planned_savings: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    planned_debt_payment: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    planned_taxes: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    planned_retirement: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    planned_safe_to_spend: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    expected_cash_flow: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    budget_remaining: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    actual_income: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    actual_fixed_expenses: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    actual_variable_expenses: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    actual_total_expenses: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    net_cash_flow: Mapped[float] = mapped_column(Float, default=0, nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="monthly_budget_snapshots")


class MonthlyBudgetCategorySnapshot(TimestampMixin, Base):
    __tablename__ = "monthly_budget_category_snapshot"
    __table_args__ = (
        Index("ix_monthly_budget_category_snapshot_user_month", "user_id", "month"),
        Index("ix_monthly_budget_category_snapshot_category", "category_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False, index=True)
    month: Mapped[date] = mapped_column(Date, nullable=False)
    category_id: Mapped[int | None] = mapped_column(Integer)
    category_name: Mapped[str] = mapped_column(String(80), nullable=False)
    category_kind: Mapped[str] = mapped_column(String(20), default="expense", nullable=False)
    planned: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    actual: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    group_key: Mapped[str | None] = mapped_column(String(80))
    sort_order: Mapped[int | None] = mapped_column(Integer)
    transaction_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    transaction_ids_json: Mapped[str | None] = mapped_column(Text)

    user: Mapped["User"] = relationship("User", back_populates="monthly_budget_category_snapshots")


class Insight(TimestampMixin, Base):
    __tablename__ = "insight"
    __table_args__ = (
        Index("ix_insight_user_month_active", "user_id", "month", "is_active"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False, index=True)
    month: Mapped[date] = mapped_column(Date, default=date.today, nullable=False)
    title: Mapped[str] = mapped_column(EncryptedText(), nullable=False)
    body: Mapped[str] = mapped_column(EncryptedText(), nullable=False)
    level: Mapped[str] = mapped_column(String(20), default="info", nullable=False)
    insight_type: Mapped[str] = mapped_column(String(40), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="insights")


class ForecastItem(TimestampMixin, Base):
    __tablename__ = "forecast_item"
    __table_args__ = (
        Index("ix_forecast_item_user_date", "user_id", "item_date"),
        Index("ix_forecast_item_user_type_date", "user_id", "item_type", "item_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False, index=True)
    item_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    description: Mapped[str] = mapped_column(EncryptedText(), nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    item_type: Mapped[str] = mapped_column(String(20), default="expense", nullable=False)
    category_label: Mapped[str | None] = mapped_column(String(80))
    notes: Mapped[str | None] = mapped_column(EncryptedText())

    user: Mapped["User"] = relationship("User", back_populates="forecast_items")


class VariableExpenseItem(TimestampMixin, Base):
    __tablename__ = "variable_expense_item"
    __table_args__ = (
        Index("ix_variable_expense_user_category", "user_id", "category_label"),
        Index("ix_variable_expense_user_frequency", "user_id", "frequency"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(EncryptedText(), nullable=False)
    amount: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    frequency: Mapped[str] = mapped_column(String(20), default="monthly", nullable=False)
    use_specific_date: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    specific_date: Mapped[date | None] = mapped_column(Date)
    days_of_week: Mapped[str | None] = mapped_column(String(30))
    category_label: Mapped[str | None] = mapped_column(String(80))
    notes: Mapped[str | None] = mapped_column(EncryptedText())


class RecurringForecastTemplate(TimestampMixin, Base):
    __tablename__ = "recurring_forecast_template"
    __table_args__ = (
        Index("ix_recurring_forecast_user_type", "user_id", "item_type"),
        Index("ix_recurring_forecast_user_frequency", "user_id", "frequency"),
        Index("ix_recurring_forecast_user_type_start", "user_id", "item_type", "start_date"),
        Index("ix_recurring_forecast_user_income_replacement_start", "user_id", "income_replacement", "start_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(EncryptedText(), nullable=False)
    amount: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    item_type: Mapped[str] = mapped_column(String(20), default="expense", nullable=False)
    frequency: Mapped[str] = mapped_column(String(20), default="monthly", nullable=False)
    start_date: Mapped[date] = mapped_column(Date, default=date.today, nullable=False)
    second_date: Mapped[date | None] = mapped_column(Date)
    days_of_week: Mapped[str | None] = mapped_column(String(30))
    second_day_of_month: Mapped[int | None] = mapped_column(Integer)
    monthly_week_numbers: Mapped[str | None] = mapped_column(String(20))
    monthly_weekday: Mapped[int | None] = mapped_column(Integer)
    category_label: Mapped[str | None] = mapped_column(String(80))
    notes: Mapped[str | None] = mapped_column(EncryptedText())
    income_replacement: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    income_basis: Mapped[str | None] = mapped_column(String(20))
    income_type: Mapped[str | None] = mapped_column(String(20))
    paycheck_cadence: Mapped[str | None] = mapped_column(String(20))
    income_next_pay_date: Mapped[date | None] = mapped_column(Date)
    hourly_hours_per_week: Mapped[float] = mapped_column(Float, default=40, nullable=False)
    additional_income_amount: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    additional_income_frequency: Mapped[str] = mapped_column(String(20), default="annual", nullable=False)
    tax_state: Mapped[str | None] = mapped_column(String(2))
    tax_filing_status: Mapped[str | None] = mapped_column(String(30))
    include_payroll_taxes: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class CashProjectionRecurringIgnore(TimestampMixin, Base):
    __tablename__ = "cash_projection_recurring_ignore"
    __table_args__ = (
        Index("ix_cash_projection_recurring_ignore_user_key", "user_id", "detection_key", unique=True),
        Index("ix_cash_projection_recurring_ignore_user_amount", "user_id", "amount"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False, index=True)
    detection_key: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(EncryptedText(), nullable=False)
    amount: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    frequency: Mapped[str] = mapped_column(String(20), default="monthly", nullable=False)
    category_label: Mapped[str | None] = mapped_column(String(80))
    last_seen: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(EncryptedText())


class LoanPlan(TimestampMixin, Base):
    __tablename__ = "loan_plan"
    __table_args__ = (
        Index("ix_loan_plan_user_type", "user_id", "loan_type"),
        Index("ix_loan_plan_user_fixed_expense", "user_id", "fixed_expense_item_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False, index=True)
    fixed_expense_item_id: Mapped[int] = mapped_column(ForeignKey("fixed_expense_item.id"), nullable=False, unique=True)
    loan_type: Mapped[str] = mapped_column(String(30), default="loan", nullable=False)
    principal_balance: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    collateral_value: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    annual_interest_rate: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    term_months: Mapped[int] = mapped_column(Integer, default=360, nullable=False)
    term_unit_preference: Mapped[str] = mapped_column(String(12), default="months", nullable=False)
    regular_payment: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    extra_payment_one: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    extra_payment_two: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    selected_scenario: Mapped[str] = mapped_column(String(20), default="base", nullable=False)
    notes: Mapped[str | None] = mapped_column(EncryptedText())

    fixed_expense_item: Mapped[FixedExpenseItem] = relationship("FixedExpenseItem")


class AIUsageLog(TimestampMixin, Base):
    __tablename__ = "ai_usage_log"
    __table_args__ = (
        Index("ix_ai_usage_log_user_created", "user_id", "created_at"),
        Index("ix_ai_usage_log_user_feature_created", "user_id", "feature", "created_at"),
        Index("ix_ai_usage_log_status_created", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False, index=True)
    feature: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    estimated_cost_cents: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    provider_request_id: Mapped[str | None] = mapped_column(String(160))
    limit_reason: Mapped[str | None] = mapped_column(String(80))

    user: Mapped["User"] = relationship("User", back_populates="ai_usage_logs")
