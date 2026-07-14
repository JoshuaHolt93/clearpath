from __future__ import annotations

import calendar
import json
from collections import defaultdict
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.feature_access import feature_min_plan_label, user_has_feature
from app.core.planning_constants import (
    BUDGET_SORT_OPTIONS,
    INCOME_BASIS_OPTIONS,
    INCOME_TYPE_OPTIONS,
    MONTHLY_WEEK_OPTIONS,
    PAYCHECK_CADENCE_OPTIONS,
    QUICK_WORKSHEET_SORT_OPTIONS,
    RECURRING_FREQUENCY_OPTIONS,
    STARTER_CATEGORY_GROUPS,
    STATE_OPTIONS,
    TAX_FILING_STATUS_OPTIONS,
    WEEKDAY_OPTIONS,
)
from app.dependencies import Principal, require_household_access
from app.models import (
    Category,
    FixedExpenseItem,
    ForecastItem,
    RecurringForecastTemplate,
    Transaction,
    User,
    VariableExpenseItem,
)
from app.schemas.planning import (
    BaselineProfileResponse,
    BudgetCreateRequest,
    BudgetDeleteRequest,
    BudgetDeleteResponse,
    BudgetLayoutResponse,
    BudgetLayoutUpdateRequest,
    BudgetResponse,
    BudgetRowResponse,
    BudgetSectionResponse,
    BudgetUpdateRequest,
    CategorySpendRowResponse,
    ExpenseSourceRowResponse,
    FixedExpenseCreateRequest,
    FixedExpenseDeleteRequest,
    FixedExpenseDeleteResponse,
    FixedExpenseItemResponse,
    FixedExpenseUpdateRequest,
    ForecastItemResponse,
    MonthlyPlanBaselineUpdateRequest,
    MonthlyPlanRecordResponse,
    MonthlyPlanResponse,
    PayPeriodResponse,
    PlanRowResponse,
    QuickWorksheetRowResponse,
    RecurringForecastTemplateResponse,
    SuggestedBudgetSectionResponse,
    TaxEstimateResponse,
    VariableExpenseCreateRequest,
    VariableExpenseDeleteRequest,
    VariableExpenseDeleteResponse,
    VariableExpenseItemResponse,
    VariableExpenseUpdateRequest,
)
from app.schemas.transactions import CategoryResponse
from app.services.planning_service import (
    BUDGET_CATEGORY_GROUP_BY_KEY,
    active_budget_categories_by_key,
    amount_for_monthly_target,
    annual_salary_from_profile,
    app_today,
    clean_selected_weekdays,
    fixed_expense_timing_from_values,
    loan_category_for_item,
    planning_item_occurrence_multiplier,
    sync_loan_fixed_expense_budget,
    sync_planning_item_budget_target,
    budget_anchor_for_label,
    budget_category_group_for_label,
    budget_category_group_for_row,
    budget_row_is_canonical_income,
    budget_suggestion_candidate,
    calculate_tax_estimate,
    credit_card_debt_paydown_between,
    current_budget_month_start,
    current_month_name,
    current_pay_period_bounds,
    editable_budget_category_for_user,
    fixed_expense_total,
    fixed_plan_detail_rows,
    get_or_create_monthly_plan,
    income_plan_detail_rows,
    monthly_amount_for_fixed_item,
    monthly_amount_for_variable_item,
    monthly_budget_category_snapshots_for_user,
    monthly_income_from_profile,
    parse_month_input,
    paycheck_timing_values,
    planned_income_for_period,
    recorded_month_income,
    recurring_template_monthly_amount,
    retirement_cash_flow_contribution,
    selected_loan_extra_payment_total,
    spending_by_category,
    sync_monthly_plan,
    tax_plan_detail_rows,
    transaction_category_allocations_for_period,
    transaction_matches_budget_category,
    variable_expense_plan_total,
    variable_plan_detail_rows,
)
from app.services.transaction_service import (
    categories_for_user,
    category_can_manage,
    category_for_user,
    category_label_options_for_user,
    delete_category_and_reassign,
    ensure_category_option,
    normalize_text,
    parse_amount,
    parse_flexible_date,
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


# --- Fixed and variable expense worksheets -----------------------------------
# Faithful ports of Flask add/edit/amount/delete handlers (main.py at cb7d969).
# The amount-only Flask routes collapse into PATCH: a payload carrying only
# monthly_target follows Flask's edit_*_amount semantics.


def _fixed_item_response(item: FixedExpenseItem) -> FixedExpenseItemResponse:
    response = FixedExpenseItemResponse.model_validate(item)
    response.monthly_amount = monthly_amount_for_fixed_item(item)
    return response


def _variable_item_response(item: VariableExpenseItem) -> VariableExpenseItemResponse:
    response = VariableExpenseItemResponse.model_validate(item)
    response.monthly_amount = monthly_amount_for_variable_item(item)
    return response


def _get_owned_fixed_item(db: Session, user: User, item_id: int) -> FixedExpenseItem:
    item = db.scalar(select(FixedExpenseItem).where(FixedExpenseItem.user_id == user.id, FixedExpenseItem.id == item_id))
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fixed expense not found.")
    return item


def _get_owned_variable_item(db: Session, user: User, item_id: int) -> VariableExpenseItem:
    item = db.scalar(select(VariableExpenseItem).where(VariableExpenseItem.user_id == user.id, VariableExpenseItem.id == item_id))
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Variable expense not found.")
    return item


def _parse_optional_date(raw_value: str | None) -> date | None:
    raw = (raw_value or "").strip()
    if not raw:
        return None
    try:
        return parse_flexible_date(raw)
    except ValueError:
        return None


def _fixed_expense_values(payload: FixedExpenseCreateRequest, *, item_label: str) -> dict:
    name = (payload.name or "").strip()
    amount = parse_amount(payload.amount or 0)
    frequency = payload.frequency or "monthly"
    raw_second_date = (payload.second_date or "").strip()
    selected_weekdays = clean_selected_weekdays(payload.days_of_week)
    start_date = _parse_optional_date(payload.start_date)
    second_date = _parse_optional_date(payload.second_date)
    start_date, second_date, selected_weekdays, monthly_week_numbers, monthly_weekday = fixed_expense_timing_from_values(
        frequency,
        start_date,
        second_date,
        selected_weekdays,
        payload.recurring_monthly_week_numbers,
        payload.recurring_monthly_weekday,
    )
    if not name or amount <= 0:
        raise HTTPException(status_code=422, detail=f"{item_label} name and amount are required.")
    if not start_date:
        raise HTTPException(status_code=422, detail=f"Enter a valid {item_label.lower()} date.")
    if frequency == "semimonthly" and monthly_weekday is not None and not monthly_week_numbers:
        message = "Choose which weeks in the month this loan payment repeats." if item_label == "Loan" else "Choose which weeks in the month this expense repeats."
        raise HTTPException(status_code=422, detail=message)
    if frequency in {"semimonthly", "biweekly"} and raw_second_date and not second_date:
        raise HTTPException(status_code=422, detail="Enter a valid second date for twice-per-month expenses.")
    return {
        "name": name,
        "amount": amount,
        "frequency": frequency,
        "start_date": start_date,
        "second_date": second_date,
        "selected_weekdays": selected_weekdays,
        "monthly_week_numbers": monthly_week_numbers,
        "monthly_weekday": monthly_weekday,
        "category_label": (payload.category_label or "").strip() or None,
        "notes": (payload.notes or "").strip() or None,
    }


@router.post("/fixed-expenses", response_model=FixedExpenseItemResponse, status_code=status.HTTP_201_CREATED)
def create_fixed_expense(
    payload: FixedExpenseCreateRequest,
    principal: Annotated[Principal, Depends(require_household_access("editor"))],
    db: Annotated[Session, Depends(get_db)],
) -> FixedExpenseItemResponse:
    user = principal.user
    is_loan_entry = payload.entry_context == "loan"
    values = _fixed_expense_values(payload, item_label="Loan" if is_loan_entry else "Fixed expense")
    ensure_category_option(db, values["category_label"], user)
    item = FixedExpenseItem(
        user_id=user.id,
        name=values["name"],
        amount=values["amount"],
        due_day=values["start_date"].day,
        start_date=values["start_date"],
        frequency=values["frequency"],
        days_of_week=",".join(values["selected_weekdays"]) if values["selected_weekdays"] else None,
        second_date=values["second_date"],
        second_day_of_month=values["second_date"].day if values["second_date"] else None,
        monthly_week_numbers=values["monthly_week_numbers"],
        monthly_weekday=values["monthly_weekday"],
        category_label=values["category_label"],
        is_loan=is_loan_entry,
        notes=values["notes"],
    )
    db.add(item)
    sync_loan_fixed_expense_budget(db, item, user, force=is_loan_entry)
    db.commit()
    sync_monthly_plan(db, user)
    return _fixed_item_response(_get_owned_fixed_item(db, user, item.id))


@router.patch("/fixed-expenses/{item_id}", response_model=FixedExpenseItemResponse)
def update_fixed_expense(
    item_id: int,
    payload: FixedExpenseUpdateRequest,
    principal: Annotated[Principal, Depends(require_household_access("editor"))],
    db: Annotated[Session, Depends(get_db)],
) -> FixedExpenseItemResponse:
    user = principal.user
    item = _get_owned_fixed_item(db, user, item_id)

    if "monthly_target" in payload.model_fields_set:
        # Flask edit_fixed_expense_amount.
        monthly_target = parse_amount(payload.monthly_target or 0)
        if monthly_target <= 0:
            raise HTTPException(status_code=422, detail="Enter a positive planned cash amount.")
        item.amount = round(amount_for_monthly_target(monthly_target, item.frequency, planning_item_occurrence_multiplier(item)), 2)
        ensure_category_option(db, item.category_label or "Other", user)
        if item.is_loan or loan_category_for_item(item):
            sync_loan_fixed_expense_budget(db, item, user, force=item.is_loan)
        else:
            sync_planning_item_budget_target(db, item.category_label or "Other", user)
        db.commit()
        sync_monthly_plan(db, user, purpose="monthly_plan")
        return _fixed_item_response(_get_owned_fixed_item(db, user, item.id))

    # Flask edit_fixed_expense.
    values = _fixed_expense_values(payload, item_label="Fixed expense")
    ensure_category_option(db, values["category_label"], user)
    item.name = values["name"]
    item.amount = values["amount"]
    item.due_day = values["start_date"].day
    item.start_date = values["start_date"]
    item.frequency = values["frequency"]
    item.days_of_week = ",".join(values["selected_weekdays"]) if values["selected_weekdays"] else None
    item.second_date = values["second_date"]
    item.second_day_of_month = values["second_date"].day if values["second_date"] else None
    item.monthly_week_numbers = values["monthly_week_numbers"]
    item.monthly_weekday = values["monthly_weekday"]
    item.category_label = values["category_label"]
    if payload.entry_context == "loan":
        item.is_loan = True
    item.notes = values["notes"]
    sync_loan_fixed_expense_budget(db, item, user, force=item.is_loan)
    db.commit()
    sync_monthly_plan(db, user)
    return _fixed_item_response(_get_owned_fixed_item(db, user, item.id))


@router.delete("/fixed-expenses/{item_id}", response_model=FixedExpenseDeleteResponse)
def delete_fixed_expense(
    item_id: int,
    payload: FixedExpenseDeleteRequest,
    principal: Annotated[Principal, Depends(require_household_access("editor"))],
    db: Annotated[Session, Depends(get_db)],
) -> FixedExpenseDeleteResponse:
    user = principal.user
    item = _get_owned_fixed_item(db, user, item_id)
    db.delete(item)
    db.commit()
    sync_monthly_plan(db, user)
    return FixedExpenseDeleteResponse(deleted_item_id=item_id)


def _variable_expense_values(payload: VariableExpenseCreateRequest) -> dict:
    name = (payload.name or "").strip()
    amount = parse_amount(payload.amount or 0)
    frequency = payload.frequency or "monthly"
    use_specific_date = payload.use_specific_date
    specific_date = _parse_optional_date(payload.specific_date)
    selected_weekdays = clean_selected_weekdays(payload.days_of_week)
    if not name or amount <= 0:
        raise HTTPException(status_code=422, detail="Variable expense name and amount are required.")
    if use_specific_date and frequency == "monthly" and not specific_date:
        raise HTTPException(status_code=422, detail="Enter a valid date for the monthly variable expense.")
    if use_specific_date and frequency != "monthly" and not selected_weekdays:
        raise HTTPException(status_code=422, detail="Choose at least one weekday for this variable expense.")
    return {
        "name": name,
        "amount": amount,
        "frequency": frequency,
        "use_specific_date": use_specific_date,
        "specific_date": specific_date if use_specific_date and frequency == "monthly" else None,
        "days_of_week": ",".join(selected_weekdays) if use_specific_date and frequency != "monthly" else None,
        "category_label": (payload.category_label or "").strip() or None,
        "notes": (payload.notes or "").strip() or None,
    }


@router.post("/variable-expenses", response_model=VariableExpenseItemResponse, status_code=status.HTTP_201_CREATED)
def create_variable_expense(
    payload: VariableExpenseCreateRequest,
    principal: Annotated[Principal, Depends(require_household_access("editor"))],
    db: Annotated[Session, Depends(get_db)],
) -> VariableExpenseItemResponse:
    user = principal.user
    values = _variable_expense_values(payload)
    ensure_category_option(db, values["category_label"], user)
    item = VariableExpenseItem(user_id=user.id, **values)
    db.add(item)
    db.commit()
    sync_monthly_plan(db, user)
    return _variable_item_response(_get_owned_variable_item(db, user, item.id))


@router.patch("/variable-expenses/{item_id}", response_model=VariableExpenseItemResponse)
def update_variable_expense(
    item_id: int,
    payload: VariableExpenseUpdateRequest,
    principal: Annotated[Principal, Depends(require_household_access("editor"))],
    db: Annotated[Session, Depends(get_db)],
) -> VariableExpenseItemResponse:
    user = principal.user
    item = _get_owned_variable_item(db, user, item_id)

    if "monthly_target" in payload.model_fields_set:
        # Flask edit_variable_expense_amount.
        monthly_target = parse_amount(payload.monthly_target or 0)
        if monthly_target <= 0:
            raise HTTPException(status_code=422, detail="Enter a positive planned cash amount.")
        item.amount = round(amount_for_monthly_target(monthly_target, item.frequency, planning_item_occurrence_multiplier(item)), 2)
        ensure_category_option(db, item.category_label or "Other", user)
        sync_planning_item_budget_target(db, item.category_label or "Other", user)
        db.commit()
        sync_monthly_plan(db, user, purpose="monthly_plan")
        return _variable_item_response(_get_owned_variable_item(db, user, item.id))

    # Flask edit_variable_expense.
    values = _variable_expense_values(payload)
    ensure_category_option(db, values["category_label"], user)
    for key, value in values.items():
        setattr(item, key, value)
    db.commit()
    sync_monthly_plan(db, user)
    return _variable_item_response(_get_owned_variable_item(db, user, item.id))


@router.delete("/variable-expenses/{item_id}", response_model=VariableExpenseDeleteResponse)
def delete_variable_expense(
    item_id: int,
    payload: VariableExpenseDeleteRequest,
    principal: Annotated[Principal, Depends(require_household_access("editor"))],
    db: Annotated[Session, Depends(get_db)],
) -> VariableExpenseDeleteResponse:
    user = principal.user
    item = _get_owned_variable_item(db, user, item_id)
    db.delete(item)
    db.commit()
    sync_monthly_plan(db, user)
    return VariableExpenseDeleteResponse(deleted_item_id=item_id)


# --- GET /v1/monthly-plan assembler ------------------------------------------
# Faithful port of Flask monthly_plan() (main.py at cb7d969, incl. the
# 64b5ed5/83ca1b6 handler changes). Web-URL plumbing (budget_url/review_url/
# edit-modal fields) is replaced by ids + anchor ids per route-map decision 17.
# Deferred seams, populated by their own sub-parts:
#   PHASE 3 (forecasts): forecast_months via build_three_month_forecast.
#   PHASE 3 (cash projections): the tools-section quick-cash summary.
#   PHASE 3 (loans/retirement): loan plans/scenarios, retirement accounts,
#     and budget_amortization_action rows.

BUDGET_SUGGESTION_FLASK_PARITY_KINDS = {"expense", "income", "cleanup"}


def _budget_progress(planned: float, actual: float) -> tuple[float, str]:
    progress_percent = min((actual / planned) * 100, 100) if planned > 0 else (100 if actual else 0)
    if planned > 0 and actual > planned:
        return progress_percent, "over"
    if planned > 0 and actual >= planned * 0.85:
        return progress_percent, "near"
    return progress_percent, "ok"


def _transaction_id_meta(transaction_ids) -> dict:
    ids = sorted({int(transaction_id) for transaction_id in transaction_ids if transaction_id})
    return {"transaction_ids": ids, "transaction_count": len(ids)}


def _with_anchor_meta(details: list[dict]) -> list[dict]:
    # Flask add_budget_links minus the web URLs: anchor + transaction counts.
    for detail in details:
        category_label = (detail.get("category_label") or detail.get("label") or "Other").strip()
        detail["budget_anchor"] = budget_anchor_for_label(category_label)
        ids = sorted({int(transaction_id) for transaction_id in detail.get("transaction_ids", []) if transaction_id})
        if ids:
            detail["transaction_ids"] = ids
            detail["transaction_count"] = len(ids)
    return details


def build_monthly_plan_response(
    db: Session,
    user: User,
    *,
    plan_view: str = "month",
    plan_section: str = "tools",
    budget_view: str = "list",
    budget_sort: str = "custom",
    quick_sort: str = "amount_desc",
    budget_month: str | None = None,
) -> MonthlyPlanResponse:
    profile = user.profile
    if plan_view not in {"month", "pay_period"}:
        plan_view = "month"
    if plan_section not in {"budgets", "baseline", "tools", "forecast"}:
        plan_section = "tools"
    if budget_view not in {"list", "grouped"}:
        budget_view = "list"
    budget_grouped = budget_view == "grouped"
    if budget_sort not in BUDGET_SORT_OPTIONS:
        budget_sort = "custom"
    budget_drag_enabled = budget_sort == "custom"
    if quick_sort not in QUICK_WORKSHEET_SORT_OPTIONS:
        quick_sort = "amount_desc"

    current_budget_month = current_budget_month_start()
    selected_budget_month = current_budget_month
    if plan_section == "budgets" and (budget_month or "").strip():
        try:
            requested_month = parse_month_input(budget_month.strip())
        except ValueError:
            requested_month = current_budget_month
        if requested_month <= current_budget_month:
            selected_budget_month = requested_month
    budget_is_current_month = selected_budget_month == current_budget_month
    budget_history_mode = plan_section == "budgets" and not budget_is_current_month
    budget_drag_enabled = budget_drag_enabled and budget_is_current_month

    if plan_section == "baseline" and not user_has_feature(user, "income_planning"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "feature_locked",
                "feature": "income_planning",
                "message": f"Income Planning is available on ClearPath {feature_min_plan_label('income_planning')} or higher.",
            },
        )

    plan = get_or_create_monthly_plan(db, user)
    month_income_actual = recorded_month_income(db, user)
    month_income_recorded = month_income_actual or plan.income
    tax_estimate = calculate_tax_estimate(profile)
    taxes_enabled = (profile.income_basis or "take_home") == "gross" if profile else False
    fixed_total = fixed_expense_total(db, user)
    variable_plan_total = variable_expense_plan_total(db, user)
    retirement_contribution = retirement_cash_flow_contribution(profile)
    loan_extra_total = selected_loan_extra_payment_total(db, user)
    effective_debt_payment = plan.planned_debt_payment + loan_extra_total
    pay_period = current_pay_period_bounds(profile, app_today())

    if plan_view == "pay_period":
        period_start = pay_period["start"]
        period_end = pay_period["end"]
        period_income = planned_income_for_period(profile, period_start, period_end)
        income_details = income_plan_detail_rows(db, user, period_income, start_date=period_start, end_date=period_end)
        fixed_details = _with_anchor_meta(fixed_plan_detail_rows(db, user, start_date=period_start, end_date=period_end))
        variable_details = _with_anchor_meta(variable_plan_detail_rows(db, user, start_date=period_start, end_date=period_end))
        period_income = sum(row["planned"] for row in income_details)
        period_income_actual = sum(row["actual"] for row in income_details)
        actual_fixed_total = sum(row["actual"] for row in fixed_details)
        period_variable_actual = sum(row["actual"] for row in variable_details)
        period_fixed_total = sum(row["planned"] for row in fixed_details)
        period_variable_total = sum(row["planned"] for row in variable_details)
        period_expense_details = sorted(fixed_details + variable_details, key=lambda row: (row.get("actual", 0) + row.get("planned", 0)), reverse=True)
        period_expense_total = period_fixed_total + period_variable_total
        period_expense_actual = actual_fixed_total + period_variable_actual
        period_days = (period_end - period_start).days + 1
        month_start, month_end = app_today().replace(day=1), app_today().replace(day=calendar.monthrange(app_today().year, app_today().month)[1])
        month_days = (month_end - month_start).days + 1
        period_savings = plan.planned_savings * (period_days / month_days)
        period_debt_payment = effective_debt_payment * (period_days / month_days)
        period_retirement = retirement_contribution * (period_days / month_days)
        period_tax_total = tax_estimate.monthly_total * (period_days / month_days) if taxes_enabled else 0
        plan_income_total = period_income
        plan_tax_total = period_tax_total
        plan_savings_total = period_savings
        plan_debt_total = period_debt_payment
        plan_retirement_total = period_retirement
        # FLASK BUG (flagged 2026-07-14, pending Flask fix): Flask never
        # assigns actual_income_total in the pay-period branch, so the income
        # budget row raises UnboundLocalError (main.py:5147 at cb7d969) on
        # view=pay_period. No Flask test covers that path. Provisional
        # behavior: use the period's recorded income; reconcile when Flask
        # lands its fix.
        actual_income_total = period_income_actual
        actual_debt_paydown = credit_card_debt_paydown_between(db, user, period_start, period_end)
        actual_savings = max(period_income_actual - actual_fixed_total - period_variable_actual - actual_debt_paydown, 0)
        planned_available = period_income - period_tax_total - period_fixed_total - period_variable_total - period_savings - period_debt_payment - period_retirement
        budget_remaining = (period_fixed_total + period_variable_total + period_tax_total) - (actual_fixed_total + period_variable_actual)
        expected_cash_flow = planned_available
        tax_row = {"label": "Taxes", "planned": period_tax_total, "actual": 0, "type": "expense", "details": tax_plan_detail_rows(tax_estimate, period_days / month_days)}
        plan_rows = [
            {"label": "Pay Period Income", "planned": period_income, "actual": period_income_actual, "type": "income", "details": income_details},
            {"label": "Expenses", "planned": period_expense_total, "actual": period_expense_actual, "type": "expense", "details": period_expense_details},
            {"label": "Savings", "planned": period_savings, "actual": actual_savings, "type": "expense"},
            {"label": "Debt Paydown", "planned": period_debt_payment, "actual": actual_debt_paydown, "type": "expense"},
        ]
        if profile and profile.retirement_enabled:
            plan_rows.append({"label": "Retirement Contribution", "planned": period_retirement, "actual": 0, "type": "expense"})
        if taxes_enabled:
            plan_rows.insert(1, tax_row)
    else:
        income_details = income_plan_detail_rows(db, user, plan.income)
        fixed_details = _with_anchor_meta(fixed_plan_detail_rows(db, user))
        variable_details = _with_anchor_meta(variable_plan_detail_rows(db, user))
        planned_income_total = sum(row["planned"] for row in income_details)
        actual_income_total = sum(row["actual"] for row in income_details)
        actual_fixed_total = sum(row["actual"] for row in fixed_details)
        actual_variable_total = sum(row["actual"] for row in variable_details)
        planned_fixed_total = sum(row["planned"] for row in fixed_details)
        planned_variable_total = sum(row["planned"] for row in variable_details)
        planned_expense_total = planned_fixed_total + planned_variable_total
        actual_expense_total = actual_fixed_total + actual_variable_total
        expense_details = sorted(fixed_details + variable_details, key=lambda row: (row.get("actual", 0) + row.get("planned", 0)), reverse=True)
        month_start, month_end = app_today().replace(day=1), app_today().replace(day=calendar.monthrange(app_today().year, app_today().month)[1])
        actual_debt_paydown = credit_card_debt_paydown_between(db, user, month_start, month_end)
        actual_savings = max(actual_income_total - actual_fixed_total - actual_variable_total - actual_debt_paydown, 0)
        monthly_tax_total = tax_estimate.monthly_total if taxes_enabled else 0
        plan_income_total = planned_income_total
        plan_tax_total = monthly_tax_total
        plan_savings_total = plan.planned_savings
        plan_debt_total = effective_debt_payment
        plan_retirement_total = retirement_contribution
        planned_available = planned_income_total - monthly_tax_total - planned_fixed_total - plan.planned_savings - effective_debt_payment - planned_variable_total - retirement_contribution
        budget_remaining = (planned_fixed_total + planned_variable_total + monthly_tax_total) - (actual_fixed_total + actual_variable_total)
        expected_cash_flow = planned_available
        tax_row = {"label": "Taxes", "planned": monthly_tax_total, "actual": 0, "type": "expense", "details": tax_plan_detail_rows(tax_estimate)}
        plan_rows = [
            {"label": "Monthly Income", "planned": planned_income_total, "actual": actual_income_total, "type": "income", "details": income_details},
            {"label": "Expenses", "planned": planned_expense_total, "actual": actual_expense_total, "type": "expense", "details": expense_details},
            {"label": "Savings", "planned": plan.planned_savings, "actual": actual_savings, "type": "expense"},
            {"label": "Debt Paydown", "planned": effective_debt_payment, "actual": actual_debt_paydown, "type": "expense"},
        ]
        if profile and profile.retirement_enabled:
            plan_rows.append({"label": "Retirement Contribution", "planned": retirement_contribution, "actual": 0, "type": "expense"})
        if taxes_enabled:
            plan_rows.insert(1, tax_row)

    category_spend = spending_by_category(db, user, purpose="monthly_plan")
    # PHASE 3 (forecasts): build_three_month_forecast ports with the forecast
    # sub-part; until then section=forecast returns an empty list.
    forecast_months: list[dict] = []

    fixed_items = sorted(
        db.scalars(select(FixedExpenseItem).where(FixedExpenseItem.user_id == user.id)).all(),
        key=monthly_amount_for_fixed_item,
        reverse=True,
    )
    variable_items = db.scalars(select(VariableExpenseItem).where(VariableExpenseItem.user_id == user.id)).all()
    variable_item_rows = sorted(
        [{"item": item, "monthly_amount": monthly_amount_for_variable_item(item)} for item in variable_items],
        key=lambda row: row["monthly_amount"],
        reverse=True,
    )

    budget_start = selected_budget_month if plan_section == "budgets" else current_budget_month
    budget_end = budget_start.replace(day=calendar.monthrange(budget_start.year, budget_start.month)[1])

    budget_rows: list[dict] = []
    suggested_budget_rows: list[dict] = []
    if budget_history_mode:
        for snapshot_row in monthly_budget_category_snapshots_for_user(db, user, selected_budget_month, purpose="monthly_plan"):
            if snapshot_row.category_kind not in BUDGET_SUGGESTION_FLASK_PARITY_KINDS:
                continue
            planned = max(snapshot_row.planned or 0, 0)
            actual = max(snapshot_row.actual or 0, 0)
            progress_percent, progress_status = _budget_progress(planned, actual)
            label = snapshot_row.category_name or "Other"
            anchor_id = budget_anchor_for_label(label)
            try:
                transaction_ids = json.loads(snapshot_row.transaction_ids_json or "[]")
            except (TypeError, ValueError):
                transaction_ids = []
            transaction_meta = _transaction_id_meta(transaction_ids)
            actual_label = "spent"
            planned_label = "planned"
            if snapshot_row.category_kind == "income":
                if not budget_row_is_canonical_income(label):
                    continue
                actual_label = "recorded" if transaction_ids else "from setup"
            elif snapshot_row.category_kind == "cleanup":
                actual_label = "needs review"
                planned_label = "not budgeted"
            budget_rows.append(
                {
                    "kind": "category",
                    "category_kind": snapshot_row.category_kind or "expense",
                    "category_id": snapshot_row.category_id,
                    "label": label,
                    "category": label,
                    "group_key": snapshot_row.group_key or budget_category_group_for_label(label)["key"],
                    "planned": planned,
                    "actual": actual,
                    "remaining": planned - actual,
                    "progress_percent": progress_percent,
                    "progress_status": progress_status,
                    "anchor_id": anchor_id,
                    "suggestion_match_count": 0,
                    "sort_order": snapshot_row.sort_order,
                    "can_remove_budget": False,
                    "amortization_action": None,
                    "actual_label": actual_label,
                    "planned_label": planned_label,
                    **transaction_meta,
                }
            )
    else:
        transactions_by_category = defaultdict(list)
        current_month_expense_transactions = db.scalars(
            select(Transaction)
            .options(joinedload(Transaction.category), joinedload(Transaction.account))
            .where(
                Transaction.user_id == user.id,
                Transaction.posted_date >= budget_start,
                Transaction.posted_date <= budget_end,
                Transaction.amount < 0,
            )
            .order_by(Transaction.posted_date.desc(), Transaction.id.desc())
        ).all()
        for allocation in transaction_category_allocations_for_period(db, user, budget_start, budget_end, purpose="monthly_plan"):
            label = allocation["category_name"] or "Other"
            transactions_by_category[normalize_text(label.strip() or "Other")].append(allocation)

        budget_categories = {normalize_text(category.name): category for category in categories_for_user(db, user)}
        active_budget_categories = active_budget_categories_by_key(db, user)
        suggestion_candidates = [transaction for transaction in current_month_expense_transactions if budget_suggestion_candidate(transaction)]
        suggestion_matches_by_label = {
            normalized_label: [
                transaction
                for transaction in suggestion_candidates
                if transaction_matches_budget_category(transaction, category.name)
            ]
            for normalized_label, category in budget_categories.items()
            if category.kind == "expense"
        }
        suggested_category_keys = {
            normalized_label
            for normalized_label, category in budget_categories.items()
            if category.kind == "expense" and category.user_id == user.id and category.is_default
        }
        budget_labels = set(active_budget_categories.keys()) | suggested_category_keys
        cleanup_allocations = [
            allocation
            for normalized_label, allocations in transactions_by_category.items()
            if normalized_label not in active_budget_categories
            for allocation in allocations
        ]
        for normalized_label in sorted(budget_labels):
            category = budget_categories.get(normalized_label)
            allocations = transactions_by_category.get(normalized_label, [])
            label = category.name if category else ((allocations[0]["category_name"] if allocations else "Other") or "Other")
            category_kind = category.kind if category else "expense"
            if category and category_kind not in {"expense", "income"}:
                continue

            is_income_budget = category_kind == "income"
            if is_income_budget and not budget_row_is_canonical_income(label):
                continue
            planned = max(category.monthly_target if category else 0, 0)
            actual = sum(allocation["amount"] for allocation in allocations)
            actual_label = "spent"
            if is_income_budget:
                planned = max(planned, plan_income_total)
                actual = actual_income_total if actual_income_total > 0 else plan_income_total
                actual_label = "recorded" if actual_income_total > 0 else "from setup"
            group = budget_category_group_for_row(category, label)
            group_key = "income" if is_income_budget else group["key"]
            progress_percent, progress_status = _budget_progress(planned, actual)
            anchor_id = budget_anchor_for_label(label)
            matched_suggestion_transactions = suggestion_matches_by_label.get(normalized_label, [])
            transaction_meta = _transaction_id_meta(allocation["transaction_id"] for allocation in allocations)
            suggestion_transaction_meta = _transaction_id_meta(transaction.id for transaction in matched_suggestion_transactions)
            row = {
                "kind": "category",
                "category_kind": category_kind,
                "category_id": category.id if category and not is_income_budget else None,
                "label": label,
                "category": label,
                "group_key": group_key,
                "planned": planned,
                "actual": actual,
                "remaining": planned - actual,
                "progress_percent": progress_percent,
                "progress_status": progress_status,
                "anchor_id": anchor_id,
                "adjust_label": "Adjust Income" if is_income_budget else "",
                "suggestion_match_count": len(matched_suggestion_transactions),
                "sort_order": category.budget_sort_order if category else None,
                "can_remove_budget": bool(
                    category
                    and not is_income_budget
                    and category_can_manage(db, category, user)
                    and category.name.strip().lower() != "other"
                ),
                # PHASE 3 (loans): budget_amortization_action (fc97040).
                "amortization_action": None,
                "actual_label": actual_label,
                "planned_label": "planned",
                **transaction_meta,
            }
            is_unused_default_budget_category = bool(
                category
                and category.user_id == user.id
                and category.is_default
                and not allocations
                and not is_income_budget
            )
            if is_unused_default_budget_category and matched_suggestion_transactions:
                row.update(suggestion_transaction_meta)
                suggested_budget_rows.append(row)
            elif is_unused_default_budget_category:
                continue
            elif normalized_label not in active_budget_categories:
                continue
            else:
                budget_rows.append(row)
        if cleanup_allocations:
            cleanup_meta = _transaction_id_meta(allocation["transaction_id"] for allocation in cleanup_allocations)
            cleanup_actual = sum(allocation["amount"] for allocation in cleanup_allocations)
            budget_rows.append(
                {
                    "kind": "cleanup",
                    "category_kind": "cleanup",
                    "category_id": None,
                    "label": "Other Spending To Categorize",
                    "category": "Other Spending To Categorize",
                    "group_key": "miscellaneous",
                    "planned": 0,
                    "actual": cleanup_actual,
                    "remaining": -cleanup_actual,
                    "progress_percent": 100 if cleanup_actual else 0,
                    "progress_status": "over" if cleanup_actual else "ok",
                    "anchor_id": "budget-other-spending-cleanup",
                    "suggestion_match_count": 0,
                    "sort_order": None,
                    "can_remove_budget": False,
                    "amortization_action": None,
                    "actual_label": "needs review",
                    "planned_label": "not budgeted",
                    **cleanup_meta,
                }
            )

    all_budget_rows = budget_rows
    income_budget_rows = [row for row in all_budget_rows if row.get("category_kind") == "income"]
    cleanup_budget_rows = [row for row in all_budget_rows if row.get("category_kind") == "cleanup"]
    expense_budget_rows = [row for row in all_budget_rows if row.get("category_kind") not in {"income", "cleanup"}]
    if plan_section == "budgets" and budget_is_current_month:
        monthly_budget_category_snapshots_for_user(db, user, selected_budget_month, purpose="monthly_plan")

    def sort_budget_rows(rows: list[dict]) -> list[dict]:
        if budget_sort == "amount_desc":
            return sorted(rows, key=lambda row: (-row["planned"], row["category"].lower()))
        if budget_sort == "amount_asc":
            return sorted(rows, key=lambda row: (row["planned"], row["category"].lower()))
        if budget_sort == "category_az":
            return sorted(rows, key=lambda row: row["category"].lower())
        if budget_sort == "category_za":
            return sorted(rows, key=lambda row: row["category"].lower(), reverse=True)
        return sorted(
            rows,
            key=lambda row: (
                row["sort_order"] is None,
                row["sort_order"] if row["sort_order"] is not None else 0,
                row["category"].lower(),
            ),
        )

    def budget_section_for_rows(group_rows: list[dict], label: str, kind: str, description: str, empty: str) -> dict:
        transaction_meta = _transaction_id_meta(
            transaction_id
            for budget_row in group_rows
            for transaction_id in budget_row.get("transaction_ids", [])
        )
        return {
            "label": label,
            "kind": kind,
            "description": description,
            "empty": empty,
            "rows": group_rows,
            "planned": sum(row["planned"] for row in group_rows),
            "actual": sum(row["actual"] for row in group_rows),
            **transaction_meta,
        }

    budget_sections: list[dict] = []
    if income_budget_rows:
        budget_sections.append(
            budget_section_for_rows(
                sort_budget_rows(income_budget_rows),
                "Income",
                "income",
                "Income recorded from setup and adjusted from Income Planning.",
                "No income budget is recorded yet.",
            )
        )

    if budget_grouped:
        for group in STARTER_CATEGORY_GROUPS:
            group_rows = sort_budget_rows([row for row in expense_budget_rows if row["group_key"] == group["key"]])
            budget_sections.append(
                budget_section_for_rows(
                    group_rows,
                    group["label"],
                    group["key"],
                    group["description"],
                    "No category budgets in this group yet.",
                )
            )
    elif expense_budget_rows:
        budget_sections.append(
            budget_section_for_rows(
                sort_budget_rows(expense_budget_rows),
                "Expense Budgets",
                "list",
                "A read-only view of the expense categories and amounts captured for this month." if budget_history_mode else "A single list for reviewing and adjusting each expense budget one by one.",
                "No historical budget categories were captured for this month." if budget_history_mode else "No category budgets yet.",
            )
        )
    suggested_budget_sections: list[dict] = []
    if budget_grouped:
        for group in STARTER_CATEGORY_GROUPS:
            group_rows = sort_budget_rows([row for row in suggested_budget_rows if row["group_key"] == group["key"]])
            if not group_rows:
                continue
            suggested_budget_sections.append({"label": group["label"], "kind": group["key"], "rows": group_rows})
    elif suggested_budget_rows:
        suggested_budget_sections.append({"label": "Suggestions", "kind": "list", "rows": sort_budget_rows(suggested_budget_rows)})

    unassigned_budget_rows = cleanup_budget_rows
    total_budget_planned = sum(row["planned"] for row in expense_budget_rows)
    total_unassigned_actual = sum(row["actual"] for row in unassigned_budget_rows)
    total_budget_actual = sum(row["actual"] for row in expense_budget_rows) + total_unassigned_actual
    total_budget_remaining = total_budget_planned - total_budget_actual
    budget_detail_rows = [
        {
            "label": row["category"],
            "planned": row["planned"],
            "actual": row["actual"],
            "diff": row["actual"] - row["planned"],
            "source": "budget_category",
            "budget_anchor": row["anchor_id"],
            "transaction_ids": row.get("transaction_ids", []),
            "transaction_count": row.get("transaction_count", 0),
        }
        for row in expense_budget_rows
    ]
    budget_detail_rows.extend(
        {
            "label": row["category"],
            "planned": row["planned"],
            "actual": row["actual"],
            "diff": row["actual"] - row["planned"],
            "source": "budget_cleanup",
            "budget_anchor": row["anchor_id"],
            "transaction_ids": row.get("transaction_ids", []),
            "transaction_count": row.get("transaction_count", 0),
        }
        for row in unassigned_budget_rows
    )
    if budget_detail_rows:
        for row in plan_rows:
            if row["label"] == "Expenses":
                row["planned"] = total_budget_planned
                row["actual"] = total_budget_actual
                row["details"] = budget_detail_rows
                break
        planned_available = plan_income_total - plan_tax_total - total_budget_planned - plan_savings_total - plan_debt_total - plan_retirement_total
        budget_remaining = total_budget_remaining
        expected_cash_flow = planned_available

    forecast_item_rows = sorted(
        db.scalars(select(ForecastItem).where(ForecastItem.user_id == user.id)).all(),
        key=lambda item: (item.amount, item.item_date),
        reverse=True,
    )
    recurring_templates = sorted(
        db.scalars(select(RecurringForecastTemplate).where(RecurringForecastTemplate.user_id == user.id)).all(),
        key=lambda template: (template.amount, template.start_date),
        reverse=True,
    )
    future_income_templates = sorted(
        [template for template in recurring_templates if template.item_type == "income"],
        key=lambda template: (template.start_date, template.id),
    )
    fixed_forecast_expense_items = [template for template in recurring_templates if template.item_type == "expense"]
    variable_forecast_expense_items = [item for item in forecast_item_rows if item.item_type == "expense"]
    from app.services.subscription_service import active_subscription_rows

    subscription_rows = active_subscription_rows(db, user, purpose="monthly_plan")
    subscription_total = sum(row["amount"] for row in subscription_rows)
    fixed_expense_rows = [
        {"source": "worksheet", "item": item, "amount": monthly_amount_for_fixed_item(item)}
        for item in fixed_items
    ] + [
        {"source": "forecast", "item": item, "amount": recurring_template_monthly_amount(item)}
        for item in fixed_forecast_expense_items
    ] + ([
        {"source": "subscriptions", "items": subscription_rows, "amount": subscription_total}
    ] if subscription_total else [])
    variable_expense_rows = [
        {"source": "worksheet", "row": row, "amount": row["monthly_amount"]}
        for row in variable_item_rows
    ] + [
        {"source": "forecast", "item": item, "amount": item.amount}
        for item in variable_forecast_expense_items
    ]

    def quick_timing_label(item, fallback: str = "This Month") -> str:
        frequency = getattr(item, "frequency", "")
        label = RECURRING_FREQUENCY_OPTIONS.get(frequency, (frequency or fallback).title())
        start_date = getattr(item, "start_date", None) or getattr(item, "specific_date", None) or getattr(item, "item_date", None)
        if start_date:
            return f"{label} starting {start_date.strftime('%b %d')}"
        return label

    def quick_row_sort_key(row: dict) -> tuple:
        if quick_sort == "amount_asc":
            return (row["amount"], row["name"].lower())
        if quick_sort == "name_asc":
            return (row["name"].lower(), row["amount"])
        if quick_sort == "name_desc":
            return (row["name"].lower(), row["amount"])
        if quick_sort == "timing_asc":
            return (row["timing_order"], row["name"].lower())
        if quick_sort == "timing_desc":
            return (row["timing_order"], row["name"].lower())
        if quick_sort == "category_az":
            return (row["category"].lower(), row["name"].lower())
        if quick_sort == "category_za":
            return (row["category"].lower(), row["name"].lower())
        return (row["amount"], row["name"].lower())

    quick_worksheet_rows = []
    for row in fixed_expense_rows:
        if row["source"] == "worksheet":
            item = row["item"]
            quick_worksheet_rows.append(
                {
                    "name": item.name,
                    "subtitle": "Fixed expense",
                    "timing": quick_timing_label(item),
                    "timing_order": item.start_date or date.max,
                    "category": item.category_label or "Other",
                    "amount": row["amount"],
                    "action_label": "Edit",
                    "readonly": False,
                    "item_type": "fixed_expense",
                    "item_id": item.id,
                }
            )
        elif row["source"] == "subscriptions":
            quick_worksheet_rows.append(
                {
                    "name": "Monthly Subscriptions",
                    "subtitle": f"{len(row['items'])} active subscriptions",
                    "timing": "Recurring",
                    "timing_order": date.max,
                    "category": "Consumer Subscriptions",
                    "amount": row["amount"],
                    "action_label": "Review",
                    "readonly": True,
                    "item_type": "subscriptions",
                    "item_id": None,
                }
            )
        else:
            template = row["item"]
            quick_worksheet_rows.append(
                {
                    "name": template.name,
                    "subtitle": "Recurring forecast item",
                    "timing": quick_timing_label(template),
                    "timing_order": template.start_date or date.max,
                    "category": template.category_label or "Other",
                    "amount": row["amount"],
                    "action_label": "Edit",
                    "readonly": False,
                    "item_type": "recurring_template",
                    "item_id": template.id,
                }
            )
    for row in variable_expense_rows:
        if row["source"] == "worksheet":
            item = row["row"]["item"]
            timing_order = item.specific_date if item.use_specific_date and item.specific_date else date.max
            quick_worksheet_rows.append(
                {
                    "name": item.name,
                    "subtitle": "Flexible budget",
                    "timing": quick_timing_label(item),
                    "timing_order": timing_order,
                    "category": item.category_label or "Other",
                    "amount": row["amount"],
                    "action_label": "Edit",
                    "readonly": False,
                    "item_type": "variable_expense",
                    "item_id": item.id,
                }
            )
        else:
            item = row["item"]
            quick_worksheet_rows.append(
                {
                    "name": item.description,
                    "subtitle": "One-time forecast item",
                    "timing": item.item_date.strftime("%b %d") if item.item_date else "This Month",
                    "timing_order": item.item_date or date.max,
                    "category": item.category_label or "Other",
                    "amount": row["amount"],
                    "action_label": "Edit",
                    "readonly": True,
                    "item_type": "forecast_item",
                    "item_id": item.id,
                }
            )
    reverse_quick_sort = quick_sort in {"amount_desc", "name_desc", "timing_desc", "category_za"}
    quick_worksheet_rows = sorted(quick_worksheet_rows, key=quick_row_sort_key, reverse=reverse_quick_sort)

    profile_response = BaselineProfileResponse.model_validate(profile) if profile else BaselineProfileResponse()
    profile_response.household_name = user.household_name
    profile_response.income_amount_display = (
        annual_salary_from_profile(profile) if profile and (profile.income_type or "salary") == "salary" else (profile.income_amount if profile else None)
    )

    def fixed_item_response(item: FixedExpenseItem) -> FixedExpenseItemResponse:
        response = FixedExpenseItemResponse.model_validate(item)
        response.monthly_amount = monthly_amount_for_fixed_item(item)
        return response

    def variable_item_response(row: dict) -> VariableExpenseItemResponse:
        response = VariableExpenseItemResponse.model_validate(row["item"])
        response.monthly_amount = row["monthly_amount"]
        return response

    def template_response(template: RecurringForecastTemplate) -> RecurringForecastTemplateResponse:
        response = RecurringForecastTemplateResponse.model_validate(template)
        response.monthly_amount = recurring_template_monthly_amount(template)
        return response

    def expense_source_row(row: dict) -> ExpenseSourceRowResponse:
        if row["source"] == "subscriptions":
            return ExpenseSourceRowResponse(source="subscriptions", amount=row["amount"], item_type="subscriptions", subscription_count=len(row["items"]))
        if "row" in row:
            return ExpenseSourceRowResponse(source=row["source"], amount=row["amount"], item_type="variable_expense", item_id=row["row"]["item"].id)
        item = row["item"]
        if isinstance(item, RecurringForecastTemplate):
            item_type = "recurring_template"
        elif isinstance(item, ForecastItem):
            item_type = "forecast_item"
        else:
            item_type = "fixed_expense"
        return ExpenseSourceRowResponse(source=row["source"], amount=row["amount"], item_type=item_type, item_id=item.id)

    return MonthlyPlanResponse(
        profile=profile_response,
        plan=MonthlyPlanRecordResponse.model_validate(plan),
        month_income_recorded=month_income_recorded,
        actual_savings=actual_savings,
        month_name=current_month_name(),
        today=app_today(),
        plan_view=plan_view,
        plan_section=plan_section,
        pay_period=PayPeriodResponse(**pay_period),
        plan_rows=[PlanRowResponse(**row) for row in plan_rows],
        category_spend=[CategorySpendRowResponse(**row) for row in category_spend],
        forecast_months=forecast_months,
        fixed_items=[fixed_item_response(item) for item in fixed_items],
        variable_items=[variable_item_response(row) for row in variable_item_rows],
        fixed_expense_rows=[expense_source_row(row) for row in fixed_expense_rows],
        variable_expense_rows=[expense_source_row(row) for row in variable_expense_rows],
        quick_worksheet_rows=[QuickWorksheetRowResponse(**{key: value for key, value in row.items() if key != "timing_order"}) for row in quick_worksheet_rows],
        forecast_items=[ForecastItemResponse.model_validate(item) for item in forecast_item_rows],
        recurring_templates=[template_response(template) for template in recurring_templates],
        future_income_templates=[template_response(template) for template in future_income_templates],
        category_label_options=category_label_options_for_user(db, user),
        fixed_total=fixed_total,
        variable_plan_total=variable_plan_total,
        retirement_contribution=retirement_contribution,
        loan_extra_total=loan_extra_total,
        effective_debt_payment=effective_debt_payment,
        tax_estimate=TaxEstimateResponse.model_validate(tax_estimate),
        taxes_enabled=taxes_enabled,
        planned_available=planned_available,
        budget_remaining=budget_remaining,
        budget_sections=[BudgetSectionResponse(**{**section, "rows": [BudgetRowResponse(**row) for row in section["rows"]]}) for section in budget_sections],
        suggested_budget_sections=[
            SuggestedBudgetSectionResponse(label=section["label"], kind=section["kind"], rows=[BudgetRowResponse(**row) for row in section["rows"]])
            for section in suggested_budget_sections
        ],
        unassigned_budget_rows=[BudgetRowResponse(**row) for row in unassigned_budget_rows],
        budget_view=budget_view,
        budget_grouped=budget_grouped,
        budget_sort=budget_sort,
        budget_drag_enabled=budget_drag_enabled,
        budget_selected_month=selected_budget_month,
        budget_current_month=current_budget_month,
        budget_month_value=selected_budget_month.strftime("%Y-%m"),
        budget_month_label=selected_budget_month.strftime("%B %Y"),
        budget_is_current_month=budget_is_current_month,
        budget_history_mode=budget_history_mode,
        total_budget_planned=total_budget_planned,
        total_budget_actual=total_budget_actual,
        total_budget_remaining=total_budget_remaining,
        expected_cash_flow=expected_cash_flow,
        quick_sort=quick_sort,
        budget_sort_options=BUDGET_SORT_OPTIONS,
        quick_sort_options=QUICK_WORKSHEET_SORT_OPTIONS,
        income_type_options=INCOME_TYPE_OPTIONS,
        income_basis_options=INCOME_BASIS_OPTIONS,
        paycheck_cadence_options=PAYCHECK_CADENCE_OPTIONS,
        tax_filing_status_options=TAX_FILING_STATUS_OPTIONS,
        state_options=STATE_OPTIONS,
        recurring_frequency_options=RECURRING_FREQUENCY_OPTIONS,
        weekday_options=WEEKDAY_OPTIONS,
        monthly_week_options=MONTHLY_WEEK_OPTIONS,
        budget_group_options=[
            {"key": group["key"], "label": group["label"], "description": group["description"]}
            for group in STARTER_CATEGORY_GROUPS
        ],
    )


