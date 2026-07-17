from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from app.core.security import decode_token, totp_code
from app.models import HouseholdInvite, HouseholdMember, OnboardingProfile, User
from app.services.auth_service import create_invite
from app.services.email_service import EmailDeliveryResult

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


def test_stay_signed_in_survives_pending_mfa_and_controls_full_cookie_lifetime(client):
    registered = client.post("/v1/auth/register", json=register_payload("persistent@example.com"))
    pending = registered.json()
    setup = client.get("/v1/auth/mfa/setup", headers=auth_header(pending["access_token"])).json()
    secret = parse_qs(urlparse(setup["provisioning_uri"]).query)["secret"][0]
    completed = client.post(
        "/v1/auth/mfa/setup",
        headers=auth_header(pending["access_token"]),
        json={"action": "verify_totp", "code": totp_code(secret)},
    )
    assert completed.status_code == 200

    persistent = client.post(
        "/v1/auth/login",
        json={"email": "persistent@example.com", "password": VALID_PASSWORD, "stay_signed_in": True},
    )
    assert persistent.status_code == 200
    pending_body = persistent.json()
    assert pending_body["principal"]["stay_signed_in"] is True
    pending_claim = decode_token(pending_body["access_token"])
    assert pending_claim["stay_signed_in"] is True
    assert pending_claim["mfa_verified"] is False
    assert pending_claim["exp"] - pending_claim["iat"] == 15 * 60
    assert "max-age=900" in persistent.headers["set-cookie"].lower()

    verified = client.post(
        "/v1/auth/mfa/verify",
        headers=auth_header(pending_body["access_token"]),
        json={"method": "totp", "code": totp_code(secret)},
    )
    assert verified.status_code == 200
    full_body = verified.json()
    full_claim = decode_token(full_body["access_token"])
    assert full_body["principal"]["stay_signed_in"] is True
    assert full_claim["stay_signed_in"] is True
    assert full_claim["exp"] - full_claim["iat"] == 30 * 24 * 60 * 60
    assert "max-age=2592000" in verified.headers["set-cookie"].lower()

    browser_session = client.post(
        "/v1/auth/login",
        json={"email": "persistent@example.com", "password": VALID_PASSWORD, "stay_signed_in": False},
    )
    assert browser_session.status_code == 200
    browser_pending = browser_session.json()
    browser_verified = client.post(
        "/v1/auth/mfa/verify",
        headers=auth_header(browser_pending["access_token"]),
        json={"method": "totp", "code": totp_code(secret)},
    )
    assert browser_verified.status_code == 200
    browser_full = browser_verified.json()
    browser_claim = decode_token(browser_full["access_token"])
    assert browser_full["principal"]["stay_signed_in"] is False
    assert browser_claim["stay_signed_in"] is False
    assert browser_claim["exp"] - browser_claim["iat"] == 14 * 24 * 60 * 60
    assert "max-age" not in browser_verified.headers["set-cookie"].lower()


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


def test_registration_throttles_per_source_after_five_signups(client):
    # Flask commit 8c9f0bf: each created account counts toward a 5-per-15-min
    # window keyed on the request source, so the sixth sign-up is blocked.
    for index in range(5):
        created = client.post("/v1/auth/register", json=register_payload(f"signup-{index}@example.com"))
        assert created.status_code == 201

    blocked = client.post("/v1/auth/register", json=register_payload("signup-blocked@example.com"))
    assert blocked.status_code == 429


def test_password_reset_requests_throttle_and_stop_issuing_tokens(client):
    client.post("/v1/auth/register", json=register_payload("reset-throttle@example.com"))
    for _ in range(5):
        response = client.post("/v1/auth/password-reset/request", json={"email": "reset-throttle@example.com"})
        assert response.status_code == 200
        # EXPOSE_DEV_TOKENS is on in tests, so a token proves the lookup ran.
        assert response.json()["reset_token"]

    throttled = client.post("/v1/auth/password-reset/request", json={"email": "reset-throttle@example.com"})
    assert throttled.status_code == 200
    assert throttled.json()["reset_token"] is None
    assert "If an account exists" in throttled.json()["message"]


