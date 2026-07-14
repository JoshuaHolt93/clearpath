from __future__ import annotations

from app.core.security import decode_token
from app.models import Category, FixedExpenseItem, User
from app.services.planning_service import app_today
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
            "display_name": "Budget User",
            "household_name": "Budget Household",
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


def mark_onboarded(token: str) -> int:
    payload = decode_token(token)
    with TestingSessionLocal() as db:
        user = db.get(User, int(payload["user_id"]))
        user.profile.income_amount = 1
        user.profile.monthly_income = 1
        db.commit()
        return user.id


def onboarded_token(client, email: str) -> tuple[str, int]:
    token = full_session_token(client, email)
    user_id = mark_onboarded(token)
    return token, user_id


def category_by_name(client, token: str, name: str) -> dict:
    response = client.get("/v1/category-rules", headers=auth_header(token))
    assert response.status_code == 200
    return next(category for category in response.json()["categories"] if category["name"] == name)


def previous_month_str() -> str:
    month_start = app_today().replace(day=1)
    previous = (month_start.year, month_start.month - 1) if month_start.month > 1 else (month_start.year - 1, 12)
    return f"{previous[0]:04d}-{previous[1]:02d}"


def test_budget_crud_flow_and_month_lock(client):
    token, user_id = onboarded_token(client, "budget-crud@example.com")

    # "Gym Membership" hits no group alias but the "gym" keyword, so the
    # Flask group resolver lands on health_wellness.
    created = client.post(
        "/v1/budgets",
        headers=auth_header(token),
        json={"category_label": "Gym Membership", "monthly_target": 80, "category_kind": "expense"},
    )
    assert created.status_code == 201
    body = created.json()
    assert body["category"]["name"] == "Gym Membership"
    assert body["category"]["kind"] == "expense"
    assert body["category"]["monthly_target"] == 80.0
    assert body["category"]["is_default"] is False
    assert body["group_key"] == "health_wellness"
    category_id = body["category"]["id"]

    # Validation parity: no label / non-positive target.
    assert client.post("/v1/budgets", headers=auth_header(token), json={"monthly_target": 50}).status_code == 422
    assert client.post("/v1/budgets", headers=auth_header(token), json={"category_label": "X", "monthly_target": 0}).status_code == 422

    updated = client.patch(f"/v1/budgets/{category_id}", headers=auth_header(token), json={"monthly_target": 120})
    assert updated.status_code == 200
    assert updated.json()["category"]["monthly_target"] == 120.0

    # Historical months are locked for edits (Flask historical_budget_edit_redirect).
    locked = client.patch(
        f"/v1/budgets/{category_id}",
        headers=auth_header(token),
        json={"monthly_target": 999, "budget_month": previous_month_str()},
    )
    assert locked.status_code == 409
    gym = category_by_name(client, token, "Gym Membership")
    assert gym["monthly_target"] == 120.0

    # Deleting the budget clears matching planning labels (Flask
    # delete_category_and_reassign -> clear_planning_category_label).
    with TestingSessionLocal() as db:
        db.add(FixedExpenseItem(user_id=user_id, name="Gym Draft", amount=30, category_label="Gym Membership"))
        db.commit()
    deleted = client.request("DELETE", f"/v1/budgets/{gym['id']}", headers=auth_header(token), json={})
    assert deleted.status_code == 200
    assert deleted.json()["deleted_category_id"] == gym["id"]
    assert deleted.json()["replacement_category"]["name"] == "Other"
    with TestingSessionLocal() as db:
        # name is an EncryptedText column, so query by owner instead.
        item = db.query(FixedExpenseItem).filter_by(user_id=user_id).one()
        assert item.name == "Gym Draft"
        assert item.category_label is None
        assert db.query(Category).filter_by(user_id=user_id, name="Gym Membership").first() is None

    # "Other" is protected as the catch-all.
    other = category_by_name(client, token, "Other")
    protected = client.request("DELETE", f"/v1/budgets/{other['id']}", headers=auth_header(token), json={})
    assert protected.status_code == 409


def test_budget_layout_reorders_and_validates(client):
    token, _user_id = onboarded_token(client, "budget-layout@example.com")
    groceries = category_by_name(client, token, "Groceries")
    dining = category_by_name(client, token, "Dining/Eating Out")

    layout = client.patch(
        "/v1/budgets/layout",
        headers=auth_header(token),
        json={
            "rows": [
                {"category_id": dining["id"], "group_key": "entertainment"},
                {"category_id": groceries["id"], "group_key": "not-a-real-group"},
            ]
        },
    )
    assert layout.status_code == 200
    assert layout.json() == {"ok": True, "updated": 2}

    dining_after = category_by_name(client, token, "Dining/Eating Out")
    groceries_after = category_by_name(client, token, "Groceries")
    assert dining_after["budget_sort_order"] == 1
    assert dining_after["budget_group_key"] == "entertainment"
    assert groceries_after["budget_sort_order"] == 2
    # Unknown group keys are ignored, order still applies (Flask parity):
    # Groceries keeps its seeded daily_living group.
    assert groceries_after["budget_group_key"] == "daily_living"

    empty = client.patch("/v1/budgets/layout", headers=auth_header(token), json={"rows": []})
    assert empty.status_code == 400
    unknown = client.patch("/v1/budgets/layout", headers=auth_header(token), json={"rows": [{"category_id": 999999}]})
    assert unknown.status_code == 400
    past = client.patch(
        "/v1/budgets/layout",
        headers=auth_header(token),
        json={"budget_month": previous_month_str(), "rows": [{"category_id": dining["id"]}]},
    )
    assert past.status_code == 400


