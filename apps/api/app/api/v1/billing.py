from __future__ import annotations

import json
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core.card_guards import contains_direct_card_submission, sanitize_card_data, sanitize_direct_card_submission
from app.core.config import get_settings
from app.core.database import get_db
from app.core.feature_access import normalize_plan_key
from app.dependencies import Principal, require_primary_account_holder
from app.schemas.billing import (
    BillingCancellationSessionCreateRequest,
    BillingCancellationSessionResponse,
    BillingCheckoutSessionCreateRequest,
    BillingCheckoutSessionResponse,
    BillingPlanResponse,
    BillingPlanSelectionRequest,
    BillingPlanSelectionResponse,
    BillingPlansResponse,
    BillingPortalSessionCreateRequest,
    BillingPortalSessionResponse,
    StripeWebhookAckResponse,
    UpgradeTutorialItemResponse,
    UserBillingStateResponse,
)
from app.services.billing_service import (
    BillingCancellationAlreadyScheduled,
    BillingConfigurationError,
    billing_status,
    construct_stripe_event,
    create_billing_portal_session,
    create_checkout_session,
    create_subscription_cancellation_portal_session,
    free_tier_signups_enabled,
    handle_stripe_event,
    marketed_plan_options,
    plan_option,
    stripe_pricing_policy,
)
from app.services.feedback_service import build_product_feedback
from app.services.transaction_service import is_onboarding_complete

logger = logging.getLogger(__name__)

router = APIRouter(tags=["billing"])

CLIENT_PRICING_KEYS = {"price", "price_id", "amount", "currency", "unit_amount", "unit_amount_decimal"}

# Flask PLAN_UPGRADE_TUTORIALS with url_for actions mapped to stable client
# targets (route-map decision 23 pattern).
UPGRADE_TUTORIAL_ACTIONS = {
    "Budgets": ("monthly_plan_budgets", "Open Budgets"),
    "Transaction Review": ("transactions", "Review Transactions"),
    "Analytics And Goals": ("analytics", "Open Analytics"),
    "Future Income Planning": ("monthly_plan_baseline", "Plan Future Income"),
    "Cash Balance Projections": ("cash_projections", "Open Cash Projections"),
    "Subscriptions": ("subscriptions", "Review Subscriptions"),
    "Mortgage/Loan Planning": ("loan_plans", "Open Loan Planning"),
    "AI Planner": ("planner", "Open AI Planner"),
    "Ask AI Coach": ("dashboard", "Go To Today"),
    "AI Dashboard Focus": ("dashboard", "Go To Today"),
    "Retirement Planning": ("retirement_plan", "Open Retirement Planning"),
}

PLAN_UPGRADE_TUTORIALS = {
    "basic": [
        {"title": "Future Income Planning", "body": "Your setup income is already the baseline. Add raises, job changes, bonuses, or side income before they start."},
        {"title": "Cash Balance Projections", "body": "See projected daily cash balances from marked recurring transactions, one-time expenses, and selected operating accounts."},
        {"title": "Subscriptions", "body": "Manage Consumer Subscription charges from your transaction history and open saved management portals."},
        {"title": "Mortgage/Loan Planning", "body": "Model loan payoff scenarios and review amortization schedules for mortgages and other tracked loans."},
    ],
    "premium": [
        {"title": "AI Planner", "body": "Generate guarded coaching from summarized financial context without sending account names by default."},
        {"title": "Ask AI Coach", "body": "Ask page-aware questions from key workspaces while ClearPath keeps the response educational and inside guardrails."},
        {"title": "AI Dashboard Focus", "body": "Let the latest AI Planner guidance surface the dashboard cards and long-range questions most relevant to your current picture."},
        {"title": "Retirement Planning", "body": "Use an educational retirement workspace for account types, long-term expense assumptions, healthcare, taxes, location, and lifestyle planning."},
    ],
}

