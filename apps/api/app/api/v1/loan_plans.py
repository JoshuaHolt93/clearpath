from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.feature_access import feature_min_plan_label, user_has_feature
from app.dependencies import Principal, require_household_access
from app.models import FixedExpenseItem, LoanPlan, User
from app.schemas.loan_plans import (
    LoanPlanListResponse,
    LoanPlanRecordResponse,
    LoanPlanResponse,
    LoanPlanScenarioResponse,
    LoanPlanScenarioSelectRequest,
    LoanPlanSummaryResponse,
    LoanPlanUpdateRequest,
)
from app.schemas.planning import FixedExpenseItemResponse
from app.services.goal_service import loan_planning_rows_for_user, sync_loan_paydown_goal
from app.services.loan_service import (
    category_is_mortgage_rent,
    debt_to_income_ratio,
    ensure_mortgage_loan_item_from_category,
    ensure_mortgage_loan_item_from_transaction,
    loan_category_label_options_for_user,
)
from app.services.planning_service import (
    amortization_schedule,
    loan_category_for_item,
    loan_plan_scenarios,
    monthly_amount_for_fixed_item,
    selected_extra_payment_for_loan_plan,
    sync_loan_fixed_expense_budget,
    sync_monthly_plan,
)
from app.services.transaction_service import (
    category_for_user,
    get_owned_transaction,
    parse_amount,
    require_onboarding_complete,
)

router = APIRouter(tags=["loan-plans"])


def _require_loan_access(user: User, *, onboarding: bool = False) -> None:
    if onboarding:
        require_onboarding_complete(user)
    if not user_has_feature(user, "mortgage_loan_planning"):
        required_plan = feature_min_plan_label("mortgage_loan_planning")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "feature_locked",
                "feature": "mortgage_loan_planning",
                "required_plan": required_plan,
                "message": f"Mortgage/Loan Planning requires ClearPath {required_plan} or higher.",
            },
        )


def _owned_fixed_item(db: Session, user: User, item_id: int) -> FixedExpenseItem:
    item = db.scalar(
        select(FixedExpenseItem).where(
            FixedExpenseItem.user_id == user.id,
            FixedExpenseItem.id == item_id,
        )
    )
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fixed expense not found.")
    return item


def _loan_kind_for_item(item: FixedExpenseItem) -> str:
    loan_kind = loan_category_for_item(item)
    if not loan_kind:
        raise HTTPException(
            status_code=422,
            detail="Only fixed expenses categorized as Mortgage or Loan can use an amortization schedule.",
        )
    return loan_kind


def _fixed_item_response(item: FixedExpenseItem) -> FixedExpenseItemResponse:
    response = FixedExpenseItemResponse.model_validate(item)
    response.monthly_amount = monthly_amount_for_fixed_item(item)
    return response


def _loan_plan_response(
    db: Session,
    user: User,
    item: FixedExpenseItem,
    loan_kind: str,
    *,
    created_fixed_expense: bool = False,
) -> LoanPlanResponse:
    plan = db.scalar(
        select(LoanPlan).where(
            LoanPlan.user_id == user.id,
            LoanPlan.fixed_expense_item_id == item.id,
        )
    )
    scenarios = loan_plan_scenarios(plan) if plan else []
    selected_schedule = []
    if plan:
        selected_schedule = amortization_schedule(
            plan.principal_balance,
            plan.annual_interest_rate,
            plan.regular_payment,
            selected_extra_payment_for_loan_plan(plan),
            plan.term_months,
        )
    return LoanPlanResponse(
        fixed_expense=_fixed_item_response(item),
        loan_kind=loan_kind,
        plan=LoanPlanRecordResponse.model_validate(plan) if plan else None,
        scenarios=[LoanPlanScenarioResponse.model_validate(row) for row in scenarios],
        selected_schedule=selected_schedule,
        created_fixed_expense=created_fixed_expense,
    )


@router.get("/loan-plans", response_model=LoanPlanListResponse)
def list_loan_plans(
    principal: Annotated[Principal, Depends(require_household_access("viewer"))],
    db: Annotated[Session, Depends(get_db)],
) -> LoanPlanListResponse:
    user = principal.user
    _require_loan_access(user, onboarding=True)
    rows = loan_planning_rows_for_user(db, user)
    return LoanPlanListResponse(
        items=[LoanPlanSummaryResponse.model_validate(row) for row in rows],
        total_debt_monthly=sum(row["total_monthly"] for row in rows),
        total_debt_balance=sum(row["current_balance"] for row in rows),
        debt_to_income_ratio=debt_to_income_ratio(db, user),
        loan_category_label_options=loan_category_label_options_for_user(db, user),
    )


@router.get("/loan-plans/{fixed_expense_item_id}", response_model=LoanPlanResponse)
def get_loan_plan(
    fixed_expense_item_id: int,
    principal: Annotated[Principal, Depends(require_household_access("viewer"))],
    db: Annotated[Session, Depends(get_db)],
) -> LoanPlanResponse:
    user = principal.user
    item = _owned_fixed_item(db, user, fixed_expense_item_id)
    _require_loan_access(user)
    loan_kind = _loan_kind_for_item(item)
    return _loan_plan_response(db, user, item, loan_kind)