def test_transaction_budget_action_and_activation(client):
    token, _user_id = onboarded_token(client, "budget-activate@example.com")

    coffee = client.post("/v1/categories", headers=auth_header(token), json={"name": "Coffee Shops", "kind": "expense"})
    assert coffee.status_code == 201
    assert coffee.json()["monthly_target"] == 0.0

    transaction = client.post(
        "/v1/transactions",
        headers=auth_header(token),
        json={
            "posted_date": str(app_today()),
            "description": "Blue Bottle",
            "amount": -63.45,
            "account_name": "Main Checking",
            "category_id": coffee.json()["id"],
        },
    )
    assert transaction.status_code == 201
    transaction_id = transaction.json()["id"]

    # Hand-computed: month actual 63.45 -> ceil(63.45/25)*25 = 75;
    # max(default 0, 75, floor 25) = 75.
    listed = client.get("/v1/transactions", headers=auth_header(token))
    assert listed.status_code == 200
    action = listed.json()["budget_actions"][str(transaction_id)]
    assert action["category_name"] == "Coffee Shops"
    assert action["target"] == 75.0
    assert action["target_label"] == "$75"
    assert action["hint"] == "Starts Coffee Shops at $75 per month."

    activated = client.post(f"/v1/transactions/{transaction_id}/budget-category", headers=auth_header(token))
    assert activated.status_code == 200
    assert activated.json()["target"] == 75.0
    assert activated.json()["category"]["monthly_target"] == 75.0
    assert activated.json()["category"]["kind"] == "expense"

    # Once the budget is active the action disappears and re-activation conflicts.
    again = client.post(f"/v1/transactions/{transaction_id}/budget-category", headers=auth_header(token))
    assert again.status_code == 409
    relisted = client.get("/v1/transactions", headers=auth_header(token))
    assert str(transaction_id) not in relisted.json()["budget_actions"]


def test_new_category_patch_activates_budget_and_applies_to_similar(client):
    token, _user_id = onboarded_token(client, "budget-similar@example.com")

    ids = []
    for _index in range(3):
        response = client.post(
            "/v1/transactions",
            headers=auth_header(token),
            json={
                "posted_date": str(app_today()),
                "description": "Golf Pro Shop",
                "amount": -42.10,
                "account_name": "Main Checking",
            },
        )
        assert response.status_code == 201
        ids.append(response.json()["id"])

    # Hand-computed: at activation only the patched transaction carries the
    # new category, so the actual basis is 42.10 -> ceil(42.10/25)*25 = 50.
    patched = client.patch(
        f"/v1/transactions/{ids[0]}/category",
        headers=auth_header(token),
        json={"new_category_name": "Golf Gear", "apply_to_similar": True},
    )
    assert patched.status_code == 200
    body = patched.json()
    assert body["transaction"]["category"]["name"] == "Golf Gear"
    assert body["created_budget_target"] == 50.0
    assert body["similar_updated_count"] == 2
    assert sorted(body["updated_transaction_ids"]) == sorted(ids)
    assert body["rule_created"] is True
    # The new category is now an active budget, so no follow-up action.
    assert body["budget_action"] is None

    rules = client.get("/v1/category-rules", headers=auth_header(token))
    golf_rules = [rule for rule in rules.json()["rules"] if rule["category"]["name"] == "Golf Gear"]
    assert len(golf_rules) == 1
    assert golf_rules[0]["match_text"] == "Golf Pro Shop"
    assert golf_rules[0]["match_type"] == "equals"

    # Re-applying does not duplicate the learned rule (Flask dedupe).
    golf = category_by_name(client, token, "Golf Gear")
    repatched = client.patch(
        f"/v1/transactions/{ids[1]}/category",
        headers=auth_header(token),
        json={"category_id": golf["id"], "apply_to_similar": True},
    )
    assert repatched.status_code == 200
    assert repatched.json()["rule_created"] is False
    assert repatched.json()["similar_updated_count"] == 0


def test_create_category_activate_budget_seeds_floor_target(client):
    token, _user_id = onboarded_token(client, "budget-newcat@example.com")

    # No current-month actuals: max(default 0, rounded 0, floor 25) = 25.
    seeded = client.post(
        "/v1/categories",
        headers=auth_header(token),
        json={"name": "Board Games", "kind": "expense", "activate_budget": True},
    )
    assert seeded.status_code == 201
    assert seeded.json()["monthly_target"] == 25.0

    # Unknown kinds normalize to expense (Flask 964c369).
    normalized = client.post("/v1/categories", headers=auth_header(token), json={"name": "Weird Kind", "kind": "transfer"})
    assert normalized.status_code == 201
    assert normalized.json()["kind"] == "expense"

    # Flask create_category runs behind ensure_onboarded.
    fresh = full_session_token(client, "budget-newcat-blocked@example.com")
    blocked = client.post("/v1/categories", headers=auth_header(fresh), json={"name": "Nope"})
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "onboarding_required"
