from __future__ import annotations

import calendar
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.v1.planning import build_monthly_plan_response
from app.core.database import get_db
from app.core.feature_access import (
    feature_is_temporarily_hidden,
    feature_min_plan_label,
    user_has_feature,
)
from app.core.planning_constants import ANALYTICS_RANGE_OPTIONS
from app.dependencies import Principal, require_household_access
from app.models import Account, Transaction, TransactionSplit
from app.schemas.dashboard import (
    AnalyticsResponse,
    AnalyticsSubscriptionCategoryResponse,
    AnalyticsSubscriptionOpportunityResponse,
    AnalyticsSubscriptionResponse,
    AnalyticsSubscriptionsResponse,
    AnalyticsSummaryResponse,
    DashboardFeatureStateResponse,
    DashboardMetricsResponse,
    DashboardResponse,
    MonthlyBudgetSnapshotResponse,
    NetWorthResponse,
)
from app.schemas.goals import GoalResponse
from app.schemas.plaid import AccountResponse
from app.schemas.planning import CategorySpendRowResponse
from app.schemas.transactions import TransactionResponse
from app.services.dashboard_service import (
    analytics_summary_for_user,
    calculate_dashboard_metrics,
    generate_insights,
    net_worth_summary,
)
from app.services.goal_service import build_goal_rows
from app.services.loan_service import debt_to_income_ratio
from app.services.planner_service import dashboard_focus_from_guidance
from app.services.planning_service import app_today, current_month_name, parse_month_input, spending_by_category
from app.services.transaction_service import require_onboarding_complete

router = APIRouter(tags=["dashboard", "analytics"])


def _analytics_subscription_response(subscription) -> AnalyticsSubscriptionResponse:
    return AnalyticsSubscriptionResponse.model_validate(subscription)


def _analytics_summary_response(summary: dict) -> AnalyticsSummaryResponse:
    subscriptions = summary["subscriptions"]
    return AnalyticsSummaryResponse(
        range_key=summary["range_key"],
        range_label=summary["range_label"],
        months=summary["months"],
        snapshots=[MonthlyBudgetSnapshotResponse.model_validate(row) for row in summary["snapshots"]],
        start_date=summary["start_date"],
        end_date=summary["end_date"],
        total_income=summary["total_income"],
        total_spending=summary["total_spending"],
        total_expected_cash_flow=summary["total_expected_cash_flow"],
        total_net_cash_flow=summary["total_net_cash_flow"],
        average_income=summary["average_income"],
        average_spending=summary["average_spending"],
        average_net_cash_flow=summary["average_net_cash_flow"],
        max_income=summary["max_income"],
        max_spending=summary["max_spending"],
        max_cash_flow=summary["max_cash_flow"],
        category_rows=[CategorySpendRowResponse.model_validate(row) for row in summary["category_rows"]],
        subscriptions=AnalyticsSubscriptionsResponse(
            subscriptions=[_analytics_subscription_response(row) for row in subscriptions["subscriptions"]],
            active_count=subscriptions["active_count"],
            review_count=subscriptions["review_count"],
            action_count=subscriptions["action_count"],
            manage_link_count=subscriptions["manage_link_count"],
            monthly_total=subscriptions["monthly_total"],
            annual_total=subscriptions["annual_total"],
            potential_savings=subscriptions["potential_savings"],
            spending_share=subscriptions["spending_share"],
            category_breakdown=[
                AnalyticsSubscriptionCategoryResponse.model_validate(row)
                for row in subscriptions["category_breakdown"]
            ],
            opportunities=[
                AnalyticsSubscriptionOpportunityResponse(
                    subscription=_analytics_subscription_response(row["subscription"]),
                    reason=row["reason"],
                )
                for row in subscriptions["opportunities"]
            ],
            upcoming=[_analytics_subscription_response(row) for row in subscriptions["upcoming"]],
        ),
    )