@router.get("/monthly-plan", response_model=MonthlyPlanResponse)
def get_monthly_plan(
    principal: Annotated[Principal, Depends(require_household_access("viewer"))],
    db: Annotated[Session, Depends(get_db)],
    view: str = "month",
    section: str = "tools",
    budget_view: str = "list",
    budget_sort: str = "custom",
    quick_sort: str = "amount_desc",
    budget_month: str = "",
) -> MonthlyPlanResponse:
    # Route-map decision 5: GET reads never trigger the Flask page-load Plaid
    # refresh; clients call POST /v1/plaid-items/refresh-stale explicitly.
    require_onboarding_complete(principal.user)
    return build_monthly_plan_response(
        db,
        principal.user,
        plan_view=view,
        plan_section=section,
        budget_view=budget_view,
        budget_sort=budget_sort,
        quick_sort=quick_sort,
        budget_month=budget_month or None,
    )


@router.patch("/monthly-plan/baseline", response_model=MonthlyPlanResponse)
def update_monthly_plan_baseline(
    payload: MonthlyPlanBaselineUpdateRequest,
    principal: Annotated[Principal, Depends(require_household_access("editor"))],
    db: Annotated[Session, Depends(get_db)],
) -> MonthlyPlanResponse:
    user = principal.user
    require_onboarding_complete(user)
    profile = user.profile
    provided = payload.model_fields_set

    is_core_baseline_update = payload.baseline_scope == "core"
    if not user_has_feature(user, "income_planning") and not is_core_baseline_update:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "feature_locked",
                "feature": "income_planning",
                "message": f"Income Planning is available on ClearPath {feature_min_plan_label('income_planning')} or higher.",
            },
        )

    if "household_name" in provided:
        user.household_name = (payload.household_name or "").strip() or user.household_name
    if "income_amount" in provided:
        profile.income_amount = parse_amount(payload.income_amount or 0)
    if "income_basis" in provided:
        income_basis = (payload.income_basis or "").strip()
        if income_basis in INCOME_BASIS_OPTIONS:
            profile.income_basis = income_basis
    if "income_type" in provided:
        income_type = (payload.income_type or "").strip()
        if income_type in INCOME_TYPE_OPTIONS:
            profile.income_type = income_type
    if "paycheck_cadence" in provided:
        paycheck_cadence = (payload.paycheck_cadence or "").strip()
        if paycheck_cadence in PAYCHECK_CADENCE_OPTIONS:
            profile.paycheck_cadence = paycheck_cadence
            profile.income_frequency = profile.paycheck_cadence
    if "next_pay_date" in provided:
        raw_next_pay_date = (payload.next_pay_date or "").strip()
        try:
            profile.next_pay_date = parse_flexible_date(raw_next_pay_date) if raw_next_pay_date else None
        except ValueError:
            profile.next_pay_date = None
    if "paycheck_cadence" in provided:
        raw_second_date = (payload.second_date or "").strip()
        try:
            second_date = parse_flexible_date(raw_second_date) if raw_second_date else None
        except ValueError:
            second_date = None
        timing = paycheck_timing_values(
            profile.paycheck_cadence,
            profile.next_pay_date,
            second_date,
            payload.recurring_days_of_week,
            payload.recurring_monthly_week_numbers,
            payload.recurring_monthly_weekday,
        )
        for key, value in timing.items():
            setattr(profile, key, value)
    if "hourly_hours_per_week" in provided:
        profile.hourly_hours_per_week = parse_amount(payload.hourly_hours_per_week or 40) if profile.income_type == "hourly" else 40
    if "additional_income_amount" in provided:
        profile.additional_income_amount = parse_amount(payload.additional_income_amount or 0)
    if "additional_income_frequency" in provided:
        additional_income_frequency = (payload.additional_income_frequency or "").strip()
        if additional_income_frequency in RECURRING_FREQUENCY_OPTIONS:
            profile.additional_income_frequency = additional_income_frequency
    if "variable_expenses" in provided:
        profile.variable_expenses = parse_amount(payload.variable_expenses or 0)
    profile.monthly_income = monthly_income_from_profile(profile)
    if "tax_state" in provided:
        tax_state = (payload.tax_state or "").strip().upper()
        if tax_state in STATE_OPTIONS and tax_state:
            profile.tax_state = tax_state
    if "tax_filing_status" in provided:
        tax_filing_status = (payload.tax_filing_status or "").strip()
        if tax_filing_status in TAX_FILING_STATUS_OPTIONS:
            profile.tax_filing_status = tax_filing_status
    if "tax_additional_label" in provided:
        profile.tax_additional_label = (payload.tax_additional_label or "").strip() or "Additional Local Tax"
    if "tax_additional_type" in provided:
        tax_additional_type = (payload.tax_additional_type or "").strip()
        if tax_additional_type in {"amount", "percent"}:
            profile.tax_additional_type = tax_additional_type
    if "tax_additional_rate" in provided:
        profile.tax_additional_rate = max(parse_amount(payload.tax_additional_rate or 0), 0)
    if "tax_additional_monthly_amount" in provided:
        profile.tax_additional_monthly_amount = max(parse_amount(payload.tax_additional_monthly_amount or 0), 0)
    if "include_payroll_taxes" in provided and payload.include_payroll_taxes is not None:
        profile.include_payroll_taxes = payload.include_payroll_taxes
    if "planned_savings_contribution" in provided:
        profile.planned_savings_contribution = parse_amount(payload.planned_savings_contribution or 0)
    if "planned_debt_payment" in provided:
        submitted_debt_target = parse_amount(payload.planned_debt_payment or 0)
        profile.planned_debt_payment = max(submitted_debt_target - selected_loan_extra_payment_total(db, user), 0)
    if "target_investment_contribution" in provided:
        profile.target_investment_contribution = parse_amount(payload.target_investment_contribution or 0)
    if "notes" in provided:
        profile.notes = (payload.notes or "").strip()
    db.commit()
    sync_monthly_plan(db, user, purpose="monthly_plan")
    return build_monthly_plan_response(db, user, plan_view=payload.view, plan_section=payload.section)

