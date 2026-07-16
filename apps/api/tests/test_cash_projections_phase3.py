from __future__ import annotations

from datetime import timedelta

import pytest

from app.core.security import decode_token
from app.models import (
    Account,
    CashProjectionRecurringIgnore,
    Category,
    FixedExpenseItem,
    ForecastItem,
    HouseholdMember,
    PlaidItem,
    RecurringForecastTemplate,
    Transaction,
    User,
    VariableExpenseItem,
)
from app.services.planning_service import app_today
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
            "display_name": "Cash Projection User",
            "household_name": "Cash Projection Household",
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


def shared_session_token(client, owner_id: int, email: str, role: str) -> str:
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


def onboard(token: str, *, plan: str = "basic") -> int:
    payload = decode_token(token)
    with TestingSessionLocal() as db:
        user = db.get(User, int(payload["user_id"]))
        user.profile.income_amount = 1
        user.profile.monthly_income = 1
        user.selected_plan = plan
        db.commit()
        return user.id


def test_cash_projection_preference_openapi_contract(client):
    operation = client.get("/openapi.json").json()["paths"]["/v1/cash-projections/preferences"]["patch"]
    request_schema = operation["requestBody"]["content"]["application/json"]["schema"]
    response_schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
    assert request_schema["$ref"].endswith("/CashProjectionPreferenceUpdateRequest")
    assert response_schema["$ref"].endswith("/CashProjectionPreferencesResponse")


def test_monthly_plan_three_month_forecast_matches_flask_math(client):
    token = full_session_token(client, "three-month-forecast@example.com")
    user_id = onboard(token)
    month_start = app_today().replace(day=1)
    item_date = month_start.replace(day=min(10, month_start.day + 9))
    with TestingSessionLocal() as db:
        user = db.get(User, user_id)
        profile = user.profile
        profile.monthly_income = 4000
        profile.income_amount = 2000
        profile.income_frequency = "semimonthly"
        profile.paycheck_cadence = "semimonthly"
        profile.income_type = "salary"
        profile.fixed_expenses = 1800
        profile.planned_savings_contribution = 300
        profile.planned_debt_payment = 200
        db.add_all(
            [
                Account(user_id=user_id, name="Checking", current_balance=2500, account_type="checking"),
                Account(user_id=user_id, name="Emergency Savings", current_balance=1000, account_type="savings"),
                Account(user_id=user_id, name="Credit Card", current_balance=900, account_type="credit card"),
                Account(user_id=user_id, name="Brokerage", current_balance=7000, account_type="investment"),
                FixedExpenseItem(
                    user_id=user_id,
                    name="Rent",
                    amount=1800,
                    due_day=1,
                    start_date=month_start,
                    frequency="monthly",
                ),
                VariableExpenseItem(user_id=user_id, name="Groceries", amount=250),
                ForecastItem(
                    user_id=user_id,
                    item_date=item_date,
                    description="Car repair",
                    amount=600,
                    item_type="expense",
                ),
                ForecastItem(
                    user_id=user_id,
                    item_date=item_date,
                    description="Tax refund",
                    amount=400,
                    item_type="income",
                ),
                RecurringForecastTemplate(
                    user_id=user_id,
                    name="Side gig",
                    amount=300,
                    item_type="income",
                    frequency="monthly",
                    start_date=item_date,
                ),
            ]
        )
        db.commit()

    response = client.get("/v1/monthly-plan?section=forecast", headers=auth_header(token))

    assert response.status_code == 200
    forecast = response.json()["forecast_months"]
    assert len(forecast) == 3
    first = forecast[0]
    assert first["starting_cash"] == pytest.approx(2500)
    assert first["planned_expenses"] == pytest.approx(600)
    assert first["planned_income"] == pytest.approx(700)
    assert first["forecast_income_total"] == pytest.approx(4700)
    assert first["forecast_expense_total"] == pytest.approx(1100)
    assert first["planned_buffer"] == pytest.approx(3600)
    assert not any(item["source"] in {"fixed", "variable"} for item in first["forecast_items"])
    assert {item["source"] for item in first["forecast_items"]} == {"recurring", "one_time"}
    amounts = [item["amount"] for item in first["forecast_items"]]
    assert amounts == sorted(amounts, reverse=True)


