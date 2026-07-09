from __future__ import annotations

from app.core.security import decode_token
from app.models import SubscriptionTransactionIgnore, User
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
            "display_name": "Subs User",
            "household_name": "Subs Household",
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


def prepare_user(token: str, *, plan: str = "basic", onboarded: bool = True) -> None:
    payload = decode_token(token)
    with TestingSessionLocal() as db:
        user = db.get(User, int(payload["user_id"]))
        user.selected_plan = plan
        if onboarded:
            user.profile.income_amount = 1
            user.profile.monthly_income = 1
        db.commit()


def subscriber_token(client, email: str) -> str:
    token = full_session_token(client, email)
    prepare_user(token)
    return token


def add_transaction(client, token: str, *, posted_date: str, description: str, amount: float) -> dict:
    response = client.post(
        "/v1/transactions",
        headers=auth_header(token),
        json={"posted_date": posted_date, "description": description, "amount": amount, "account_name": "Main Checking"},
    )
    assert response.status_code == 201
    return response.json()


def add_netflix_history(client, token: str) -> list[dict]:
    return [
        add_transaction(client, token, posted_date=day, description="NETFLIX.COM 880123", amount=-18.99)
        for day in ("2026-04-01", "2026-05-01", "2026-05-31")
    ]


def scan(client, token: str) -> dict:
    response = client.post("/v1/subscriptions/scan", headers=auth_header(token))
    assert response.status_code == 200
    return response.json()


def test_feature_gate_requires_onboarding_then_plan(client):
    token = full_session_token(client, "gate@example.com")
    blocked = client.get("/v1/subscriptions", headers=auth_header(token))
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "onboarding_required"

    prepare_user(token, plan="")
    locked = client.get("/v1/subscriptions", headers=auth_header(token))
    assert locked.status_code == 403
    assert locked.json()["detail"]["code"] == "feature_locked"

    prepare_user(token, plan="basic")
    assert client.get("/v1/subscriptions", headers=auth_header(token)).status_code == 200


def test_catalog_detection_finds_netflix_monthly(client):
    token = subscriber_token(client, "catalog@example.com")
    add_netflix_history(client, token)

    result = scan(client, token)
    assert result["synced_count"] == 1
    subscription = result["subscriptions"][0]
    assert subscription["merchant_key"] == "netflix"
    assert subscription["name"] == "Netflix"
    assert subscription["service_category"] == "Streaming"
    assert subscription["cycle"] == "Monthly"
    assert subscription["amount"] == 18.99
    assert subscription["monthly_amount"] == 18.99
    assert subscription["annual_amount"] == 227.88
    assert subscription["status"] == "active"
    assert subscription["confidence"] == 0.95
    assert subscription["cancel_url"] == "https://www.netflix.com/cancelplan"
    assert subscription["next_charge_date"] == "2026-06-30"

    listing = client.get("/v1/subscriptions", headers=auth_header(token)).json()
    assert listing["summary"]["active_count"] == 1
    assert listing["summary"]["monthly_total"] == 18.99
    assert [row["category"] for row in listing["category_breakdown"]] == ["Streaming"]
    evidence = listing["subscriptions"][0]["evidence"]
    assert len(evidence) == 3
    assert {item["amount"] for item in evidence} == {18.99}


def test_heuristic_detection_needs_subscription_signal(client):
    token = subscriber_token(client, "heuristic@example.com")
    for day in ("2026-04-05", "2026-05-05", "2026-06-04"):
        add_transaction(client, token, posted_date=day, description="Acme Gym Membership", amount=-25.0)

    result = scan(client, token)
    assert result["synced_count"] == 1
    subscription = result["subscriptions"][0]
    assert subscription["merchant_key"] == "acme gym"
    assert subscription["cycle"] == "Monthly"
    assert subscription["status"] == "active"
    assert subscription["confidence"] >= 0.85


def test_common_purchases_are_not_subscriptions(client):
    token = subscriber_token(client, "grocery@example.com")
    for day in ("2026-04-07", "2026-04-14", "2026-04-21", "2026-04-28"):
        add_transaction(client, token, posted_date=day, description="KROGER STORE 214", amount=-84.12)

    result = scan(client, token)
    assert result["synced_count"] == 0


def test_manual_subscription_and_cycle_math(client):
    token = subscriber_token(client, "manual@example.com")
    created = client.post(
        "/v1/subscriptions",
        headers=auth_header(token),
        json={"name": "Neighborhood Gym", "amount": 120, "cycle": "Annual", "next_charge_date": "2026-12-01"},
    )
    assert created.status_code == 201
    body = created.json()
    assert body["is_manual"] is True
    assert body["cycle_is_manual"] is True
    assert body["monthly_amount"] == 10.0
    assert body["annual_amount"] == 120.0

    bad_cycle = client.post(
        "/v1/subscriptions",
        headers=auth_header(token),
        json={"name": "Thing", "amount": 5, "cycle": "Fortnightly"},
    )
    assert bad_cycle.status_code == 422


