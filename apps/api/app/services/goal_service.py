from __future__ import annotations

from collections import defaultdict
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import FixedExpenseItem, Goal, LoanPlan, User
from app.services.planning_service import (
    amortization_summary,
    app_today,
    editable_budget_category_for_user,
    loan_category_for_item,
    monthly_amount_for_fixed_item,
    selected_extra_payment_for_loan_plan,
)
from app.services.transaction_service import categories_for_user, ensure_category_option, normalize_text


def months_until(target_date: date | None, start_date: date | None = None) -> int:
    if not target_date:
        return 0
    start_date = start_date or app_today()
    if target_date <= start_date:
        return 0
    months = (target_date.year - start_date.year) * 12 + (target_date.month - start_date.month)
    if target_date.day > start_date.day:
        months += 1
    return max(months, 1)


def required_monthly_for_goal(goal: Goal, start_date: date | None = None) -> float:
    remaining = max(goal.target_amount - goal.current_amount, 0)
    months = months_until(goal.target_date, start_date)
    if remaining <= 0 or months <= 0:
        return 0.0
    return remaining / months


def estimate_goal_timeline(goal: Goal) -> str:
    remaining = max(goal.target_amount - goal.current_amount, 0)
    if remaining <= 0:
        return "Complete"
    if goal.monthly_contribution <= 0:
        if goal.target_date:
            required = required_monthly_for_goal(goal)
            if goal.goal_type == "savings":
                return f"Save ${required:,.0f}/month to hit target date"
            return f"Pay ${required:,.0f}/month extra to hit target date"
        return "No contribution pace yet"
    months = int((remaining + goal.monthly_contribution - 1) // goal.monthly_contribution)
    return f"About {months} month{'s' if months != 1 else ''}"


def savings_goal_budget_label(goal: Goal) -> str:
    goal_name = normalize_text(goal.name or "")
    if "education" in goal_name or "college" in goal_name or "tuition" in goal_name:
        return "Education Savings"
    if "retirement" in goal_name or "401k" in goal_name or "ira" in goal_name:
        return "Retirement (401k, IRA)"
    if "invest" in goal_name or "brokerage" in goal_name:
        return "Investments"
    return "Emergency Fund"


def sync_savings_goal_budget_targets(db: Session, user: User) -> int:
    categories = categories_for_user(db, user)
    categories_by_name = {category.name.strip().lower(): category for category in categories}
    totals_by_label: dict[str, float] = defaultdict(float)
    goals = db.scalars(select(Goal).where(Goal.user_id == user.id, Goal.goal_type == "savings")).all()
    for goal in goals:
        contribution = max(goal.monthly_contribution or 0, 0)
        if contribution <= 0:
            continue
        totals_by_label[savings_goal_budget_label(goal)] += contribution

    updated = 0
    for label, total in totals_by_label.items():
        category = categories_by_name.get(label.lower()) or ensure_category_option(db, label, user)
        if not category:
            continue
        editable_category = editable_budget_category_for_user(db, category, user)
        target = round(total, 2)
        if editable_category.monthly_target != target or editable_category.is_default:
            editable_category.monthly_target = target
            editable_category.is_default = False
            updated += 1
    if updated:
        db.commit()
    return updated


def sync_loan_paydown_goal(
    db: Session,
    plan: LoanPlan | None,
    item: FixedExpenseItem,
    user: User,
) -> Goal | None:
    if not plan:
        return None
    selected_extra = max(selected_extra_payment_for_loan_plan(plan), 0)
    auto_name = f"{item.name} Paydown Plan"
    auto_key = normalize_text(auto_name)
    linked_goals = db.scalars(
        select(Goal)
        .where(
            Goal.user_id == user.id,
            Goal.goal_type == "debt",
            Goal.fixed_expense_item_id == item.id,
        )
        .order_by(Goal.created_at.asc())
    ).all()
    auto_goal = next((goal for goal in linked_goals if normalize_text(goal.name) == auto_key), None)
    if selected_extra <= 0:
        if auto_goal:
            db.delete(auto_goal)
        return None

    goal = auto_goal or (linked_goals[0] if linked_goals else None)
    if not goal:
        goal = Goal(
            user_id=user.id,
            name=auto_name,
            goal_type="debt",
            fixed_expense_item_id=item.id,
            target_amount=0,
        )
        db.add(goal)
    goal.target_amount = max(plan.principal_balance or goal.target_amount or 0, 0)
    goal.current_amount = 0
    goal.monthly_contribution = round(selected_extra, 2)
    goal.fixed_expense_item_id = item.id
    return goal


def required_extra_payment_for_debt_goal(db: Session, goal: Goal) -> float:
    if goal.goal_type != "debt" or not goal.fixed_expense_item_id or not goal.target_date:
        return 0.0
    plan = db.scalar(
        select(LoanPlan).where(
            LoanPlan.user_id == goal.user_id,
            LoanPlan.fixed_expense_item_id == goal.fixed_expense_item_id,
        )
    )
    if not plan or plan.principal_balance <= 0:
        return 0.0
    target_months = months_until(goal.target_date)
    if target_months <= 0:
        return 0.0

    baseline = amortization_summary(
        plan.principal_balance,
        plan.annual_interest_rate,
        plan.regular_payment,
        0,
        plan.term_months,
    )
    if baseline["payoff_possible"] and baseline["months"] <= target_months:
        return 0.0

    high = max(plan.principal_balance / max(target_months, 1), plan.regular_payment, 100.0)
    for _ in range(20):
        candidate = amortization_summary(
            plan.principal_balance,
            plan.annual_interest_rate,
            plan.regular_payment,
            high,
            plan.term_months,
        )
        if candidate["payoff_possible"] and candidate["months"] <= target_months:
            break
        high *= 2

    low = 0.0
    for _ in range(32):
        midpoint = (low + high) / 2
        candidate = amortization_summary(
            plan.principal_balance,
            plan.annual_interest_rate,
            plan.regular_payment,
            midpoint,
            plan.term_months,
        )
        if candidate["payoff_possible"] and candidate["months"] <= target_months:
            high = midpoint
        else:
            low = midpoint
    return high


def loan_planning_rows_for_user(db: Session, user: User) -> list[dict]:
    fixed_items = db.scalars(select(FixedExpenseItem).where(FixedExpenseItem.user_id == user.id)).all()
    loan_plans = {
        plan.fixed_expense_item_id: plan
        for plan in db.scalars(select(LoanPlan).where(LoanPlan.user_id == user.id)).all()
    }
    rows = []
    for item in fixed_items:
        loan_kind = loan_category_for_item(item)
        if not loan_kind:
            continue
        plan = loan_plans.get(item.id)
        monthly_payment = monthly_amount_for_fixed_item(item)
        selected_extra = selected_extra_payment_for_loan_plan(plan)
        rows.append(
            {
                "fixed_expense_item_id": item.id,
                "name": item.name,
                "loan_kind": loan_kind,
                "monthly_payment": monthly_payment,
                "selected_extra": selected_extra,
                "total_monthly": monthly_payment + selected_extra,
                "principal_balance": plan.principal_balance if plan else 0,
                "current_balance": max(plan.principal_balance or 0, 0) if plan else 0,
                "collateral_value": plan.collateral_value if plan else 0,
                "selected_scenario": plan.selected_scenario if plan else "base",
            }
        )
    return sorted(rows, key=lambda row: row["total_monthly"], reverse=True)


def build_goal_row(
    db: Session,
    goal: Goal,
    *,
    loan_plans: dict[int, LoanPlan] | None = None,
    loan_items: dict[int, FixedExpenseItem] | None = None,
) -> dict:
    if loan_plans is None:
        loan_plans = {
            plan.fixed_expense_item_id: plan
            for plan in db.scalars(select(LoanPlan).where(LoanPlan.user_id == goal.user_id)).all()
        }
    if loan_items is None:
        loan_items = {
            item.id: item
            for item in db.scalars(select(FixedExpenseItem).where(FixedExpenseItem.user_id == goal.user_id)).all()
        }

    linked_item = loan_items.get(goal.fixed_expense_item_id)
    linked_plan = loan_plans.get(goal.fixed_expense_item_id)
    if goal.goal_type == "debt" and linked_plan:
        target_amount = goal.target_amount or linked_plan.principal_balance or 0
        remaining = max(linked_plan.principal_balance or 0, 0)
        current_amount = max(target_amount - remaining, 0)
        summary = amortization_summary(
            linked_plan.principal_balance,
            linked_plan.annual_interest_rate,
            linked_plan.regular_payment,
            selected_extra_payment_for_loan_plan(linked_plan),
            linked_plan.term_months,
        )
        if not summary["payoff_possible"]:
            timeline = "Selected payoff plan needs review"
        else:
            months = int(summary["months"] or 0)
            if months <= 0:
                timeline = "Loan paid off"
            else:
                timeline = f"Selected payoff plan: {months} month{'s' if months != 1 else ''}"
    else:
        target_amount = goal.target_amount or 0
        current_amount = goal.current_amount or 0
        remaining = max(target_amount - current_amount, 0)
        timeline = estimate_goal_timeline(goal)
    progress = 0 if target_amount <= 0 else min((current_amount / target_amount) * 100, 100)
    return {
        "goal": goal,
        "progress": progress,
        "timeline": timeline,
        "remaining": remaining,
        "current_amount": current_amount,
        "target_amount": target_amount,
        "required_monthly": required_monthly_for_goal(goal),
        "required_extra": required_extra_payment_for_debt_goal(db, goal),
        "linked_item": linked_item,
    }


def build_goal_rows(db: Session, user: User) -> list[dict]:
    loan_plans = {
        plan.fixed_expense_item_id: plan
        for plan in db.scalars(select(LoanPlan).where(LoanPlan.user_id == user.id)).all()
    }
    loan_items = {
        item.id: item
        for item in db.scalars(select(FixedExpenseItem).where(FixedExpenseItem.user_id == user.id)).all()
    }
    goals = db.scalars(
        select(Goal).where(Goal.user_id == user.id).order_by(Goal.created_at.desc())
    ).all()
    return [build_goal_row(db, goal, loan_plans=loan_plans, loan_items=loan_items) for goal in goals]