def test_password_reset_email_token_and_login_ledger_match_flask(client, monkeypatch):
    client.post("/v1/auth/register", json=register_payload("reset-parity@example.com"))
    sent: dict[str, str] = {}

    def fake_send_password_reset_email(*, to_email: str, reset_url: str) -> EmailDeliveryResult:
        sent.update(to_email=to_email, reset_url=reset_url)
        return EmailDeliveryResult(sent=True)

    monkeypatch.setattr("app.api.v1.auth.send_password_reset_email", fake_send_password_reset_email)
    requested = client.post("/v1/auth/password-reset/request", json={"email": "RESET-PARITY@example.com"})
    assert requested.status_code == 200
    token = requested.json()["reset_token"]
    assert token
    assert sent == {
        "to_email": "reset-parity@example.com",
        "reset_url": f"http://127.0.0.1:3000/reset-password/{token}",
    }
    claim = decode_token(token)
    assert claim["exp"] - claim["iat"] == 30 * 60
    assert claim["password_hash"]
    assert client.get(f"/v1/auth/password-reset/{token}").json() == {
        "valid": True,
        "email": "reset-parity@example.com",
    }

    for _ in range(5):
        assert client.post(
            "/v1/auth/login",
            json={"email": "reset-parity@example.com", "password": "wrong"},
        ).status_code == 401
    assert client.post(
        "/v1/auth/login",
        json={"email": "reset-parity@example.com", "password": VALID_PASSWORD},
    ).status_code == 429

    completed = client.post(
        f"/v1/auth/password-reset/{token}",
        json={"password": "NewCorrectHorse2!", "confirm_password": "NewCorrectHorse2!"},
    )
    assert completed.status_code == 200
    assert completed.json() == {"ok": True}
    assert "clearpath_session=" in completed.headers["set-cookie"]
    assert "max-age=0" in completed.headers["set-cookie"].lower()
    assert client.get(f"/v1/auth/password-reset/{token}").json() == {"valid": False, "email": None}
    assert client.post(
        "/v1/auth/login",
        json={"email": "reset-parity@example.com", "password": VALID_PASSWORD},
    ).status_code == 401
    assert client.post(
        "/v1/auth/login",
        json={"email": "reset-parity@example.com", "password": "NewCorrectHorse2!"},
    ).status_code == 200


def test_password_reset_request_keeps_unknown_account_indistinguishable(client, monkeypatch):
    monkeypatch.setattr(
        "app.api.v1.auth.send_password_reset_email",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("email must not be sent")),
    )
    response = client.post("/v1/auth/password-reset/request", json={"email": "missing@example.com"})
    assert response.status_code == 200
    assert response.json() == {
        "message": "If an account exists for that email, a password reset link has been sent.",
        "reset_token": None,
    }


def test_household_invite_acceptance_creates_shared_pending_session(client, db):
    owner = User(
        email="invite-owner@example.com",
        display_name="Owner",
        household_name="Invite Household",
        selected_plan="basic",
    )
    owner.set_password(VALID_PASSWORD)
    db.add(owner)
    db.flush()
    db.add(OnboardingProfile(user_id=owner.id, income_amount=5000, monthly_income=5000))
    db.commit()
    invite, token = create_invite(owner, "invited-viewer@example.com", "viewer", db=db)

    challenge = client.get(f"/v1/household-invites/{token}")
    assert challenge.status_code == 200
    assert challenge.json() == {
        "valid": True,
        "email": "invited-viewer@example.com",
        "household_name": "Invite Household",
        "role": "viewer",
    }
    assert "clearpath_session=" in challenge.headers["set-cookie"]
    assert "max-age=0" in challenge.headers["set-cookie"].lower()

    accepted = client.post(
        f"/v1/household-invites/{token}/accept",
        json={
            "display_name": "Taylor Viewer",
            "password": "SharedVault123!",
            "confirm_password": "SharedVault123!",
            "policy_acknowledgement": True,
        },
    )
    assert accepted.status_code == 200
    pending = accepted.json()
    assert pending["next_step"] == "mfa_setup"
    assert pending["mfa_verified"] is False
    assert pending["principal"]["subject_type"] == "household_member"
    assert pending["principal"]["household_role"] == "viewer"
    assert "max-age=900" in accepted.headers["set-cookie"].lower()

    db.expire_all()
    member = db.query(HouseholdMember).filter_by(email="invited-viewer@example.com").one()
    refreshed_invite = db.get(HouseholdInvite, invite.id)
    assert member.owner_user_id == owner.id
    assert member.display_name == "Taylor Viewer"
    assert member.status == "active"
    assert member.last_login_at is not None
    assert refreshed_invite.status == "accepted"
    assert refreshed_invite.accepted_member_id == member.id

    completed = client.post(
        "/v1/auth/mfa/setup",
        headers=auth_header(pending["access_token"]),
        json={"action": "skip"},
    )
    assert completed.status_code == 200
    assert completed.json()["next_step"] == "dashboard"
    assert completed.json()["principal"]["household_member_id"] == member.id

    assert client.get(f"/v1/household-invites/{token}").json()["valid"] is False
    reused = client.post(
        f"/v1/household-invites/{token}/accept",
        json={
            "display_name": "Taylor Viewer",
            "password": "SharedVault123!",
            "confirm_password": "SharedVault123!",
            "policy_acknowledgement": True,
        },
    )
    assert reused.status_code == 410


def test_household_invite_acceptance_preserves_flask_validation_order(client, db):
    owner = User(email="validation-owner@example.com", household_name="Validation Home", selected_plan="basic")
    owner.set_password(VALID_PASSWORD)
    db.add(owner)
    db.commit()
    invite, token = create_invite(owner, "validation-member@example.com", "editor", db=db)

    missing_name = client.post(
        f"/v1/household-invites/{token}/accept",
        json={
            "display_name": "",
            "password": "short",
            "confirm_password": "different",
            "policy_acknowledgement": False,
        },
    )
    assert missing_name.status_code == 422
    assert missing_name.json()["detail"] == "Your name is required."
    db.refresh(invite)
    assert invite.status == "pending"
