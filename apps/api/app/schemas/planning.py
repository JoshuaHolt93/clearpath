from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.transactions import CategoryResponse


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
