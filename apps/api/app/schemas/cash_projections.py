from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class CashProjectionEventResponse(BaseModel):
    date: date
    description: str
    amount: float
    item_type: str
    source: str
    category_label: str | None = None
    notes: str | None = None
    source_id: int | str | None = None
    signed_amount: float | None = None
    account_name: str | None = None
    pending: bool = False


class CashProjectionBalanceAccountResponse(BaseModel):
    id: int
    name: str
    institution: str | None = None
    account_type: str
    balance: float
    mask: str | None = None
    cash_projection_role: str


class CashProjectionBalanceAnchorResponse(BaseModel):
    date: date
    balance: float
    checking_balance: float
    account_count: int
    checking_account_count: int
    included_accounts: list[CashProjectionBalanceAccountResponse]
    uses_cash_accounts: bool


class CashProjectionBalancePointResponse(BaseModel):
    date: date
    balance: float


class CashProjectionDayResponse(BaseModel):
    date: date
    day: int
    weekday: str
    is_today: bool
    is_past: bool
    events: list[CashProjectionEventResponse]
    actual_events: list[CashProjectionEventResponse]
    scheduled_events: list[CashProjectionEventResponse]
    actual_balance: float | None = None
    balance_basis: str
    net_change: float
    actual_change: float
    scheduled_change: float
    ending_balance: float


class CashProjectionWeekResponse(BaseModel):
    week_start: date
    week_end: date
    days: list[CashProjectionDayResponse]
    income: float
    expenses: float
    ending_balance: float
    net_change: float


class CashProjectionGraphPointResponse(BaseModel):
    x_pct: float
    y_pct: float
    date_label: str
    balance: float
    balance_basis: str


class CashProjectionGraphMarkerResponse(BaseModel):
    label: str
    axis_label: str
    x_pct: float


class CashProjectionGraphResponse(BaseModel):
    points: str
    zero_axis_pct: float
    show_zero_line: bool
    min_value: float
    max_value: float
    month_markers: list[CashProjectionGraphMarkerResponse]
    point_rows: list[CashProjectionGraphPointResponse]


class CashProjectionTrendResponse(BaseModel):
    current_variable_spend: float
    planned_variable_spend: float
    average_first_half_share: float
    affects_projection: bool
    message: str


class CashProjectionPeriodResponse(BaseModel):
    month: date
    month_label: str
    start_date: date
    end_date: date
    start_balance: float
    end_balance: float
    balance_anchor: CashProjectionBalanceAnchorResponse
    lowest_balance: CashProjectionBalancePointResponse
    highest_balance: CashProjectionBalancePointResponse
    days: list[CashProjectionDayResponse]
    weeks: list[CashProjectionWeekResponse] = Field(default_factory=list)
    calendar_cells: list[CashProjectionDayResponse | None]
    events: list[CashProjectionEventResponse]
    trend: CashProjectionTrendResponse
    graph: CashProjectionGraphResponse


class CashProjectionRangeResponse(BaseModel):
    start_month: date
    start_date: date
    end_date: date
    months: int
    projections: list[CashProjectionPeriodResponse]
    days: list[CashProjectionDayResponse]
    events: list[CashProjectionEventResponse]
    start_balance: float
    end_balance: float
    balance_anchor: CashProjectionBalanceAnchorResponse
    lowest_balance: CashProjectionBalancePointResponse
    highest_balance: CashProjectionBalancePointResponse
    graph: CashProjectionGraphResponse


class CashProjectionAccountRowResponse(BaseModel):
    account_id: int
    name: str
    institution: str | None = None
    account_type: str
    balance: float
    mask: str | None = None
    role: str
    included: bool
    status_label: str
    status_class: str
    status_detail: str


class DetectedRecurringCashScheduleResponse(BaseModel):
    detection_key: str
    name: str
    amount: float
    frequency: str
    start_date: date
    second_day_of_month: int | None = None
    category_label: str | None = None
    notes: str | None = None
    last_seen: date


class IgnoredRecurringCashScheduleResponse(BaseModel):
    id: int
    detection_key: str
    name: str
    amount: float
    frequency: str
    category_label: str | None = None
    last_seen: date | None = None
    notes: str | None = None


class CashProjectionCalendarFeedResponse(BaseModel):
    enabled: bool
    feed_url: str | None = None
    webcal_url: str | None = None
    google_url: str | None = None
    generated_at: datetime | None = None
    history_months: int


class CashProjectionRefreshResultResponse(BaseModel):
    synced: int
    errors: list[str]


class CashProjectionResponse(BaseModel):
    horizon: str
    view: str
    projection: CashProjectionPeriodResponse
    projection_range: CashProjectionRangeResponse
    previous_month: date
    next_month: date
    custom_start: date
    custom_end: date
    custom_min_date: date
    custom_max_date: date
    projection_min_month: str
    projection_max_month: str
    account_rows: list[CashProjectionAccountRowResponse]
    detected_recurring: list[DetectedRecurringCashScheduleResponse]
    ignored_recurring: list[IgnoredRecurringCashScheduleResponse]
    calendar_feed: CashProjectionCalendarFeedResponse
    refresh: CashProjectionRefreshResultResponse | None = None


class CashProjectionRefreshRequest(BaseModel):
    month: str | None = None
    horizon: str | None = None
    view: str = "calendar"
    start_date: str | None = None
    end_date: str | None = None


class CashProjectionAutoRecurringRequest(CashProjectionRefreshRequest):
    action: str = Field(default="ignore", pattern="^(ignore|save)$")
    name: str | None = None
    amount: float | None = None
    frequency: str | None = None
    schedule_start_date: str | None = None
    second_date: str | None = None
    recurring_days_of_week: list[int | str] = Field(default_factory=list)
    recurring_monthly_week_numbers: list[int | str] = Field(default_factory=list)
    recurring_monthly_weekday: int | str | None = None
    category_label: str | None = None
    notes: str | None = None


class CashProjectionCalendarFeedUpdateRequest(BaseModel):
    action: str = Field(default="enable", pattern="^(enable|reset|disable)$")


class ThreeMonthForecastResponse(BaseModel):
    month_start: date
    month_name: str
    baseline_income: float
    fixed_expenses: float
    planned_savings: float
    planned_debt: float
    planned_taxes: float
    planned_retirement: float
    planned_variable: float
    planned_income: float
    planned_expenses: float
    one_time_income: float
    one_time_expenses: float
    forecast_income_total: float
    forecast_expense_total: float
    planned_buffer: float
    starting_cash: float
    ending_cash: float
    forecast_items: list[CashProjectionEventResponse]
