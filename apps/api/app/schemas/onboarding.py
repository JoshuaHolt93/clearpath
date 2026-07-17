from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.plaid import PlaidStatusResponse
from app.schemas.planning import BaselineProfileResponse


class OnboardingIncomePlanRequest(BaseModel):
    income_amount: float | None = None
    monthly_income: float | None = None
    income_basis: str = "take_home"
    income_type: str = "salary"
    paycheck_cadence: str = "monthly"
    next_pay_date: str | None = None
    second_date: str | None = None
    recurring_days_of_week: list[int | str] = Field(default_factory=list)
    recurring_monthly_week_numbers: list[int | str] = Field(default_factory=list)
    recurring_monthly_weekday: int | str | None = None
    hourly_hours_per_week: float | None = 40
    fixed_expenses: float | None = None
    variable_expenses: float | None = None
    additional_income_amount: float | None = None
    additional_income_frequency: str = "annual"
    planned_savings_contribution: float | None = None
    planned_debt_payment: float | None = None
    target_investment_contribution: float | None = None
    tax_filing_status: str = "married_joint"
    tax_state: str | None = None
    include_payroll_taxes: bool = True
    notes: str | None = None


class OnboardingCompleteRequest(BaseModel):
    confirm: bool = True


class OnboardingPlaidItemResponse(BaseModel):
    id: int
    institution_name: str | None = None
    status: str
    last_synced_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class OnboardingCategoryResponse(BaseModel):
    id: int
    name: str
    kind: str

    model_config = ConfigDict(from_attributes=True)


class OnboardingTransactionResponse(BaseModel):
    id: int
    display_merchant: str
    posted_date: date
    amount: float
    account_name: str | None = None
    source_name: str | None = None
    category_id: int | None = None


class OnboardingStatusResponse(BaseModel):
    active_step: Literal["connect", "income", "transactions"]
    income_ready: bool
    has_bank: bool
    setup_complete: bool
    profile: BaselineProfileResponse
    today: date
    plaid_status: PlaidStatusResponse
    plaid_items: list[OnboardingPlaidItemResponse] = Field(default_factory=list)
    transactions: list[OnboardingTransactionResponse] = Field(default_factory=list)
    categories: list[OnboardingCategoryResponse] = Field(default_factory=list)
    auto_categorized_count: int = 0
    seeded_budget_count: int = 0
    message: str | None = None
    next_path: str | None = None
    income_basis_options: dict[str, str]
    income_type_options: dict[str, str]
    paycheck_cadence_options: dict[str, str]
    recurring_frequency_options: dict[str, str]
    weekday_options: dict[str, str]
    monthly_week_options: dict[str, str]
    tax_filing_status_options: dict[str, str]
    state_options: dict[str, str]
