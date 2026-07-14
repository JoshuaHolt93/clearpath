from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies import Principal, require_household_access
from app.models import FixedExpenseItem, Goal, LoanPlan, User
from app.schemas.goals import (
    GoalCreateRequest,
    GoalDeleteRequest,
    GoalDeleteResponse,
    GoalListResponse,
    GoalResponse,
    GoalUpdateRequest,
)
from app.services.goal_service import (
    build_goal_row,
    build_goal_rows,
    loan_planning_rows_for_user,
    sync_savings_goal_budget_targets,
)
from app.services.planning_service import loan_category_for_item, sync_monthly_plan
from app.services.transaction_service import parse_amount, parse_flexible_date, require_onboarding_complete

router = APIRouter(tags=["goals"])


def _owned_goal(db: Session, user: User, goal_id: int) -> Goal:
    goal = db.scalar(select(Goal).where(Goal.user_id == user.id, Goal.id == goal_id))
    if not goal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Goal not found.")
    return goal


def _parse_target_date(raw_value: str | None) -> date | None:
    raw = (raw_value or "").strip()
    if not raw:
        return None
    try:
        return parse_flexible_date(raw)
    except ValueError:
        return None


def _linked_loan(
    db: Session,
    user: User,
    goal_type: str,
    fixed_expense_item_id: int | None,
) -> tuple[FixedExpenseItem | None, LoanPlan | None]:
    if goal_type != "debt" or not fixed_expense_item_id:
        return None, None
    item = db.scalar(
        select(FixedExpenseItem).where(
            FixedExpenseItem.user_id == user.id,
            FixedExpenseItem.id == fixed_expense_item_id,
        )
    )
    if not item or not loan_category_for_item(item):
        return None, None
    plan = db.scalar(
        select(LoanPlan).where(
            LoanPlan.user_id == user.id,
            LoanPlan.fixed_expense_item_id == item.id,
        )
    )
    return item, plan


def _sync_goal_mutation(db: Session, user: User) -> None:
    sync_savings_goal_budget_targets(db, user)
    sync_monthly_plan(db, user, purpose="monthly_plan")


@router.get("/goals", response_model=GoalListResponse)
def list_goals(
    principal: Annotated[Principal, Depends(require_household_access("viewer"))],
    db: Annotated[Session, Depends(get_db)],
) -> GoalListResponse:
    user = principal.user
    require_onboarding_complete(user)
    return GoalListResponse(
        goals=[GoalResponse.model_validate(row) for row in build_goal_rows(db, user)],
        loan_options=loan_planning_rows_for_user(db, user),
    )


@router.post("/goals", response_model=GoalResponse, status_code=status.HTTP_201_CREATED)
def create_goal(
    payload: GoalCreateRequest,
    principal: Annotated[Principal, Depends(require_household_access("editor"))],
    db: Annotated[Session, Depends(get_db)],
) -> GoalResponse:
    user = principal.user
    require_onboarding_complete(user)
    goal_type = payload.goal_type if payload.goal_type in {"savings", "debt"} else "savings"
    linked_item, linked_plan = _linked_loan(db, user, goal_type, payload.fixed_expense_item_id)
    target_amount = parse_amount(payload.target_amount or 0)
    if goal_type == "debt" and linked_plan:
        target_amount = target_amount or linked_plan.principal_balance or 0
    goal = Goal(
        user_id=user.id,
        name=(payload.name or "").strip() or (f"{linked_item.name} Paydown" if linked_item else "New Goal"),
        goal_type=goal_type,
        target_amount=target_amount,
        current_amount=parse_amount(payload.current_amount or 0),
        monthly_contribution=parse_amount(payload.monthly_contribution or 0),
        target_date=_parse_target_date(payload.target_date),
        fixed_expense_item_id=linked_item.id if linked_item else None,
    )
    db.add(goal)
    db.commit()
    _sync_goal_mutation(db, user)
    return GoalResponse.model_validate(build_goal_row(db, goal))


@router.patch("/goals/{goal_id}", response_model=GoalResponse)
def update_goal(
    goal_id: int,
    payload: GoalUpdateRequest,
    principal: Annotated[Principal, Depends(require_household_access("editor"))],
    db: Annotated[Session, Depends(get_db)],
) -> GoalResponse:
    user = principal.user
    goal = _owned_goal(db, user, goal_id)
    fields = payload.model_fields_set
    goal_type = goal.goal_type
    if "goal_type" in fields and payload.goal_type in {"savings", "debt"}:
        goal_type = payload.goal_type

    linked_id = goal.fixed_expense_item_id
    if "fixed_expense_item_id" in fields:
        linked_id = payload.fixed_expense_item_id
    linked_item, linked_plan = _linked_loan(db, user, goal_type, linked_id)

    if "name" in fields:
        goal.name = (payload.name or "").strip() or goal.name
    goal.goal_type = goal_type
    if "target_amount" in fields:
        parsed_target = parse_amount(payload.target_amount or 0)
        goal.target_amount = parsed_target or (linked_plan.principal_balance if linked_plan else goal.target_amount)
    if "current_amount" in fields:
        goal.current_amount = parse_amount(payload.current_amount or 0)
    if "monthly_contribution" in fields:
        goal.monthly_contribution = parse_amount(payload.monthly_contribution or 0)
    if "target_date" in fields:
        goal.target_date = _parse_target_date(payload.target_date)
    goal.fixed_expense_item_id = linked_item.id if linked_item else None

    db.commit()
    _sync_goal_mutation(db, user)
    return GoalResponse.model_validate(build_goal_row(db, goal))


@router.delete("/goals/{goal_id}", response_model=GoalDeleteResponse)
def delete_goal(
    goal_id: int,
    _payload: GoalDeleteRequest,
    principal: Annotated[Principal, Depends(require_household_access("editor"))],
    db: Annotated[Session, Depends(get_db)],
) -> GoalDeleteResponse:
    user = principal.user
    goal = _owned_goal(db, user, goal_id)
    db.delete(goal)
    db.commit()
    _sync_goal_mutation(db, user)
    return GoalDeleteResponse(deleted_goal_id=goal_id)
