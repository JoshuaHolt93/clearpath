from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.plaid import AccountResponse

from app.schemas.cash_projections import (
    CashProjectionAccountRowResponse,
    CashProjectionPeriodResponse,
    ThreeMonthForecastResponse,
)
from app.schemas.transactions import AmortizationActionResponse, CategoryResponse


class BudgetResponse(BaseModel):
    category: CategoryResponse
    group_key: str
    group_label: str


class BudgetCreateRequest(BaseModel):
    category_label: str | None = None
    monthly_target: float | None = None
    category_kind: str | None = None
    budget_month: str | None = None


class BudgetUpdateRequest(BaseModel):
    monthly_target: float | None = None
    budget_month: str | None = None


class BudgetDeleteRequest(BaseModel):
    budget_month: str | None = None


class BudgetDeleteResponse(BaseModel):
    deleted_category_id: int
    replacement_category: CategoryResponse | None = None


class BudgetLayoutRowInput(BaseModel):
    category_id: int
    group_key: str | None = None


class BudgetLayoutUpdateRequest(BaseModel):
    budget_month: str | None = None
    rows: list[BudgetLayoutRowInput] = Field(default_factory=list)


class BudgetLayoutResponse(BaseModel):
    ok: bool
    updated: int


class TransactionBudgetActivateResponse(BaseModel):
    category: CategoryResponse
    target: float


class FixedExpenseItemResponse(BaseModel):
    id: int
    name: str
    amount: float
    due_day: int | None = None
    start_date: date
    frequency: str
    days_of_week: str | None = None
    second_date: date | None = None
    second_day_of_month: int | None = None
    monthly_week_numbers: str | None = None
    monthly_weekday: int | None = None
    category_label: str | None = None
    is_loan: bool
    notes: str | None = None
    monthly_amount: float | None = None

    model_config = ConfigDict(from_attributes=True)


class LoanPlanRecordResponse(BaseModel):
    id: int
    fixed_expense_item_id: int
    loan_type: str
    principal_balance: float
    collateral_value: float
    annual_interest_rate: float
    term_months: int
    term_unit_preference: str
    regular_payment: float
    extra_payment_one: float
    extra_payment_two: float
    selected_scenario: str
    notes: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LoanPlanScenarioResponse(BaseModel):
    key: str
    label: str
    extra_payment: float
    months: int
    years: float
    interest_paid: float
    payoff_possible: bool


class VariableExpenseItemResponse(BaseModel):
    id: int
    name: str
    amount: float
    frequency: str
    use_specific_date: bool
    specific_date: date | None = None
    days_of_week: str | None = None
    category_label: str | None = None
    notes: str | None = None
    monthly_amount: float | None = None

    model_config = ConfigDict(from_attributes=True)


class ForecastItemResponse(BaseModel):
    id: int
    item_date: date
    description: str
    amount: float
    item_type: str
    category_label: str | None = None
    notes: str | None = None

    model_config = ConfigDict(from_attributes=True)


class RecurringForecastTemplateResponse(BaseModel):
    id: int
    name: str
    amount: float
    item_type: str
    frequency: str
    start_date: date
    second_date: date | None = None
    days_of_week: str | None = None
    second_day_of_month: int | None = None
    monthly_week_numbers: str | None = None
    monthly_weekday: int | None = None
    category_label: str | None = None
    notes: str | None = None
    income_replacement: bool
    income_basis: str | None = None
    income_type: str | None = None
    paycheck_cadence: str | None = None
    income_next_pay_date: date | None = None
    hourly_hours_per_week: float
    additional_income_amount: float
    additional_income_frequency: str
    tax_state: str | None = None
    tax_filing_status: str | None = None
    include_payroll_taxes: bool
    monthly_amount: float | None = None

    model_config = ConfigDict(from_attributes=True)


