from __future__ import annotations

from datetime import UTC, datetime

from app.core.security import decode_token
from app.models import ProductFeedback, StripeWebhookEvent, User
from app.services.billing_service import handle_stripe_event
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
            "display_name": "Billing User",
            "household_name": "Billing Household",
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


def user_id_for(token: str) -> int:
    return int(decode_token(token)["user_id"])


def test_billing_plans_public_shape(client):
    body = client.get("/v1/billing/plans").json()
    plans = {plan["key"]: plan for plan in body["plans"]}
    # Hand-computed Flask defaults: 299/699/1199 cents.
    assert plans["at_cost"]["price_display"] == "$2.99"
    assert plans["basic"]["price_display"] == "$6.99"
    assert plans["premium"]["price_display"] == "$11.99"
    assert plans["at_cost"]["name"] == "ClearPath Basic"
    assert plans["premium"]["billing_interval"] == "month"
    assert plans["premium"]["price_configured"] is False
    assert body["billing_status"]["enabled"] is False
    # Policy default amount is 1200 cents.
    assert body["pricing_policy"]["price_display"] == "$12.00"
    assert body["free_tier_signups_enabled"] is False
    # Premium tutorial stacks basic + premium items (4 + 4).
    assert len(body["upgrade_tutorials"]["premium"]) == 8
    assert body["upgrade_tutorials"]["premium"][0]["target"] == "monthly_plan_baseline"


def test_plan_selection_flow_and_guards(client):
    token = full_session_token(client, "billing-select@example.com")

    invalid = client.post("/v1/billing/plan-selection", headers=auth_header(token), json={"plan": "mega"})
    assert invalid.status_code == 422
    assert invalid.json()["detail"] == "Choose a valid ClearPath plan."

    carded = client.post(
        "/v1/billing/plan-selection",
        headers=auth_header(token),
        json={"plan": "premium", "card": {"number": "4242 4242 4242 4242"}},
    )
    assert carded.status_code == 400
    assert carded.json()["detail"] == "Payment card details must be entered only on Stripe-hosted billing pages."

    priced = client.post(
        "/v1/billing/plan-selection",
        headers=auth_header(token),
        json={"plan": "premium", "amount": 100},
    )
    assert priced.status_code == 400
    assert "Do not submit pricing fields" in priced.json()["detail"]

    selected = client.post("/v1/billing/plan-selection", headers=auth_header(token), json={"plan": "premium"})
    assert selected.status_code == 200
    body = selected.json()
    assert body["selected_plan"] == "premium"
    assert body["already_selected"] is False
    # Billing disabled: no checkout session, plan saved locally,
    # "free" -> "plan_selected" (Flask _save_selected_plan).
    assert body["checkout_url"] is None
    assert body["billing"]["billing_status"] == "plan_selected"
    # Not onboarded yet: no tutorial items (Flask redirects to onboarding).
    assert body["upgrade_tutorial_items"] == []

    with TestingSessionLocal() as db:
        user = db.get(User, user_id_for(token))
        user.profile.income_amount = 1
        user.profile.monthly_income = 1
        db.commit()

    repeat = client.post("/v1/billing/plan-selection", headers=auth_header(token), json={"plan": "premium"})
    assert repeat.status_code == 200
    assert repeat.json()["already_selected"] is True

    status_body = client.get("/v1/billing/status", headers=auth_header(token)).json()
    assert status_body["selected_plan"] == "premium"
    assert status_body["has_stripe_customer"] is False


def test_checkout_and_portal_require_configured_billing(client):
    token = full_session_token(client, "billing-checkout@example.com")
    checkout = client.post("/v1/billing/checkout-sessions", headers=auth_header(token), json={"plan": "premium"})
    assert checkout.status_code == 422
    assert checkout.json()["detail"].startswith("Stripe Checkout could not start: Stripe billing is not ready.")
    portal = client.post("/v1/billing/portal-sessions", headers=auth_header(token), json={})
    assert portal.status_code == 422


