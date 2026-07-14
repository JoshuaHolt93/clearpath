from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies import Principal, require_household_access
from app.schemas.planning import (
    BudgetCreateRequest,
    BudgetDeleteRequest,
    BudgetDeleteResponse,
    BudgetLayoutResponse,
    BudgetLayoutUpdateRequest,
    BudgetResponse,
    BudgetUpdateRequest,
)
from app.schemas.transactions import CategoryResponse
from app.services.planning_service import (
    BUDGET_CATEGORY_GROUP_BY_KEY,
    budget_category_group_for_row,
    current_budget_month_start,
    editable_budget_category_for_user,
    parse_month_input,
    sync_monthly_plan,
)
from app.services.transaction_service import (
    category_can_manage,
    category_for_user,
    delete_category_and_reassign,
    ensure_category_option,
    parse_amount,
    require_onboarding_complete,
)

router = APIRouter(tags=["planning"])

BUDGET_MONTH_LOCKED_MESSAGE = "Previous monthly budgets are locked for history. Use the current month to change active budgets."


def reject_historical_budget_edit(budget_month: str | None) -> None:
    # Flask historical_budget_edit_redirect: a parseable past month blocks the
    # edit; a missing or unparseable month falls through to the current month.
    if not (budget_month or "").strip():
        return
    try:
        selected_month = parse_month_input(budget_month.strip())
    except ValueError:
        return
    if selected_month < current_budget_month_start():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=BUDGET_MONTH_LOCKED_MESSAGE)


def budget_response(category) -> BudgetResponse:
    group = budget_category_group_for_row(category, category.name)
    response = CategoryResponse.model_validate(category)
    return BudgetResponse(category=response, group_key=group["key"], group_label=group["label"])


@router.post("/budgets", response_model=BudgetResponse, status_code=status.HTTP_201_CREATED)
def create_budget(
    payload: BudgetCreateRequest,
    principal: Annotated[Principal, Depends(require_household_access("editor"))],
    db: Annotated[Session, Depends(get_db)],
) -> BudgetResponse:
    user = principal.user
    require_onboarding_complete(user)
    reject_historical_budget_edit(payload.budget_month)
    label = (payload.category_label or "").strip() or None
    target = max(parse_amount(payload.monthly_target or 0), 0)
    category_kind = "income" if (payload.category_kind or "").strip().lower() == "income" else "expense"
    if not label:
        raise HTTPException(status_code=422, detail="Choose or create a category before adding a budget.")
    if target <= 0:
        raise HTTPException(status_code=422, detail="Enter a monthly budget amount greater than $0.")

    category = ensure_category_option(db, label, user)
    if not category:
        raise HTTPException(status_code=422, detail="Category could not be created.")
    editable_category = editable_budget_category_for_user(db, category, user)
    editable_category.kind = category_kind
    editable_category.monthly_target = target
    editable_category.is_default = False
    db.commit()
    sync_monthly_plan(db, user, purpose="monthly_plan")
    return budget_response(editable_category)


@router.patch("/budgets/layout", response_model=BudgetLayoutResponse)
def update_budget_layout(
    payload: BudgetLayoutUpdateRequest,
    principal: Annotated[Principal, Depends(require_household_access("editor"))],
    db: Annotated[Session, Depends(get_db)],
) -> BudgetLayoutResponse:
    user = principal.user
    require_onboarding_complete(user)
    # Flask update_category_budget_layout: an invalid month silently falls
    # back to the current month; a past month is a 400.
    payload_month = current_budget_month_start()
    if (payload.budget_month or "").strip():
        try:
            payload_month = parse_month_input(payload.budget_month.strip())
        except ValueError:
            payload_month = current_budget_month_start()
    if payload_month < current_budget_month_start():
        raise HTTPException(status_code=400, detail="Previous monthly budgets are locked for history.")

    if not payload.rows:
        raise HTTPException(status_code=400, detail="No budget rows were provided.")

    updated = 0
    for index, row in enumerate(payload.rows):
        category = category_for_user(db, row.category_id, user)
        if not category:
            continue
        editable_category = editable_budget_category_for_user(db, category, user)
        group_key = (row.group_key or "").strip()
        if group_key and group_key in BUDGET_CATEGORY_GROUP_BY_KEY:
            editable_category.budget_group_key = group_key
        editable_category.budget_sort_order = index + 1
        updated += 1

    if not updated:
        raise HTTPException(status_code=400, detail="No editable budget rows were found.")
    db.commit()
    return BudgetLayoutResponse(ok=True, updated=updated)


@router.patch("/budgets/{category_id}", response_model=BudgetResponse)
def update_budget(
    category_id: int,
    payload: BudgetUpdateRequest,
    principal: Annotated[Principal, Depends(require_household_access("editor"))],
    db: Annotated[Session, Depends(get_db)],
) -> BudgetResponse:
    user = principal.user
    require_onboarding_complete(user)
    reject_historical_budget_edit(payload.budget_month)
    category = category_for_user(db, category_id, user)
    if not category:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found for this account.")

    target = max(parse_amount(payload.monthly_target or 0), 0)
    editable_category = editable_budget_category_for_user(db, category, user)
    editable_category.monthly_target = target
    editable_category.is_default = False
    db.commit()
    sync_monthly_plan(db, user, purpose="monthly_plan")
    return budget_response(editable_category)


@router.delete("/budgets/{category_id}", response_model=BudgetDeleteResponse)
def delete_budget(
    category_id: int,
    payload: BudgetDeleteRequest,
    principal: Annotated[Principal, Depends(require_household_access("editor"))],
    db: Annotated[Session, Depends(get_db)],
) -> BudgetDeleteResponse:
    user = principal.user
    require_onboarding_complete(user)
    reject_historical_budget_edit(payload.budget_month)
    category = category_for_user(db, category_id, user)
    if not category:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found for this account.")
    if category.name.strip().lower() == "other":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Other is kept as the catch-all for uncategorized transactions.")
    if not category_can_manage(db, category, user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="That budget category cannot be removed for this account.")

    replacement = delete_category_and_reassign(db, category, user)
    db.commit()
    sync_monthly_plan(db, user, purpose="monthly_plan")
    return BudgetDeleteResponse(
        deleted_category_id=category_id,
        replacement_category=CategoryResponse.model_validate(replacement) if replacement else None,
    )

