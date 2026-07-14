from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class GoalCreateRequest(BaseModel):
    name: str = ""
    goal_type: str = "savings"
    target_amount: float | None = None
    current_amount: float | None = None
    monthly_contribution: float | None = None
    target_date: str | None = None
    fixed_expense_item_id: int | None = None


class GoalUpdateRequest(BaseModel):
    name: str | None = None
    goal_type: str | None = None
    target_amount: float | None = None
    current_amount: float | None = None
    monthly_contribution: float | None = None
    target_date: str | None = None
    fixed_expense_item_id: int | None = None


class GoalDeleteRequest(BaseModel):
    confirm: bool = True


class GoalDeleteResponse(BaseModel):
    deleted_goal_id: int


class GoalRecordResponse(BaseModel):
    id: int
    name: str
    goal_type: str
    target_amount: float
    current_amount: float
    monthly_contribution: float
    target_date: date | None = None
    fixed_expense_item_id: int | None = None

    model_config = ConfigDict(from_attributes=True)


class GoalLinkedItemResponse(BaseModel):
    id: int
    name: str

    model_config = ConfigDict(from_attributes=True)


class GoalResponse(BaseModel):
    goal: GoalRecordResponse
    progress: float
    timeline: str
    remaining: float
    current_amount: float
    target_amount: float
    required_monthly: float
    required_extra: float
    linked_item: GoalLinkedItemResponse | None = None


class GoalLoanOptionResponse(BaseModel):
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


class GoalListResponse(BaseModel):
    goals: list[GoalResponse] = Field(default_factory=list)
    loan_options: list[GoalLoanOptionResponse] = Field(default_factory=list)
