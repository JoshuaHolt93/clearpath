from __future__ import annotations

import re
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import select

from app.api.v1 import auth as auth_routes
from app.core.config import get_settings
from app.core.security import totp_code
from app.models import User
from app.services import auth_service, mfa_push_service
from app.services.email_service import EmailDeliveryResult
from app.services.mfa_push_service import PushMFAError

VALID_PASSWORD = "CorrectHorse1!"


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _register(client, email: str) -> dict:
    response = client.post(
        "/v1/auth/register",
        json={
            "email": email,
            "password": VALID_PASSWORD,
            "display_name": "MFA Test",
            "household_name": "MFA Household",
            "policy_acknowledgement": True,
        },
    )
    assert response.status_code == 201
    return response.json()


def _code_from_message(text_body: str) -> str:
    match = re.search(r"\b(\d{6})\b", text_body)
    assert match
    return match.group(1)


def _configure_fake_email(monkeypatch) -> list[str]:
    messages: list[str] = []

    def fake_send_transactional_email(*, to_email: str, subject: str, text_body: str):
        assert to_email.endswith("@example.com")
        assert subject == "Your ClearPath Finance verification code"
        messages.append(text_body)
        return EmailDeliveryResult(True)

    monkeypatch.setattr(auth_service, "email_delivery_configured", lambda: True)
    monkeypatch.setattr(auth_service, "send_transactional_email", fake_send_transactional_email)
    monkeypatch.setattr(auth_routes, "email_delivery_configured", lambda: True)
    return messages


def test_email_code_setup_and_login_match_flask(monkeypatch, client, db):
    messages = _configure_fake_email(monkeypatch)
    registered = _register(client, "email-mfa@example.com")
    pending_header = _auth_header(registered["access_token"])

    setup = client.get("/v1/auth/mfa/setup", headers=pending_header)
    assert setup.status_code == 200
    setup_body = setup.json()
    mobile_token = setup_body["mobile_setup_token"]
    assert setup_body["setup_key"]
    assert setup_body["email_available"] is True

    sent = client.post(
        "/v1/auth/mfa/setup/email-code",
        headers=pending_header,
        json={"purpose": "setup"},
    )
    assert sent.status_code == 200
    assert sent.json()["sent"] is True
    assert sent.json()["challenge_token"]
    assert len(messages) == 1

    completed = client.post(
        "/v1/auth/mfa/setup",
        headers=pending_header,
        json={
            "action": "confirm_email_code",
            "email_code": _code_from_message(messages[-1]),
            "email_challenge_token": sent.json()["challenge_token"],
        },
    )
    assert completed.status_code == 200
    assert completed.json()["mfa_verified"] is True
    assert len(completed.json()["recovery_codes"]) == 10

    db.expire_all()
    user = db.scalar(select(User).where(User.email == "email-mfa@example.com"))
    assert user.mfa_enabled is True
    assert user.mfa_preferred_method == "email"
    assert user.mfa_confirmed_at is not None

    # Flask rejects a setup handoff as soon as MFA is enabled.
    expired_handoff = client.get(f"/v1/auth/mfa/setup/mobile/{mobile_token}")
    assert expired_handoff.status_code == 410

    pending = client.post(
        "/v1/auth/login",
        json={"email": "email-mfa@example.com", "password": VALID_PASSWORD},
    ).json()
    challenge = client.get(
        "/v1/auth/mfa/challenge",
        headers=_auth_header(pending["access_token"]),
    )
    assert challenge.status_code == 200
    challenge_body = challenge.json()
    assert challenge_body["preferred_method"] == "email"
    assert challenge_body["email_available"] is True
    assert challenge_body["email_challenge_sent"] is True
    assert challenge_body["email_challenge_token"]
    assert len(messages) == 2

    repeated_challenge = client.get(
        "/v1/auth/mfa/challenge",
        headers=_auth_header(pending["access_token"]),
        params={"email_challenge_token": challenge_body["email_challenge_token"]},
    )
    assert repeated_challenge.status_code == 200
    assert repeated_challenge.json()["email_challenge_sent"] is True
    assert repeated_challenge.json()["email_challenge_token"] == challenge_body["email_challenge_token"]
    assert len(messages) == 2

    verified = client.post(
        "/v1/auth/mfa/verify",
        headers=_auth_header(pending["access_token"]),
        json={
            "method": "email",
            "email_code": _code_from_message(messages[-1]),
            "email_challenge_token": challenge_body["email_challenge_token"],
        },
    )
    assert verified.status_code == 200
    assert verified.json()["mfa_verified"] is True


