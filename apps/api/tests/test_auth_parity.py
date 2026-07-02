from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from app.core.security import totp_code
from app.models import HouseholdMember, OnboardingProfile, User

VALID_PASSWORD = "CorrectHorse1!"


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def register_payload(email: str = "user@example.com") -> dict:
    return {
        "email": email,
        "password": VALID_PASSWORD,
        "display_name": "Test User",
        "household_name": "Test Household",
        "policy_acknowledgement": True,
    }


def test_register_returns_pending_token_and_mfa_verify_mints_full_session(client):
    response = client.post("/v1/auth/register", json=register_payload())
    assert response.status_code == 201
    pending = response.json()
    assert pending["mfa_verified"] is False
    assert pending["requires_mfa"] is True
    assert pending["next_step"] == "mfa_setup"

    assert client.get("/v1/me", headers=auth_header(pending["access_token"])).status_code == 403

    setup = client.get("/v1/auth/mfa/setup", headers=auth_header(pending["access_token"]))
    assert setup.status_code == 200
    setup_body = setup.json()
    assert setup_body["mobile_setup_token"]
    secret = parse_qs(urlparse(setup_body["provisioning_uri"]).query)["secret"][0]

    mobile = client.get(f"/v1/auth/mfa/setup/mobile/{setup_body['mobile_setup_token']}")
    assert mobile.status_code == 200
    assert mobile.json()["provisioning_uri"].startswith("otpauth://totp/ClearPath")

    verified = client.post(
        "/v1/auth/mfa/setup",
        headers=auth_header(pending["access_token"]),
        json={"action": "verify_totp", "code": totp_code(secret)},
    )
    assert verified.status_code == 200
    full = verified.json()
    assert full["mfa_verified"] is True
    assert full["requires_mfa"] is False
    assert len(full["recovery_codes"]) == 10

    me = client.get("/v1/me", headers=auth_header(full["access_token"]))
    assert me.status_code == 200
    assert me.json()["email"] == "user@example.com"


def test_shared_household_login_uses_member_as_pending_mfa_subject(client, db):
    owner = User(email="owner@example.com", display_name="Owner", household_name="Owner Home", selected_plan="basic")
    owner.set_password(VALID_PASSWORD)
    db.add(owner)
    db.flush()
    db.add(OnboardingProfile(user_id=owner.id, income_amount=1, monthly_income=1))
    member = HouseholdMember(owner_user_id=owner.id, invited_by_user_id=owner.id, email="shared@example.com", role="viewer", status="active")
    member.set_password(VALID_PASSWORD)
    db.add(member)
    db.commit()

    login = client.post("/v1/auth/login", json={"email": "shared@example.com", "password": VALID_PASSWORD})
    assert login.status_code == 200
    body = login.json()
    assert body["mfa_verified"] is False
    assert body["principal"]["subject_type"] == "household_member"
    assert body["principal"]["household_member_id"] == member.id
    assert body["principal"]["household_role"] == "viewer"

    completed = client.post("/v1/auth/mfa/setup", headers=auth_header(body["access_token"]), json={"action": "skip"})
    assert completed.status_code == 200
    assert completed.json()["principal"]["subject_type"] == "household_member"
    assert completed.json()["mfa_verified"] is True


def test_recovery_code_is_consumed_once(client):
    registered = client.post("/v1/auth/register", json=register_payload("recover@example.com")).json()
    setup = client.get("/v1/auth/mfa/setup", headers=auth_header(registered["access_token"])).json()
    secret = parse_qs(urlparse(setup["provisioning_uri"]).query)["secret"][0]
    completed = client.post(
        "/v1/auth/mfa/setup",
        headers=auth_header(registered["access_token"]),
        json={"action": "verify_totp", "code": totp_code(secret)},
    ).json()
    recovery_code = completed["recovery_codes"][0]

    pending = client.post("/v1/auth/login", json={"email": "recover@example.com", "password": VALID_PASSWORD}).json()
    first = client.post("/v1/auth/mfa/recovery", headers=auth_header(pending["access_token"]), json={"recovery_code": recovery_code})
    assert first.status_code == 200
    assert first.json()["mfa_verified"] is True

    pending_again = client.post("/v1/auth/login", json={"email": "recover@example.com", "password": VALID_PASSWORD}).json()
    reused = client.post("/v1/auth/mfa/recovery", headers=auth_header(pending_again["access_token"]), json={"recovery_code": recovery_code})
    assert reused.status_code == 422


def test_login_attempt_ledger_throttles_after_five_failures(client):
    client.post("/v1/auth/register", json=register_payload("throttle@example.com"))
    for _ in range(5):
        failed = client.post("/v1/auth/login", json={"email": "throttle@example.com", "password": "wrong"})
        assert failed.status_code == 401

    locked = client.post("/v1/auth/login", json={"email": "throttle@example.com", "password": VALID_PASSWORD})
    assert locked.status_code == 429
