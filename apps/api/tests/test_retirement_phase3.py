from __future__ import annotations

import pytest
from sqlalchemy import text

from app.core.security import decode_token
from app.models import Account, HouseholdMember, MonthlyPlan, User
from app.services.planning_service import calculate_tax_estimate
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
            "display_name": "Retirement User",
            "household_name": "Retirement Household",
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
            user.profile.income_amount = 120000
            user.profile.monthly_income = 10000
            user.profile.income_type = "salary"
            user.profile.income_frequency = "annual"
            user.profile.income_basis = "gross"
        db.commit()
        return user.id


def onboarded_token(client, email: str, *, plan: str = "premium") -> tuple[str, int]:
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


def test_retirement_openapi_contract_paths_and_methods(client):
    schema = client.get("/openapi.json").json()
    paths = schema["paths"]
    assert set(paths["/v1/retirement-plan"]) == {"get", "patch"}
    assert set(paths["/v1/retirement-plan/worksheet"]) == {"patch"}
    update_schema = paths["/v1/retirement-plan"]["patch"]["requestBody"]["content"]["application/json"]["schema"]
    worksheet_schema = paths["/v1/retirement-plan/worksheet"]["patch"]["requestBody"]["content"]["application/json"]["schema"]
    assert update_schema["$ref"].endswith("/RetirementPlanUpdateRequest")
    assert worksheet_schema["$ref"].endswith("/RetirementWorksheetUpdateRequest")


