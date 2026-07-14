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
            "display_name": "Plan User",
            "household_name": "Plan Household",
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


def category_by_name(client, token: str, name: str) -> dict:
    response = client.get("/v1/category-rules", headers=auth_header(token))
    assert response.status_code == 200
    return next(category for category in response.json()["categories"] if category["name"] == name)


def set_monthly_takehome_5200(client, token: str) -> dict:
    # 62400 annual salary on a take-home basis -> 5200/month, no tax rows.
    response = client.patch(
        "/v1/monthly-plan/baseline",
        headers=auth_header(token),
        json={
            "income_amount": 62400,
            "income_type": "salary",
            "income_basis": "take_home",
            "paycheck_cadence": "monthly",
        },
    )
    assert response.status_code == 200
    return response.json()


def previous_month_str() -> str:
    month_start = app_today().replace(day=1)
    previous = (month_start.year, month_start.month - 1) if month_start.month > 1 else (month_start.year - 1, 12)
    return f"{previous[0]:04d}-{previous[1]:02d}"


def test_baseline_update_sets_plan_income_and_month_view(client):
    token = full_session_token(client, "plan-baseline@example.com")
    onboard(token)
    body = set_monthly_takehome_5200(client, token)

    # Hand-computed: 62400 annual salary / 12 = 5200 monthly income.
    assert body["profile"]["monthly_income"] == pytest.approx(5200)
    assert body["profile"]["income_amount_display"] == pytest.approx(62400)
    assert body["plan"]["income"] == pytest.approx(5200)
    assert body["taxes_enabled"] is False

    income_row = body["plan_rows"][0]
    assert income_row["label"] == "Monthly Income"
    assert income_row["planned"] == pytest.approx(5200)
    assert income_row["actual"] == pytest.approx(0)
    # Take-home basis: no Taxes row.
    assert all(row["label"] != "Taxes" for row in body["plan_rows"])

    # Nothing planned or spent: available cash equals income.
    assert body["planned_available"] == pytest.approx(5200)
    assert body["budget_remaining"] == pytest.approx(0)
    assert body["month_income_recorded"] == pytest.approx(5200)

    # The canonical Income budget row reflects planned income "from setup".
    income_section = body["budget_sections"][0]
    assert income_section["kind"] == "income"
    assert income_section["rows"][0]["planned"] == pytest.approx(5200)
    assert income_section["rows"][0]["actual"] == pytest.approx(5200)
    assert income_section["rows"][0]["actual_label"] == "from setup"


def test_month_view_budgets_cleanup_and_activation_math(client):
    token = full_session_token(client, "plan-budgets@example.com")
    onboard(token)
    set_monthly_takehome_5200(client, token)
    groceries = category_by_name(client, token, "Groceries")

    created = client.post(
        "/v1/transactions",
        headers=auth_header(token),
        json={
            "posted_date": str(app_today()),
            "description": "Kroger 250",
            "amount": -250,
            "account_name": "Main Checking",
            "category_id": groceries["id"],
        },
    )
    assert created.status_code == 201
    transaction_id = created.json()["id"]

    before = client.get("/v1/monthly-plan?section=budgets", headers=auth_header(token))
    assert before.status_code == 200
    before_body = before.json()
    # Groceries is still a default category, so the spend lands on the
    # cleanup row (Flask 64b5ed5 active-budget gating).
    assert before_body["unassigned_budget_rows"][0]["label"] == "Other Spending To Categorize"
    assert before_body["unassigned_budget_rows"][0]["actual"] == pytest.approx(250)
    assert before_body["unassigned_budget_rows"][0]["transaction_ids"] == [transaction_id]
    assert before_body["total_budget_planned"] == pytest.approx(0)
    assert before_body["total_budget_actual"] == pytest.approx(250)
    expenses_row = next(row for row in before_body["plan_rows"] if row["label"] == "Expenses")
    assert expenses_row["planned"] == pytest.approx(0)
    assert expenses_row["actual"] == pytest.approx(250)
    assert before_body["budget_remaining"] == pytest.approx(-250)
    assert before_body["planned_available"] == pytest.approx(5200)

    activated = client.patch(f"/v1/budgets/{groceries['id']}", headers=auth_header(token), json={"monthly_target": 600})
    assert activated.status_code == 200

    after = client.get("/v1/monthly-plan?section=budgets", headers=auth_header(token))
    assert after.status_code == 200
    after_body = after.json()
    assert after_body["unassigned_budget_rows"] == []
    expense_section = next(section for section in after_body["budget_sections"] if section["kind"] == "list")
    groceries_row = next(row for row in expense_section["rows"] if row["label"] == "Groceries")
    # Hand-computed: planned 600, actual 250 -> remaining 350, 41.67% "ok".
    assert groceries_row["planned"] == pytest.approx(600)
    assert groceries_row["actual"] == pytest.approx(250)
    assert groceries_row["remaining"] == pytest.approx(350)
    assert groceries_row["progress_percent"] == pytest.approx(250 / 600 * 100)
    assert groceries_row["progress_status"] == "ok"
    assert groceries_row["can_remove_budget"] is True
    assert after_body["total_budget_planned"] == pytest.approx(600)
    assert after_body["total_budget_actual"] == pytest.approx(250)
    assert after_body["total_budget_remaining"] == pytest.approx(350)
    # Available cash drops by the full budgeted amount: 5200 - 600 = 4600.
    assert after_body["planned_available"] == pytest.approx(4600)
    assert after_body["budget_remaining"] == pytest.approx(350)
    expenses_row = next(row for row in after_body["plan_rows"] if row["label"] == "Expenses")
    assert expenses_row["planned"] == pytest.approx(600)
    assert expenses_row["actual"] == pytest.approx(250)


