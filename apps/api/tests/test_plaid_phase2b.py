from __future__ import annotations

from datetime import timedelta

import pytest

from app.core.config import get_settings
from app.models import Account, PlaidAccountIgnore, PlaidItem, PlaidWebhookEvent, Transaction, utc_now
from app.services.plaid_service import decrypt_access_token, encrypt_access_token
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
            "display_name": "Plaid User",
            "household_name": "Plaid Household",
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


class FakePlaidClient:
    def __init__(self):
        self.sync_calls = 0
        self.item_remove_calls = []
        self.accounts = [
            {
                "account_id": "acct-checking-1",
                "name": "Everyday Checking",
                "official_name": "Everyday Checking Account",
                "type": "depository",
                "subtype": "checking",
                "mask": "0442",
                "balances": {"available": 1250.75, "current": 1300.10},
            }
        ]
        self.added = [
            {
                "transaction_id": "plaid-txn-1",
                "account_id": "acct-checking-1",
                "amount": 42.5,
                "date": "2026-07-01",
                "name": "KROGER 214 CINCINNATI OH",
                "merchant_name": "Kroger",
                "pending": False,
                "personal_finance_category": {"primary": "FOOD_AND_DRINK", "detailed": "FOOD_AND_DRINK_GROCERIES"},
            },
            {
                "transaction_id": "plaid-txn-2",
                "account_id": "acct-checking-1",
                "amount": -3100.0,
                "date": "2026-07-02",
                "name": "PAYROLL DEPOSIT",
                "merchant_name": None,
                "pending": False,
                "personal_finance_category": {"primary": "INCOME", "detailed": "INCOME_WAGES"},
            },
        ]

    def link_token_create(self, request):
        return {"link_token": "link-sandbox-test-token"}

    def item_public_token_exchange(self, request):
        return {"item_id": "item-test-1", "access_token": "access-sandbox-test-abc"}

    def accounts_get(self, request):
        return {"accounts": self.accounts}

    def transactions_sync(self, request):
        self.sync_calls += 1
        return {"added": list(self.added), "modified": [], "removed": [], "has_more": False, "next_cursor": f"cursor-{self.sync_calls}"}

    def item_remove(self, request):
        self.item_remove_calls.append(request)
        return {"removed": True}


@pytest.fixture
def fake_plaid(monkeypatch):
    from app.services import plaid_service

    fake = FakePlaidClient()
    monkeypatch.setattr(plaid_service, "plaid", object())
    monkeypatch.setattr(plaid_service, "plaid_client", lambda: fake)
    monkeypatch.setattr(plaid_service, "Products", lambda value: value)
    monkeypatch.setattr(plaid_service, "CountryCode", lambda value: value)
    for name in [
        "LinkTokenTransactions",
        "LinkTokenCreateRequest",
        "ItemPublicTokenExchangeRequest",
        "ItemRemoveRequest",
        "AccountsGetRequest",
        "TransactionsSyncRequest",
        "TransactionsSyncRequestOptions",
    ]:
        monkeypatch.setattr(plaid_service, name, lambda **kwargs: kwargs)
    return fake


def connect_plaid_item(client, token: str) -> dict:
    link = client.post("/v1/plaid/link-token", headers=auth_header(token))
    assert link.status_code == 200
    consent_token = link.json()["consent_token"]
    exchanged = client.post(
        "/v1/plaid/exchange-public-token",
        headers=auth_header(token),
        json={"public_token": "public-sandbox-test", "metadata": {"institution": {"name": "Test Bank", "institution_id": "ins_1"}}, "consent_token": consent_token},
    )
    assert exchanged.status_code == 200
    return exchanged.json()


