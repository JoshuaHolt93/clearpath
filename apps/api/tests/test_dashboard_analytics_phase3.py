from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest

from app.core.ai_policy import AI_GUIDANCE_DISCLAIMER
from app.core.security import decode_token
from app.models import (
    Account,
    Category,
    FixedExpenseItem,
    Goal,
    HouseholdMember,
    LoanPlan,
    MonthlyBudgetSnapshot,
    Subscription,
    Transaction,
    User,
)
from app.services.planning_service import app_today
from app.services.dashboard_service import DashboardMetrics, generate_insights
from conftest import TestingSessionLocal

VALID_PASSWORD = "CorrectHorse1!"


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def full_session_token(client, email: str) -> str:
    registered = client.post(
        "/v1/auth/register",
        json={
            "email": email,
            "password": VALID_PASSWORD,
            "display_name": "Dashboard User",
            "household_name": "Dashboard Household",
            "policy_acknowledgement": True,
        },
    )
    assert registered.status_code == 201
    completed = client.post(
        "/v1/auth/mfa/setup",
        headers=auth_header(registered.json()["access_token"]),
        json={"action": "skip"},
    )
    assert completed.status_code == 200
    return completed.json()["access_token"]


def configure_user(token: str, *, plan: str = "premium", onboarded: bool = True) -> int:
    payload = decode_token(token)
    with TestingSessionLocal() as db:
        user = db.get(User, int(payload["user_id"]))
        user.selected_plan = plan
        if onboarded:
            user.profile.income_amount = 60000
            user.profile.monthly_income = 5000
            user.profile.income_type = "salary"
            user.profile.income_basis = "take_home"
            user.profile.fixed_expenses = 0
            user.profile.variable_expenses = 0
        db.commit()
        return user.id


def onboarded_token(client, email: str, *, plan: str = "premium") -> tuple[str, int]:
    token = full_session_token(client, email)
    return token, configure_user(token, plan=plan)


def shared_session_token(client, owner_id: int, email: str, role: str = "viewer") -> str:
    with TestingSessionLocal() as db:
        member = HouseholdMember(
            owner_user_id=owner_id,
            invited_by_user_id=owner_id,
            email=email,
            role=role,
            status="active",
        )
        member.set_password(VALID_PASSWORD)
        db.add(member)
        db.commit()
    login = client.post("/v1/auth/login", json={"email": email, "password": VALID_PASSWORD})
    assert login.status_code == 200
    completed = client.post(
        "/v1/auth/mfa/setup",
        headers=auth_header(login.json()["access_token"]),
        json={"action": "skip"},
    )
    assert completed.status_code == 200
    return completed.json()["access_token"]