def test_mobile_setup_token_is_bound_to_the_current_secret(client, db):
    registered = _register(client, "fingerprint@example.com")
    setup = client.get(
        "/v1/auth/mfa/setup",
        headers=_auth_header(registered["access_token"]),
    ).json()

    user = db.scalar(select(User).where(User.email == "fingerprint@example.com"))
    user.mfa_secret = "JBSWY3DPEHPK3PXP"
    db.commit()

    response = client.get(f"/v1/auth/mfa/setup/mobile/{setup['mobile_setup_token']}")
    assert response.status_code == 410


def test_mfa_attempts_throttle_per_source_after_five_failures(client):
    registered = _register(client, "mfa-throttle@example.com")
    setup = client.get(
        "/v1/auth/mfa/setup",
        headers=_auth_header(registered["access_token"]),
    ).json()
    secret = parse_qs(urlparse(setup["provisioning_uri"]).query)["secret"][0]
    client.post(
        "/v1/auth/mfa/setup",
        headers=_auth_header(registered["access_token"]),
        json={"action": "verify_totp", "code": totp_code(secret)},
    )

    pending = client.post(
        "/v1/auth/login",
        json={"email": "mfa-throttle@example.com", "password": VALID_PASSWORD},
    ).json()
    headers = _auth_header(pending["access_token"])
    for _ in range(5):
        failed = client.post(
            "/v1/auth/mfa/verify",
            headers=headers,
            json={"method": "totp", "code": "000000"},
        )
        assert failed.status_code == 422

    locked = client.post(
        "/v1/auth/mfa/verify",
        headers=headers,
        json={"method": "totp", "code": totp_code(secret)},
    )
    assert locked.status_code == 429
    assert "Too many failed MFA attempts" in locked.json()["detail"]


def test_push_opt_in_start_and_callback_match_flask(monkeypatch, client, db):
    monkeypatch.setattr(auth_service, "push_mfa_available", lambda: True)
    monkeypatch.setattr(
        auth_service,
        "push_mfa_status",
        lambda: {
            "provider": "duo",
            "configured": True,
            "available": True,
            "missing": [],
            "dependency_installed": True,
        },
    )
    registered = _register(client, "push-mfa@example.com")
    setup = client.get(
        "/v1/auth/mfa/setup",
        headers=_auth_header(registered["access_token"]),
    ).json()
    assert setup["push_available"] is True
    secret = parse_qs(urlparse(setup["provisioning_uri"]).query)["secret"][0]

    enabled = client.post(
        "/v1/auth/mfa/setup",
        headers=_auth_header(registered["access_token"]),
        json={
            "action": "verify_totp",
            "code": totp_code(secret),
            "mfa_push_opt_in": True,
        },
    )
    assert enabled.status_code == 200
    db.expire_all()
    user = db.scalar(select(User).where(User.email == "push-mfa@example.com"))
    assert user.mfa_push_enabled is True
    assert user.mfa_preferred_method == "push"

    pending = client.post(
        "/v1/auth/login",
        json={"email": "push-mfa@example.com", "password": VALID_PASSWORD},
    ).json()
    pending_header = _auth_header(pending["access_token"])
    monkeypatch.setattr(
        auth_routes,
        "start_push_mfa",
        lambda subject, redirect_uri: "https://duo.example.test/prompt",
    )
    started = client.post(
        "/v1/auth/mfa/push/start",
        headers=pending_header,
        json={},
    )
    assert started.status_code == 200
    assert started.json()["authorization_url"] == "https://duo.example.test/prompt"

    monkeypatch.setattr(
        auth_routes,
        "complete_push_mfa",
        lambda subject, state, code, redirect_uri: None,
    )
    callback = client.get(
        "/v1/auth/mfa/push/callback?state=good&duo_code=approved",
        headers=pending_header,
    )
    assert callback.status_code == 200
    assert callback.json()["mfa_verified"] is True