class TaxEstimateResponse(BaseModel):
    annual_gross_income: float
    taxable_income: float
    federal_income_tax: float
    state_income_tax: float
    social_security_tax: float
    medicare_tax: float
    additional_medicare_tax: float
    additional_tax_label: str
    additional_tax_type: str
    additional_tax_rate: float
    additional_tax_annual: float
    additional_tax_monthly: float
    annual_total: float
    monthly_total: float
    filing_status: str
    state: str | None = None
    state_rate: float
    state_method: str
    state_taxable_income: float
    state_standard_deduction: float
    state_personal_exemption: float
    state_credit: float
    state_brackets: list[list[float | None]]
    state_note: str
    state_source_url: str | None = None
    federal_brackets: list[list[float | None]]
    standard_deduction: float

    model_config = ConfigDict(from_attributes=True)


class BaselineProfileResponse(BaseModel):
    household_name: str | None = None
    income_amount: float | None = None
    income_amount_display: float | None = None
    monthly_income: float | None = None
    income_basis: str | None = None
    income_type: str | None = None
    income_frequency: str | None = None
    paycheck_cadence: str | None = None
    next_pay_date: date | None = None
    paycheck_second_date: date | None = None
    paycheck_days_of_week: str | None = None
    paycheck_second_day_of_month: int | None = None
    paycheck_monthly_week_numbers: str | None = None
    paycheck_monthly_weekday: int | None = None
    hourly_hours_per_week: float | None = None
    additional_income_amount: float | None = None
    additional_income_frequency: str | None = None
    variable_expenses: float | None = None
    tax_state: str | None = None
    tax_filing_status: str | None = None
    tax_additional_label: str | None = None
    tax_additional_type: str | None = None
    tax_additional_rate: float | None = None
    tax_additional_monthly_amount: float | None = None
    include_payroll_taxes: bool | None = None
    planned_savings_contribution: float | None = None
    planned_debt_payment: float | None = None
    target_investment_contribution: float | None = None
    retirement_enabled: bool | None = None
    notes: str | None = None

    model_config = ConfigDict(from_attributes=True)


class MonthlyPlanRecordResponse(BaseModel):
    month: date
    income: float
    fixed_expenses: float
    planned_savings: float
    planned_debt_payment: float
    safe_to_spend_target: float

    model_config = ConfigDict(from_attributes=True)


class PayPeriodResponse(BaseModel):
    start: date
    end: date
    next_pay_date: date


class PlanRowResponse(BaseModel):
    label: str
    planned: float
    actual: float
    type: str
    details: list[dict] = Field(default_factory=list)


class BudgetRowResponse(BaseModel):
    kind: str
    category_kind: str
    category_id: int | None = None
    label: str
    category: str
    group_key: str
    planned: float
    actual: float
    remaining: float
    progress_percent: float
    progress_status: str
    anchor_id: str
    transaction_ids: list[int] = Field(default_factory=list)
    transaction_count: int = 0
    suggestion_match_count: int = 0
    sort_order: int | None = None
    can_remove_budget: bool = False
    amortization_action: AmortizationActionResponse | None = None
    actual_label: str = "spent"
    planned_label: str = "planned"
    adjust_label: str = ""


class BudgetSectionResponse(BaseModel):
    label: str
    kind: str
    description: str = ""
    empty: str = ""
    rows: list[BudgetRowResponse] = Field(default_factory=list)
    planned: float = 0
    actual: float = 0
    transaction_ids: list[int] = Field(default_factory=list)
    transaction_count: int = 0


class SuggestedBudgetSectionResponse(BaseModel):
    label: str
    kind: str
    rows: list[BudgetRowResponse] = Field(default_factory=list)


class QuickWorksheetRowResponse(BaseModel):
    name: str
    subtitle: str
    timing: str
    category: str
    amount: float
    action_label: str
    readonly: bool
    item_type: str
    item_id: int | None = None


class CategorySpendRowResponse(BaseModel):
    category: str
    category_id: int | None = None
    amount: float


class ExpenseSourceRowResponse(BaseModel):
    source: str
    amount: float
    item_type: str
    item_id: int | None = None
    subscription_count: int | None = None