def test_cash_projection_get_is_read_only_and_uses_operating_cash(client, monkeypatch):
    token = full_session_token(client, "cash-read-only@example.com")
    user_id = onboard(token)
    with TestingSessionLocal() as db:
        db.add_all(
            [
                Account(user_id=user_id, name="Checking", account_type="checking", current_balance=1800),
                Account(user_id=user_id, name="Savings", account_type="savings", current_balance=9000),
                Account(user_id=user_id, name="Credit Card", account_type="credit card", current_balance=700),
            ]
        )
        db.commit()
    refresh_calls = []

    def fake_refresh(*args, **kwargs):
        refresh_calls.append((args, kwargs))
        return {"synced": 1, "errors": []}

    monkeypatch.setattr("app.services.plaid_service.refresh_plaid_account_balances", fake_refresh)
    response = client.get("/v1/cash-projections?horizon=week&view=list", headers=auth_header(token))

    assert response.status_code == 200
    body = response.json()
    assert body["horizon"] == "week"
    assert body["view"] == "list"
    assert len(body["projection"]["days"]) == 7
    assert body["projection"]["balance_anchor"]["balance"] == pytest.approx(1800)
    assert [row["name"] for row in body["account_rows"] if row["included"]] == ["Checking"]
    assert refresh_calls == []
    with TestingSessionLocal() as db:
        assert db.get(User, user_id).cash_projection_default_horizon == "1m"


def test_cash_projection_preference_is_explicit_validated_and_editor_only(client):
    token = full_session_token(client, "cash-preference@example.com")
    user_id = onboard(token)

    updated = client.patch(
        "/v1/cash-projections/preferences",
        headers=auth_header(token),
        json={"default_horizon": "3m"},
    )

    assert updated.status_code == 200
    assert updated.json() == {"default_horizon": "3m"}
    with TestingSessionLocal() as db:
        assert db.get(User, user_id).cash_projection_default_horizon == "3m"

    projection = client.get("/v1/cash-projections", headers=auth_header(token))
    assert projection.status_code == 200
    assert projection.json()["horizon"] == "3m"

    rejected = client.patch(
        "/v1/cash-projections/preferences",
        headers=auth_header(token),
        json={"default_horizon": "custom"},
    )
    assert rejected.status_code == 422

    viewer_token = shared_session_token(client, user_id, "cash-preference-viewer@example.com", "viewer")
    forbidden = client.patch(
        "/v1/cash-projections/preferences",
        headers=auth_header(viewer_token),
        json={"default_horizon": "6m"},
    )
    assert forbidden.status_code == 403
    with TestingSessionLocal() as db:
        assert db.get(User, user_id).cash_projection_default_horizon == "3m"


def test_cash_projection_explicit_refresh_returns_result(client, monkeypatch):
    token = full_session_token(client, "cash-refresh@example.com")
    user_id = onboard(token)
    with TestingSessionLocal() as db:
        db.add(Account(user_id=user_id, name="Checking", account_type="checking", current_balance=1000))
        db.commit()
    calls = []

    def fake_refresh(db, user, *, purpose):
        calls.append((user.id, purpose))
        account = db.query(Account).filter(Account.user_id == user.id).one()
        account.current_balance = 1250
        db.commit()
        return {"synced": 1, "errors": []}

    monkeypatch.setattr("app.services.plaid_service.refresh_plaid_account_balances", fake_refresh)
    response = client.post(
        "/v1/cash-projections/refresh",
        headers=auth_header(token),
        json={"horizon": "week"},
    )

    assert response.status_code == 200
    assert response.json()["refresh"] == {"synced": 1, "errors": []}
    assert response.json()["projection"]["balance_anchor"]["balance"] == pytest.approx(1250)
    assert calls == [(user_id, "forecast")]


