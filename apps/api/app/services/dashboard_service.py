from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.ai_policy import guardrail_ai_guidance_items
from app.core.plaid_policy import assert_plaid_data_purpose
from app.core.planning_constants import ANALYTICS_RANGE_OPTIONS, DEFAULT_CATEGORY_TARGETS
from app.models import Account, Goal, LoanPlan, MonthlyBudgetSnapshot, User
from app.services.loan_service import debt_to_income_ratio
from app.services.planning_service import (
    _expense_transactions_between,
    _fixed_plan_claimed_transaction_ids,
    _income_transactions_between,
    account_is_liability,
    analytics_months,
    app_today,
    calculate_tax_estimate,
    get_or_create_monthly_plan,
    month_bounds,
    retirement_cash_flow_contribution,
    selected_loan_extra_payment_total,
    spending_by_category,
    spending_by_category_between,
    sync_monthly_budget_snapshots_for_range,
    transaction_category_allocations_for_period,
)
from app.services.subscription_service import (
    subscription_category_breakdown,
    subscription_opportunities,
    subscription_summary,
    upcoming_subscriptions,
)
from app.services.transaction_service import normalize_text


@dataclass
class DashboardMetrics:
    month_income: float
    fixed_expenses: float
    variable_spend: float
    safe_to_spend: float
    safe_to_spend_target: float
    net_cash_flow: float
    on_track_status: str
    expected_variable_spend: float


def calculate_dashboard_metrics(
    db: Session,
    user: User,
    target_date: date,
    *,
    purpose: str = "dashboard",
) -> DashboardMetrics:
    assert_plaid_data_purpose(purpose)
    start, end = month_bounds(target_date)
    plan = get_or_create_monthly_plan(db, user, target_date)
    monthly_tax = calculate_tax_estimate(user.profile).monthly_total
    retirement_total = retirement_cash_flow_contribution(user.profile)
    loan_extra_total = selected_loan_extra_payment_total(db, user)

    income = float(sum(transaction.amount or 0 for transaction in _income_transactions_between(db, user, start, end)))
    allocations = transaction_category_allocations_for_period(db, user, start, end, purpose=purpose)
    total_expenses = float(sum(allocation["amount"] for allocation in allocations))
    fixed_claimed_transaction_ids = _fixed_plan_claimed_transaction_ids(
        db,
        user,
        _expense_transactions_between(db, user, start, end),
    )
    variable_spend = sum(
        allocation["amount"]
        for allocation in allocations
        if allocation.get("transaction_id") not in fixed_claimed_transaction_ids
    )
    safe_to_spend = (
        plan.income
        - monthly_tax
        - plan.fixed_expenses
        - plan.planned_savings
        - plan.planned_debt_payment
        - retirement_total
        - loan_extra_total
        - variable_spend
    )
    net_cash_flow = income - total_expenses
    day_of_month = max(target_date.day, 1)
    expected_variable_spend = max(plan.safe_to_spend_target, 0) * (day_of_month / end.day)
    if variable_spend <= expected_variable_spend * 1.05:
        on_track_status = "green"
    elif variable_spend <= expected_variable_spend * 1.2:
        on_track_status = "yellow"
    else:
        on_track_status = "red"

    return DashboardMetrics(
        month_income=income or plan.income,
        fixed_expenses=plan.fixed_expenses,
        variable_spend=variable_spend,
        safe_to_spend=safe_to_spend,
        safe_to_spend_target=plan.safe_to_spend_target,
        net_cash_flow=net_cash_flow,
        on_track_status=on_track_status,
        expected_variable_spend=expected_variable_spend,
    )


