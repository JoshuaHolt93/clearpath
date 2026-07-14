from __future__ import annotations

import pytest

from app.core.security import decode_token
from app.models import User
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
            "display_name": "Forecast User",
            "household_name": "Forecast Household",
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


def onboard(token: str, *, plan: str | None = "basic") -> int:
    payload = decode_token(token)
    with TestingSessionLocal() as db:
        user = db.get(User, int(payload["user_id"]))
        user.profile.income_amount = 1
        user.profile.monthly_income = 1
        if plan:
            user.selected_plan = plan
        db.commit()
        return user.id


def next_month_first():
    first = app_today().replace(day=1)
    return first.replace(year=first.year + 1, month=1) if first.month == 12 else first.replace(month=first.month + 1)


def test_forecast_item_lifecycle(client):
    token = full_session_token(client, "forecast-items@example.com")
    onboard(token)

    created = client.post(
        "/v1/forecast-items",
        headers=auth_header(token),
        json={"item_date": str(app_today()), "description": "Car Registration", "amount": 150, "item_type": "expense"},
    )
    assert created.status_code == 201
    body = created.json()
    assert body["description"] == "Car Registration"
    assert body["amount"] == pytest.approx(150)
    item_id = body["id"]

    plan = client.get("/v1/monthly-plan", headers=auth_header(token)).json()
    assert any(item["id"] == item_id for item in plan["forecast_items"])
    forecast_sources = [row for row in plan["variable_expense_rows"] if row["item_type"] == "forecast_item"]
    assert forecast_sources and forecast_sources[0]["amount"] == pytest.approx(150)

    edited = client.patch(
        f"/v1/forecast-items/{item_id}",
        headers=auth_header(token),
        json={"item_date": str(app_today()), "description": "Car Registration", "amount": 175, "item_type": "expense"},
    )
    assert edited.status_code == 200
    assert edited.json()["amount"] == pytest.approx(175)

    bad_type = client.patch(
        f"/v1/forecast-items/{item_id}",
        headers=auth_header(token),
        json={"item_date": str(app_today()), "description": "X", "amount": 10, "item_type": "transfer"},
    )
    assert bad_type.status_code == 422
    assert bad_type.json()["detail"] == "Choose whether this forecast item is income or an expense."

    missing = client.post("/v1/forecast-items", headers=auth_header(token), json={"description": "X", "amount": 10})
    assert missing.status_code == 422
    assert missing.json()["detail"] == "Date, description, and a positive amount are required."

    deleted = client.request("DELETE", f"/v1/forecast-items/{item_id}", headers=auth_header(token), json={})
    assert deleted.status_code == 200
    assert deleted.json()["deleted_item_id"] == item_id


def test_recurring_template_lifecycle_and_amount_patch(client):
    token = full_session_token(client, "recurring-plain@example.com")
    onboard(token)

    created = client.post(
        "/v1/recurring-templates",
        headers=auth_header(token),
        json={"name": "HOA Dues", "amount": 75, "item_type": "expense", "frequency": "quarterly", "start_date": str(app_today().replace(day=1))},
    )
    assert created.status_code == 201
    body = created.json()
    # Hand-computed: 75 quarterly -> 75 * 4 / 12 = 25/month.
    assert body["monthly_amount"] == pytest.approx(25)
    template_id = body["id"]

    # Monthly-week pattern without a start date defaults to the current month
    # (Flask fallback) and stores the pattern.
    pattern = client.post(
        "/v1/recurring-templates",
        headers=auth_header(token),
        json={
            "name": "Cleaning Service",
            "amount": 60,
            "item_type": "expense",
            "frequency": "monthly",
            "recurring_monthly_week_numbers": [1, 3],
            "recurring_monthly_weekday": 4,
        },
    )
    assert pattern.status_code == 201
    assert pattern.json()["start_date"] == str(app_today().replace(day=1))
    assert pattern.json()["monthly_week_numbers"] == "1,3"
    assert pattern.json()["monthly_weekday"] == 4

    # Amount-only patch: 30/month on a quarterly template -> 30 * 3 = 90.
    patched = client.patch(f"/v1/recurring-templates/{template_id}", headers=auth_header(token), json={"monthly_target": 30})
    assert patched.status_code == 200
    assert patched.json()["amount"] == pytest.approx(90)
    assert patched.json()["monthly_amount"] == pytest.approx(30)

    deleted = client.request("DELETE", f"/v1/recurring-templates/{template_id}", headers=auth_header(token), json={})
    assert deleted.status_code == 200
    assert deleted.json()["deleted_template_id"] == template_id


