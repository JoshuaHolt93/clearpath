from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.planning_constants import (
    INCOME_BASIS_OPTIONS,
    INCOME_TYPE_OPTIONS,
    MONTHLY_WEEK_OPTIONS,
    PAYCHECK_CADENCE_OPTIONS,
    RECURRING_FREQUENCY_OPTIONS,
    STATE_OPTIONS,
    TAX_FILING_STATUS_OPTIONS,
    WEEKDAY_OPTIONS,
)
from app.dependencies import Principal, require_household_access
from app.models import OnboardingProfile, User
from app.schemas.onboarding import (
    OnboardingCategoryResponse,
    OnboardingCompleteRequest,
    OnboardingIncomePlanRequest,
    OnboardingPlaidItemResponse,
    OnboardingStatusResponse,
    OnboardingTransactionResponse,
)
from app.schemas.plaid import PlaidStatusResponse
from app.schemas.planning import BaselineProfileResponse
from app.services.auth_service import is_onboarding_complete
from app.services.onboarding_service import (
    auto_categorize_onboarding_transactions,
    onboarding_training_transactions_for_user,
    seed_initial_budgets_from_onboarding,
    visible_plaid_items_for_user,
)
from app.services.plaid_service import plaid_status
from app.services.planning_service import (
    annual_salary_from_profile,
    app_today,
    monthly_income_from_profile,
    paycheck_timing_values,
    sync_monthly_plan,
)
from app.services.transaction_service import categories_for_user, parse_amount, parse_flexible_date

router = APIRouter(tags=["onboarding"])


def _string_options(options: dict) -> dict[str, str]:
    return {str(key): str(value) for key, value in options.items()}


def _profile_response(user: User) -> BaselineProfileResponse:
    profile = user.profile
    response = BaselineProfileResponse.model_validate(profile) if profile else BaselineProfileResponse()
    response.household_name = user.household_name
    response.income_amount_display = (
        annual_salary_from_profile(profile)
        if profile and (profile.income_type or "salary") == "salary"
        else (profile.income_amount if profile else None)
    )
    return response


def _active_step(requested_step: str, *, has_bank: bool, income_ready: bool) -> str:
    if requested_step == "connect" or not requested_step:
        return "connect"
    if not has_bank:
        return "connect"
    if requested_step == "income":
        return "income"
    if not income_ready:
        return "income"
    return "transactions"


def _status_response(
    db: Session,
    user: User,
    *,
    requested_step: str = "",
    auto_categorized_count: int = 0,
    seeded_budget_count: int = 0,
    message: str | None = None,
    next_path: str | None = None,
) -> OnboardingStatusResponse:
    plaid_items = visible_plaid_items_for_user(db, user)
    categories = categories_for_user(db, user)
    income_ready = is_onboarding_complete(user)
    active_step = _active_step(requested_step, has_bank=bool(plaid_items), income_ready=income_ready)
    transactions = (
        onboarding_training_transactions_for_user(db, user, categories, limit=10)
        if active_step == "transactions"
        else []
    )
    return OnboardingStatusResponse(
        active_step=active_step,
        income_ready=income_ready,
        has_bank=bool(plaid_items),
        setup_complete=bool(plaid_items) and income_ready,
        profile=_profile_response(user),
        today=app_today(),
        plaid_status=PlaidStatusResponse(**plaid_status()),
        plaid_items=[OnboardingPlaidItemResponse.model_validate(item) for item in plaid_items],
        transactions=[
            OnboardingTransactionResponse(
                id=transaction.id,
                display_merchant=transaction.display_merchant,
                posted_date=transaction.posted_date,
                amount=transaction.amount,
                account_name=transaction.account.name if transaction.account else None,
                source_name=transaction.source_name,
                category_id=transaction.category_id,
            )
            for transaction in transactions
        ],
        categories=[OnboardingCategoryResponse.model_validate(category) for category in categories],
        auto_categorized_count=auto_categorized_count,
        seeded_budget_count=seeded_budget_count,
        message=message,
        next_path=next_path,
        income_basis_options=_string_options(INCOME_BASIS_OPTIONS),
        income_type_options=_string_options(INCOME_TYPE_OPTIONS),
        paycheck_cadence_options=_string_options(PAYCHECK_CADENCE_OPTIONS),
        recurring_frequency_options=_string_options(RECURRING_FREQUENCY_OPTIONS),
        weekday_options=_string_options(WEEKDAY_OPTIONS),
        monthly_week_options=_string_options(MONTHLY_WEEK_OPTIONS),
        tax_filing_status_options=_string_options(TAX_FILING_STATUS_OPTIONS),
        state_options=_string_options(STATE_OPTIONS),
    )


@router.get("/onboarding/status", response_model=OnboardingStatusResponse)
def get_onboarding_status(
    principal: Annotated[Principal, Depends(require_household_access("viewer"))],
    db: Annotated[Session, Depends(get_db)],
    step: str = Query(default=""),
) -> OnboardingStatusResponse:
    return _status_response(db, principal.user, requested_step=step)