def test_exchange_public_token_creates_item_accounts_and_transactions(client, fake_plaid):
    token = full_session_token(client, "plaid-exchange@example.com")
    item = connect_plaid_item(client, token)
    assert item["institution_name"] == "Test Bank"
    assert item["status"] == "connected"
    assert item["consent_acknowledged_at"] is not None
    assert [account["name"] for account in item["accounts"]] == ["Everyday Checking"]
    # Depository accounts use the available balance, matching Flask.
    assert item["accounts"][0]["current_balance"] == 1250.75

    listed = client.get("/v1/transactions?per_page=50", headers=auth_header(token))
    assert listed.status_code == 200
    body = listed.json()
    assert body["total"] == 2
    by_desc = {row["description"]: row for row in body["items"]}
    assert by_desc["Kroger"]["amount"] == -42.5
    assert by_desc["Kroger"]["category"]["name"] == "Groceries"
    assert by_desc["PAYROLL DEPOSIT"]["amount"] == 3100.0
    assert by_desc["PAYROLL DEPOSIT"]["category"]["name"] == "Income"

    # The stored access token is Fernet-encrypted and decrypts to the raw token.
    with TestingSessionLocal() as db:
        stored = db.query(PlaidItem).one()
        assert stored.access_token_encrypted != "access-sandbox-test-abc"
    from app.services import plaid_service as ps
    assert decrypt_access_token(stored.access_token_encrypted) == "access-sandbox-test-abc"

    # Re-syncing the same Plaid data must not duplicate transactions.
    synced = client.post(f"/v1/plaid-items/{item['id']}/sync", headers=auth_header(token))
    assert synced.status_code == 200
    assert client.get("/v1/transactions?per_page=50", headers=auth_header(token)).json()["total"] == 2


def test_webhook_requires_secret_when_configured(client, fake_plaid, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "plaid_webhook_secret", "hook-secret")
    payload = {"webhook_type": "TRANSACTIONS", "webhook_code": "SYNC_UPDATES_AVAILABLE", "item_id": "missing", "webhook_id": "wh-1"}

    denied = client.post("/v1/webhooks/plaid", json=payload)
    assert denied.status_code == 401
    wrong = client.post("/v1/webhooks/plaid", json=payload, headers={"X-ClearPath-Webhook-Secret": "nope"})
    assert wrong.status_code == 401
    allowed = client.post("/v1/webhooks/plaid", json=payload, headers={"X-ClearPath-Webhook-Secret": "hook-secret"})
    assert allowed.status_code == 200
    via_query = client.post("/v1/webhooks/plaid?webhook_secret=hook-secret", json=payload)
    assert via_query.status_code == 200


def test_webhook_sync_and_idempotency(client, fake_plaid):
    token = full_session_token(client, "plaid-webhook@example.com")
    connect_plaid_item(client, token)

    payload = {
        "webhook_type": "TRANSACTIONS",
        "webhook_code": "SYNC_UPDATES_AVAILABLE",
        "item_id": "item-test-1",
        "webhook_id": "webhook-unique-1",
    }
    first = client.post("/v1/webhooks/plaid", json=payload)
    assert first.status_code == 200
    assert first.json()["handled"] is True
    assert first.json()["status"] == "synced"

    duplicate = client.post("/v1/webhooks/plaid", json=payload)
    assert duplicate.status_code == 200
    assert duplicate.json()["handled"] is False
    assert duplicate.json()["duplicate"] is True

    with TestingSessionLocal() as db:
        events = db.query(PlaidWebhookEvent).all()
        assert len(events) == 1
        assert events[0].status == "processed"


def test_item_webhook_marks_reconnect_required(client, fake_plaid):
    token = full_session_token(client, "plaid-reconnect@example.com")
    item = connect_plaid_item(client, token)

    response = client.post(
        "/v1/webhooks/plaid",
        json={"webhook_type": "ITEM", "webhook_code": "ITEM_LOGIN_REQUIRED", "item_id": "item-test-1", "webhook_id": "webhook-item-1"},
    )
    assert response.status_code == 200
    assert response.json()["handled"] is True
    assert response.json()["status"] == "reconnect_required"

    items = client.get("/v1/plaid-items", headers=auth_header(token)).json()["items"]
    assert items[0]["status"] == "reconnect_required"
    assert items[0]["error_code"] == "ITEM_LOGIN_REQUIRED"

    # A reconnect-required item refuses manual sync.
    refused = client.post(f"/v1/plaid-items/{item['id']}/sync", headers=auth_header(token))
    assert refused.status_code == 400


