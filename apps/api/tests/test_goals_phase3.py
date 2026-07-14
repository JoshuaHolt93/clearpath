from __future__ import annotations

import pytest

from app.core.security import decode_token
from app.models import Category, FixedExpenseItem, Goal, HouseholdMember, LoanPlan, MonthlyPlan, User
from app.services.planning_service import add_months, app_today
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
            "display_name": "Goal User",
            "household_name": "Goal Household",
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


def mark_onboarded(token: str) -> int:
    payload = decode_token(token)
    with TestingSessionLocal() as db:
        user = db.get(User, int(payload["user_id"]))
        user.profile.income_amount = 1
        user.profile.monthly_income = 1
        db.commit()
        return user.id


def onboarded_token(client, email: str) -> tuple[str, int]:
    token = full_session_token(client, email)
    return token, mark_onboarded(token)


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


def test_savings_goal_crud_syncs_budget_and_monthly_plan(client):
    token, user_id = onboarded_token(client, "goal-savings@example.com")
    target_date = add_months(app_today(), 2)

    created = client.post(
        "/v1/goals",
        headers=auth_header(token),
        json={
            "name": "Emergency Fund",
            "goal_type": "savings",
            "target_amount": 1000,
            "current_amount": 200,
            "monthly_contribution": 100,
            "target_date": target_date.isoformat(),
        },
    )
    assert created.status_code == 201
    body = created.json()
    goal_id = body["goal"]["id"]
    assert body["goal"]["target_amount"] == 1000.0
    assert body["goal"]["current_amount"] == 200.0
    assert body["progress"] == 20.0
    assert body["remaining"] == 800.0
    assert body["required_monthly"] == 400.0
    assert body["timeline"] == "About 8 months"

    with TestingSessionLocal() as db:
        emergency = db.query(Category).filter_by(user_id=user_id, name="Emergency Fund").one()
        plan = db.query(MonthlyPlan).filter_by(user_id=user_id).one()
        assert emergency.monthly_target == 100.0
        assert emergency.is_default is False
        assert plan.planned_savings == 100.0

    # PATCH fields-set behavior preserves omitted goal fields while applying
    # Flask's name-based savings-category mapping and plan resync.
    updated = client.patch(
        f"/v1/goals/{goal_id}",
        headers=auth_header(token),
        json={"name": "College Tuition", "monthly_contribution": 250},
    )
    assert updated.status_code == 200
    updated_body = updated.json()
    assert updated_body["goal"]["target_amount"] == 1000.0
    assert updated_body["goal"]["current_amount"] == 200.0
    assert updated_body["goal"]["target_date"] == target_date.isoformat()
    assert updated_body["timeline"] == "About 4 months"

    with TestingSessionLocal() as db:
        education = db.query(Category).filter_by(user_id=user_id, name="Education Savings").one()
        emergency = db.query(Category).filter_by(user_id=user_id, name="Emergency Fund").one()
        plan = db.query(MonthlyPlan).filter_by(user_id=user_id).one()
        assert education.monthly_target == 250.0
        # Flask only updates labels represented by active savings goals; it
        # does not clear the prior category target on rename/delete.
        assert emergency.monthly_target == 100.0
        assert plan.planned_savings == 250.0

    deleted = client.request("DELETE", f"/v1/goals/{goal_id}", headers=auth_header(token), json={})
    assert deleted.status_code == 200
    assert deleted.json() == {"deleted_goal_id": goal_id}
    assert client.get("/v1/goals", headers=auth_header(token)).json()["goals"] == []
    with TestingSessionLocal() as db:
        assert db.query(MonthlyPlan).filter_by(user_id=user_id).one().planned_savings == 0.0
        assert db.query(Category).filter_by(user_id=user_id, name="Education Savings").one().monthly_target == 250.0