def test_future_income_adjustment_gate_and_validation(client):
    token = full_session_token(client, "recurring-income@example.com")
    onboard(token, plan=None)

    # income templates are feature-gated at plan "basic".
    locked = client.post(
        "/v1/recurring-templates",
        headers=auth_header(token),
        json={"name": "New Job", "amount": 1000, "item_type": "income", "start_date": str(next_month_first())},
    )
    assert locked.status_code == 403
    assert locked.json()["detail"]["code"] == "feature_locked"

    with TestingSessionLocal() as db:
        payload = decode_token(token)
        user = db.get(User, int(payload["user_id"]))
        user.selected_plan = "basic"
        db.commit()

    start = next_month_first()
    first_pay = start.replace(day=3)
    created = client.post(
        "/v1/recurring-templates",
        headers=auth_header(token),
        json={
            "name": "New Job",
            "item_type": "income",
            "income_adjustment": True,
            "start_date": str(start),
            "income_amount": 90000,
            "income_basis": "gross",
            "income_type": "salary",
            "paycheck_cadence": "biweekly",
            "income_next_pay_date": str(first_pay),
            "tax_filing_status": "single",
            "include_payroll_taxes": True,
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert body["item_type"] == "income"
    assert body["income_replacement"] is True
    assert body["frequency"] == "biweekly"
    assert body["paycheck_cadence"] == "biweekly"
    assert body["category_label"] == "Income"
    # Biweekly with no explicit weekdays inherits the first pay date's weekday.
    assert body["days_of_week"] == str(first_pay.weekday())
    assert body["tax_filing_status"] == "single"
    assert body["include_payroll_taxes"] is True

    plan = client.get("/v1/monthly-plan", headers=auth_header(token)).json()
    assert any(template["id"] == body["id"] for template in plan["future_income_templates"])

    bad_order = client.post(
        "/v1/recurring-templates",
        headers=auth_header(token),
        json={
            "name": "Backwards",
            "item_type": "income",
            "income_adjustment": True,
            "start_date": str(start),
            "income_amount": 90000,
            "income_next_pay_date": str(app_today()),
        },
    )
    assert bad_order.status_code == 422
    assert bad_order.json()["detail"] == "First pay date cannot be before the adjustment start date."


def test_mark_recurring_from_transaction_category_patch(client):
    token = full_session_token(client, "recurring-mark@example.com")
    onboard(token)

    created = client.post(
        "/v1/transactions",
        headers=auth_header(token),
        json={"posted_date": str(app_today()), "description": "Netflix.com", "amount": -15.49, "account_name": "Main Checking"},
    )
    assert created.status_code == 201
    transaction_id = created.json()["id"]

    response = client.get("/v1/category-rules", headers=auth_header(token))
    streaming = next(category for category in response.json()["categories"] if category["name"] == "Streaming Services")

    patched = client.patch(
        f"/v1/transactions/{transaction_id}/category",
        headers=auth_header(token),
        json={"category_id": streaming["id"], "mark_recurring": True, "recurring_frequency": "monthly"},
    )
    assert patched.status_code == 200
    body = patched.json()
    assert body["recurring_success"] is True
    assert body["recurring_message"] == "Category updated and recurring expense schedule added to forecasts and cash balance projections."

    plan = client.get("/v1/monthly-plan", headers=auth_header(token)).json()
    template = next(template for template in plan["recurring_templates"] if template["name"] == "Netflix.com")
    assert template["amount"] == pytest.approx(15.49)
    assert template["category_label"] == "Streaming Services"
    assert f"transaction #{transaction_id}" in template["notes"]

    # The transactions list flags the row as recurring (Flask 0ddefb0).
    listed = client.get("/v1/transactions", headers=auth_header(token))
    assert transaction_id in listed.json()["recurring_transaction_ids"]

    # Marking again matches the existing template instead of duplicating.
    repatched = client.patch(
        f"/v1/transactions/{transaction_id}/category",
        headers=auth_header(token),
        json={"category_id": streaming["id"], "mark_recurring": True, "recurring_frequency": "monthly"},
    )
    assert repatched.status_code == 200
    assert repatched.json()["recurring_message"] == "Category updated and recurring expense schedule updated for matching transactions."
    plan = client.get("/v1/monthly-plan", headers=auth_header(token)).json()
    assert len([template for template in plan["recurring_templates"] if template["name"] == "Netflix.com"]) == 1

    # Income transactions cannot be marked recurring (Flask parity message).
    income_txn = client.post(
        "/v1/transactions",
        headers=auth_header(token),
        json={"posted_date": str(app_today()), "description": "Paycheck", "amount": 2000, "account_name": "Main Checking"},
    ).json()
    income_category = next(category for category in client.get("/v1/category-rules", headers=auth_header(token)).json()["categories"] if category["name"] == "Income")
    income_patch = client.patch(
        f"/v1/transactions/{income_txn['id']}/category",
        headers=auth_header(token),
        json={"category_id": income_category["id"], "mark_recurring": True},
    )
    assert income_patch.status_code == 200
    assert income_patch.json()["recurring_success"] is False
    assert income_patch.json()["recurring_message"].startswith("Category updated. Recurring schedules from Transactions are for expense charges")
