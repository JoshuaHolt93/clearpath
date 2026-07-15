from __future__ import annotations

from sqlalchemy import text

from app.core.ai_policy import AI_GUIDANCE_DISCLAIMER
from app.core.security import decode_token
from app.models import AIUsageLog, HouseholdMember, Subscription, User
from app.services.planner_service import PlannerAIError, normalize_planner_model
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
            "display_name": "Planner User",
            "household_name": "Planner Household",
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


def configure_user(token: str, *, plan: str = "premium", onboarded: bool = True) -> int:
    payload = decode_token(token)
    with TestingSessionLocal() as db:
        user = db.get(User, int(payload["user_id"]))
        user.selected_plan = plan
        if onboarded:
            user.profile.income_amount = 60000
            user.profile.monthly_income = 5000
            user.profile.income_type = "salary"
            user.profile.income_basis = "take_home"
        db.commit()
        return user.id


def onboarded_token(client, email: str, *, plan: str = "premium") -> tuple[str, int]:
    token = full_session_token(client, email)
    return token, configure_user(token, plan=plan)


def shared_session_token(client, owner_id: int, email: str, role: str = "viewer") -> str:
    with TestingSessionLocal() as db:
        member = HouseholdMember(
            owner_user_id=owner_id,
            invited_by_user_id=owner_id,
            email=email,
            role=role,
            status="active",
        )
        member.set_password(VALID_PASSWORD)
        db.add(member)
        db.commit()
    login = client.post("/v1/auth/login", json={"email": email, "password": VALID_PASSWORD})
    assert login.status_code == 200
    completed = client.post(
        "/v1/auth/mfa/setup",
        headers=auth_header(login.json()["access_token"]),
        json={"action": "skip"},
    )
    assert completed.status_code == 200
    return completed.json()["access_token"]


