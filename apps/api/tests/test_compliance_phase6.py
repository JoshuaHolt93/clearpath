from __future__ import annotations

from app.core.security import decode_token
from app.models import PrivilegedAccessLog, User
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
            "display_name": "Compliance User",
            "household_name": "Compliance Household",
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


def make_admin(token: str) -> int:
    payload = decode_token(token)
    with TestingSessionLocal() as db:
        user = db.get(User, int(payload["user_id"]))
        user.is_admin = True
        db.commit()
        return user.id


def test_feedback_endpoint_validation_and_creation(client):
    token = full_session_token(client, "compliance-feedback@example.com")

    options = client.get("/v1/feedback/options", headers=auth_header(token)).json()
    assert len(options["reasons"]) == 4
    assert len(options["broken_features"]) == 10

    missing_reason = client.post("/v1/feedback", headers=auth_header(token), json={})
    assert missing_reason.status_code == 422
    assert missing_reason.json()["detail"] == "Choose the main reason."

    created = client.post(
        "/v1/feedback",
        headers=auth_header(token),
        json={"reason": "broken", "broken_features": ["dashboard", "not-a-key"], "description": "The dashboard fails."},
    )
    assert created.status_code == 201
    body = created.json()
    assert body["feedback_type"] == "general"
    assert body["source"] == "feedback"
    assert body["reason"] == "broken"
    assert body["status"] == "new"


def test_control_evaluations_admin_gate_and_audit_trail(client):
    token = full_session_token(client, "compliance-admin@example.com")

    denied = client.get("/v1/compliance/control-evaluations", headers=auth_header(token))
    assert denied.status_code == 403
    with TestingSessionLocal() as db:
        failure = db.query(PrivilegedAccessLog).filter_by(success=False).one()
        assert failure.action == "compliance.control_evaluations"
        assert failure.resource == "SOC2 CC4.1 control evaluations"

    # Registration left a session cookie on the client; clear it so this is a
    # genuinely unauthenticated attempt.
    client.cookies.clear()
    unauthenticated = client.get("/v1/compliance/control-evaluations")
    assert unauthenticated.status_code == 401
    with TestingSessionLocal() as db:
        assert db.query(PrivilegedAccessLog).filter_by(success=False, user_id=None).count() == 1

    user_id = make_admin(token)
    listed = client.get("/v1/compliance/control-evaluations", headers=auth_header(token))
    assert listed.status_code == 200
    assert listed.json()["evaluations"] == []
    assert len(listed.json()["controls"]) == 6
    with TestingSessionLocal() as db:
        success = db.query(PrivilegedAccessLog).filter_by(success=True).one()
        assert success.user_id == user_id


def test_run_control_evaluations_statuses(client):
    token = full_session_token(client, "compliance-run@example.com")
    make_admin(token)

    run = client.post("/v1/compliance/control-evaluations/run", headers=auth_header(token), json={})
    assert run.status_code == 200
    body = run.json()
    assert body["evaluated"] == 6
    statuses = {result["control_id"]: result["status"] for result in body["results"]}
    # Hand-derived for the test environment: secret present (testing env),
    # CSRF pass by token-auth architecture, security-header middleware
    # registered, HTTPS flags off outside production -> warn, login_attempt
    # table present with throttling columns, Plaid creds + valid Fernet key.
    assert statuses == {
        "CC4.1-PROD-SECRET": "pass",
        "CC4.1-CSRF": "pass",
        "CC4.1-SECURITY-HEADERS": "pass",
        "CC4.1-HTTPS": "warn",
        "CC4.1-LOGIN-THROTTLE": "pass",
        "CC4.1-PLAID-TOKEN-KEY": "pass",
    }

    listed = client.get("/v1/compliance/control-evaluations", headers=auth_header(token))
    assert len(listed.json()["evaluations"]) == 6


def test_security_headers_middleware_applied(client):
    response = client.get("/v1/billing/plans")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
