from __future__ import annotations

from datetime import date

import pytest

from app.core.security import decode_token
from app.models import Account, Category, FixedExpenseItem, Goal, HouseholdMember, LoanPlan, Transaction, User
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
            "display_name": "Loan User",
            "household_name": "Loan Household",
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


def configure_user(token: str, *, plan: str = "basic", onboarded: bool = True) -> int:
    payload = decode_token(token)
    with TestingSessionLocal() as db:
        user = db.get(User, int(payload["user_id"]))
        user.selected_plan = plan
        if onboarded:
            user.profile.income_amount = 48000
            user.profile.monthly_income = 4000
            user.profile.income_type = "salary"
        db.commit()
        return user.id


def onboarded_token(client, email: str, *, plan: str = "basic") -> tuple[str, int]:
    token = full_session_token(client, email)
    return token, configure_user(token, plan=plan)


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


def add_loan_item(user_id: int, *, name: str = "Truck Loan", amount: float = 500) -> int:
    with TestingSessionLocal() as db:
        item = FixedExpenseItem(
            user_id=user_id,
            name=name,
            amount=amount,
            due_day=10,
            start_date=app_today().replace(day=10),
            frequency="monthly",
            category_label="Vehicle Payments",
            is_loan=True,
        )
        db.add(item)
        db.commit()
        return item.id


def test_loan_openapi_contract_paths_and_methods(client):
    schema = client.get("/openapi.json").json()
    paths = schema["paths"]
    assert set(paths["/v1/loan-plans"]) == {"get"}
    assert set(paths["/v1/loan-plans/{fixed_expense_item_id}"]) == {"get", "patch"}
    assert set(paths["/v1/loan-plans/{fixed_expense_item_id}/selected-scenario"]) == {"patch"}
    assert set(paths["/v1/transactions/{transaction_id}/loan-plan"]) == {"post"}
    assert set(paths["/v1/budgets/{category_id}/loan-plan"]) == {"post"}
    update_schema = paths["/v1/loan-plans/{fixed_expense_item_id}"]["patch"]["requestBody"]["content"]["application/json"]["schema"]
    assert update_schema["$ref"].endswith("/LoanPlanUpdateRequest")