def test_linked_debt_goal_uses_loan_balance_and_flask_amortization_math(client):
    token, user_id = onboarded_token(client, "goal-debt@example.com")
    with TestingSessionLocal() as db:
        item = FixedExpenseItem(
            user_id=user_id,
            name="Car Loan",
            amount=100,
            start_date=app_today(),
            frequency="monthly",
            category_label="Vehicle Payments",
            is_loan=True,
        )
        db.add(item)
        db.flush()
        db.add(
            LoanPlan(
                user_id=user_id,
                fixed_expense_item_id=item.id,
                principal_balance=1200,
                annual_interest_rate=0,
                term_months=12,
                regular_payment=500,
                extra_payment_one=100,
                selected_scenario="extra_one",
            )
        )
        db.commit()
        item_id = item.id

    created = client.post(
        "/v1/goals",
        headers=auth_header(token),
        json={
            "name": "",
            "goal_type": "debt",
            "target_amount": 0,
            "current_amount": 500,
            "monthly_contribution": 25,
            "target_date": add_months(app_today(), 6).isoformat(),
            "fixed_expense_item_id": item_id,
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert body["goal"]["name"] == "Car Loan Paydown"
    assert body["goal"]["target_amount"] == 1200.0
    assert body["goal"]["current_amount"] == 500.0
    assert body["current_amount"] == 0.0
    assert body["remaining"] == 1200.0
    assert body["progress"] == 0.0
    # Flask amortization uses the scheduled term payment (1200 / 12 = 100)
    # plus the selected $100 extra, so payoff is hand-computed at six months.
    assert body["timeline"] == "Selected payoff plan: 6 months"
    assert body["required_extra"] == pytest.approx(100.0, abs=0.01)
    assert body["linked_item"] == {"id": item_id, "name": "Car Loan"}

    listed = client.get("/v1/goals", headers=auth_header(token))
    assert listed.status_code == 200
    option = listed.json()["loan_options"][0]
    assert option == {
        "fixed_expense_item_id": item_id,
        "name": "Car Loan",
        "loan_kind": "loan",
        "monthly_payment": 100.0,
        "selected_extra": 100.0,
        "total_monthly": 200.0,
        "principal_balance": 1200.0,
        "current_balance": 1200.0,
        "collateral_value": 0.0,
        "selected_scenario": "extra_one",
    }


def test_goal_household_access_and_owner_isolation(client):
    owner_token, owner_id = onboarded_token(client, "goal-owner@example.com")
    created = client.post(
        "/v1/goals",
        headers=auth_header(owner_token),
        json={"name": "Private Goal", "target_amount": 500, "monthly_contribution": 50},
    )
    assert created.status_code == 201
    goal_id = created.json()["goal"]["id"]

    viewer_token = shared_session_token(client, owner_id, "goal-viewer@example.com", "viewer")
    viewer_list = client.get("/v1/goals", headers=auth_header(viewer_token))
    assert viewer_list.status_code == 200
    assert viewer_list.json()["goals"][0]["goal"]["name"] == "Private Goal"
    viewer_create = client.post(
        "/v1/goals",
        headers=auth_header(viewer_token),
        json={"name": "Blocked Goal", "target_amount": 100},
    )
    assert viewer_create.status_code == 403

    other_token, _other_id = onboarded_token(client, "goal-other@example.com")
    assert client.patch(
        f"/v1/goals/{goal_id}",
        headers=auth_header(other_token),
        json={"name": "Stolen"},
    ).status_code == 404
    assert client.request(
        "DELETE",
        f"/v1/goals/{goal_id}",
        headers=auth_header(other_token),
        json={},
    ).status_code == 404
    with TestingSessionLocal() as db:
        assert db.get(Goal, goal_id).name == "Private Goal"


def test_goal_list_and_create_require_onboarding(client):
    token = full_session_token(client, "goal-onboarding@example.com")
    listed = client.get("/v1/goals", headers=auth_header(token))
    created = client.post(
        "/v1/goals",
        headers=auth_header(token),
        json={"name": "Too Soon", "target_amount": 100},
    )
    assert listed.status_code == 409
    assert listed.json()["detail"]["code"] == "onboarding_required"
    assert created.status_code == 409
