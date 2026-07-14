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
            "display_name": "Items User",
            "household_name": "Items Household",
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


def onboard(token: str) -> int:
    payload = decode_token(token)
    with TestingSessionLocal() as db:
        user = db.get(User, int(payload["user_id"]))
        user.profile.income_amount = 1
        user.profile.monthly_income = 1
        user.selected_plan = "basic"
        db.commit()
        return user.id


def set_income(client, token: str) -> None:
    response = client.patch(
        "/v1/monthly-plan/baseline",
        headers=auth_header(token),
        json={"income_amount": 62400, "income_type": "salary", "income_basis": "take_home", "paycheck_cadence": "monthly"},
    )
    assert response.status_code == 200


def category_by_name(client, token: str, name: str) -> dict:
    response = client.get("/v1/category-rules", headers=auth_header(token))
    assert response.status_code == 200
    return next(category for category in response.json()["categories"] if category["name"] == name)


def test_fixed_expense_lifecycle_and_amount_patch(client):
    token = full_session_token(client, "items-fixed@example.com")
    onboard(token)
    set_income(client, token)
    month_first = app_today().replace(day=1)

    created = client.post(
        "/v1/fixed-expenses",
        headers=auth_header(token),
        json={"name": "Rent", "amount": 1200, "frequency": "monthly", "start_date": str(month_first), "category_label": "Mortgage/Rent"},
    )
    assert created.status_code == 201
    body = created.json()
    assert body["monthly_amount"] == pytest.approx(1200)
    assert body["due_day"] == 1
    assert body["is_loan"] is False
    item_id = body["id"]

    plan = client.get("/v1/monthly-plan", headers=auth_header(token)).json()
    assert plan["fixed_total"] == pytest.approx(1200)
    assert plan["plan"]["fixed_expenses"] == pytest.approx(1200)
    # Take-home income, no budgets active yet: 5200 - 1200 = 4000 available.
    assert plan["planned_available"] == pytest.approx(4000)

    edited = client.patch(
        f"/v1/fixed-expenses/{item_id}",
        headers=auth_header(token),
        json={"name": "Rent", "amount": 1500, "frequency": "monthly", "start_date": str(month_first), "category_label": "Mortgage/Rent"},
    )
    assert edited.status_code == 200
    assert edited.json()["monthly_amount"] == pytest.approx(1500)

    # Amount-only patch (Flask edit_fixed_expense_amount): monthly target 900
    # on a monthly item stores 900. Mortgage/Rent is a loan-category label, so
    # the loan budget sync runs — and Flask's sticky-target rule keeps the
    # 1500 target: 900 is not an increase, the category is no longer default,
    # and 1500 is not among the auto targets recomputed from the new amount.
    amount_patch = client.patch(f"/v1/fixed-expenses/{item_id}", headers=auth_header(token), json={"monthly_target": 900})
    assert amount_patch.status_code == 200
    assert amount_patch.json()["amount"] == pytest.approx(900)
    mortgage = category_by_name(client, token, "Mortgage/Rent")
    assert mortgage["monthly_target"] == pytest.approx(1500)
    assert mortgage["is_default"] is False

    # Validation parity.
    assert client.post("/v1/fixed-expenses", headers=auth_header(token), json={"amount": 10, "start_date": str(month_first)}).status_code == 422
    invalid_date = client.post("/v1/fixed-expenses", headers=auth_header(token), json={"name": "X", "amount": 10, "start_date": "not-a-date"})
    assert invalid_date.status_code == 422
    assert invalid_date.json()["detail"] == "Enter a valid fixed expense date."
    zero_target = client.patch(f"/v1/fixed-expenses/{item_id}", headers=auth_header(token), json={"monthly_target": 0})
    assert zero_target.status_code == 422

    deleted = client.request("DELETE", f"/v1/fixed-expenses/{item_id}", headers=auth_header(token), json={})
    assert deleted.status_code == 200
    assert deleted.json()["deleted_item_id"] == item_id
    assert client.get("/v1/monthly-plan", headers=auth_header(token)).json()["fixed_total"] == pytest.approx(0)