def test_uncategorized_spend_produces_budget_suggestions(client):
    token = full_session_token(client, "plan-suggest@example.com")
    onboard(token)
    set_monthly_takehome_5200(client, token)

    created = client.post(
        "/v1/transactions",
        headers=auth_header(token),
        json={
            "posted_date": str(app_today()),
            "description": "Shell Gas Station",
            "amount": -40,
            "account_name": "Main Checking",
        },
    )
    assert created.status_code == 201
    transaction_id = created.json()["id"]

    body = client.get("/v1/monthly-plan?section=budgets", headers=auth_header(token)).json()
    # The uncategorized spend needs review on the cleanup row...
    assert body["unassigned_budget_rows"][0]["actual"] == pytest.approx(40)
    # ...and the matching unused default category is suggested (Flask 964c369
    # suggestion hints: "shell"/"gas station" -> Fuel/Gasoline).
    suggestion_rows = [row for section in body["suggested_budget_sections"] for row in section["rows"]]
    fuel = next(row for row in suggestion_rows if row["label"] == "Fuel/Gasoline")
    assert fuel["suggestion_match_count"] == 1
    assert fuel["transaction_ids"] == [transaction_id]


def test_pay_period_view_with_month_aligned_period(client):
    token = full_session_token(client, "plan-payperiod@example.com")
    onboard(token)
    set_monthly_takehome_5200(client, token)
    today = app_today()
    month_start = today.replace(day=1)
    next_month_first = (month_start.replace(year=month_start.year + 1, month=1) if month_start.month == 12 else month_start.replace(month=month_start.month + 1))
    updated = client.patch(
        "/v1/monthly-plan/baseline",
        headers=auth_header(token),
        json={"paycheck_cadence": "monthly", "next_pay_date": str(next_month_first)},
    )
    assert updated.status_code == 200

    body = client.get("/v1/monthly-plan?view=pay_period", headers=auth_header(token)).json()
    # Monthly cadence anchored to the 1st: the pay period is the whole month.
    assert body["pay_period"]["start"] == str(month_start)
    assert body["pay_period"]["next_pay_date"] == str(next_month_first)
    income_row = body["plan_rows"][0]
    assert income_row["label"] == "Pay Period Income"
    assert income_row["planned"] == pytest.approx(5200)
    # Income budget row falls back to planned income (provisional behavior
    # for the flagged Flask pay-period UnboundLocalError).
    income_section = body["budget_sections"][0]
    assert income_section["rows"][0]["actual"] == pytest.approx(5200)
    assert income_section["rows"][0]["actual_label"] == "from setup"
    assert body["planned_available"] == pytest.approx(5200)


def test_budget_history_mode_and_baseline_feature_gate(client):
    token = full_session_token(client, "plan-gates@example.com")
    onboard(token, plan=None)

    history = client.get(
        f"/v1/monthly-plan?section=budgets&budget_month={previous_month_str()}",
        headers=auth_header(token),
    )
    assert history.status_code == 200
    assert history.json()["budget_history_mode"] is True
    assert history.json()["budget_is_current_month"] is False
    assert history.json()["budget_drag_enabled"] is False

    # No plan selected: Income Planning is gated (min plan "basic").
    locked_get = client.get("/v1/monthly-plan?section=baseline", headers=auth_header(token))
    assert locked_get.status_code == 403
    assert locked_get.json()["detail"]["code"] == "feature_locked"

    locked_patch = client.patch("/v1/monthly-plan/baseline", headers=auth_header(token), json={"income_amount": 50000})
    assert locked_patch.status_code == 403

    core = client.patch(
        "/v1/monthly-plan/baseline",
        headers=auth_header(token),
        json={"baseline_scope": "core", "income_amount": 62400, "income_type": "salary", "income_basis": "take_home"},
    )
    assert core.status_code == 200
    assert core.json()["profile"]["monthly_income"] == pytest.approx(5200)


def test_baseline_semimonthly_timing_fields(client):
    token = full_session_token(client, "plan-timing@example.com")
    onboard(token)
    today = app_today()
    first = today.replace(day=1)
    next_month_first = (first.replace(year=first.year + 1, month=1) if first.month == 12 else first.replace(month=first.month + 1))
    fifteenth = next_month_first.replace(day=15)
    body = client.patch(
        "/v1/monthly-plan/baseline",
        headers=auth_header(token),
        json={
            "income_amount": 62400,
            "income_type": "salary",
            "income_basis": "take_home",
            "paycheck_cadence": "semimonthly",
            "next_pay_date": str(next_month_first),
            "second_date": str(fifteenth),
        },
    ).json()
    assert body["profile"]["paycheck_cadence"] == "semimonthly"
    assert body["profile"]["next_pay_date"] == str(next_month_first)
    assert body["profile"]["paycheck_second_date"] == str(fifteenth)
    assert body["profile"]["paycheck_second_day_of_month"] == 15