def test_planner_openapi_contract(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert set(paths["/v1/planner/guidance"]) == {"get"}
    assert set(paths["/v1/planner/guidance/generate"]) == {"post"}
    assert set(paths["/v1/planner/preferences"]) == {"patch"}
    assert set(paths["/v1/planner/page-context"]) == {"post"}
    assert set(paths["/v1/subscriptions/{subscription_id}/link-help"]) == {"post"}


def test_model_normalization_and_planner_access_boundaries(client, monkeypatch):
    assert normalize_planner_model("bad", "also-bad") == ("openai", "gpt-5.5")
    assert normalize_planner_model("google", "bad") == ("google", "gemini-2.5-pro")
    monkeypatch.setattr("app.services.planner_service._provider_api_key", lambda _provider: None)

    premium_token, owner_id = onboarded_token(client, "planner-premium@example.com")
    premium_headers = auth_header(premium_token)
    ready = client.get("/v1/planner/guidance", headers=premium_headers)
    assert ready.status_code == 200
    body = ready.json()
    assert body["status"] == "ready"
    assert body["items"]
    assert all(item["disclaimer"] == AI_GUIDANCE_DISCLAIMER for item in body["items"])
    assert [option["key"] for option in body["model_options"]] == [
        "openai",
        "anthropic",
        "google",
    ]
    assert body["usage"]["daily_count"] == 0
    fallback = client.post(
        "/v1/planner/guidance/generate",
        headers=premium_headers,
        json={},
    )
    assert fallback.status_code == 200
    assert fallback.json()["status"] == "fallback"
    assert fallback.json()["generated_at"] is not None

    viewer_token = shared_session_token(client, owner_id, "planner-viewer@example.com")
    viewer_headers = auth_header(viewer_token)
    assert client.get("/v1/planner/guidance", headers=viewer_headers).status_code == 200
    assert (
        client.post(
            "/v1/planner/page-context",
            headers=viewer_headers,
            json={"path": "/dashboard", "visible_text": "Safe to spend"},
        ).status_code
        == 200
    )
    assert (
        client.patch(
            "/v1/planner/preferences",
            headers=viewer_headers,
            json={"provider": "openai", "model": "gpt-5.1"},
        ).status_code
        == 403
    )

    basic_token, _ = onboarded_token(client, "planner-basic@example.com", plan="basic")
    locked = client.get("/v1/planner/guidance", headers=auth_header(basic_token))
    assert locked.status_code == 403
    assert locked.json()["detail"]["code"] == "feature_locked"

    pending_token = full_session_token(client, "planner-onboarding@example.com")
    configure_user(pending_token, plan="premium", onboarded=False)
    assert (
        client.get("/v1/planner/guidance", headers=auth_header(pending_token)).status_code
        == 409
    )


def test_preferences_generation_guardrail_retry_usage_and_encrypted_snapshot(
    client,
    monkeypatch,
):
    token, user_id = onboarded_token(client, "planner-generate@example.com")
    headers = auth_header(token)
    preference = client.patch(
        "/v1/planner/preferences",
        headers=headers,
        json={"provider": "openai", "model": "gpt-5.1"},
    )
    assert preference.status_code == 200
    assert preference.json()["selected_model"] == "gpt-5.1"

    monkeypatch.setattr("app.services.planner_service._provider_api_key", lambda _provider: "test-key")
    calls = []

    def fake_post_json(_url, _headers, payload, *args, **kwargs):
        calls.append(payload)
        if len(calls) == 1:
            return {
                "id": "resp_guardrail_first",
                "output_text": '{"items":[{"title":"Buy this fund","body":"You should buy this fund now.","level":"info","type":"bad"}]}',
                "usage": {"input_tokens": 100, "output_tokens": 40, "total_tokens": 140},
            }
        return {
            "id": "resp_guardrail_retry",
            "output_text": '{"items":[{"title":"Cash Flow Review","body":"Review upcoming bills and category timing before adding new goals.","level":"info","type":"cash_flow"}]}',
            "usage": {"input_tokens": 120, "output_tokens": 30, "total_tokens": 150},
        }

    monkeypatch.setattr("app.services.planner_service._post_json", fake_post_json)
    generated = client.post(
        "/v1/planner/guidance/generate",
        headers=headers,
        json={},
    )
    assert generated.status_code == 200
    body = generated.json()
    assert len(calls) == 2
    assert "previous draft could not be shown" in calls[1]["instructions"].lower()
    assert body["status"] == "ai"
    assert body["items"][0]["title"] == "Cash Flow Review"
    assert body["items"][0]["action"] == {
        "label": "Review Forecast",
        "target": "monthly_plan_forecast",
    }
    assert body["generated_at"] is not None

    with TestingSessionLocal() as db:
        usage = db.query(AIUsageLog).filter_by(user_id=user_id).one()
        assert usage.prompt_tokens == 220
        assert usage.completion_tokens == 70
        assert usage.total_tokens == 290
        assert usage.estimated_cost_cents == 0.057
        assert usage.provider_request_id == "resp_guardrail_retry"
        raw_snapshot = db.execute(
            text("SELECT ai_guidance_snapshot FROM user WHERE id = :user_id"),
            {"user_id": user_id},
        ).scalar_one()
        assert "Cash Flow Review" not in raw_snapshot

    saved = client.get("/v1/planner/guidance", headers=headers)
    assert saved.status_code == 200
    assert saved.json()["items"][0]["title"] == "Cash Flow Review"
    dashboard = client.get("/v1/dashboard", headers=headers)
    assert dashboard.status_code == 200
    assert dashboard.json()["dashboard_focus"]["items"][0]["title"] == "Cash Flow Review"


def test_page_context_scope_fallback_and_fair_use_logging(client, monkeypatch):
    token, user_id = onboarded_token(client, "planner-context@example.com")
    headers = auth_header(token)
    monkeypatch.setattr("app.services.planner_service._provider_api_key", lambda _provider: "test-key")

    def markup_response(*_args, **_kwargs):
        return {
            "output_text": """```json
{"items":[{"title":"**Cash Flow**","body":"<p>Review the upcoming bills and category movement.</p>","level":"info","type":"page_context"}]}
```"""
        }

    monkeypatch.setattr("app.services.planner_service._post_json", markup_response)
    coached = client.post(
        "/v1/planner/page-context",
        headers=headers,
        json={"path": "/dashboard", "visible_text": "Safe to spend"},
    )
    assert coached.status_code == 200
    assert coached.json()["items"][0]["title"] == "Cash Flow"
    assert coached.json()["items"][0]["body"] == (
        "Review the upcoming bills and category movement."
    )

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("out-of-scope page coaching should not call a provider")

    monkeypatch.setattr("app.services.planner_service._post_json", fail_if_called)
    outside = client.post(
        "/v1/planner/page-context",
        headers=headers,
        json={
            "path": "/dashboard",
            "title": "Dashboard",
            "visible_text": "Safe to spend is lower than target.",
            "question": "Give me a chicken recipe for dinner.",
        },
    )
    assert outside.status_code == 200
    assert outside.json()["status"] == "out_of_scope"
    assert outside.json()["items"][0]["title"] == "Outside ClearPath Scope"

    with TestingSessionLocal() as db:
        db.add(
            AIUsageLog(
                user_id=user_id,
                feature="page_context",
                provider="openai",
                model="gpt-5.5",
                status="ai",
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
                estimated_cost_cents=0.05,
            )
        )
        db.commit()
    monkeypatch.setattr(
        "app.services.planner_service._fair_use_limits",
        lambda: {
            "burst_window_minutes": 10,
            "burst_limit": 8,
            "daily_limit": 1,
            "monthly_limit": 300,
            "monthly_cost_limit": 250,
        },
    )
    limited = client.post(
        "/v1/planner/page-context",
        headers=headers,
        json={"path": "/dashboard", "visible_text": "Safe to spend"},
    )
    assert limited.status_code == 200
    assert limited.json()["status"] == "fallback"
    assert "limit" not in limited.json()["message"].lower()
    with TestingSessionLocal() as db:
        log = db.query(AIUsageLog).filter_by(user_id=user_id, status="limited").one()
        assert log.limit_reason == "daily_request_limit"


def test_subscription_link_help_web_search_filters_and_timeout_message(
    client,
    monkeypatch,
):
    token, user_id = onboarded_token(client, "planner-links@example.com")
    headers = auth_header(token)
    with TestingSessionLocal() as db:
        subscription = Subscription(
            user_id=user_id,
            merchant_key="twilio",
            name="Twilio",
            service_category="Software",
            amount=20,
            monthly_amount=20,
            annual_amount=240,
            cycle="Monthly",
            cycle_days=30,
            confidence=0.7,
            status="active",
        )
        db.add(subscription)
        db.commit()
        subscription_id = subscription.id

    monkeypatch.setattr("app.services.planner_service._provider_api_key", lambda _provider: None)
    fallback = client.post(
        f"/v1/subscriptions/{subscription_id}/link-help",
        headers=headers,
        json={},
    )
    assert fallback.status_code == 200
    assert fallback.json()["status"] == "fallback"
    assert "OpenAI API key" in fallback.json()["message"]

    monkeypatch.setattr("app.services.planner_service._provider_api_key", lambda _provider: "test-key")
    calls = []

    def fake_post_json(_url, _headers, payload, *args, **kwargs):
        calls.append({"payload": payload, "kwargs": kwargs})
        return {
            "id": "resp_subscription_link",
            "output_text": (
                '{"candidates":['
                '{"title":"Search","url":"https://google.com/search?q=twilio","reason":"Search result","confidence":"high"},'
                '{"title":"Twilio Billing","url":"https://console.twilio.com/billing","reason":"Official Twilio console billing page.","confidence":"high"}'
                '],"message":"Review before saving."}'
            ),
            "usage": {"input_tokens": 120, "output_tokens": 40, "total_tokens": 160},
        }

    monkeypatch.setattr("app.services.planner_service._post_json", fake_post_json)
    response = client.post(
        f"/v1/subscriptions/{subscription_id}/link-help",
        headers=headers,
        json={},
    )
    assert response.status_code == 200
    assert calls[0]["payload"]["tools"] == [{"type": "web_search"}]
    assert calls[0]["kwargs"]["timeout"] == 45
    assert response.json()["status"] == "ai"
    assert [row["url"] for row in response.json()["candidates"]] == [
        "https://console.twilio.com/billing"
    ]
    with TestingSessionLocal() as db:
        usage = db.query(AIUsageLog).filter_by(
            user_id=user_id,
            feature="subscription_link_search",
        ).one()
        assert usage.provider_request_id == "resp_subscription_link"

    def timeout_post_json(*_args, **_kwargs):
        raise PlannerAIError(
            "AI provider timed out after 60 seconds, so local guarded Planner analytics were used."
        )

    monkeypatch.setattr("app.services.planner_service._post_json", timeout_post_json)
    monkeypatch.setattr(
        "app.services.planner_service._subscription_link_search_timeout_seconds",
        lambda: 60,
    )
    timeout_response = client.post(
        f"/v1/subscriptions/{subscription_id}/link-help",
        headers=headers,
        json={},
    )
    assert timeout_response.status_code == 200
    assert timeout_response.json()["status"] == "error"
    assert "took too long" in timeout_response.json()["message"].lower()