def test_fixed_expense_biweekly_round_trip(client):
    token = full_session_token(client, "items-biweekly@example.com")
    onboard(token)
    set_income(client, token)

    created = client.post(
        "/v1/fixed-expenses",
        headers=auth_header(token),
        json={"name": "Insurance Draft", "amount": 120, "frequency": "biweekly", "start_date": str(app_today())},
    )
    assert created.status_code == 201
    body = created.json()
    # Biweekly items inherit the start date's weekday (Flask timing helper).
    assert body["days_of_week"] == str(app_today().weekday())
    # Hand-computed: 120 every two weeks -> 120 * 26 / 12 = 260/month.
    assert body["monthly_amount"] == pytest.approx(260)

    # Amount-only round trip: 260/month -> 260 * 12 / 26 = 120 per occurrence.
    patched = client.patch(f"/v1/fixed-expenses/{body['id']}", headers=auth_header(token), json={"monthly_target": 260})
    assert patched.status_code == 200
    assert patched.json()["amount"] == pytest.approx(120)


def test_loan_entry_syncs_budget_category(client):
    token = full_session_token(client, "items-loan@example.com")
    onboard(token)
    set_income(client, token)

    created = client.post(
        "/v1/fixed-expenses",
        headers=auth_header(token),
        json={
            "name": "Car Loan",
            "amount": 350,
            "frequency": "monthly",
            "start_date": str(app_today().replace(day=1)),
            "category_label": "Vehicle Payments",
            "entry_context": "loan",
        },
    )
    assert created.status_code == 201
    assert created.json()["is_loan"] is True
    # Hand-computed loan budget target: max(350, 350 + 0 extra) = 350.
    vehicle = category_by_name(client, token, "Vehicle Payments")
    assert vehicle["monthly_target"] == pytest.approx(350)
    assert vehicle["is_default"] is False


def test_variable_expense_lifecycle_and_amount_patch(client):
    token = full_session_token(client, "items-variable@example.com")
    onboard(token)
    set_income(client, token)

    created = client.post(
        "/v1/variable-expenses",
        headers=auth_header(token),
        json={"name": "Fun Money", "amount": 30, "frequency": "weekly", "use_specific_date": True, "days_of_week": [1, 3]},
    )
    assert created.status_code == 201
    body = created.json()
    assert body["days_of_week"] == "1,3"
    # Hand-computed: $30 twice a week -> 30 * 52/12 * 2 = 260/month.
    assert body["monthly_amount"] == pytest.approx(260)
    item_id = body["id"]

    plan = client.get("/v1/monthly-plan", headers=auth_header(token)).json()
    assert plan["variable_plan_total"] == pytest.approx(260)

    # Amount-only patch: monthly target 130 over 2 weekly occurrences ->
    # (130 / 2) * 12 / 52 = 15 per occurrence.
    patched = client.patch(f"/v1/variable-expenses/{item_id}", headers=auth_header(token), json={"monthly_target": 130})
    assert patched.status_code == 200
    assert patched.json()["amount"] == pytest.approx(15)
    # Budget target syncs to the item's category ("Other" fallback): 130.
    other = category_by_name(client, token, "Other")
    assert other["monthly_target"] == pytest.approx(130)

    # Validation parity.
    missing_date = client.post(
        "/v1/variable-expenses",
        headers=auth_header(token),
        json={"name": "X", "amount": 5, "frequency": "monthly", "use_specific_date": True},
    )
    assert missing_date.status_code == 422
    assert missing_date.json()["detail"] == "Enter a valid date for the monthly variable expense."
    missing_weekdays = client.post(
        "/v1/variable-expenses",
        headers=auth_header(token),
        json={"name": "X", "amount": 5, "frequency": "weekly", "use_specific_date": True},
    )
    assert missing_weekdays.status_code == 422

    deleted = client.request("DELETE", f"/v1/variable-expenses/{item_id}", headers=auth_header(token), json={})
    assert deleted.status_code == 200
    assert client.get("/v1/monthly-plan", headers=auth_header(token)).json()["variable_plan_total"] == pytest.approx(0)