@router.patch("/onboarding/income-plan", response_model=OnboardingStatusResponse)
def update_onboarding_income_plan(
    payload: OnboardingIncomePlanRequest,
    principal: Annotated[Principal, Depends(require_household_access("editor"))],
    db: Annotated[Session, Depends(get_db)],
) -> OnboardingStatusResponse:
    user = principal.user
    profile = user.profile
    if not profile:
        profile = OnboardingProfile(user_id=user.id)
        db.add(profile)

    income_type = payload.income_type if payload.income_type in INCOME_TYPE_OPTIONS else "salary"
    income_basis = payload.income_basis if payload.income_basis in INCOME_BASIS_OPTIONS else "take_home"
    paycheck_cadence = (
        payload.paycheck_cadence if payload.paycheck_cadence in PAYCHECK_CADENCE_OPTIONS else "monthly"
    )
    additional_frequency = (
        payload.additional_income_frequency
        if payload.additional_income_frequency in RECURRING_FREQUENCY_OPTIONS
        else "annual"
    )
    filing_status = (
        payload.tax_filing_status
        if payload.tax_filing_status in TAX_FILING_STATUS_OPTIONS
        else "married_joint"
    )
    tax_state = (payload.tax_state or "").strip().upper()
    try:
        next_pay_date = parse_flexible_date(payload.next_pay_date) if payload.next_pay_date else None
    except ValueError:
        next_pay_date = None
    try:
        second_date = parse_flexible_date(payload.second_date) if payload.second_date else None
    except ValueError:
        second_date = None

    profile.income_amount = parse_amount(payload.income_amount or payload.monthly_income or 0)
    profile.income_basis = income_basis
    profile.income_type = income_type
    profile.income_frequency = paycheck_cadence
    profile.paycheck_cadence = paycheck_cadence
    for key, value in paycheck_timing_values(
        paycheck_cadence,
        next_pay_date,
        second_date,
        payload.recurring_days_of_week,
        payload.recurring_monthly_week_numbers,
        payload.recurring_monthly_weekday,
    ).items():
        setattr(profile, key, value)
    profile.hourly_hours_per_week = (
        parse_amount(payload.hourly_hours_per_week or 40) if income_type == "hourly" else 40
    )
    profile.fixed_expenses = parse_amount(payload.fixed_expenses or 0)
    profile.variable_expenses = parse_amount(payload.variable_expenses or 0)
    profile.additional_income_amount = parse_amount(payload.additional_income_amount or 0)
    profile.additional_income_frequency = additional_frequency
    profile.planned_savings_contribution = parse_amount(payload.planned_savings_contribution or 0)
    profile.planned_debt_payment = parse_amount(payload.planned_debt_payment or 0)
    profile.target_investment_contribution = parse_amount(payload.target_investment_contribution or 0)
    profile.tax_filing_status = filing_status
    profile.tax_state = tax_state if tax_state in STATE_OPTIONS and tax_state else None
    profile.include_payroll_taxes = payload.include_payroll_taxes
    profile.notes = (payload.notes or "").strip()
    profile.monthly_income = monthly_income_from_profile(profile)
    db.commit()
    sync_monthly_plan(db, user)
    categories = categories_for_user(db, user)
    auto_count = auto_categorize_onboarding_transactions(db, user, categories)
    db.expire_all()
    return _status_response(
        db,
        user,
        requested_step="transactions",
        auto_categorized_count=auto_count,
        message="Your income plan is saved. Review a few transaction examples next.",
    )


@router.post("/onboarding/complete", response_model=OnboardingStatusResponse)
def complete_onboarding(
    _payload: OnboardingCompleteRequest,
    principal: Annotated[Principal, Depends(require_household_access("editor"))],
    db: Annotated[Session, Depends(get_db)],
) -> OnboardingStatusResponse:
    user = principal.user
    if not visible_plaid_items_for_user(db, user):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "bank_connection_required",
                "step": "connect",
                "message": "Connect a bank account before finishing setup.",
            },
        )
    if not is_onboarding_complete(user):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "income_plan_required",
                "step": "income",
                "message": "Save your income plan before finishing setup.",
            },
        )
    categories = categories_for_user(db, user)
    auto_count = auto_categorize_onboarding_transactions(db, user, categories)
    seeded_count = seed_initial_budgets_from_onboarding(db, user)
    message = (
        "Initial budgets are ready. Keep categorizing transactions so each budget captures all of your spending."
        if seeded_count
        else "Setup is complete. Continue categorizing transactions to build out your first budget view."
    )
    return _status_response(
        db,
        user,
        requested_step="transactions",
        auto_categorized_count=auto_count,
        seeded_budget_count=seeded_count,
        message=message,
        next_path="/monthly-plan?section=budgets&onboarding=complete",
    )