def net_worth_summary(db: Session, user: User, *, purpose: str = "dashboard") -> dict:
    assert_plaid_data_purpose(purpose)
    accounts = db.scalars(select(Account).where(Account.user_id == user.id)).all()
    account_assets = 0.0
    account_liabilities = 0.0
    for account in accounts:
        balance = account.current_balance or 0.0
        if account_is_liability(account) or balance < 0:
            account_liabilities += abs(balance)
        else:
            account_assets += balance

    loan_plans = db.scalars(
        select(LoanPlan)
        .options(selectinload(LoanPlan.fixed_expense_item))
        .where(LoanPlan.user_id == user.id)
    ).all()
    loan_balances = 0.0
    collateral_value = 0.0
    secured_positive_equity = 0.0
    secured_negative_equity = 0.0
    secured_loan_balances = 0.0
    unsecured_loan_balances = 0.0
    for plan in loan_plans:
        balance = max(plan.principal_balance or 0, 0)
        collateral = max(plan.collateral_value or 0, 0)
        loan_balances += balance
        collateral_value += collateral
        if collateral:
            secured_loan_balances += balance
            equity = collateral - balance
            if equity >= 0:
                secured_positive_equity += equity
            else:
                secured_negative_equity += abs(equity)
        else:
            unsecured_loan_balances += balance
    account_assets += secured_positive_equity

    tracked_loan_item_ids = {plan.fixed_expense_item_id for plan in loan_plans}
    tracked_loan_names = {
        normalize_text(plan.fixed_expense_item.name)
        for plan in loan_plans
        if plan.fixed_expense_item
    }

    def debt_goal_duplicates_tracked_loan(goal: Goal) -> bool:
        if goal.fixed_expense_item_id in tracked_loan_item_ids:
            return True
        goal_name = normalize_text(goal.name)
        if not goal_name:
            return False
        return any(goal_name in loan_name or loan_name in goal_name for loan_name in tracked_loan_names)

    goals = db.scalars(select(Goal).where(Goal.user_id == user.id)).all()
    unlinked_debt_goals = sum(
        max(goal.target_amount - goal.current_amount, 0)
        for goal in goals
        if goal.goal_type == "debt" and not debt_goal_duplicates_tracked_loan(goal)
    )
    total_liabilities = account_liabilities + loan_balances + unlinked_debt_goals
    return {
        "assets": account_assets,
        "liabilities": total_liabilities,
        "loan_balances": loan_balances,
        "collateral_assets": secured_positive_equity,
        "collateral_value": collateral_value,
        "secured_loan_equity": secured_positive_equity - secured_negative_equity,
        "secured_negative_equity": secured_negative_equity,
        "secured_loan_balances": secured_loan_balances,
        "unsecured_loan_balances": unsecured_loan_balances,
        "debt_goals": unlinked_debt_goals,
        "net_worth": account_assets - total_liabilities,
    }


def recurring_charge_candidates(
    db: Session,
    user: User,
    target_date: date | None = None,
    *,
    purpose: str = "dashboard",
) -> list[tuple[str, int, float]]:
    assert_plaid_data_purpose(purpose)
    target_date = target_date or app_today()
    start = date(target_date.year, max(target_date.month - 2, 1), 1)
    counts: Counter[str] = Counter()
    totals: defaultdict[str, float] = defaultdict(float)
    for transaction in _expense_transactions_between(db, user, start, target_date):
        key = normalize_text(transaction.description)
        counts[key] += 1
        totals[key] += abs(transaction.amount)
    candidates = [
        (key.title(), count, round(totals[key] / count, 2))
        for key, count in counts.items()
        if count >= 3
    ]
    return sorted(candidates, key=lambda item: item[2], reverse=True)[:3]


def generate_insights(
    db: Session,
    user: User,
    target_date: date | None = None,
    *,
    purpose: str = "dashboard",
    metrics: DashboardMetrics | None = None,
    category_spend: list[dict] | None = None,
) -> list[dict]:
    assert_plaid_data_purpose(purpose)
    metrics = metrics or calculate_dashboard_metrics(
        db,
        user,
        target_date or app_today(),
        purpose=purpose,
    )
    category_spend = (
        category_spend
        if category_spend is not None
        else spending_by_category(db, user, target_date, purpose=purpose)
    )
    profile = user.profile
    insights: list[dict] = []

    if metrics.on_track_status == "red":
        insights.append(
            {
                "title": "Spending pace is too high",
                "body": "At your current pace, you may run short before month-end unless you trim flexible spending.",
                "level": "alert",
                "type": "cash_flow_risk",
            }
        )
    elif metrics.on_track_status == "yellow":
        insights.append(
            {
                "title": "You are slightly ahead of plan",
                "body": "Variable spending is running a bit above your usual pace, so this is a good week to stay intentional.",
                "level": "warning",
                "type": "overspending_warning",
            }
        )

    dining = sum(
        item["amount"]
        for item in category_spend
        if item["category"] in {"Dining", "Dining/Eating Out"}
    )
    dining_target = DEFAULT_CATEGORY_TARGETS["Dining/Eating Out"]
    if dining > dining_target * 1.2:
        over_by = round(dining - dining_target, 2)
        insights.append(
            {
                "title": "Dining spend is trending high",
                "body": f"You are trending ${over_by:,.0f} over your usual dining spend this month.",
                "level": "warning",
                "type": "category_overspend",
            }
        )

    if metrics.safe_to_spend > 250:
        insights.append(
            {
                "title": "You have room to move money with purpose",
                "body": (
                    f"You can safely move about ${min(metrics.safe_to_spend, 500):,.0f} "
                    "to savings or extra debt paydown this month."
                ),
                "level": "good",
                "type": "surplus_opportunity",
            }
        )

    dti = debt_to_income_ratio(db, user)
    if dti >= 0.43:
        insights.append(
            {
                "title": "Debt payments are taking a lot of income",
                "body": (
                    f"Your debt payments are about {dti * 100:.0f}% of monthly income. "
                    "Consider focusing extra dollars on high-interest loans or refinancing options "
                    "before adding new debt."
                ),
                "level": "alert",
                "type": "debt_to_income_warning",
            }
        )
    elif dti >= 0.36:
        insights.append(
            {
                "title": "Debt-to-income is worth watching",
                "body": (
                    f"Your debt payments are about {dti * 100:.0f}% of monthly income. "
                    "A steady paydown plan can help keep cash flow more flexible."
                ),
                "level": "warning",
                "type": "debt_to_income_watch",
            }
        )

    recurring = recurring_charge_candidates(db, user, target_date, purpose=purpose)
    if recurring:
        name, count, amount = recurring[0]
        insights.append(
            {
                "title": "Recurring charges are worth a quick review",
                "body": (
                    f"{name} appeared {count} times recently at about ${amount:,.0f} each. "
                    "This could be subscription creep."
                ),
                "level": "info",
                "type": "subscription_warning",
            }
        )

    if profile and profile.planned_debt_payment > 0 and metrics.safe_to_spend > profile.planned_debt_payment:
        insights.append(
            {
                "title": "Extra debt payment is possible",
                "body": "Reducing one flexible category this week could improve your debt paydown timeline.",
                "level": "good",
                "type": "debt_opportunity",
            }
        )

    guarded_insights = guardrail_ai_guidance_items(insights[:4])
    for index, guarded in enumerate(guarded_insights):
        if guarded.get("guardrail_violations"):
            original = insights[index] if index < len(insights) else {}
            guarded.update(
                {
                    "title": "Review this spending pattern",
                    "body": (
                        "A repeat or high-impact transaction pattern needs review. Open Transactions "
                        "to check the category, budget impact, and whether it should become a categorization rule."
                    ),
                    "level": original.get("level") or "info",
                    "type": original.get("type") or "dashboard_pattern_review",
                }
            )
            guarded.pop("guardrail_violations", None)
    return guarded_insights