def test_loan_plan_directory_detail_update_and_scenario_side_effects(client):
    token, user_id = onboarded_token(client, "loan-plan@example.com")
    item_id = add_loan_item(user_id)
    headers = auth_header(token)

    listed = client.get("/v1/loan-plans", headers=headers)
    assert listed.status_code == 200
    listed_body = listed.json()
    assert listed_body["items"][0] == {
        "fixed_expense_item_id": item_id,
        "name": "Truck Loan",
        "loan_kind": "loan",
        "monthly_payment": 500.0,
        "selected_extra": 0.0,
        "total_monthly": 500.0,
        "principal_balance": 0.0,
        "current_balance": 0.0,
        "collateral_value": 0.0,
        "selected_scenario": "base",
    }
    assert listed_body["total_debt_monthly"] == 500.0
    assert listed_body["total_debt_balance"] == 0.0
    assert listed_body["debt_to_income_ratio"] == pytest.approx(0.125)
    assert "Vehicle Payments" in listed_body["loan_category_label_options"]
    assert listed_body["today"] == app_today().isoformat()
    assert listed_body["recurring_frequency_options"]["semimonthly"] == "Twice Per Month"
    assert listed_body["weekday_options"]["0"] == "Monday"
    assert listed_body["monthly_week_options"]["5"] == "Last"

    with TestingSessionLocal() as db:
        db.add(
            Account(
                user_id=user_id,
                name="Rewards Credit Card",
                account_type="credit",
                current_balance=2000,
                is_manual=True,
            )
        )
        db.commit()
    # Flask estimates an otherwise-unplanned revolving payment as the lesser
    # of the balance or max(2% of balance, $25): $40 here.
    assert client.get("/v1/loan-plans", headers=headers).json()["debt_to_income_ratio"] == pytest.approx(0.135)

    detail = client.get(f"/v1/loan-plans/{item_id}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["plan"] is None
    assert detail.json()["scenarios"] == []
    assert detail.json()["selected_schedule"] == []

    updated = client.patch(
        f"/v1/loan-plans/{item_id}",
        headers=headers,
        json={
            "principal_balance": 1200,
            "collateral_value": 900,
            "annual_interest_rate": 0,
            "term_value": 12,
            "term_unit": "months",
            "regular_payment": 500,
            "extra_payment_one": 100,
            "extra_payment_two": 200,
            "selected_scenario": "base",
            "notes": "Zero-interest parity fixture",
        },
    )
    assert updated.status_code == 200
    updated_body = updated.json()
    assert updated_body["plan"]["term_months"] == 12
    assert updated_body["plan"]["regular_payment"] == 500.0
    # Flask recomputes the baseline from principal/term, so the stored $500
    # regular payment does not change these hand-computed payoff lengths.
    assert [(row["key"], row["months"]) for row in updated_body["scenarios"]] == [
        ("base", 12),
        ("extra_one", 6),
        ("extra_two", 4),
    ]
    assert len(updated_body["selected_schedule"]) == 12
    assert updated_body["selected_schedule"][0]["payment"] == 100.0

    selected = client.patch(
        f"/v1/loan-plans/{item_id}/selected-scenario",
        headers=headers,
        json={"selected_scenario": "extra_two"},
    )
    assert selected.status_code == 200
    assert selected.json()["plan"]["selected_scenario"] == "extra_two"
    assert len(selected.json()["selected_schedule"]) == 4
    assert client.get("/v1/loan-plans", headers=headers).json()["debt_to_income_ratio"] == pytest.approx(0.185)
    monthly_plan = client.get("/v1/monthly-plan?section=budgets", headers=headers)
    assert monthly_plan.status_code == 200
    monthly_body = monthly_plan.json()
    assert [item["id"] for item in monthly_body["loan_items"]] == [item_id]
    assert monthly_body["loan_plans"][str(item_id)]["selected_scenario"] == "extra_two"
    assert [row["months"] for row in monthly_body["loan_scenarios"][str(item_id)]] == [12, 6, 4]
    with TestingSessionLocal() as db:
        budget = db.query(Category).filter_by(user_id=user_id, name="Vehicle Payments").one()
        goal = db.query(Goal).filter_by(user_id=user_id, goal_type="debt", fixed_expense_item_id=item_id).one()
        assert budget.monthly_target == 700.0
        assert budget.is_default is False
        assert goal.name == "Truck Loan Paydown Plan"
        assert goal.target_amount == 1200.0
        assert goal.monthly_contribution == 200.0

    reset = client.patch(
        f"/v1/loan-plans/{item_id}/selected-scenario",
        headers=headers,
        json={"selected_scenario": "invalid-value"},
    )
    assert reset.status_code == 200
    assert reset.json()["plan"]["selected_scenario"] == "base"
    with TestingSessionLocal() as db:
        assert db.query(Category).filter_by(user_id=user_id, name="Vehicle Payments").one().monthly_target == 500.0
        assert db.query(Goal).filter_by(user_id=user_id, fixed_expense_item_id=item_id).count() == 0


def test_mortgage_transaction_and_budget_shortcuts_return_resource_and_actions(client):
    token, user_id = onboarded_token(client, "loan-shortcuts@example.com", plan="premium")
    headers = auth_header(token)
    with TestingSessionLocal() as db:
        mortgage = Category(
            user_id=user_id,
            name="Mortgage/Rent",
            kind="expense",
            monthly_target=2100,
            is_default=False,
        )
        db.add(mortgage)
        db.flush()
        transaction = Transaction(
            user_id=user_id,
            category_id=mortgage.id,
            posted_date=date(2026, 7, 1),
            description="Mortgage Servicer",
            merchant="Mortgage Servicer",
            amount=-2100,
            transaction_type="expense",
            source_name="Checking",
            import_hash="loan-shortcut-transaction",
        )
        db.add(transaction)
        db.commit()
        category_id = mortgage.id
        transaction_id = transaction.id

    transactions = client.get("/v1/transactions", headers=headers)
    assert transactions.status_code == 200
    assert transactions.json()["amortization_actions"][str(transaction_id)] == {
        "action": "create",
        "fixed_expense_item_id": None,
        "label": "Create Amortization Schedule",
        "hint": "Start a mortgage payoff schedule from this Mortgage/Rent transaction.",
    }
    category_update = client.patch(
        f"/v1/transactions/{transaction_id}/category",
        headers=headers,
        json={"category_id": category_id},
    )
    assert category_update.status_code == 200
    assert category_update.json()["amortization_action"]["action"] == "create"

    started = client.post(f"/v1/transactions/{transaction_id}/loan-plan", headers=headers)
    assert started.status_code == 200
    started_body = started.json()
    assert started_body["created_fixed_expense"] is True
    assert started_body["loan_kind"] == "mortgage"
    assert started_body["plan"] is None
    assert started_body["fixed_expense"]["name"] == "Mortgage Servicer"
    assert started_body["fixed_expense"]["amount"] == 2100.0
    assert started_body["fixed_expense"]["is_loan"] is True
    item_id = started_body["fixed_expense"]["id"]

    refreshed = client.get("/v1/transactions", headers=headers).json()
    assert refreshed["amortization_actions"][str(transaction_id)]["action"] == "open"
    assert refreshed["amortization_actions"][str(transaction_id)]["fixed_expense_item_id"] == item_id

    category_started = client.post(f"/v1/budgets/{category_id}/loan-plan", headers=headers)
    assert category_started.status_code == 200
    assert category_started.json()["created_fixed_expense"] is False
    assert category_started.json()["fixed_expense"]["id"] == item_id

    monthly_plan = client.get("/v1/monthly-plan?section=budgets", headers=headers)
    assert monthly_plan.status_code == 200
    mortgage_row = next(
        row
        for section in monthly_plan.json()["budget_sections"]
        for row in section["rows"]
        if row["label"] == "Mortgage/Rent"
    )
    assert mortgage_row["amortization_action"] == {
        "action": "open",
        "fixed_expense_item_id": item_id,
        "label": "Open Amortization Schedule",
        "hint": None,
    }


def test_loan_access_feature_gate_household_roles_and_owner_isolation(client):
    owner_token, owner_id = onboarded_token(client, "loan-owner@example.com")
    item_id = add_loan_item(owner_id, name="Private Loan")
    owner_headers = auth_header(owner_token)
    assert client.patch(
        f"/v1/loan-plans/{item_id}",
        headers=owner_headers,
        json={"principal_balance": 600, "term_months": 6},
    ).status_code == 200

    viewer_token = shared_session_token(client, owner_id, "loan-viewer@example.com", "viewer")
    assert client.get("/v1/loan-plans", headers=auth_header(viewer_token)).status_code == 200
    assert client.get(f"/v1/loan-plans/{item_id}", headers=auth_header(viewer_token)).status_code == 200
    assert client.patch(
        f"/v1/loan-plans/{item_id}/selected-scenario",
        headers=auth_header(viewer_token),
        json={"selected_scenario": "base"},
    ).status_code == 403

    other_token, _ = onboarded_token(client, "loan-other@example.com")
    assert client.get(f"/v1/loan-plans/{item_id}", headers=auth_header(other_token)).status_code == 404

    locked_token, locked_id = onboarded_token(client, "loan-locked@example.com", plan="at_cost")
    locked_item_id = add_loan_item(locked_id, name="Locked Loan")
    locked = client.get(f"/v1/loan-plans/{locked_item_id}", headers=auth_header(locked_token))
    assert locked.status_code == 403
    assert locked.json()["detail"]["code"] == "feature_locked"
    with TestingSessionLocal() as db:
        mortgage = Category(
            user_id=locked_id,
            name="Mortgage/Rent",
            kind="expense",
            monthly_target=1800,
            is_default=False,
        )
        db.add(mortgage)
        db.flush()
        transaction = Transaction(
            user_id=locked_id,
            category_id=mortgage.id,
            posted_date=date(2026, 7, 1),
            description="Locked Mortgage",
            merchant="Locked Mortgage",
            amount=-1800,
            transaction_type="expense",
            source_name="Checking",
            import_hash="locked-loan-shortcut",
        )
        db.add(transaction)
        db.commit()
        locked_transaction_id = transaction.id
    locked_headers = auth_header(locked_token)
    assert str(locked_transaction_id) not in client.get("/v1/transactions", headers=locked_headers).json()["amortization_actions"]
    locked_shortcut = client.post(f"/v1/transactions/{locked_transaction_id}/loan-plan", headers=locked_headers)
    assert locked_shortcut.status_code == 403
    assert locked_shortcut.json()["detail"]["code"] == "feature_locked"

    pending_onboarding_token = full_session_token(client, "loan-onboarding@example.com")
    configure_user(pending_onboarding_token, onboarded=False)
    onboarding = client.get("/v1/loan-plans", headers=auth_header(pending_onboarding_token))
    assert onboarding.status_code == 409
    assert onboarding.json()["detail"]["code"] == "onboarding_required"
