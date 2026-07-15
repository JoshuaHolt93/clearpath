from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from app.schemas.planning import FixedExpenseItemResponse, LoanPlanRecordResponse, LoanPlanScenarioResponse


class LoanPlanListQuery(BaseModel):
    pass


class AmortizationScheduleRowResponse(BaseModel):
    month: int
    payment_date: date
    beginning_balance: float
    payment: float
    principal: float
    interest: float
    ending_balance: float


class LoanPlanSummaryResponse(BaseModel):
    fixed_expense_item_id: int
    name: str
    loan_kind: str
    monthly_payment: float
    selected_extra: float
    total_monthly: float
    principal_balance: float
    current_balance: float
    collateral_value: float
    selected_scenario: str


class LoanPlanResponse(BaseModel):
    fixed_expense: FixedExpenseItemResponse
    loan_kind: str
    plan: LoanPlanRecordResponse | None = None
    scenarios: list[LoanPlanScenarioResponse] = Field(default_factory=list)
    selected_schedule: list[AmortizationScheduleRowResponse] = Field(default_factory=list)
    created_fixed_expense: bool = False


class LoanPlanListResponse(BaseModel):
    items: list[LoanPlanSummaryResponse] = Field(default_factory=list)
    total_debt_monthly: float
    total_debt_balance: float
    debt_to_income_ratio: float
    loan_category_label_options: list[str] = Field(default_factory=list)


class LoanPlanUpdateRequest(BaseModel):
    principal_balance: float | str | None = None
    collateral_value: float | str | None = None
    annual_interest_rate: float | str | None = None
    term_value: float | str | None = None
    term_months: float | str | None = None
    term_unit: str = "months"
    regular_payment: float | str | None = None
    extra_payment_one: float | str | None = None
    extra_payment_two: float | str | None = None
    selected_scenario: str = "base"
    notes: str | None = None


class LoanPlanScenarioSelectRequest(BaseModel):
    selected_scenario: str = "base"