class MonthlyPlanResponse(BaseModel):
    profile: BaselineProfileResponse
    plan: MonthlyPlanRecordResponse
    month_income_recorded: float
    actual_savings: float
    month_name: str
    today: date
    plan_view: str
    plan_section: str
    pay_period: PayPeriodResponse
    plan_rows: list[PlanRowResponse]
    category_spend: list[CategorySpendRowResponse]
    forecast_months: list[ThreeMonthForecastResponse] = Field(default_factory=list)
    fixed_items: list[FixedExpenseItemResponse]
    loan_items: list[FixedExpenseItemResponse] = Field(default_factory=list)
    loan_plans: dict[int, LoanPlanRecordResponse] = Field(default_factory=dict)
    loan_scenarios: dict[int, list[LoanPlanScenarioResponse]] = Field(default_factory=dict)
    retirement_accounts: list[AccountResponse] = Field(default_factory=list)
    variable_items: list[VariableExpenseItemResponse]
    fixed_expense_rows: list[ExpenseSourceRowResponse]
    variable_expense_rows: list[ExpenseSourceRowResponse]
    quick_worksheet_rows: list[QuickWorksheetRowResponse]
    forecast_items: list[ForecastItemResponse]
    recurring_templates: list[RecurringForecastTemplateResponse]
    future_income_templates: list[RecurringForecastTemplateResponse]
    category_label_options: list[str]
    fixed_total: float
    variable_plan_total: float
    retirement_contribution: float
    loan_extra_total: float
    effective_debt_payment: float
    tax_estimate: TaxEstimateResponse
    taxes_enabled: bool
    planned_available: float
    budget_remaining: float
    budget_sections: list[BudgetSectionResponse]
    suggested_budget_sections: list[SuggestedBudgetSectionResponse]
    unassigned_budget_rows: list[BudgetRowResponse]
    budget_view: str
    budget_grouped: bool
    budget_sort: str
    budget_drag_enabled: bool
    budget_selected_month: date
    budget_current_month: date
    budget_month_value: str
    budget_month_label: str
    budget_is_current_month: bool
    budget_history_mode: bool
    total_budget_planned: float
    total_budget_actual: float
    total_budget_remaining: float
    expected_cash_flow: float
    quick_cash_projection: CashProjectionPeriodResponse | None = None
    cash_projection_account_rows: list[CashProjectionAccountRowResponse] = Field(default_factory=list)
    quick_cash_week_change: float = 0
    quick_cash_week_end_balance: float = 0
    quick_cash_remaining_income: float = 0
    quick_cash_remaining_expenses: float = 0
    quick_sort: str
    # Server constants echoed for client rendering parity with Flask.
    budget_sort_options: dict[str, str]
    quick_sort_options: dict[str, str]
    income_type_options: dict[str, str]
    income_basis_options: dict[str, str]
    paycheck_cadence_options: dict[str, str]
    tax_filing_status_options: dict[str, str]
    state_options: dict[str, str]
    recurring_frequency_options: dict[str, str]
    weekday_options: dict[int, str]
    monthly_week_options: dict[int, str]
    budget_group_options: list[dict]


class FixedExpenseCreateRequest(BaseModel):
    name: str = ""
    amount: float | None = None
    frequency: str = "monthly"
    start_date: str = ""
    second_date: str | None = None
    days_of_week: list[int | str] = Field(default_factory=list)
    recurring_monthly_week_numbers: list[int | str] = Field(default_factory=list)
    recurring_monthly_weekday: int | str | None = None
    category_label: str | None = None
    # Flask entry_context="loan" marks the item as a loan and syncs the
    # loan budget category.
    entry_context: str | None = None
    notes: str | None = None


class FixedExpenseUpdateRequest(FixedExpenseCreateRequest):
    # When only monthly_target is provided, the PATCH behaves like Flask's
    # amount-only route: convert the monthly planned cash back to the item's
    # cadence amount and re-sync budget targets.
    monthly_target: float | None = None