VALIDATION_PLAN_UPGRADE_TUTORIALS = {
    "basic": [
        {"title": "Budgets", "body": "Set category budgets and compare spending progress against transactions."},
        {"title": "Transaction Review", "body": "Categorize transactions, split purchases across categories, and train rules for cleanup."},
        {"title": "Analytics And Goals", "body": "Review spending trends, cash-flow history, and progress toward savings or payoff goals."},
    ],
    "premium": [
        {"title": "Future Income Planning", "body": "Plan future raises, job changes, bonuses, or side income before they start."},
        {"title": "Cash Balance Projections", "body": "See projected daily cash balances from marked recurring transactions, one-time expenses, and selected operating accounts."},
        {"title": "Subscriptions", "body": "Manage Consumer Subscription charges from your transaction history and open saved management portals."},
        {"title": "Mortgage/Loan Planning", "body": "Model loan payoff scenarios and review amortization schedules for mortgages and other tracked loans."},
    ],
}


def _upgrade_tutorial_items(plan_key: str | None) -> list[UpgradeTutorialItemResponse]:
    tutorial_source = VALIDATION_PLAN_UPGRADE_TUTORIALS if get_settings().validation_pricing_mode else PLAN_UPGRADE_TUTORIALS
    if plan_key == "basic":
        items = tutorial_source["basic"]
    elif plan_key == "premium":
        items = tutorial_source["basic"] + tutorial_source["premium"]
    else:
        items = []
    decorated = []
    for item in items:
        action = UPGRADE_TUTORIAL_ACTIONS.get(item["title"])
        decorated.append(
            UpgradeTutorialItemResponse(
                title=item["title"],
                body=item["body"],
                target=action[0] if action else None,
                cta=action[1] if action else None,
            )
        )
    return decorated


def _payload_contains_client_pricing(payload) -> bool:
    if isinstance(payload, dict):
        for key, value in payload.items():
            if str(key).strip().lower() in CLIENT_PRICING_KEYS:
                return True
            if _payload_contains_client_pricing(value):
                return True
    elif isinstance(payload, (list, tuple)):
        return any(_payload_contains_client_pricing(item) for item in payload)
    return False


async def _guard_billing_payload(request: Request) -> None:
    # Flask rejects both direct card data and client-supplied pricing fields
    # before any billing mutation runs.
    raw = await request.body()
    if not raw:
        return
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return
    if contains_direct_card_submission(payload):
        logger.warning(
            "Rejected direct payment card data submitted to billing endpoint. endpoint=%s payload=%s",
            request.url.path,
            sanitize_direct_card_submission(payload),
        )
        raise HTTPException(status_code=400, detail="Payment card details must be entered only on Stripe-hosted billing pages.")
    if _payload_contains_client_pricing(payload):
        logger.warning(
            "Rejected client-supplied billing pricing fields. endpoint=%s payload=%s",
            request.url.path,
            sanitize_card_data(payload),
        )
        raise HTTPException(status_code=400, detail="Billing price, amount, and currency are configured by ClearPath and Stripe. Do not submit pricing fields.")


def _safe_web_path(value: str | None) -> str | None:
    path = (value or "").strip()
    if not path or not path.startswith("/") or path.startswith("//"):
        return None
    return path


def _web_url_for_path(path: str | None, fallback_path: str) -> str:
    base = (get_settings().web_app_url or "").rstrip("/")
    resolved = _safe_web_path(path) or fallback_path
    return f"{base}{resolved}" if base else resolved


def _user_billing_state(user) -> UserBillingStateResponse:
    return UserBillingStateResponse(
        selected_plan=user.selected_plan,
        billing_status=user.billing_status,
        has_stripe_customer=bool(user.stripe_customer_id),
        has_stripe_subscription=bool(user.stripe_subscription_id),
        stripe_current_period_end=user.stripe_current_period_end,
        billing_price_id=user.billing_price_id,
        config=billing_status(),
    )