def test_monthly_plan_tools_includes_quick_cash_summary(client):
    token = full_session_token(client, "quick-cash-tools@example.com")
    user_id = onboard(token)
    today = app_today()
    with TestingSessionLocal() as db:
        user = db.get(User, user_id)
        user.profile.next_pay_date = today + timedelta(days=3650)
        db.add(Account(user_id=user_id, name="Checking", account_type="checking", current_balance=1000))
        db.add_all(
            [
                ForecastItem(
                    user_id=user_id,
                    item_date=today + timedelta(days=1),
                    description="Planned bill",
                    amount=200,
                    item_type="expense",
                ),
                ForecastItem(
                    user_id=user_id,
                    item_date=today + timedelta(days=2),
                    description="Expected refund",
                    amount=300,
                    item_type="income",
                ),
            ]
        )
        db.commit()

    response = client.get("/v1/monthly-plan?section=tools", headers=auth_header(token))

    assert response.status_code == 200
    body = response.json()
    assert body["quick_cash_projection"]["balance_anchor"]["balance"] == pytest.approx(1000)
    assert body["quick_cash_week_change"] == pytest.approx(100)
    assert body["quick_cash_week_end_balance"] == pytest.approx(1100)
    assert body["quick_cash_remaining_income"] == pytest.approx(300)
    assert body["quick_cash_remaining_expenses"] == pytest.approx(200)
    assert [row["name"] for row in body["cash_projection_account_rows"] if row["included"]] == ["Checking"]


def _seed_detected_recurring_charge(user_id: int, *, prefix: str) -> None:
    with TestingSessionLocal() as db:
        account = Account(user_id=user_id, name="Checking", account_type="checking", current_balance=1000)
        category = Category(user_id=user_id, name="Fitness", kind="expense", monthly_target=45)
        db.add_all([account, category])
        db.flush()
        today = app_today()
        for days_ago in [90, 60, 30]:
            db.add(
                Transaction(
                    user_id=user_id,
                    account_id=account.id,
                    category_id=category.id,
                    posted_date=today - timedelta(days=days_ago),
                    description="LOCAL FITNESS AUTOPAY",
                    merchant="Local Fitness",
                    amount=-45,
                    transaction_type="expense",
                    source_name="Checking",
                    import_hash=f"{prefix}-{days_ago}",
                )
            )
        db.commit()


def test_cash_projection_can_ignore_detected_recurring_charge(client):
    token = full_session_token(client, "cash-ignore-auto@example.com")
    user_id = onboard(token)
    _seed_detected_recurring_charge(user_id, prefix="ignore-auto")
    page = client.get("/v1/cash-projections?horizon=3m", headers=auth_header(token))
    assert page.status_code == 200
    detection_key = page.json()["detected_recurring"][0]["detection_key"]

    ignored = client.post(
        f"/v1/cash-projections/auto-recurring/{detection_key}",
        headers=auth_header(token),
        json={"action": "ignore", "horizon": "3m"},
    )

    assert ignored.status_code == 200
    assert ignored.json()["detected_recurring"] == []
    assert ignored.json()["ignored_recurring"][0]["detection_key"] == detection_key
    with TestingSessionLocal() as db:
        row = db.query(CashProjectionRecurringIgnore).filter_by(user_id=user_id, detection_key=detection_key).one()
        assert row.notes == "Ignored from Cash Balance Projections by the user."


def test_cash_projection_can_convert_detected_recurring_charge(client):
    token = full_session_token(client, "cash-convert-auto@example.com")
    user_id = onboard(token)
    _seed_detected_recurring_charge(user_id, prefix="convert-auto")
    page = client.get("/v1/cash-projections?horizon=3m", headers=auth_header(token))
    detection_key = page.json()["detected_recurring"][0]["detection_key"]
    first_date = app_today() + timedelta(days=15)
    second_date = app_today() + timedelta(days=30)

    converted = client.post(
        f"/v1/cash-projections/auto-recurring/{detection_key}",
        headers=auth_header(token),
        json={
            "action": "save",
            "horizon": "3m",
            "name": "Local Fitness Adjusted",
            "amount": 50,
            "frequency": "semimonthly",
            "schedule_start_date": str(first_date),
            "second_date": str(second_date),
            "category_label": "Fitness",
        },
    )

    assert converted.status_code == 200
    with TestingSessionLocal() as db:
        template = next(
            row
            for row in db.query(RecurringForecastTemplate).filter_by(user_id=user_id).all()
            if row.name == "Local Fitness Adjusted"
        )
        assert template.amount == pytest.approx(50)
        assert template.frequency == "semimonthly"
        assert template.second_date == second_date
        assert db.query(CashProjectionRecurringIgnore).filter_by(user_id=user_id, detection_key=detection_key).count() == 1