def test_retirement_plan_read_update_sync_and_account_filter_parity(client):
    token, user_id = onboarded_token(client, "retirement-plan@example.com")
    headers = auth_header(token)
    with TestingSessionLocal() as db:
        accounts = [
            Account(user_id=user_id, name="Workplace 401(k)", account_type="investment", institution="Payroll Custodian", current_balance=45000),
            Account(user_id=user_id, name="Long-Term Brokerage", account_type="ira", institution="Brokerage", current_balance=12000),
            Account(user_id=user_id, name="General Savings", account_type="savings", institution="Vanguard", current_balance=8000),
            Account(user_id=user_id, name="Daily Checking", account_type="checking", institution="Local Bank", current_balance=2500),
        ]
        db.add_all(accounts)
        db.commit()
        expected_account_ids = [account.id for account in accounts[:3]]

    updated = client.patch(
        "/v1/retirement-plan",
        headers=headers,
        json={
            "retirement_enabled": True,
            "retirement_has_employer_plan": True,
            "retirement_employer_withheld": True,
            "retirement_has_personal_plan": True,
            "retirement_monthly_contribution": "$500.00",
            "retirement_personal_monthly_contribution": "200",
        },
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["profile"]["retirement_monthly_contribution"] == 500.0
    assert body["profile"]["retirement_personal_monthly_contribution"] == 200.0
    assert body["retirement_contribution"] == 700.0
    assert [account["id"] for account in body["retirement_accounts"]] == expected_account_ids
    assert body["plaid_status"] == client.get("/v1/plaid/status", headers=headers).json()

    monthly = client.get("/v1/monthly-plan?section=tools", headers=headers)
    assert monthly.status_code == 200
    monthly_body = monthly.json()
    assert monthly_body["retirement_contribution"] == 700.0
    assert [account["id"] for account in monthly_body["retirement_accounts"]] == expected_account_ids
    assert next(row for row in monthly_body["plan_rows"] if row["label"] == "Retirement Contribution")["planned"] == 700.0

    with TestingSessionLocal() as db:
        user = db.get(User, user_id)
        plan = db.query(MonthlyPlan).filter_by(user_id=user_id).one()
        monthly_tax = calculate_tax_estimate(user.profile).monthly_total
        assert plan.safe_to_spend_target == pytest.approx(plan.income - monthly_tax - 700)

    # Flask's survey POST overwrites missing form fields as false/zero. The
    # REST PATCH deliberately preserves that behavior rather than fields-set.
    reset = client.patch("/v1/retirement-plan", headers=headers, json={"retirement_enabled": False})
    assert reset.status_code == 200
    reset_profile = reset.json()["profile"]
    assert {
        key: reset_profile[key]
        for key in (
            "retirement_enabled",
            "retirement_has_employer_plan",
            "retirement_employer_withheld",
            "retirement_has_personal_plan",
            "retirement_monthly_contribution",
            "retirement_personal_monthly_contribution",
        )
    } == {
        "retirement_enabled": False,
        "retirement_has_employer_plan": False,
        "retirement_employer_withheld": False,
        "retirement_has_personal_plan": False,
        "retirement_monthly_contribution": 0.0,
        "retirement_personal_monthly_contribution": 0.0,
    }
    assert reset.json()["retirement_contribution"] == 0.0


def test_retirement_worksheet_trims_overwrites_and_stays_encrypted(client):
    token, user_id = onboarded_token(client, "retirement-worksheet@example.com")
    headers = auth_header(token)
    saved = client.patch(
        "/v1/retirement-plan/worksheet",
        headers=headers,
        json={
            "retirement_lifestyle_notes": "  Live near family and keep travel modest.  ",
            "retirement_location_notes": "Compare Indiana and Michigan cost of living.",
            "retirement_healthcare_notes": "Track Medicare timing.",
            "retirement_income_notes": "Review 401(k), Roth IRA, and Social Security questions.",
            "retirement_debt_notes": "Pay off the mortgage before retirement.",
            "retirement_family_notes": "Keep charitable giving visible.",
        },
    )
    assert saved.status_code == 200
    assert saved.json()["profile"]["retirement_lifestyle_notes"] == "Live near family and keep travel modest."

    with TestingSessionLocal() as db:
        user = db.get(User, user_id)
        assert user.profile.retirement_lifestyle_notes == "Live near family and keep travel modest."
        raw_note = db.execute(
            text("SELECT retirement_lifestyle_notes FROM onboarding_profile WHERE user_id = :user_id"),
            {"user_id": user_id},
        ).scalar_one()
        assert "Live near family" not in raw_note

    overwritten = client.patch(
        "/v1/retirement-plan/worksheet",
        headers=headers,
        json={"retirement_lifestyle_notes": "A quieter plan"},
    )
    assert overwritten.status_code == 200
    assert overwritten.json()["profile"]["retirement_lifestyle_notes"] == "A quieter plan"
    assert overwritten.json()["profile"]["retirement_location_notes"] == ""
    assert overwritten.json()["profile"]["retirement_family_notes"] == ""


def test_retirement_access_feature_onboarding_and_household_roles(client):
    owner_token, owner_id = onboarded_token(client, "retirement-owner@example.com")
    owner_headers = auth_header(owner_token)
    assert client.get("/v1/retirement-plan", headers=owner_headers).status_code == 200

    viewer_token = shared_session_token(client, owner_id, "retirement-viewer@example.com", "viewer")
    viewer_headers = auth_header(viewer_token)
    assert client.get("/v1/retirement-plan", headers=viewer_headers).status_code == 200
    assert client.patch(
        "/v1/retirement-plan/worksheet",
        headers=viewer_headers,
        json={"retirement_lifestyle_notes": "Viewer cannot save"},
    ).status_code == 403

    editor_token = shared_session_token(client, owner_id, "retirement-editor@example.com", "editor")
    edited = client.patch(
        "/v1/retirement-plan/worksheet",
        headers=auth_header(editor_token),
        json={"retirement_lifestyle_notes": "Shared editor can save"},
    )
    assert edited.status_code == 200
    assert edited.json()["profile"]["retirement_lifestyle_notes"] == "Shared editor can save"

    locked_token, _ = onboarded_token(client, "retirement-locked@example.com", plan="at_cost")
    locked = client.get("/v1/retirement-plan", headers=auth_header(locked_token))
    assert locked.status_code == 403
    assert locked.json()["detail"]["code"] == "feature_locked"

    pending_onboarding_token = full_session_token(client, "retirement-onboarding@example.com")
    configure_user(pending_onboarding_token, plan="premium", onboarded=False)
    not_onboarded = client.get("/v1/retirement-plan", headers=auth_header(pending_onboarding_token))
    assert not_onboarded.status_code == 409
    assert not_onboarded.json()["detail"]["code"] == "onboarding_required"
    # Flask's two mutation handlers do not call ensure_onboarded().
    assert client.patch(
        "/v1/retirement-plan",
        headers=auth_header(pending_onboarding_token),
        json={"retirement_enabled": True},
    ).status_code == 200
