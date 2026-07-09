from __future__ import annotations

import json
from pathlib import Path

from app.core.security import decode_token
from app.models import User
from conftest import TestingSessionLocal

VALID_PASSWORD = "CorrectHorse1!"
API_ROOT = Path(__file__).resolve().parents[1]
CANONICAL_SAMPLE = Path(r"C:\Users\joshu\Documents\Codex\ClearPath Finance\data\sample_transactions.csv")
SAMPLE_PATH = CANONICAL_SAMPLE if CANONICAL_SAMPLE.exists() else API_ROOT / "tests" / "fixtures" / "sample_transactions.csv"
GOLDEN_PATH = API_ROOT / "tests" / "fixtures" / "sample_transactions_preview_golden.json"


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def full_session_token(client, email: str = "phase2a@example.com") -> str:
    registered = client.post(
        "/v1/auth/register",
        json={
            "email": email,
            "password": VALID_PASSWORD,
            "display_name": "Phase 2A User",
            "household_name": "Phase 2A Household",
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


def mark_onboarded(token: str) -> None:
    payload = decode_token(token)
    with TestingSessionLocal() as db:
        user = db.get(User, int(payload["user_id"]))
        user.profile.income_amount = 1
        user.profile.monthly_income = 1
        db.commit()


def category_by_name(client, token: str, name: str) -> dict:
    response = client.get("/v1/category-rules", headers=auth_header(token))
    assert response.status_code == 200
    return next(category for category in response.json()["categories"] if category["name"] == name)


def normalized_import_rows(rows: list[dict]) -> list[dict]:
    return [
        {
            "posted_date": row["posted_date"],
            "description": row["description"],
            "amount": row["amount"],
            "transaction_type": row["transaction_type"],
            "source_name": row["source_name"],
            "category_name": row["category_name"],
        }
        for row in rows
    ]


def test_csv_import_preview_and_commit_match_flask_golden(client):
    token = full_session_token(client, "csv-import@example.com")
    csv_text = SAMPLE_PATH.read_text(encoding="utf-8")
    golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))

    preview = client.post("/v1/transaction-imports/preview", headers=auth_header(token), json={"csv_text": csv_text})
    assert preview.status_code == 200
    preview_body = preview.json()
    assert preview_body["mapping"] == {"date": "Date", "description": "Description", "amount": "Amount", "debit": None, "credit": None, "account": "Account"}
    assert preview_body["new_count"] == 8
    assert preview_body["duplicate_count"] == 0
    assert normalized_import_rows(preview_body["new_transactions"]) == golden

    staged = client.get(f"/v1/transaction-imports/{preview_body['staged_import_id']}", headers=auth_header(token))
    assert staged.status_code == 200
    assert normalized_import_rows(staged.json()["new_transactions"]) == golden

    committed = client.post(f"/v1/transaction-imports/{preview_body['staged_import_id']}/commit", headers=auth_header(token), json={"confirm": True})
    assert committed.status_code == 200
    assert committed.json()["imported"] == 8
    assert committed.json()["duplicate_count"] == 0

    listed = client.get("/v1/transactions?per_page=50", headers=auth_header(token))
    assert listed.status_code == 200
    assert listed.json()["total"] == 8

    duplicate_preview = client.post("/v1/transaction-imports/preview", headers=auth_header(token), json={"csv_text": csv_text})
    assert duplicate_preview.status_code == 200
    assert duplicate_preview.json()["new_count"] == 0
    assert duplicate_preview.json()["duplicate_count"] == 8


def test_staged_import_is_bound_to_creating_user(client):
    owner_token = full_session_token(client, "stage-owner@example.com")
    csv_text = SAMPLE_PATH.read_text(encoding="utf-8")
    preview = client.post("/v1/transaction-imports/preview", headers=auth_header(owner_token), json={"csv_text": csv_text})
    assert preview.status_code == 200
    staged_id = preview.json()["staged_import_id"]

    intruder_token = full_session_token(client, "stage-intruder@example.com")
    assert client.get(f"/v1/transaction-imports/{staged_id}", headers=auth_header(intruder_token)).status_code == 404
    assert (
        client.post(f"/v1/transaction-imports/{staged_id}/commit", headers=auth_header(intruder_token), json={"confirm": True}).status_code
        == 404
    )

    # The creating user can still read and commit their own staged import.
    assert client.get(f"/v1/transaction-imports/{staged_id}", headers=auth_header(owner_token)).status_code == 200
    committed = client.post(f"/v1/transaction-imports/{staged_id}/commit", headers=auth_header(owner_token), json={"confirm": True})
    assert committed.status_code == 200
    assert committed.json()["imported"] == 8


def test_category_rule_requires_onboarding_and_returns_applied_count(client):
    token = full_session_token(client, "rules@example.com")
    groceries = category_by_name(client, token, "Groceries")
    created = client.post(
        "/v1/transactions",
        headers=auth_header(token),
        json={"posted_date": "2026-04-04", "description": "Kroger Store 214", "amount": -142.16, "account_name": "Main Checking"},
    )
    assert created.status_code == 201

    payload = {
        "category_id": groceries["id"],
        "conditions": [{"field": "description", "operator": "contains", "value": "kroger"}],
    }
    blocked = client.post("/v1/category-rules", headers=auth_header(token), json=payload)
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "onboarding_required"

    mark_onboarded(token)
    rule = client.post("/v1/category-rules", headers=auth_header(token), json=payload)
    assert rule.status_code == 201
    assert rule.json()["applied_count"] == 1
    assert rule.json()["match_text"] == "kroger"

    updated = client.get(f"/v1/transactions?ids={created.json()['id']}", headers=auth_header(token))
    assert updated.status_code == 200
    assert updated.json()["items"][0]["category"]["name"] == "Groceries"


def test_transaction_splits_and_duplicate_merge(client):
    token = full_session_token(client, "splits@example.com")
    groceries = category_by_name(client, token, "Groceries")
    dining = category_by_name(client, token, "Dining/Eating Out")

    transaction = client.post(
        "/v1/transactions",
        headers=auth_header(token),
        json={"posted_date": "2026-04-20", "description": "Mixed Errands", "amount": -100, "account_name": "Main Checking"},
    )
    assert transaction.status_code == 201
    split_response = client.patch(
        f"/v1/transactions/{transaction.json()['id']}/splits",
        headers=auth_header(token),
        json={"splits": [{"category_id": groceries["id"], "amount": 60}, {"category_id": dining["id"], "amount": 40}]},
    )
    assert split_response.status_code == 200
    assert [split["amount"] for split in split_response.json()["splits"]] == [60.0, 40.0]
    assert split_response.json()["category"]["name"] == "Groceries"

    first = client.post(
        "/v1/transactions",
        headers=auth_header(token),
        json={"posted_date": "2026-04-21", "description": "Shell Oil 0442", "amount": -58.02, "account_name": "Main Checking"},
    ).json()
    second = client.post(
        "/v1/transactions",
        headers=auth_header(token),
        json={"posted_date": "2026-04-21", "description": "Shell Gas", "amount": -58.02, "account_name": "Main Checking"},
    ).json()
    merged = client.post(
        "/v1/transactions/duplicates/merge",
        headers=auth_header(token),
        json={"first_transaction_id": first["id"], "second_transaction_id": second["id"]},
    )
    assert merged.status_code == 200
    assert merged.json()["merged"] is True
    assert merged.json()["deleted_transaction_id"] == second["id"]