class FixedExpenseDeleteRequest(BaseModel):
    confirm: bool = True


class FixedExpenseDeleteResponse(BaseModel):
    deleted_item_id: int


class VariableExpenseCreateRequest(BaseModel):
    name: str = ""
    amount: float | None = None
    frequency: str = "monthly"
    use_specific_date: bool = False
    specific_date: str | None = None
    days_of_week: list[int | str] = Field(default_factory=list)
    category_label: str | None = None
    notes: str | None = None


class VariableExpenseUpdateRequest(VariableExpenseCreateRequest):
    monthly_target: float | None = None


class VariableExpenseDeleteRequest(BaseModel):
    confirm: bool = True


class VariableExpenseDeleteResponse(BaseModel):
    deleted_item_id: int


class ForecastItemCreateRequest(BaseModel):
    item_date: str = ""
    description: str = ""
    amount: float | None = None
    item_type: str = "expense"
    category_label: str | None = None
    notes: str | None = None


class ForecastItemUpdateRequest(ForecastItemCreateRequest):
    pass


class ForecastItemDeleteRequest(BaseModel):
    confirm: bool = True


class ForecastItemDeleteResponse(BaseModel):
    deleted_item_id: int


class RecurringForecastTemplateCreateRequest(BaseModel):
    name: str = ""
    amount: float | None = None
    item_type: str = "expense"
    frequency: str = "monthly"
    start_date: str | None = None
    second_date: str | None = None
    recurring_days_of_week: list[int | str] = Field(default_factory=list)
    recurring_monthly_week_numbers: list[int | str] = Field(default_factory=list)
    recurring_monthly_weekday: int | str | None = None
    category_label: str | None = None
    notes: str | None = None
    # Future income adjustment fields (Flask income_adjustment="yes" path).
    income_adjustment: bool = False
    income_replacement: bool | None = None
    income_basis: str = "take_home"
    income_type: str = "salary"
    paycheck_cadence: str = "monthly"
    income_next_pay_date: str | None = None
    income_amount: float | None = None
    hourly_hours_per_week: float | None = None
    additional_income_amount: float | None = None
    additional_income_frequency: str = "annual"
    tax_state: str | None = None
    tax_filing_status: str = "married_joint"
    include_payroll_taxes: bool = False


class RecurringForecastTemplateUpdateRequest(RecurringForecastTemplateCreateRequest):
    # A monthly_target-only payload follows Flask's amount-only route.
    monthly_target: float | None = None


class RecurringForecastTemplateDeleteRequest(BaseModel):
    confirm: bool = True


class RecurringForecastTemplateDeleteResponse(BaseModel):
    deleted_template_id: int


class MonthlyPlanBaselineUpdateRequest(BaseModel):
    # Flask applies only the fields present in the form; the API mirrors that
    # with fields-set semantics (model_fields_set).
    baseline_scope: str | None = None
    household_name: str | None = None
    income_amount: float | None = None
    income_basis: str | None = None
    income_type: str | None = None
    paycheck_cadence: str | None = None
    next_pay_date: str | None = None
    second_date: str | None = None
    recurring_days_of_week: list[int | str] = Field(default_factory=list)
    recurring_monthly_week_numbers: list[int | str] = Field(default_factory=list)
    recurring_monthly_weekday: int | str | None = None
    hourly_hours_per_week: float | None = None
    additional_income_amount: float | None = None
    additional_income_frequency: str | None = None
    variable_expenses: float | None = None
    tax_state: str | None = None
    tax_filing_status: str | None = None
    tax_additional_label: str | None = None
    tax_additional_type: str | None = None
    tax_additional_rate: float | None = None
    tax_additional_monthly_amount: float | None = None
    include_payroll_taxes: bool | None = None
    planned_savings_contribution: float | None = None
    planned_debt_payment: float | None = None
    target_investment_contribution: float | None = None
    notes: str | None = None
    # Response context (mirrors Flask's redirect back to view/section).
    view: str = "month"
    section: str = "tools"
