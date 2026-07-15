from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.goals import GoalResponse
from app.schemas.plaid import AccountResponse
from app.schemas.planner import PlannerDashboardFocusResponse
from app.schemas.planning import CategorySpendRowResponse, PlanRowResponse
from app.schemas.transactions import TransactionResponse


class DashboardQuery(BaseModel):
    pass


class DashboardMetricsResponse(BaseModel):
    month_income: float
    fixed_expenses: float
    variable_spend: float
    safe_to_spend: float
    safe_to_spend_target: float
    net_cash_flow: float
    on_track_status: str
    expected_variable_spend: float

    model_config = ConfigDict(from_attributes=True)


class NetWorthResponse(BaseModel):
    assets: float
    liabilities: float
    loan_balances: float
    collateral_assets: float
    collateral_value: float
    secured_loan_equity: float
    secured_negative_equity: float
    secured_loan_balances: float
    unsecured_loan_balances: float
    debt_goals: float
    net_worth: float


class DashboardFeatureStateResponse(BaseModel):
    feature: str
    locked: bool
    hidden: bool = False
    required_plan: str | None = None


class DashboardInsightResponse(BaseModel):
    title: str
    body: str
    level: str
    type: str
    disclaimer: str


class DashboardResponse(BaseModel):
    metrics: DashboardMetricsResponse
    net_worth: NetWorthResponse
    category_totals: list[CategorySpendRowResponse] = Field(default_factory=list)
    goals: list[GoalResponse] = Field(default_factory=list)
    recent_transactions: list[TransactionResponse] = Field(default_factory=list)
    accounts: list[AccountResponse] = Field(default_factory=list)
    month_name: str
    today: date
    elapsed_days: int
    total_days: int
    days_left: int
    pace_pct: float
    spend_pct: float
    feature_states: list[DashboardFeatureStateResponse] = Field(default_factory=list)
    plan_rows: list[PlanRowResponse] = Field(default_factory=list)
    budget_remaining: float
    expected_cash_flow: float
    insights: list[DashboardInsightResponse] = Field(default_factory=list)
    dashboard_focus: PlannerDashboardFocusResponse | None = None


class AnalyticsQuery(BaseModel):
    range: str = "month"
    end_month: str = ""
    history_range: str = "quarter"
    history_end_month: str = ""


class MonthlyBudgetSnapshotResponse(BaseModel):
    month: date
    planned_income: float
    planned_fixed_expenses: float
    planned_variable_expenses: float
    planned_savings: float
    planned_debt_payment: float
    planned_taxes: float
    planned_retirement: float
    planned_safe_to_spend: float
    expected_cash_flow: float
    budget_remaining: float
    actual_income: float
    actual_fixed_expenses: float
    actual_variable_expenses: float
    actual_total_expenses: float
    net_cash_flow: float

    model_config = ConfigDict(from_attributes=True)


class AnalyticsSubscriptionResponse(BaseModel):
    id: int
    name: str
    service_category: str
    monthly_amount: float
    annual_amount: float
    cycle: str
    confidence: float
    status: str
    replaceable: bool
    next_charge_date: date | None = None

    model_config = ConfigDict(from_attributes=True)


class AnalyticsSubscriptionCategoryResponse(BaseModel):
    category: str
    amount: float
    percent: int


class AnalyticsSubscriptionOpportunityResponse(BaseModel):
    subscription: AnalyticsSubscriptionResponse
    reason: str


class AnalyticsSubscriptionsResponse(BaseModel):
    subscriptions: list[AnalyticsSubscriptionResponse] = Field(default_factory=list)
    active_count: int
    review_count: int
    action_count: int
    manage_link_count: int
    monthly_total: float
    annual_total: float
    potential_savings: float
    spending_share: int
    category_breakdown: list[AnalyticsSubscriptionCategoryResponse] = Field(default_factory=list)
    opportunities: list[AnalyticsSubscriptionOpportunityResponse] = Field(default_factory=list)
    upcoming: list[AnalyticsSubscriptionResponse] = Field(default_factory=list)


class AnalyticsSummaryResponse(BaseModel):
    range_key: str
    range_label: str
    months: list[date]
    snapshots: list[MonthlyBudgetSnapshotResponse]
    start_date: date
    end_date: date
    total_income: float
    total_spending: float
    total_expected_cash_flow: float
    total_net_cash_flow: float
    average_income: float
    average_spending: float
    average_net_cash_flow: float
    max_income: float
    max_spending: float
    max_cash_flow: float
    category_rows: list[CategorySpendRowResponse]
    subscriptions: AnalyticsSubscriptionsResponse


class AnalyticsResponse(BaseModel):
    summary: AnalyticsSummaryResponse
    budget_history_summary: AnalyticsSummaryResponse
    debt_to_income_ratio: float
    range_options: dict[str, str]
    selected_range: str
    end_month: date
    selected_history_range: str
    history_end_month: date
    subscription_analytics_enabled: bool
    subscription_analytics_plan_label: str
    ai_coach_enabled: bool
    ai_coach_hidden: bool