def test_dashboard_analytics_openapi_contract(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert set(paths["/v1/dashboard"]) == {"get"}
    assert set(paths["/v1/analytics"]) == {"get"}
    analytics_parameters = {parameter["name"] for parameter in paths["/v1/analytics"]["get"]["parameters"]}
    assert analytics_parameters == {"range", "end_month", "history_range", "history_end_month"}


def seed_dashboard_fixture(user_id: int) -> dict[str, int]:
    today = app_today()
    with TestingSessionLocal() as db:
        income = Category(user_id=user_id, name="Income", kind="income", monthly_target=5000, is_default=False)
        mortgage = Category(user_id=user_id, name="Mortgage/Rent", kind="expense", monthly_target=1800, is_default=False)
        groceries = Category(user_id=user_id, name="Groceries", kind="expense", monthly_target=600, is_default=False)
        db.add_all([income, mortgage, groceries])
        db.flush()
        item = FixedExpenseItem(
            user_id=user_id,
            name="Mortgage Payment",
            amount=1800,
            start_date=today.replace(day=1),
            frequency="monthly",
            category_label="Mortgage/Rent",
            is_loan=True,
        )
        checking = Account(user_id=user_id, name="Primary Checking", account_type="checking", current_balance=10000)
        credit = Account(user_id=user_id, name="Rewards Card", account_type="credit card", current_balance=2000)
        db.add_all([item, checking, credit])
        db.flush()
        loan = LoanPlan(
            user_id=user_id,
            fixed_expense_item_id=item.id,
            loan_type="mortgage",
            principal_balance=100000,
            collateral_value=150000,
            annual_interest_rate=0,
            term_months=360,
            regular_payment=1800,
        )
        linked_goal = Goal(
            user_id=user_id,
            name="Mortgage Payment Paydown Plan",
            goal_type="debt",
            target_amount=100000,
            current_amount=0,
            monthly_contribution=0,
            fixed_expense_item_id=item.id,
        )
        unlinked_goal = Goal(
            user_id=user_id,
            name="Family Loan",
            goal_type="debt",
            target_amount=5000,
            current_amount=2000,
            monthly_contribution=100,
        )
        db.add_all([loan, linked_goal, unlinked_goal])
        db.add_all(
            [
                Transaction(
                    user_id=user_id,
                    account_id=checking.id,
                    category_id=income.id,
                    posted_date=today.replace(day=2),
                    description="Paycheck",
                    amount=5000,
                    transaction_type="income",
                    source_name="Primary Checking",
                    import_hash="dashboard-income",
                ),
                Transaction(
                    user_id=user_id,
                    account_id=checking.id,
                    category_id=mortgage.id,
                    posted_date=today.replace(day=3),
                    description="Mortgage Payment",
                    amount=-1800,
                    transaction_type="expense",
                    source_name="Primary Checking",
                    import_hash="dashboard-mortgage",
                ),
                Transaction(
                    user_id=user_id,
                    account_id=checking.id,
                    category_id=groceries.id,
                    posted_date=today.replace(day=4),
                    description="Grocery Run",
                    amount=-200,
                    transaction_type="expense",
                    source_name="Primary Checking",
                    import_hash="dashboard-groceries",
                ),
            ]
        )
        db.commit()
        return {"checking_id": checking.id, "credit_id": credit.id, "unlinked_goal_id": unlinked_goal.id}


def test_dashboard_metrics_net_worth_context_and_read_only_plaid_behavior(client):
    token, user_id = onboarded_token(client, "dashboard-metrics@example.com")
    fixture = seed_dashboard_fixture(user_id)
    headers = auth_header(token)
    with patch("app.services.plaid_service.maybe_refresh_live_bank_data", side_effect=AssertionError("GET refreshed Plaid")):
        response = client.get("/v1/dashboard", headers=headers)
    assert response.status_code == 200
    body = response.json()

    assert body["metrics"]["month_income"] == 5000.0
    assert body["metrics"]["fixed_expenses"] == 1800.0
    assert body["metrics"]["variable_spend"] == 200.0
    assert body["metrics"]["safe_to_spend_target"] == 3200.0
    assert body["metrics"]["safe_to_spend"] == 3000.0
    assert body["metrics"]["net_cash_flow"] == 3000.0
    assert body["metrics"]["expected_variable_spend"] == pytest.approx(3200 * app_today().day / body["total_days"])
    assert body["metrics"]["on_track_status"] == "green"

    assert body["net_worth"] == {
        "assets": 60000.0,
        "liabilities": 105000.0,
        "loan_balances": 100000.0,
        "collateral_assets": 50000.0,
        "collateral_value": 150000.0,
        "secured_loan_equity": 50000.0,
        "secured_negative_equity": 0.0,
        "secured_loan_balances": 100000.0,
        "unsecured_loan_balances": 0.0,
        "debt_goals": 3000.0,
        "net_worth": -45000.0,
    }
    assert {account["id"] for account in body["accounts"]} == {fixture["checking_id"], fixture["credit_id"]}
    assert [transaction["description"] for transaction in body["recent_transactions"]] == [
        "Grocery Run",
        "Mortgage Payment",
        "Paycheck",
    ]
    assert next(goal for goal in body["goals"] if goal["goal"]["id"] == fixture["unlinked_goal_id"])["remaining"] == 3000.0
    assert next(row for row in body["plan_rows"] if row["label"] == "Expenses")["actual"] == 2000.0
    assert body["budget_remaining"] == 400.0
    assert body["expected_cash_flow"] == 2600.0
    assert [insight["type"] for insight in body["insights"]] == [
        "surplus_opportunity",
        "debt_to_income_watch",
    ]
    assert body["insights"][0]["disclaimer"] == AI_GUIDANCE_DISCLAIMER


def test_dashboard_insight_order_cap_and_guardrail_collision(client):
    token, user_id = onboarded_token(client, "dashboard-insights@example.com")
    metrics = DashboardMetrics(
        month_income=5000,
        fixed_expenses=0,
        variable_spend=1000,
        safe_to_spend=500,
        safe_to_spend_target=1000,
        net_cash_flow=4000,
        on_track_status="red",
        expected_variable_spend=400,
    )
    with TestingSessionLocal() as db:
        user = db.get(User, user_id)
        with patch(
            "app.services.dashboard_service.recurring_charge_candidates",
            return_value=[("Streaming Plus", 3, 25)],
        ):
            insights = generate_insights(
                db,
                user,
                app_today(),
                metrics=metrics,
                category_spend=[{"category": "Dining/Eating Out", "amount": 500}],
            )
        assert [insight["type"] for insight in insights] == [
            "cash_flow_risk",
            "category_overspend",
            "surplus_opportunity",
            "subscription_warning",
        ]
        assert all(insight["disclaimer"] == AI_GUIDANCE_DISCLAIMER for insight in insights)

        safe_metrics = DashboardMetrics(**{**metrics.__dict__, "safe_to_spend": 0, "on_track_status": "green"})
        with patch(
            "app.services.dashboard_service.recurring_charge_candidates",
            return_value=[("Buy $TSLA now", 3, 12)],
        ):
            guarded = generate_insights(
                db,
                user,
                app_today(),
                metrics=safe_metrics,
                category_spend=[],
            )
    assert guarded[0]["title"] == "Review this spending pattern"
    assert guarded[0]["type"] == "subscription_warning"
    assert "converted" not in guarded[0]["body"]


def seed_analytics_fixture(user_id: int) -> None:
    with TestingSessionLocal() as db:
        user = db.get(User, user_id)
        user.profile.income_amount = 72000
        user.profile.monthly_income = 6000
        user.profile.fixed_expenses = 1500
        user.profile.variable_expenses = 700
        subscriptions_category = Category(
            user_id=user_id,
            name="Consumer Subscriptions",
            kind="expense",
            monthly_target=50,
            is_default=False,
        )
        db.add(subscriptions_category)
        db.flush()
        for month in [3, 4, 5]:
            db.add(
                Transaction(
                    user_id=user_id,
                    category_id=subscriptions_category.id,
                    posted_date=date(2026, month, 10),
                    description=f"Subscription spend {month}",
                    amount=-1000,
                    transaction_type="expense",
                    source_name="Checking",
                    import_hash=f"analytics-subscription-{month}",
                )
            )
        db.add_all(
            [
                Subscription(
                    user_id=user_id,
                    merchant_key="streaming-plus",
                    name="Streaming Plus",
                    service_category="Streaming",
                    amount=20,
                    monthly_amount=20,
                    annual_amount=240,
                    cycle="Monthly",
                    cycle_days=30,
                    confidence=0.9,
                    status="active",
                    replaceable=True,
                    next_charge_date=date(2026, 6, 15),
                ),
                Subscription(
                    user_id=user_id,
                    merchant_key="cloud-suite",
                    name="Cloud Suite",
                    service_category="Software",
                    amount=30,
                    monthly_amount=30,
                    annual_amount=360,
                    cycle="Monthly",
                    cycle_days=30,
                    confidence=0.7,
                    status="review",
                    replaceable=False,
                    next_charge_date=date(2026, 6, 5),
                ),
                Subscription(
                    user_id=user_id,
                    merchant_key="canceled-media",
                    name="Canceled Media",
                    service_category="Streaming",
                    amount=99,
                    monthly_amount=99,
                    annual_amount=1188,
                    cycle="Monthly",
                    cycle_days=30,
                    confidence=0.9,
                    status="canceled",
                    replaceable=True,
                    next_charge_date=date(2026, 6, 1),
                ),
            ]
        )
        db.commit()


def test_analytics_ranges_snapshots_subscriptions_and_flask_math(client):
    token, user_id = onboarded_token(client, "analytics-summary@example.com")
    seed_analytics_fixture(user_id)
    response = client.get(
        "/v1/analytics?range=quarter&end_month=2026-05&history_range=month&history_end_month=2026-04",
        headers=auth_header(token),
    )
    assert response.status_code == 200
    body = response.json()
    summary = body["summary"]
    assert summary["months"] == ["2026-03-01", "2026-04-01", "2026-05-01"]
    assert summary["range_label"] == "Quarter"
    assert summary["total_expected_cash_flow"] == 3 * (6000 - 1500 - 700 - 50)
    assert summary["total_spending"] == 3000.0
    assert summary["category_rows"] == [
        {"category": "Consumer Subscriptions", "category_id": summary["category_rows"][0]["category_id"], "amount": 3000.0}
    ]
    subscriptions = summary["subscriptions"]
    assert subscriptions["monthly_total"] == 50.0
    assert subscriptions["annual_total"] == 600.0
    assert subscriptions["active_count"] == 2
    assert subscriptions["review_count"] == 1
    assert subscriptions["spending_share"] == 5
    assert [row["category"] for row in subscriptions["category_breakdown"]] == ["Software", "Streaming"]
    assert [row["name"] for row in subscriptions["upcoming"]] == ["Cloud Suite", "Streaming Plus"]
    assert {row["subscription"]["name"] for row in subscriptions["opportunities"]} == {"Cloud Suite", "Streaming Plus"}
    assert body["budget_history_summary"]["months"] == ["2026-04-01"]
    assert body["selected_range"] == "quarter"
    assert body["selected_history_range"] == "month"
    assert body["subscription_analytics_enabled"] is True
    with TestingSessionLocal() as db:
        assert db.query(MonthlyBudgetSnapshot).filter_by(user_id=user_id).count() == 3


def test_dashboard_analytics_access_onboarding_and_invalid_range_normalization(client):
    owner_token, owner_id = onboarded_token(client, "dashboard-owner@example.com")
    viewer_token = shared_session_token(client, owner_id, "dashboard-viewer@example.com")
    viewer_headers = auth_header(viewer_token)
    assert client.get("/v1/dashboard", headers=viewer_headers).status_code == 200
    analytics = client.get(
        "/v1/analytics?range=bad&end_month=bad&history_range=bad&history_end_month=bad",
        headers=viewer_headers,
    )
    assert analytics.status_code == 200
    body = analytics.json()
    assert body["selected_range"] == "month"
    assert body["selected_history_range"] == "quarter"
    assert body["end_month"] == app_today().replace(day=1).isoformat()
    assert body["history_end_month"] == app_today().replace(day=1).isoformat()

    pending_token = full_session_token(client, "dashboard-onboarding@example.com")
    configure_user(pending_token, plan="premium", onboarded=False)
    assert client.get("/v1/dashboard", headers=auth_header(pending_token)).status_code == 409
    assert client.get("/v1/analytics", headers=auth_header(pending_token)).status_code == 409
    assert client.get("/v1/dashboard", headers=auth_header(owner_token)).status_code == 200