def test_status_and_manual_cycle_survive_rescan(client):
    token = subscriber_token(client, "sticky@example.com")
    add_netflix_history(client, token)
    subscription = scan(client, token)["subscriptions"][0]

    canceling = client.patch(
        f"/v1/subscriptions/{subscription['id']}",
        headers=auth_header(token),
        json={"status": "canceling", "notes": "Dropping this"},
    )
    assert canceling.status_code == 200
    assert canceling.json()["status"] == "canceling"

    recycled = client.patch(
        f"/v1/subscriptions/{subscription['id']}",
        headers=auth_header(token),
        json={"cycle": "Annual"},
    )
    assert recycled.status_code == 200
    assert recycled.json()["cycle"] == "Annual"
    assert recycled.json()["monthly_amount"] == round(18.99 / 12, 2)

    rescanned = scan(client, token)["subscriptions"][0]
    # Flask preserves canceling/canceled/ignored statuses and manual cycles.
    assert rescanned["status"] == "canceling"
    assert rescanned["cycle"] == "Annual"
    assert rescanned["cycle_is_manual"] is True

    bad_url = client.patch(
        f"/v1/subscriptions/{subscription['id']}",
        headers=auth_header(token),
        json={"cancel_url": "ftp://example.com"},
    )
    assert bad_url.status_code == 422


def test_ignored_subscription_stays_out_of_scans(client):
    token = subscriber_token(client, "ignored@example.com")
    add_netflix_history(client, token)
    subscription = scan(client, token)["subscriptions"][0]

    ignored = client.patch(
        f"/v1/subscriptions/{subscription['id']}",
        headers=auth_header(token),
        json={"status": "ignored"},
    )
    assert ignored.status_code == 200

    assert scan(client, token)["synced_count"] == 0
    listing = client.get("/v1/subscriptions", headers=auth_header(token)).json()
    assert listing["subscriptions"][0]["status"] == "ignored"
    assert listing["summary"]["active_count"] == 0


def test_evidence_ignore_removes_transaction_from_future_scans(client):
    token = subscriber_token(client, "evidence@example.com")
    transactions = add_netflix_history(client, token)
    subscription = scan(client, token)["subscriptions"][0]

    response = client.post(
        f"/v1/subscriptions/{subscription['id']}/evidence/{transactions[-1]['id']}/ignore",
        headers=auth_header(token),
    )
    assert response.status_code == 200
    assert len(response.json()["evidence"]) == 2

    with TestingSessionLocal() as db:
        ignore_rows = db.query(SubscriptionTransactionIgnore).all()
        assert len(ignore_rows) == 1
        assert ignore_rows[0].transaction_id == transactions[-1]["id"]
        assert ignore_rows[0].merchant_key == "netflix"

    # Flask keys the ignore ledger on merchant+amount, so ignoring one 18.99
    # Netflix charge suppresses every identical charge from future scans: the
    # rescan finds no candidate, and the stored subscription keeps its
    # refreshed two-item evidence.
    assert scan(client, token)["synced_count"] == 0
    listing = client.get("/v1/subscriptions", headers=auth_header(token)).json()
    assert len(listing["subscriptions"]) == 1
    assert len(listing["subscriptions"][0]["evidence"]) == 2


def test_csv_import_and_export_roundtrip(client):
    token = subscriber_token(client, "csv@example.com")
    csv_text = (
        "Date,Description,Amount\n"
        "04/09/2026,Spotify Premium,-11.99\n"
        "05/09/2026,Spotify Premium,-11.99\n"
        "06/08/2026,Spotify Premium,-11.99\n"
    )
    imported = client.post("/v1/subscription-imports", headers=auth_header(token), json={"csv_text": csv_text})
    assert imported.status_code == 200
    assert imported.json()["imported"] == 3
    assert imported.json()["synced_count"] == 1

    export = client.get("/v1/subscriptions/export.csv", headers=auth_header(token))
    assert export.status_code == 200
    assert export.headers["content-type"].startswith("text/csv")
    lines = export.text.strip().splitlines()
    assert lines[0] == "name,category,amount,cycle,monthly,annual,nextDate,status,confidence,manageUrl,source"
    assert any("Spotify" in line and "detected" in line for line in lines[1:])


def test_plaid_post_sync_hook_scans_subscriptions(client):
    from app.services import plaid_service
    from app.services.subscription_service import _plaid_post_sync_hook

    assert _plaid_post_sync_hook in plaid_service.POST_SYNC_HOOKS

    token = subscriber_token(client, "hook@example.com")
    add_netflix_history(client, token)
    payload = decode_token(token)
    with TestingSessionLocal() as db:
        user = db.get(User, int(payload["user_id"]))
        plaid_service.run_post_sync_hooks(db, user)

    listing = client.get("/v1/subscriptions", headers=auth_header(token)).json()
    assert listing["summary"]["active_count"] == 1
    assert listing["subscriptions"][0]["merchant_key"] == "netflix"
