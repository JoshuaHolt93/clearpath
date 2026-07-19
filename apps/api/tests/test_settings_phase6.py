from __future__ import annotations

from datetime import UTC, datetime

from app.core.security import decode_token
from app.models import PrivilegedAccessLog, SecurityIncident, User
from conftest import TestingSessionLocal

VALID_PASSWORD = "CorrectHorse1!"
NEW_PASSWORD = "AnotherHorse2@"


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def full_session_token(client, email: str) -> str:
    registered = client.post(
        "/v1/auth/register",
        json={
            "email": email,
            "password": VALID_PASSWORD,
            "display_name": "Settings User",
            "household_name": "Settings Household",
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
        db.commit()
        return user.id


def test_settings_dashboard_aggregate(client):
    token = full_session_token(client, "settings-dash@example.com")
    onboard(token)
    body = client.get("/v1/me/settings", headers=auth_header(token)).json()
    assert body["email"] == "settings-dash@example.com"
    assert body["household_name"] == "Settings Household"
    assert body["account_delete_confirmation"] == "DELETE MY ACCOUNT"
    assert body["can_manage_household_access"] is True
    assert body["household_access_is_shared"] is False
    assert body["household_role_options"] == {"editor": "Can Edit", "viewer": "View Only"}
    # MFA was skipped during setup, so the stored preference is "none".
    assert body["mfa_preferred_method"] == "none"
    assert body["billing_status"]["enabled"] is False
    assert len(body["feedback_options"]["reasons"]) == 4
    # Starter categories seed the manager rows; all are user-owned/manageable
    # except none — spot-check Groceries exists with usage counters.
    groceries = next(row for row in body["category_rows"] if row["category"]["name"] == "Groceries")
    assert groceries["can_manage"] is True
    assert groceries["usage"]["transactions"] == 0
    assert body["account_delete_billing_blocked"] is False


def test_password_change_flow(client):
    token = full_session_token(client, "settings-pass@example.com")
    onboard(token)
    wrong = client.patch(
        "/v1/me/password",
        headers=auth_header(token),
        json={"current_password": "nope", "new_password": NEW_PASSWORD, "confirm_password": NEW_PASSWORD},
    )
    assert wrong.status_code == 422
    assert wrong.json()["detail"] == "Current password was incorrect."
    mismatch = client.patch(
        "/v1/me/password",
        headers=auth_header(token),
        json={"current_password": VALID_PASSWORD, "new_password": NEW_PASSWORD, "confirm_password": "different"},
    )
    assert mismatch.status_code == 422
    weak = client.patch(
        "/v1/me/password",
        headers=auth_header(token),
        json={"current_password": VALID_PASSWORD, "new_password": "short", "confirm_password": "short"},
    )
    assert weak.status_code == 422
    changed = client.patch(
        "/v1/me/password",
        headers=auth_header(token),
        json={"current_password": VALID_PASSWORD, "new_password": NEW_PASSWORD, "confirm_password": NEW_PASSWORD},
    )
    assert changed.status_code == 200
    relogin = client.post("/v1/auth/login", json={"email": "settings-pass@example.com", "password": NEW_PASSWORD})
    assert relogin.status_code == 200


def test_household_invite_member_lifecycle_and_primary_gate(client):
    token = full_session_token(client, "settings-house@example.com")
    onboard(token)

    own_email = client.post(
        "/v1/households/current/invites",
        headers=auth_header(token),
        json={"invite_email": "settings-house@example.com", "invite_role": "viewer"},
    )
    assert own_email.status_code == 422
    assert own_email.json()["detail"] == "You already have access with that email."

    created = client.post(
        "/v1/households/current/invites",
        headers=auth_header(token),
        json={"invite_email": "partner@example.com", "invite_role": "viewer"},
    )
    assert created.status_code == 201
    body = created.json()
    assert body["invite"]["status"] == "pending"
    assert body["invite"]["role"] == "viewer"
    # Test env has no email provider: Flask surfaces the fallback URL.
    assert body["email_sent"] is False
    assert body["delivery_reason"] == "not_configured"
    assert "/household/invite/" in body["fallback_invite_url"]
    invite_token = body["fallback_invite_url"].rsplit("/", 1)[1]

    # A second invite to the same email revokes the first pending invite.
    again = client.post(
        "/v1/households/current/invites",
        headers=auth_header(token),
        json={"invite_email": "partner@example.com", "invite_role": "editor"},
    )
    assert again.status_code == 201
    dashboard = client.get("/v1/me/settings", headers=auth_header(token)).json()
    assert len(dashboard["pending_household_invites"]) == 1
    assert dashboard["pending_household_invites"][0]["role"] == "editor"
    second_token = again.json()["fallback_invite_url"].rsplit("/", 1)[1]
    assert client.get(f"/v1/household-invites/{invite_token}", headers=auth_header(token)).json()["valid"] is False

    accepted = client.post(
        f"/v1/household-invites/{second_token}/accept",
        json={"display_name": "Partner", "password": VALID_PASSWORD, "confirm_password": VALID_PASSWORD, "policy_acknowledgement": True},
    )
    assert accepted.status_code == 200
    member_token = accepted.json()["access_token"]

    dashboard = client.get("/v1/me/settings", headers=auth_header(token)).json()
    member = dashboard["household_members"][0]
    assert member["email"] == "partner@example.com"
    assert member["status"] == "active"

    # Shared sessions cannot touch primary-only settings.
    blocked = client.patch(
        "/v1/me/password",
        headers=auth_header(member_token),
        json={"current_password": VALID_PASSWORD, "new_password": NEW_PASSWORD, "confirm_password": NEW_PASSWORD},
    )
    assert blocked.status_code == 403
    blocked_invite = client.post(
        "/v1/households/current/invites",
        headers=auth_header(member_token),
        json={"invite_email": "third@example.com"},
    )
    assert blocked_invite.status_code == 403

    updated = client.patch(
        f"/v1/households/current/members/{member['id']}",
        headers=auth_header(token),
        json={"member_role": "editor"},
    )
    assert updated.status_code == 200
    assert updated.json()["role"] == "editor"
    revoked = client.request("DELETE", f"/v1/households/current/members/{member['id']}", headers=auth_header(token), json={})
    assert revoked.status_code == 200
    assert revoked.json()["status"] == "revoked"


def test_mfa_preferences_and_ethics_acknowledgement(client):
    token = full_session_token(client, "settings-mfa@example.com")
    onboard(token)
    push = client.patch("/v1/auth/mfa/preferences", headers=auth_header(token), json={"mfa_preferred_method": "push"})
    assert push.status_code == 200
    # Duo is unconfigured in tests: Flask falls back to TOTP with the notice.
    assert push.json()["mfa_preferred_method"] == "totp"
    assert push.json()["mfa_push_enabled"] is False
    assert push.json()["message"] == "Push approval is not configured yet. Authenticator codes remain active."

    ack = client.post("/v1/me/compliance-acknowledgements/ethics", headers=auth_header(token), json={})
    assert ack.status_code == 200
    assert ack.json()["ethics_policy_version"] == "2026-01"
    assert ack.json()["ethics_acknowledged_at"] is not None


def test_account_deletion_guards_and_audit_row_survival(client):
    token = full_session_token(client, "settings-delete@example.com")
    user_id = onboard(token)

    with TestingSessionLocal() as db:
        now = datetime.now(UTC).replace(tzinfo=None)
        db.add(SecurityIncident(incident_type="authentication_throttled", severity="high", source="login_throttle", description="x", status="open", detected_at=now, report_deadline_at=now, user_id=user_id))
        db.add(PrivilegedAccessLog(user_id=user_id, action="export", resource="/admin", success=True))
        user = db.get(User, user_id)
        user.stripe_customer_id = "cus_123"
        user.billing_status = "active"
        db.commit()

    blocked = client.request(
        "DELETE", "/v1/me/account", headers=auth_header(token),
        json={"current_password": VALID_PASSWORD, "confirmation": "DELETE MY ACCOUNT"},
    )
    assert blocked.status_code == 409

    with TestingSessionLocal() as db:
        db.get(User, user_id).billing_status = "canceled"
        db.commit()

    wrong_phrase = client.request(
        "DELETE", "/v1/me/account", headers=auth_header(token),
        json={"current_password": VALID_PASSWORD, "confirmation": "delete"},
    )
    assert wrong_phrase.status_code == 422
    assert wrong_phrase.json()["detail"] == "Type DELETE MY ACCOUNT to confirm account deletion."
    wrong_password = client.request(
        "DELETE", "/v1/me/account", headers=auth_header(token),
        json={"current_password": "nope", "confirmation": "DELETE MY ACCOUNT"},
    )
    assert wrong_password.status_code == 422

    deleted = client.request(
        "DELETE", "/v1/me/account", headers=auth_header(token),
        json={"current_password": VALID_PASSWORD, "confirmation": "DELETE MY ACCOUNT"},
    )
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True

    relogin = client.post("/v1/auth/login", json={"email": "settings-delete@example.com", "password": VALID_PASSWORD})
    assert relogin.status_code == 401

    # Flask parity: audit rows survive with user_id nulled.
    with TestingSessionLocal() as db:
        assert db.get(User, user_id) is None
        incident = db.query(SecurityIncident).one()
        assert incident.user_id is None
        access_log = db.query(PrivilegedAccessLog).one()
        assert access_log.user_id is None