def test_refresh_stale_honors_min_interval_throttle(client, fake_plaid):
    token = full_session_token(client, "plaid-throttle@example.com")
    connect_plaid_item(client, token)
    calls_after_connect = fake_plaid.sync_calls

    # Just synced during exchange: within the 15-minute window nothing refreshes.
    fresh = client.post("/v1/plaid-items/refresh-stale", headers=auth_header(token), json={})
    assert fresh.status_code == 200
    assert fresh.json()["synced"] == 0
    assert fake_plaid.sync_calls == calls_after_connect

    with TestingSessionLocal() as db:
        stored = db.query(PlaidItem).one()
        stored.last_synced_at = utc_now() - timedelta(minutes=30)
        db.commit()

    stale = client.post("/v1/plaid-items/refresh-stale", headers=auth_header(token), json={})
    assert stale.status_code == 200
    assert stale.json()["synced"] == 1
    assert fake_plaid.sync_calls == calls_after_connect + 1


def test_remove_synced_account_ignores_and_restore(client, fake_plaid):
    token = full_session_token(client, "plaid-remove@example.com")
    item = connect_plaid_item(client, token)
    account_id = item["accounts"][0]["id"]

    removed = client.delete(f"/v1/accounts/{account_id}", headers=auth_header(token))
    assert removed.status_code == 200
    ignore_id = removed.json()["ignored_account_id"]

    assert client.get("/v1/transactions?per_page=50", headers=auth_header(token)).json()["total"] == 0

    # While ignored, syncing does not resurrect the account or its transactions.
    synced = client.post(f"/v1/plaid-items/{item['id']}/sync", headers=auth_header(token))
    assert synced.status_code == 200
    listing = client.get("/v1/plaid-items", headers=auth_header(token)).json()
    assert listing["items"][0]["accounts"] == []
    assert [row["id"] for row in listing["ignored_accounts"]] == [ignore_id]
    assert client.get("/v1/transactions?per_page=50", headers=auth_header(token)).json()["total"] == 0

    restored = client.post(f"/v1/plaid-ignored-accounts/{ignore_id}/restore", headers=auth_header(token))
    assert restored.status_code == 200
    resynced = client.post(f"/v1/plaid-items/{item['id']}/sync", headers=auth_header(token))
    assert resynced.status_code == 200
    assert client.get("/v1/transactions?per_page=50", headers=auth_header(token)).json()["total"] == 2


def test_disconnect_revokes_and_keeps_history(client, fake_plaid):
    token = full_session_token(client, "plaid-disconnect@example.com")
    item = connect_plaid_item(client, token)

    disconnected = client.delete(f"/v1/plaid-items/{item['id']}", headers=auth_header(token))
    assert disconnected.status_code == 200
    assert disconnected.json() == {"disconnected": True, "already_disconnected": False}
    assert len(fake_plaid.item_remove_calls) == 1

    with TestingSessionLocal() as db:
        stored_item = db.query(PlaidItem).one()
        assert stored_item.status == "disconnected"
        assert stored_item.access_token_encrypted == ""
        assert stored_item.plaid_item_id == f"disconnected:{stored_item.id}"
        account = db.query(Account).one()
        assert account.is_manual is True
        assert account.plaid_account_id is None
        assert account.plaid_item_id is None
        assert account.cash_projection_role == "exclude"
        # Transaction history is kept, but Plaid identifiers are stripped.
        transactions = db.query(Transaction).all()
        assert len(transactions) == 2
        assert all(transaction.plaid_transaction_id is None for transaction in transactions)

    # Disconnecting again reports already_disconnected without calling Plaid.
    again = client.delete(f"/v1/plaid-items/{item['id']}", headers=auth_header(token))
    assert again.status_code == 200
    assert again.json()["already_disconnected"] is True
    assert len(fake_plaid.item_remove_calls) == 1


def test_plaid_items_are_scoped_to_owner(client, fake_plaid):
    owner_token = full_session_token(client, "plaid-owner@example.com")
    item = connect_plaid_item(client, owner_token)

    intruder_token = full_session_token(client, "plaid-intruder@example.com")
    assert client.post(f"/v1/plaid-items/{item['id']}/sync", headers=auth_header(intruder_token)).status_code == 404
    assert client.delete(f"/v1/plaid-items/{item['id']}", headers=auth_header(intruder_token)).status_code == 404
    account_id = item["accounts"][0]["id"]
    assert client.delete(f"/v1/accounts/{account_id}", headers=auth_header(intruder_token)).status_code == 404
