from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.feature_access import feature_min_plan_label, user_has_feature
from app.dependencies import Principal, require_household_access
from app.models import OnboardingProfile, User
from app.schemas.plaid import AccountResponse, PlaidStatusResponse
from app.schemas.retirement import (
    RetirementPlanResponse,
    RetirementPlanUpdateRequest,
    RetirementProfileResponse,
    RetirementWorksheetUpdateRequest,
)
from app.services.plaid_service import plaid_status
from app.services.planning_service import retirement_cash_flow_contribution, sync_monthly_plan
from app.services.retirement_service import RETIREMENT_WORKSHEET_FIELDS, retirement_accounts_for_user
from app.services.transaction_service import parse_amount, require_onboarding_complete

router = APIRouter(tags=["retirement-plan"])


def _require_retirement_access(user: User, *, onboarding: bool = False) -> None:
    if onboarding:
        require_onboarding_complete(user)
    if not user_has_feature(user, "retirement_planning"):
        required_plan = feature_min_plan_label("retirement_planning")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "feature_locked",
                "feature": "retirement_planning",
                "required_plan": required_plan,
                "message": f"Retirement Planning requires ClearPath {required_plan} or higher.",
            },
        )


def _retirement_plan_response(
    db: Session,
    user: User,
    profile: OnboardingProfile,
) -> RetirementPlanResponse:
    return RetirementPlanResponse(
        profile=RetirementProfileResponse.model_validate(profile),
        retirement_accounts=[
            AccountResponse.model_validate(account)
            for account in retirement_accounts_for_user(db, user)
        ],
        retirement_contribution=retirement_cash_flow_contribution(profile),
        plaid_status=PlaidStatusResponse(**plaid_status()),
    )


@router.get("/retirement-plan", response_model=RetirementPlanResponse)
def get_retirement_plan(
    principal: Annotated[Principal, Depends(require_household_access("viewer"))],
    db: Annotated[Session, Depends(get_db)],
) -> RetirementPlanResponse:
    user = principal.user
    _require_retirement_access(user, onboarding=True)
    return _retirement_plan_response(db, user, user.profile)


@router.patch("/retirement-plan", response_model=RetirementPlanResponse)
def update_retirement_plan(
    payload: RetirementPlanUpdateRequest,
    principal: Annotated[Principal, Depends(require_household_access("editor"))],
    db: Annotated[Session, Depends(get_db)],
) -> RetirementPlanResponse:
    user = principal.user
    _require_retirement_access(user)
    profile = user.profile
    profile.retirement_enabled = payload.retirement_enabled
    profile.retirement_has_employer_plan = payload.retirement_has_employer_plan
    profile.retirement_employer_withheld = payload.retirement_employer_withheld
    profile.retirement_has_personal_plan = payload.retirement_has_personal_plan
    profile.retirement_monthly_contribution = parse_amount(payload.retirement_monthly_contribution)
    profile.retirement_personal_monthly_contribution = parse_amount(payload.retirement_personal_monthly_contribution)
    db.commit()
    sync_monthly_plan(db, user)
    return _retirement_plan_response(db, user, profile)


@router.patch("/retirement-plan/worksheet", response_model=RetirementPlanResponse)
def update_retirement_worksheet(
    payload: RetirementWorksheetUpdateRequest,
    principal: Annotated[Principal, Depends(require_household_access("editor"))],
    db: Annotated[Session, Depends(get_db)],
) -> RetirementPlanResponse:
    user = principal.user
    _require_retirement_access(user)
    profile = user.profile
    if profile is None:
        profile = OnboardingProfile(user_id=user.id)
        db.add(profile)
    for field in RETIREMENT_WORKSHEET_FIELDS:
        setattr(profile, field, (getattr(payload, field) or "").strip())
    db.commit()
    return _retirement_plan_response(db, user, profile)