def test_cancellation_saves_feedback_without_stripe_customer(client):
    token = full_session_token(client, "billing-cancel@example.com")

    broken = client.post(
        "/v1/billing/cancellation-sessions",
        headers=auth_header(token),
        json={"reason": "broken", "broken_features": []},
    )
    assert broken.status_code == 422
    assert broken.json()["detail"] == "Choose at least one feature that was not working."

    cancelled = client.post("/v1/billing/cancellation-sessions", headers=auth_header(token), json={})
    assert cancelled.status_code == 200
    body = cancelled.json()
    assert body["feedback_saved"] is True
    assert body["portal_url"] is None
    assert "no Stripe customer is connected" in body["message"]

    with TestingSessionLocal() as db:
        entry = db.query(ProductFeedback).one()
        # Flask defaults a missing reason to "other" for cancellations and
        # snapshots the user's billing state.
        assert entry.feedback_type == "cancellation"
        assert entry.source == "billing_cancel"
        assert entry.reason == "other"
        # Registration clears selected_plan until the user picks one.
        assert entry.selected_plan == ""
        assert entry.billing_status == "free"


def test_webhook_rejects_invalid_signature(client):
    response = client.post("/v1/webhooks/stripe", content=b'{"id": "evt_x"}', headers={"Stripe-Signature": "bad"})
    assert response.status_code == 400
    assert response.text == "Invalid Stripe signature."


def test_stripe_event_idempotency_and_subscription_lifecycle(client):
    token = full_session_token(client, "billing-events@example.com")
    user_id = user_id_for(token)

    checkout_event = {
        "id": "evt_checkout_1",
        "type": "checkout.session.completed",
        "created": 1752800000,
        "data": {
            "object": {
                "client_reference_id": str(user_id),
                "customer": "cus_A",
                "subscription": "sub_A",
                "metadata": {"user_id": str(user_id), "selected_plan": "premium"},
            }
        },
    }
    with TestingSessionLocal() as db:
        assert handle_stripe_event(db, checkout_event) is True
        user = db.get(User, user_id)
        assert user.stripe_customer_id == "cus_A"
        assert user.stripe_subscription_id == "sub_A"
        assert user.billing_status == "checkout_complete"
        assert user.selected_plan == "premium"
        record = db.query(StripeWebhookEvent).filter_by(stripe_event_id="evt_checkout_1").one()
        assert record.status == "processed"

    # Replays are skipped without touching state (idempotency ledger).
    with TestingSessionLocal() as db:
        assert handle_stripe_event(db, checkout_event) is False
        assert db.query(StripeWebhookEvent).count() == 1

    subscription_event = {
        "id": "evt_sub_1",
        "type": "customer.subscription.updated",
        "created": 1752900000,
        "data": {
            "object": {
                "id": "sub_A",
                "customer": "cus_A",
                "status": "active",
                "cancel_at_period_end": False,
                "current_period_end": 1760000000,
                "items": {"data": []},
            }
        },
    }
    with TestingSessionLocal() as db:
        assert handle_stripe_event(db, subscription_event) is True
        user = db.get(User, user_id)
        assert user.billing_status == "active"
        assert user.stripe_current_period_end == datetime.fromtimestamp(1760000000, tz=UTC).replace(tzinfo=None)

    # A stale event (earlier period end) is ignored.
    stale_event = {
        "id": "evt_sub_stale",
        "type": "customer.subscription.updated",
        "created": 1752950000,
        "data": {
            "object": {
                "id": "sub_A",
                "customer": "cus_A",
                "status": "past_due",
                "cancel_at_period_end": False,
                "current_period_end": 1750000000,
                "items": {"data": []},
            }
        },
    }
    with TestingSessionLocal() as db:
        assert handle_stripe_event(db, stale_event) is False
        user = db.get(User, user_id)
        assert user.billing_status == "active"
        record = db.query(StripeWebhookEvent).filter_by(stripe_event_id="evt_sub_stale").one()
        assert record.status == "skipped"

    deleted_event = {
        "id": "evt_sub_deleted",
        "type": "customer.subscription.deleted",
        "created": 1753000000,
        "data": {
            "object": {
                "id": "sub_A",
                "customer": "cus_A",
                "status": "canceled",
                "cancel_at_period_end": False,
                "current_period_end": 1760000000,
                "items": {"data": []},
            }
        },
    }
    with TestingSessionLocal() as db:
        assert handle_stripe_event(db, deleted_event) is True
        assert db.get(User, user_id).billing_status == "canceled"

    unknown_event = {"id": "evt_other", "type": "invoice.paid", "created": 1753100000, "data": {"object": {}}}
    with TestingSessionLocal() as db:
        assert handle_stripe_event(db, unknown_event) is False
        assert db.query(StripeWebhookEvent).filter_by(stripe_event_id="evt_other").one().status == "skipped"