def test_duo_state_is_signed_and_bound_to_the_subject(monkeypatch, db):
    settings = get_settings()
    monkeypatch.setattr(settings, "mfa_push_provider", "duo")
    monkeypatch.setattr(settings, "duo_client_id", "client-id")
    monkeypatch.setattr(settings, "duo_client_secret", "client-secret")
    monkeypatch.setattr(settings, "duo_api_hostname", "api.example.test")

    calls: dict[str, str] = {}

    class FakeDuoClient:
        def __init__(self, client_id, client_secret, api_hostname, redirect_uri):
            calls["redirect_uri"] = redirect_uri

        def health_check(self):
            calls["health"] = "ok"

        def generate_state(self):
            return "provider-random-state"

        def create_auth_url(self, email, state):
            calls["email"] = email
            calls["state"] = state
            return f"https://duo.example.test/prompt?state={state}"

        def exchange_authorization_code_for_2fa_result(self, code, email):
            calls["code"] = code
            calls["exchange_email"] = email

    monkeypatch.setattr(
        mfa_push_service,
        "duo_universal",
        SimpleNamespace(Client=FakeDuoClient),
    )
    user = User(email="duo-state@example.com", display_name="Duo", household_name="Duo Home")
    user.set_password(VALID_PASSWORD)
    db.add(user)
    db.commit()

    authorization_url = mfa_push_service.start_push_mfa(
        user,
        redirect_uri="https://web.example.test/mfa/push/callback",
    )
    assert authorization_url.startswith("https://duo.example.test/prompt")
    assert calls["state"] != "provider-random-state"

    mfa_push_service.complete_push_mfa(
        user,
        state=calls["state"],
        code="approved",
        redirect_uri="https://web.example.test/mfa/push/callback",
    )
    assert calls["code"] == "approved"

    other_user = User(email="other@example.com", display_name="Other", household_name="Other Home")
    other_user.set_password(VALID_PASSWORD)
    db.add(other_user)
    db.commit()
    with pytest.raises(PushMFAError, match="state did not match"):
        mfa_push_service.complete_push_mfa(
            other_user,
            state=calls["state"],
            code="approved",
            redirect_uri="https://web.example.test/mfa/push/callback",
        )


def test_full_session_user_can_enroll_mfa_from_settings(client):
    # A user who skipped MFA at registration holds a full (verified) session
    # with mfa_enabled=False. They must be able to enrol later from Settings.
    # Before the guard change this GET 409'd because the endpoint was
    # pending-session only, so enrolment was unreachable after skipping.
    registered = _register(client, "late-enroll@example.com")
    skip = client.post(
        "/v1/auth/mfa/setup",
        headers=_auth_header(registered["access_token"]),
        json={"action": "skip", "mfa_push_opt_in": False},
    )
    assert skip.status_code == 200
    full_token = skip.json()["access_token"]

    setup = client.get("/v1/auth/mfa/setup", headers=_auth_header(full_token))
    assert setup.status_code == 200, setup.text
    secret = parse_qs(urlparse(setup.json()["provisioning_uri"]).query)["secret"][0]

    confirm = client.post(
        "/v1/auth/mfa/setup",
        headers=_auth_header(full_token),
        json={"action": "verify_totp", "code": totp_code(secret)},
    )
    assert confirm.status_code == 200, confirm.text

    # A second setup attempt now 409s, proving MFA is enrolled and the secret
    # is locked. (The /v1/me/settings dashboard itself is gated on completed
    # onboarding, which this minimal flow skips.)
    enrolled_token = confirm.json()["access_token"]
    reattempt = client.get("/v1/auth/mfa/setup", headers=_auth_header(enrolled_token))
    assert reattempt.status_code == 409


def test_full_session_user_cannot_reset_mfa_secret_once_enrolled(client):
    # Once enrolled, re-hitting setup must 409 rather than silently rotating the
    # secret -- the service guard, now reachable by full sessions, still holds.
    registered = _register(client, "already-enrolled@example.com")
    setup = client.get("/v1/auth/mfa/setup", headers=_auth_header(registered["access_token"])).json()
    secret = parse_qs(urlparse(setup["provisioning_uri"]).query)["secret"][0]
    confirmed = client.post(
        "/v1/auth/mfa/setup",
        headers=_auth_header(registered["access_token"]),
        json={"action": "verify_totp", "code": totp_code(secret)},
    )
    full_token = confirmed.json()["access_token"]

    reattempt = client.get("/v1/auth/mfa/setup", headers=_auth_header(full_token))
    assert reattempt.status_code == 409