def analytics_summary_for_user(
    db: Session,
    user: User,
    range_key: str = "month",
    end_month: date | None = None,
    *,
    purpose: str = "monthly_plan",
) -> dict:
    assert_plaid_data_purpose(purpose)
    months = analytics_months(end_month, range_key)
    snapshots = sync_monthly_budget_snapshots_for_range(db, user, months, purpose=purpose)
    start_date = months[0]
    end_date = month_bounds(months[-1])[1]
    total_income = sum(snapshot.actual_income for snapshot in snapshots)
    total_spending = sum(snapshot.actual_total_expenses for snapshot in snapshots)
    total_expected_cash_flow = sum(snapshot.expected_cash_flow for snapshot in snapshots)
    total_net_cash_flow = sum(snapshot.net_cash_flow for snapshot in snapshots)
    max_income = max(
        [snapshot.actual_income for snapshot in snapshots]
        + [snapshot.planned_income for snapshot in snapshots]
        + [1]
    )
    max_spending = max(
        [snapshot.actual_total_expenses for snapshot in snapshots]
        + [snapshot.planned_fixed_expenses + snapshot.planned_variable_expenses for snapshot in snapshots]
        + [1]
    )
    max_cash_flow = max(
        [abs(snapshot.net_cash_flow) for snapshot in snapshots]
        + [abs(snapshot.expected_cash_flow) for snapshot in snapshots]
        + [1]
    )
    subscriptions = subscription_summary(db, user, purpose="subscriptions")
    subscription_rows = subscriptions["subscriptions"]
    active_subscription_spend = subscriptions["monthly_total"]
    average_spending = total_spending / len(snapshots) if snapshots else 0
    subscription_spending_share = round((active_subscription_spend / average_spending) * 100) if average_spending else 0
    return {
        "range_key": range_key if range_key in ANALYTICS_RANGE_OPTIONS else "month",
        "range_label": ANALYTICS_RANGE_OPTIONS.get(range_key, ANALYTICS_RANGE_OPTIONS["month"]),
        "months": months,
        "snapshots": snapshots,
        "start_date": start_date,
        "end_date": end_date,
        "total_income": total_income,
        "total_spending": total_spending,
        "total_expected_cash_flow": total_expected_cash_flow,
        "total_net_cash_flow": total_net_cash_flow,
        "average_income": total_income / len(snapshots) if snapshots else 0,
        "average_spending": average_spending,
        "average_net_cash_flow": total_net_cash_flow / len(snapshots) if snapshots else 0,
        "max_income": max_income,
        "max_spending": max_spending,
        "max_cash_flow": max_cash_flow,
        "category_rows": spending_by_category_between(db, user, start_date, end_date, purpose=purpose),
        "subscriptions": {
            **subscriptions,
            "spending_share": subscription_spending_share,
            "category_breakdown": subscription_category_breakdown(subscription_rows),
            "opportunities": subscription_opportunities(subscription_rows),
            "upcoming": upcoming_subscriptions(subscription_rows),
        },
    }
