from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.core.security import decode_token
from app.models import Account, Category, HouseholdMember, PlaidItem, Transaction, User
from app.services.planning_service import app_today
from app.services.transaction_service import ensure_user_starter_categories
from conftest import TestingSessionLocal

VALID_PASSWORD = "CorrectHorse1!"


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def full_session_token(client, email: str = "onboarding@example.com") -> tuple[str, int]:
    registered = client.post(
        "/v1/auth/register",
        json={
            "email": email,
            "password": VALID_PASSWORD,
            "display_name": "Onboarding User",
            "household_name": "Onboarding Household",
            "policy_acknowledgement": True,
        },
    )
    completed = client.post(
        "/v1/auth/mfa/setup",
        headers=auth_header(registered.json()["access_token"]),
        json={"action": "skip"},
    )
    token = completed.json()["access_token"]
    return token, int(decode_token(token)["user_id"])


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
    completed = client.post(
        "/v1/auth/mfa/setup",
        headers=auth_header(login.json()["access_token"]),
        json={"action": "skip"},
    )
    return completed.json()["access_token"]


def add_connected_bank_and_transactions(user_id: int) -> None:
    with TestingSessionLocal() as db:
        user = db.get(User, user_id)
        assert user is not None
        ensure_user_starter_categories(db, user)
        item = PlaidItem(
            user_id=user_id,
            plaid_item_id="onboarding-item",
            access_token_encrypted="encrypted-token",
            institution_name="First Test Bank",
            status="connected",
        )
        db.add(item)
        db.flush()
        account = Account(
            user_id=user_id,
            plaid_item_id=item.id,
            plaid_account_id="onboarding-checking",
            name="Everyday Checking",
            account_type="checking",
            institution="First Test Bank",
            is_manual=False,
        )
        db.add(account)
        db.flush()
        other = db.scalar(select(Category).where(Category.user_id == user_id, Category.name == "Other"))
        assert other is not None
        db.add_all(
            [
                Transaction(
                    user_id=user_id,
                    account_id=account.id,
                    category_id=other.id,
                    posted_date=app_today(),
                    description="KROGER MARKET",
                    merchant="Kroger",
                    amount=-63.45,
                    import_hash="onboarding-grocery",
                    source_name=None,
                ),
                Transaction(
                    user_id=user_id,
                    account_id=account.id,
                    category_id=other.id,
                    posted_date=app_today() - timedelta(days=1),
                    description="UNKNOWN SHOP",
                    merchant="Unknown Shop",
                    amount=-42.10,
                    import_hash="onboarding-other",
                    source_name=None,
                ),
            ]
        )
        db.commit()


def test_status_income_save_and_completion_match_flask_onboarding(client):
    token, user_id = full_session_token(client)
    headers = auth_header(token)

    initial = client.get("/v1/onboarding/status", headers=headers)
    assert initial.status_code == 200
    assert initial.json()["active_step"] == "connect"
    assert initial.json()["income_ready"] is False
    assert initial.json()["has_bank"] is False

    add_connected_bank_and_transactions(user_id)
    connected = client.get("/v1/onboarding/status?step=income", headers=headers)
    assert connected.status_code == 200
    assert connected.json()["active_step"] == "income"
    assert connected.json()["plaid_items"][0]["institution_name"] == "First Test Bank"

    saved = client.patch(
        "/v1/onboarding/income-plan",
        headers=headers,
        json={
            "income_amount": 120000,
            "income_basis": "take_home",
            "income_type": "salary",
            "paycheck_cadence": "semimonthly",
            "next_pay_date": "2026-07-15",
            "second_date": "2026-07-31",
            "additional_income_amount": 1200,
            "additional_income_frequency": "annual",
            "include_payroll_taxes": True,
            "notes": "Seasonal bonus",
        },
    )
    assert saved.status_code == 200
    body = saved.json()
    assert body["active_step"] == "transactions"
    assert body["income_ready"] is True
    assert body["auto_categorized_count"] == 1
    assert body["profile"]["monthly_income"] == pytest.approx(10100)
    assert body["profile"]["next_pay_date"] == "2026-07-15"
    assert body["profile"]["paycheck_second_date"] == "2026-07-31"
    grocery = next(row for row in body["categories"] if row["name"] == "Groceries")
    grocery_transaction = next(row for row in body["transactions"] if row["display_merchant"] == "Kroger")
    assert grocery_transaction["category_id"] == grocery["id"]

    completed = client.post("/v1/onboarding/complete", headers=headers, json={})
    assert completed.status_code == 200
    result = completed.json()
    assert result["setup_complete"] is True
    assert result["seeded_budget_count"] == 2
    assert result["next_path"] == "/monthly-plan?section=budgets&onboarding=complete"

    with TestingSessionLocal() as db:
        user = db.get(User, user_id)
        groceries = db.scalar(select(Category).where(Category.user_id == user_id, Category.name == "Groceries"))
        income = db.scalar(select(Category).where(Category.user_id == user_id, Category.name == "Income"))
        assert user.profile.monthly_income == pytest.approx(10100)
        assert user.profile.next_pay_date.isoformat() == "2026-07-15"
        assert user.profile.paycheck_second_date.isoformat() == "2026-07-31"
        assert groceries.monthly_target == 600
        assert groceries.is_default is False
        assert income.monthly_target == pytest.approx(10100)
        assert income.is_default is False


def test_completion_requires_bank_then_income(client):
    token, user_id = full_session_token(client, "onboarding-gates@example.com")
    headers = auth_header(token)
    missing_bank = client.post("/v1/onboarding/complete", headers=headers, json={})
    assert missing_bank.status_code == 409
    assert missing_bank.json()["detail"]["code"] == "bank_connection_required"

    add_connected_bank_and_transactions(user_id)
    missing_income = client.post("/v1/onboarding/complete", headers=headers, json={})
    assert missing_income.status_code == 409
    assert missing_income.json()["detail"]["code"] == "income_plan_required"


def test_shared_viewer_can_read_but_cannot_mutate_onboarding(client):
    _owner_token, owner_id = full_session_token(client, "onboarding-owner@example.com")
    viewer_token = shared_session_token(client, owner_id, "onboarding-viewer@example.com", "viewer")
    headers = auth_header(viewer_token)

    assert client.get("/v1/onboarding/status", headers=headers).status_code == 200
    assert client.patch("/v1/onboarding/income-plan", headers=headers, json={}).status_code == 403
    assert client.post("/v1/onboarding/complete", headers=headers, json={}).status_code == 403


def test_openapi_exposes_typed_onboarding_contract(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert "get" in paths["/v1/onboarding/status"]
    assert "patch" in paths["/v1/onboarding/income-plan"]
    assert "post" in paths["/v1/onboarding/complete"]