@router.get("/dashboard", response_model=DashboardResponse)
def get_dashboard(
    principal: Annotated[Principal, Depends(require_household_access("viewer"))],
    db: Annotated[Session, Depends(get_db)],
) -> DashboardResponse:
    user = principal.user
    require_onboarding_complete(user)
    # Route-map decision 5: clients explicitly call the throttled Plaid
    # refresh mutation; dashboard reads never sync live bank data.
    today = app_today()
    metrics = calculate_dashboard_metrics(db, user, today, purpose="dashboard")
    category_totals = spending_by_category(db, user, today, purpose="dashboard")
    plan_context = build_monthly_plan_response(db, user, plan_section="budgets")
    recent_transactions = db.scalars(
        select(Transaction)
        .options(
            selectinload(Transaction.category),
            selectinload(Transaction.account),
            selectinload(Transaction.splits).selectinload(TransactionSplit.category),
        )
        .where(Transaction.user_id == user.id)
        .order_by(Transaction.posted_date.desc(), Transaction.id.desc())
        .limit(6)
    ).all()
    accounts = db.scalars(select(Account).where(Account.user_id == user.id)).all()
    total_days = calendar.monthrange(today.year, today.month)[1]
    elapsed_days = today.day
    pace_pct = round((elapsed_days / total_days) * 100, 1)
    spend_pct = round((metrics.variable_spend / metrics.safe_to_spend_target) * 100, 1) if metrics.safe_to_spend_target > 0 else 0
    feature_states = [
        DashboardFeatureStateResponse(feature="budgets", locked=False),
        DashboardFeatureStateResponse(
            feature="cash_projection",
            locked=not user_has_feature(user, "cash_projection"),
            required_plan=feature_min_plan_label("cash_projection"),
        ),
    ]
    if not feature_is_temporarily_hidden("retirement_planning"):
        feature_states.append(
            DashboardFeatureStateResponse(
                feature="retirement_planning",
                locked=not user_has_feature(user, "retirement_planning"),
                required_plan=feature_min_plan_label("retirement_planning"),
            )
        )
    return DashboardResponse(
        metrics=DashboardMetricsResponse.model_validate(metrics),
        net_worth=NetWorthResponse.model_validate(net_worth_summary(db, user, purpose="dashboard")),
        category_totals=[CategorySpendRowResponse.model_validate(row) for row in category_totals],
        goals=[GoalResponse.model_validate(row) for row in build_goal_rows(db, user)],
        recent_transactions=[TransactionResponse.model_validate(row) for row in recent_transactions],
        accounts=[AccountResponse.model_validate(row) for row in accounts],
        month_name=current_month_name(today),
        today=today,
        elapsed_days=elapsed_days,
        total_days=total_days,
        days_left=max(total_days - elapsed_days, 0),
        pace_pct=pace_pct,
        spend_pct=spend_pct,
        feature_states=feature_states,
        plan_rows=plan_context.plan_rows,
        budget_remaining=plan_context.budget_remaining,
        expected_cash_flow=plan_context.expected_cash_flow,
        insights=generate_insights(
            db,
            user,
            today,
            purpose="dashboard",
            metrics=metrics,
            category_spend=category_totals,
        ),
        dashboard_focus=dashboard_focus_from_guidance(user),
    )


@router.get("/analytics", response_model=AnalyticsResponse)
def get_analytics(
    principal: Annotated[Principal, Depends(require_household_access("viewer"))],
    db: Annotated[Session, Depends(get_db)],
    range: str = "month",
    end_month: str = "",
    history_range: str = "quarter",
    history_end_month: str = "",
) -> AnalyticsResponse:
    user = principal.user
    require_onboarding_complete(user)
    range_key = range if range in ANALYTICS_RANGE_OPTIONS else "month"
    try:
        selected_end_month = parse_month_input(end_month.strip())
    except ValueError:
        selected_end_month = app_today().replace(day=1)
    history_range_key = history_range if history_range in ANALYTICS_RANGE_OPTIONS else "quarter"
    try:
        selected_history_end_month = parse_month_input(history_end_month.strip()) if history_end_month.strip() else selected_end_month
    except ValueError:
        selected_history_end_month = selected_end_month

    summary = analytics_summary_for_user(db, user, range_key, selected_end_month, purpose="monthly_plan")
    history_summary = analytics_summary_for_user(
        db,
        user,
        history_range_key,
        selected_history_end_month,
        purpose="monthly_plan",
    )
    return AnalyticsResponse(
        summary=_analytics_summary_response(summary),
        budget_history_summary=_analytics_summary_response(history_summary),
        debt_to_income_ratio=debt_to_income_ratio(db, user),
        range_options=ANALYTICS_RANGE_OPTIONS,
        selected_range=range_key,
        end_month=selected_end_month,
        selected_history_range=history_range_key,
        history_end_month=selected_history_end_month,
        subscription_analytics_enabled=user_has_feature(user, "subscription_analytics"),
        subscription_analytics_plan_label=feature_min_plan_label("subscription_analytics"),
        ai_coach_enabled=user_has_feature(user, "ai_coach"),
        ai_coach_hidden=feature_is_temporarily_hidden("ai_coach"),
    )