@router.patch("/loan-plans/{fixed_expense_item_id}", response_model=LoanPlanResponse)
def update_loan_plan(
    fixed_expense_item_id: int,
    payload: LoanPlanUpdateRequest,
    principal: Annotated[Principal, Depends(require_household_access("editor"))],
    db: Annotated[Session, Depends(get_db)],
) -> LoanPlanResponse:
    user = principal.user
    item = _owned_fixed_item(db, user, fixed_expense_item_id)
    _require_loan_access(user)
    loan_kind = _loan_kind_for_item(item)
    plan = db.scalar(
        select(LoanPlan).where(
            LoanPlan.user_id == user.id,
            LoanPlan.fixed_expense_item_id == item.id,
        )
    )
    if not plan:
        plan = LoanPlan(user_id=user.id, fixed_expense_item_id=item.id, loan_type=loan_kind)
        db.add(plan)

    plan.loan_type = loan_kind
    plan.principal_balance = parse_amount(payload.principal_balance or 0)
    plan.collateral_value = parse_amount(payload.collateral_value or 0)
    plan.annual_interest_rate = parse_amount(payload.annual_interest_rate or 0)
    term_value = parse_amount(payload.term_value or payload.term_months or 360)
    term_unit = payload.term_unit or "months"
    plan.term_unit_preference = term_unit if term_unit in {"months", "years"} else "months"
    plan.term_months = max(int(round(term_value * 12 if term_unit == "years" else term_value)), 1)
    plan.regular_payment = parse_amount(payload.regular_payment or item.amount or 0)
    plan.extra_payment_one = parse_amount(payload.extra_payment_one or 0)
    plan.extra_payment_two = parse_amount(payload.extra_payment_two or 0)
    plan.selected_scenario = payload.selected_scenario if payload.selected_scenario in {"base", "extra_one", "extra_two"} else "base"
    plan.notes = (payload.notes or "").strip() or None
    sync_loan_fixed_expense_budget(db, item, user, force=True)
    sync_loan_paydown_goal(db, plan, item, user)
    db.commit()
    sync_monthly_plan(db, user)
    return _loan_plan_response(db, user, item, loan_kind)


@router.patch("/loan-plans/{fixed_expense_item_id}/selected-scenario", response_model=LoanPlanResponse)
def select_loan_plan_scenario(
    fixed_expense_item_id: int,
    payload: LoanPlanScenarioSelectRequest,
    principal: Annotated[Principal, Depends(require_household_access("editor"))],
    db: Annotated[Session, Depends(get_db)],
) -> LoanPlanResponse:
    user = principal.user
    item = _owned_fixed_item(db, user, fixed_expense_item_id)
    _require_loan_access(user)
    loan_kind = _loan_kind_for_item(item)
    plan = db.scalar(
        select(LoanPlan).where(
            LoanPlan.user_id == user.id,
            LoanPlan.fixed_expense_item_id == item.id,
        )
    )
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Loan plan not found.")
    plan.selected_scenario = payload.selected_scenario if payload.selected_scenario in {"base", "extra_one", "extra_two"} else "base"
    sync_loan_fixed_expense_budget(db, item, user, force=True)
    sync_loan_paydown_goal(db, plan, item, user)
    db.commit()
    sync_monthly_plan(db, user)
    return _loan_plan_response(db, user, item, loan_kind)


@router.post("/transactions/{transaction_id}/loan-plan", response_model=LoanPlanResponse)
def start_transaction_loan_plan(
    transaction_id: int,
    principal: Annotated[Principal, Depends(require_household_access("editor"))],
    db: Annotated[Session, Depends(get_db)],
) -> LoanPlanResponse:
    user = principal.user
    _require_loan_access(user, onboarding=True)
    transaction = get_owned_transaction(db, user, transaction_id)
    if (transaction.amount or 0) >= 0 or not category_is_mortgage_rent(transaction.category):
        raise HTTPException(
            status_code=422,
            detail="Choose Mortgage/Rent on an expense transaction before starting an amortization schedule.",
        )
    item, created = ensure_mortgage_loan_item_from_transaction(db, transaction, user)
    db.commit()
    sync_monthly_plan(db, user, purpose="monthly_plan")
    return _loan_plan_response(db, user, item, "mortgage", created_fixed_expense=created)


@router.post("/budgets/{category_id}/loan-plan", response_model=LoanPlanResponse)
def start_budget_loan_plan(
    category_id: int,
    principal: Annotated[Principal, Depends(require_household_access("editor"))],
    db: Annotated[Session, Depends(get_db)],
) -> LoanPlanResponse:
    user = principal.user
    _require_loan_access(user, onboarding=True)
    category = category_for_user(db, category_id, user)
    if not category or not category_is_mortgage_rent(category):
        raise HTTPException(
            status_code=422,
            detail="Only the Mortgage/Rent budget can start a mortgage amortization schedule.",
        )
    item, created = ensure_mortgage_loan_item_from_category(db, category, user)
    db.commit()
    sync_monthly_plan(db, user, purpose="monthly_plan")
    return _loan_plan_response(db, user, item, "mortgage", created_fixed_expense=created)