def _plan_response(option: dict) -> BillingPlanResponse:
    return BillingPlanResponse(
        key=option["key"],
        name=option["name"],
        amount_cents=option["amount_cents"],
        currency=option["currency"],
        billing_interval=option["billing_interval"],
        price_display=option["price_display"],
        interval_display=option["interval_display"],
        trial_period_days=option["trial_period_days"],
        features=option["features"],
        price_configured=bool(option["stripe_price_id"]),
    )


@router.get("/billing/plans", response_model=BillingPlansResponse)
def get_billing_plans() -> BillingPlansResponse:
    return BillingPlansResponse(
        plans=[_plan_response(option) for option in marketed_plan_options()],
        billing_status=billing_status(),
        pricing_policy=stripe_pricing_policy(),
        free_tier_signups_enabled=free_tier_signups_enabled(),
        upgrade_tutorials={
            "basic": _upgrade_tutorial_items("basic"),
            "premium": _upgrade_tutorial_items("premium"),
        },
    )


@router.get("/billing/status", response_model=UserBillingStateResponse)
def get_billing_state(
    principal: Annotated[Principal, Depends(require_primary_account_holder)],
) -> UserBillingStateResponse:
    return _user_billing_state(principal.user)


@router.post("/billing/plan-selection", response_model=BillingPlanSelectionResponse)
async def select_plan(
    request: Request,
    payload: BillingPlanSelectionRequest,
    principal: Annotated[Principal, Depends(require_primary_account_holder)],
    db: Annotated[Session, Depends(get_db)],
) -> BillingPlanSelectionResponse:
    await _guard_billing_payload(request)
    user = principal.user
    try:
        selected_plan = plan_option((payload.plan or "").strip().lower())
    except BillingConfigurationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    previous_plan_key = normalize_plan_key(user.selected_plan)
    setup_complete = is_onboarding_complete(user)
    if previous_plan_key == selected_plan["key"] and setup_complete:
        return BillingPlanSelectionResponse(
            selected_plan=selected_plan["key"],
            plan_name=selected_plan["name"],
            already_selected=True,
            billing=_user_billing_state(user),
            upgrade_tutorial_items=[],
        )

    checkout_url = None
    if billing_status()["enabled"]:
        try:
            checkout_url = create_checkout_session(
                db,
                user,
                selected_plan["key"],
                success_url=_web_url_for_path(payload.success_path, "/onboarding"),
                cancel_url=_web_url_for_path(payload.cancel_path, "/onboarding"),
                promotion_code=payload.promotion_code,
            )
        except BillingConfigurationError as exc:
            raise HTTPException(status_code=422, detail=f"Stripe Checkout could not start: {exc}") from exc
        except Exception as exc:
            logger.exception("Stripe Checkout session creation failed for selected plan.")
            message = str(exc)
            if "price specified is inactive" in message.lower():
                detail = (
                    f"Stripe Checkout could not start because the billing price for {selected_plan['name']} is inactive. "
                    "Contact support to finish this plan change."
                )
            else:
                detail = f"Stripe Checkout could not start: {exc}"
            raise HTTPException(status_code=502, detail=detail) from exc

    # Flask _save_selected_plan.
    user.selected_plan = selected_plan["key"]
    user.billing_price_id = selected_plan["stripe_price_id"] or user.billing_price_id
    if user.billing_status == "free":
        user.billing_status = "plan_selected"
    db.commit()

    return BillingPlanSelectionResponse(
        selected_plan=selected_plan["key"],
        plan_name=selected_plan["name"],
        already_selected=False,
        checkout_url=checkout_url,
        billing=_user_billing_state(user),
        upgrade_tutorial_items=_upgrade_tutorial_items(selected_plan["key"]) if setup_complete else [],
    )