def test_cash_projection_calendar_feed_token_lifecycle_and_content(client):
    token = full_session_token(client, "cash-calendar@example.com")
    user_id = onboard(token)
    event_date = app_today() + timedelta(days=7)
    with TestingSessionLocal() as db:
        user = db.get(User, user_id)
        user.profile.next_pay_date = app_today() + timedelta(days=3650)
        db.add(Account(user_id=user_id, name="Checking", account_type="checking", current_balance=2200))
        db.add(
            Transaction(
                user_id=user_id,
                posted_date=app_today(),
                description="Coffee Shop",
                amount=-50,
                transaction_type="expense",
                import_hash="cash-calendar-coffee",
            )
        )
        db.add(
            ForecastItem(
                user_id=user_id,
                item_date=event_date,
                description="Car Repair",
                amount=300,
                item_type="expense",
                category_label="Transportation",
            )
        )
        db.commit()

    enabled = client.patch(
        "/v1/cash-projections/calendar-feed",
        headers=auth_header(token),
        json={"action": "enable"},
    )
    assert enabled.status_code == 200
    first_url = enabled.json()["feed_url"]
    assert enabled.json()["enabled"] is True
    assert enabled.json()["history_months"] == 3

    feed = client.get(first_url)
    assert feed.status_code == 200
    assert feed.headers["content-type"].startswith("text/calendar")
    unfolded = feed.text.replace("\r\n ", "")
    assert "SUMMARY:Current Balance: $2\\,200.00 (1 expense)" in unfolded
    assert "Actual expense total: -$50.00" in unfolded
    assert "* -$50.00 Coffee Shop" in unfolded
    assert "SUMMARY:Projected Balance: $1\\,900.00 (1 planned expense)" in unfolded
    assert "Planned expense total: -$300.00" in unfolded
    assert "* -$300.00 Car Repair" in unfolded
    assert "Category: Transportation" in unfolded

    reset = client.patch(
        "/v1/cash-projections/calendar-feed",
        headers=auth_header(token),
        json={"action": "reset"},
    )
    second_url = reset.json()["feed_url"]
    assert second_url != first_url
    assert client.get(first_url).status_code == 404
    assert client.get(second_url).status_code == 200

    disabled = client.patch(
        "/v1/cash-projections/calendar-feed",
        headers=auth_header(token),
        json={"action": "disable"},
    )
    assert disabled.status_code == 200
    assert disabled.json()["enabled"] is False
    assert client.get(second_url).status_code == 404


def test_cash_projection_collapses_reconnected_accounts_and_restricts_role_edit(client):
    token = full_session_token(client, "cash-account-dedupe@example.com")
    user_id = onboard(token)
    with TestingSessionLocal() as db:
        older_item = PlaidItem(
            user_id=user_id,
            plaid_item_id="older-item",
            access_token_encrypted="older-token",
            institution_name="Primary Bank",
            status="connected",
        )
        newer_item = PlaidItem(
            user_id=user_id,
            plaid_item_id="newer-item",
            access_token_encrypted="newer-token",
            institution_name="Primary Bank",
            status="connected",
        )
        db.add_all([older_item, newer_item])
        db.flush()
        older = Account(
            user_id=user_id,
            plaid_item_id=older_item.id,
            plaid_account_id="older-checking",
            name="Legacy Checking",
            account_type="checking",
            institution="Primary Bank",
            current_balance=1300,
            is_manual=False,
            mask="1234",
        )
        newer = Account(
            user_id=user_id,
            plaid_item_id=newer_item.id,
            plaid_account_id="newer-checking",
            name="Main Checking",
            account_type="checking",
            institution="Primary Bank",
            current_balance=2400,
            is_manual=False,
            mask="1234",
        )
        db.add_all([older, newer])
        db.flush()
        older.updated_at = older.updated_at - timedelta(days=1)
        older_id, newer_id = older.id, newer.id
        db.commit()

    response = client.get("/v1/cash-projections", headers=auth_header(token))

    assert response.status_code == 200
    assert [row["name"] for row in response.json()["account_rows"]] == ["Main Checking"]
    assert response.json()["projection"]["balance_anchor"]["balance"] == pytest.approx(2400)
    rejected = client.patch(
        f"/v1/accounts/{older_id}/cash-projection-role",
        headers=auth_header(token),
        json={"cash_projection_role": "include"},
    )
    assert rejected.status_code == 422
    accepted = client.patch(
        f"/v1/accounts/{newer_id}/cash-projection-role",
        headers=auth_header(token),
        json={"cash_projection_role": "exclude"},
    )
    assert accepted.status_code == 200