@router.post("/billing/checkout-sessions", response_model=BillingCheckoutSessionResponse)
async def create_checkout(
    request: Request,
    payload: BillingCheckoutSessionCreateRequest,
    principal: Annotated[Principal, Depends(require_primary_account_holder)],
    db: Annotated[Session, Depends(get_db)],
) -> BillingCheckoutSessionResponse:
    await _guard_billing_payload(request)
    user = principal.user
    plan_key = payload.plan or user.selected_plan
    success_url = _web_url_for_path(payload.success_path, "/settings") if payload.success_path else None
    cancel_url = _web_url_for_path(payload.cancel_path, "/settings") if payload.cancel_path else None
    try:
        checkout_url = create_checkout_session(
            db, user, plan_key, success_url=success_url, cancel_url=cancel_url, promotion_code=payload.promotion_code
        )
    except BillingConfigurationError as exc:
        raise HTTPException(status_code=422, detail=f"Stripe Checkout could not start: {exc}") from exc
    except Exception as exc:
        logger.exception("Stripe Checkout session creation failed.")
        raise HTTPException(status_code=502, detail=f"Stripe Checkout could not start: {exc}") from exc
    return BillingCheckoutSessionResponse(checkout_url=checkout_url)


@router.post("/billing/portal-sessions", response_model=BillingPortalSessionResponse)
async def create_portal(
    request: Request,
    payload: BillingPortalSessionCreateRequest,
    principal: Annotated[Principal, Depends(require_primary_account_holder)],
) -> BillingPortalSessionResponse:
    await _guard_billing_payload(request)
    try:
        portal_url = create_billing_portal_session(principal.user)
    except BillingConfigurationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return BillingPortalSessionResponse(portal_url=portal_url)


@router.post("/billing/cancellation-sessions", response_model=BillingCancellationSessionResponse)
async def create_cancellation(
    request: Request,
    payload: BillingCancellationSessionCreateRequest,
    principal: Annotated[Principal, Depends(require_primary_account_holder)],
    db: Annotated[Session, Depends(get_db)],
) -> BillingCancellationSessionResponse:
    await _guard_billing_payload(request)
    user = principal.user
    feedback_form = {
        "reason": payload.reason or "other",
        "feature_expectation_reason": payload.feature_expectation_reason,
        "broken_features": payload.broken_features,
        "description": payload.description,
        "notify_when_addressed": payload.notify_when_addressed,
    }
    entry, errors = build_product_feedback(user, feedback_form, feedback_type="cancellation", source="billing_cancel")
    if errors:
        raise HTTPException(status_code=422, detail=" ".join(errors))
    db.add(entry)
    db.commit()
    if not user.stripe_customer_id:
        return BillingCancellationSessionResponse(
            feedback_saved=True,
            portal_url=None,
            message="Your feedback was saved, but no Stripe customer is connected to this account yet. Contact support if you still need billing help.",
        )
    try:
        portal_url = create_subscription_cancellation_portal_session(db, user)
    except BillingCancellationAlreadyScheduled as exc:
        return BillingCancellationSessionResponse(feedback_saved=True, portal_url=None, message=str(exc))
    except BillingConfigurationError as exc:
        raise HTTPException(status_code=422, detail=f"Your feedback was saved, but Stripe Billing Portal could not open: {exc}") from exc
    return BillingCancellationSessionResponse(feedback_saved=True, portal_url=portal_url)


@router.post("/webhooks/stripe", response_model=StripeWebhookAckResponse)
async def stripe_webhook(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
):
    payload = await request.body()
    try:
        decoded = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        decoded = None
    if decoded is not None and contains_direct_card_submission(decoded):
        return Response("Payment card details must be entered only on Stripe-hosted billing pages.", status_code=400)
    signature = request.headers.get("Stripe-Signature")
    try:
        event = construct_stripe_event(payload, signature)
    except Exception as exc:
        logger.warning(
            "Rejected Stripe webhook with invalid signature: %s metadata=%s",
            exc.__class__.__name__,
            sanitize_card_data(
                {
                    "content_type": request.headers.get("content-type"),
                    "content_length": request.headers.get("content-length"),
                    "signature_present": bool(signature),
                }
            ),
        )
        return Response("Invalid Stripe signature.", status_code=400)

    handle_stripe_event(db, event)
    return StripeWebhookAckResponse(received=True)
