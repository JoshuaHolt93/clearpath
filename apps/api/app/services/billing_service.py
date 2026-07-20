from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import UTC, datetime
from urllib.parse import urlsplit

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.card_guards import minimum_tls_12_context
from app.core.config import get_settings
from app.core.feature_access import normalize_plan_key
from app.core.plaid_policy import plaid_data_purpose_allowed
from app.models import StripeWebhookEvent, User, utc_now

try:
    import stripe
except ImportError:  # pragma: no cover - local installs may not configure billing yet
    stripe = None

# Faithful port of Flask billing_service.py at 92ccdbc. The FastAPI settings
# object stands in for app.config; url_for-based fallbacks become WEB_APP_URL
# paths (route-map decision 24 pattern).


class BillingConfigurationError(RuntimeError):
    pass


class BillingCancellationAlreadyScheduled(BillingConfigurationError):
    pass


PLAN_DEFINITIONS = {
    "at_cost": {
        "key": "at_cost",
        "name": "ClearPath Basic",
        "amount_cents": 299,
        "features": [
            "Set budgets to guide your spending",
            "Manage and sort transactions into categories to track progress against your budgets",
            "Setup automated rules to manage recurring transactions",
            "Split transactions into multiple categories",
            "Analyze spending trends and set financial goals",
            "Review your progress in a dashboard to see where you are today",
        ],
    },
    "basic": {
        "key": "basic",
        "name": "ClearPath Plus",
        "amount_cents": 699,
        "features": [
            "Everything in Basic.",
            "Forecast operating cash balance",
            "Plan for income fluctuations and long-term adjustments",
            "Sync your calendar with your cash balance and upcoming expenses to stay locked in",
            "Track and manage your subscriptions",
            "Model mortgage and loan payoff schedules with amortization schedules",
        ],
    },
    "premium": {
        "key": "premium",
        "name": "ClearPath Premier",
        "amount_cents": 1199,
        "features": [
            "Everything in Plus.",
            "Ask AI Coach questions from key planning, budget, transaction, and analytics pages.",
            "Generate AI Planner summaries that help spot cash-flow patterns and next planning moves.",
            "Use AI-guided dashboard focus and Retirement Planning education for bigger long-term decisions.",
        ],
    },
}

PLAN_PRICE_ID_CONFIG_KEYS = {
    "at_cost": "STRIPE_BASIC_PRICE_ID",
    "basic": "STRIPE_PLUS_PRICE_ID",
    "premium": "STRIPE_PREMIUM_PRICE_ID",
}

DEFAULT_STRIPE_PRICING_POLICY = {
    "title": "ClearPath Billing And Pricing Policy",
    "version": "2026.05.16",
    "effective_date": "2026-05-16",
    "owner": "ClearPath Finance Billing Owner",
    "plan_name": "ClearPath Finance Household Plan",
    "amount_cents": 1200,
    "currency": "USD",
    "billing_interval": "month",
    "processor": "Stripe",
    "cancellation_terms": "Cancel anytime in the Stripe Billing Portal. Access continues through the current paid period unless Stripe marks the subscription inactive.",
    "payment_collection": "Payment details are collected and managed only on Stripe-hosted Checkout and Billing Portal pages. ClearPath never collects or stores card numbers, CVC codes, or card expiration fields.",
}


def _pricing_amount_cents(value, default: int) -> int:
    try:
        amount = int(value)
    except (TypeError, ValueError):
        amount = default
    return max(amount, 0)


def stripe_trial_period_days() -> int:
    try:
        days = int(get_settings().stripe_trial_period_days or 0)
    except (TypeError, ValueError):
        days = 30
    return max(days, 0)


def _plan_price_id(key: str, settings) -> str | None:
    if key == "at_cost":
        return settings.stripe_basic_price_id or settings.stripe_at_cost_price_id or settings.stripe_free_price_id
    if key == "basic":
        return settings.stripe_plus_price_id
    return settings.stripe_premium_price_id or settings.stripe_price_id


def plan_options() -> list[dict]:
    settings = get_settings()
    currency = (settings.stripe_plan_currency or "USD").upper()
    interval = (settings.stripe_plan_interval or "month").lower()
    amount_overrides = {
        "at_cost": settings.stripe_basic_plan_amount_cents,
        "basic": settings.stripe_plus_plan_amount_cents,
        "premium": settings.stripe_premium_plan_amount_cents,
    }
    name_overrides = {
        "at_cost": settings.stripe_basic_plan_name,
        "basic": settings.stripe_plus_plan_name,
        "premium": settings.stripe_premium_plan_name,
    }
    options = []
    for key, definition in PLAN_DEFINITIONS.items():
        amount_cents = _pricing_amount_cents(amount_overrides.get(key), definition["amount_cents"])
        if key == "premium" and settings.stripe_plan_amount_cents:
            amount_cents = _pricing_amount_cents(settings.stripe_plan_amount_cents, amount_cents)
        options.append(
            {
                **definition,
                "name": name_overrides.get(key) or definition["name"],
                "amount_cents": amount_cents,
                "currency": currency,
                "billing_interval": interval,
                "price_display": f"${amount_cents / 100:,.2f}",
                "interval_display": interval.replace("_", " ").title(),
                "stripe_price_id": _plan_price_id(key, settings),
                "trial_period_days": stripe_trial_period_days(),
            }
        )
    return options


def free_tier_signups_enabled() -> bool:
    return get_settings().free_tier_signups_enabled


def marketed_plan_options() -> list[dict]:
    options = plan_options()
    marketed_options = []
    for option in options:
        if option["key"] == "basic":
            features = list(option["features"])
            if features and features[0] == "Everything in Basic.":
                features[0] = "Everything in Basic."
            option = {**option, "features": features}
        marketed_options.append(option)
    return marketed_options


def plan_option(plan_key: str | None) -> dict:
    normalized = normalize_plan_key(plan_key)
    options = {option["key"]: option for option in plan_options()}
    if normalized not in options:
        raise BillingConfigurationError("Choose a valid ClearPath plan.")
    return options[normalized]


def stripe_pricing_policy() -> dict:
    settings = get_settings()
    policy = deepcopy(DEFAULT_STRIPE_PRICING_POLICY)
    policy["plan_name"] = settings.stripe_plan_name or policy["plan_name"]
    policy["amount_cents"] = _pricing_amount_cents(settings.stripe_plan_amount_cents, DEFAULT_STRIPE_PRICING_POLICY["amount_cents"])
    policy["currency"] = (settings.stripe_plan_currency or policy["currency"]).upper()
    policy["billing_interval"] = (settings.stripe_plan_interval or policy["billing_interval"]).lower()
    policy["cancellation_terms"] = settings.stripe_cancellation_terms or policy["cancellation_terms"]
    policy["price_display"] = f"${policy['amount_cents'] / 100:,.2f}"
    policy["interval_display"] = policy["billing_interval"].replace("_", " ").title()
    policy["stripe_price_id_configured"] = bool(settings.stripe_price_id)
    return policy


def billing_status() -> dict:
    settings = get_settings()
    options = plan_options()
    return {
        "enabled": settings.billing_enabled,
        "sdk_installed": bool(stripe),
        "has_secret_key": bool(settings.stripe_secret_key),
        "has_price_id": any(option["stripe_price_id"] for option in options),
        "has_at_cost_price_id": bool(next(option for option in options if option["key"] == "at_cost")["stripe_price_id"]),
        "has_basic_price_id": bool(next(option for option in options if option["key"] == "basic")["stripe_price_id"]),
        "has_premium_price_id": bool(next(option for option in options if option["key"] == "premium")["stripe_price_id"]),
        "has_webhook_secret": bool(settings.stripe_webhook_secret),
    }


def _require_billing_ready(*, require_price: bool = True, require_webhook: bool = False, plan_key: str | None = None) -> None:
    assert_billing_uses_no_plaid_data()
    status = billing_status()
    missing = []
    if not status["enabled"]:
        missing.append("BILLING_ENABLED=true")
    if not status["sdk_installed"]:
        missing.append("stripe")
    if not status["has_secret_key"]:
        missing.append("STRIPE_SECRET_KEY")
    if require_price:
        if plan_key:
            price_id = plan_option(plan_key)["stripe_price_id"]
            if not price_id:
                missing.append(PLAN_PRICE_ID_CONFIG_KEYS.get(normalize_plan_key(plan_key), f"STRIPE_{plan_key.upper()}_PRICE_ID"))
        elif not status["has_price_id"]:
            missing.append("STRIPE_PRICE_ID")
    if require_webhook and not status["has_webhook_secret"]:
        missing.append("STRIPE_WEBHOOK_SECRET")
    if missing:
        raise BillingConfigurationError("Stripe billing is not ready. Missing: " + ", ".join(missing) + ".")
    minimum_tls_12_context()
    stripe.api_base = _require_https_url(getattr(stripe, "api_base", None) or "https://api.stripe.com", "Stripe API base")
    stripe.api_key = get_settings().stripe_secret_key


def assert_billing_uses_no_plaid_data() -> bool:
    if plaid_data_purpose_allowed("billing") or plaid_data_purpose_allowed("payments"):
        raise BillingConfigurationError("Billing is not an approved Plaid data purpose.")
    return True


def _web_url(path: str) -> str:
    base = (get_settings().web_app_url or "").rstrip("/")
    return f"{base}{path}" if base else path


def _absolute_config_url(configured: str | None, fallback_path: str) -> str:
    url = configured or _web_url(fallback_path)
    if get_settings().app_env == "production":
        return _require_https_url(url, "Stripe redirect URL")
    return url


def _require_https_url(url: str | None, label: str) -> str:
    parsed = urlsplit(str(url or ""))
    if parsed.scheme != "https":
        raise BillingConfigurationError(f"{label} must use HTTPS.")
    return str(url)


def _normalize_promotion_code(value: str | None) -> str:
    code = (value or "").strip()
    if not code:
        return ""
    if len(code) > 80:
        raise BillingConfigurationError("Promo code is too long.")
    if any(character in code for character in "\r\n\t"):
        raise BillingConfigurationError("Promo code contains invalid characters.")
    return code


def _stripe_promotion_code_id_from_code(code: str) -> str:
    if not hasattr(stripe, "PromotionCode"):
        raise BillingConfigurationError("Promo code support is unavailable in the Stripe SDK.")
    response = stripe.PromotionCode.list(code=code, active=True, limit=1)
    promotion_codes = _stripe_value(response, "data", []) or []
    if not promotion_codes:
        raise BillingConfigurationError("Promo code was not found or is no longer active.")
    promotion_code_id = _stripe_value(promotion_codes[0], "id")
    if not promotion_code_id:
        raise BillingConfigurationError("Promo code could not be applied.")
    return promotion_code_id


def create_checkout_session(
    db: Session,
    user: User,
    plan_key: str | None = None,
    *,
    success_url: str | None = None,
    cancel_url: str | None = None,
    promotion_code: str | None = None,
) -> str:
    selected_plan = plan_option(plan_key or user.selected_plan or "premium")
    _require_billing_ready(plan_key=selected_plan["key"])
    normalized_promotion_code = _normalize_promotion_code(promotion_code)
    settings = get_settings()
    success_url = success_url or _absolute_config_url(settings.stripe_success_url, "/settings")
    cancel_url = cancel_url or _absolute_config_url(settings.stripe_cancel_url, "/settings")
    if settings.app_env == "production":
        success_url = _require_https_url(success_url, "Stripe Checkout success URL")
        cancel_url = _require_https_url(cancel_url, "Stripe Checkout cancel URL")
    kwargs = {
        "mode": "subscription",
        "line_items": [{"price": selected_plan["stripe_price_id"], "quantity": 1}],
        "success_url": success_url,
        "cancel_url": cancel_url,
        "client_reference_id": str(user.id),
        "metadata": {"user_id": str(user.id), "selected_plan": selected_plan["key"]},
    }
    if normalized_promotion_code:
        kwargs["discounts"] = [{"promotion_code": _stripe_promotion_code_id_from_code(normalized_promotion_code)}]
    else:
        kwargs["allow_promotion_codes"] = True
    trial_days = stripe_trial_period_days()
    if trial_days > 0:
        kwargs["subscription_data"] = {"trial_period_days": trial_days}
    if user.stripe_customer_id:
        kwargs["customer"] = user.stripe_customer_id
    else:
        kwargs["customer_email"] = user.email

    session = stripe.checkout.Session.create(**kwargs)
    checkout_url = _require_https_url(_stripe_value(session, "url"), "Stripe Checkout session URL")
    customer_id = _stripe_value(session, "customer")
    subscription_id = _stripe_value(session, "subscription")
    if customer_id and not user.stripe_customer_id:
        user.stripe_customer_id = customer_id
    if subscription_id:
        user.stripe_subscription_id = subscription_id
    if customer_id or subscription_id:
        user.selected_plan = selected_plan["key"]
        user.billing_price_id = selected_plan["stripe_price_id"]
        db.commit()
    return checkout_url


def create_billing_portal_session(user: User) -> str:
    _require_billing_ready(require_price=False)
    if not user.stripe_customer_id:
        raise BillingConfigurationError("No Stripe customer exists for this account yet.")
    session = stripe.billing_portal.Session.create(
        customer=user.stripe_customer_id,
        return_url=_absolute_config_url(get_settings().stripe_portal_return_url, "/settings"),
    )
    return _require_https_url(_stripe_value(session, "url"), "Stripe Billing Portal session URL")


def create_subscription_cancellation_portal_session(db: Session, user: User) -> str:
    _require_billing_ready(require_price=False)
    if not user.stripe_customer_id:
        raise BillingConfigurationError("No Stripe customer exists for this account yet.")
    if not user.stripe_subscription_id:
        return create_billing_portal_session(user)
    return_url = _absolute_config_url(get_settings().stripe_portal_return_url, "/settings")
    try:
        session = stripe.billing_portal.Session.create(
            customer=user.stripe_customer_id,
            return_url=return_url,
            flow_data={
                "type": "subscription_cancel",
                "subscription_cancel": {"subscription": user.stripe_subscription_id},
                "after_completion": {
                    "type": "redirect",
                    "redirect": {"return_url": return_url},
                },
            },
        )
    except Exception as exc:
        if _stripe_subscription_cancel_already_scheduled(exc):
            user.billing_status = "canceling"
            db.commit()
            raise BillingCancellationAlreadyScheduled(
                "Your Stripe subscription is already scheduled to cancel at the end of the current billing period."
            ) from exc
        raise
    return _require_https_url(_stripe_value(session, "url"), "Stripe cancellation session URL")


def _stripe_subscription_cancel_already_scheduled(exc: Exception) -> bool:
    message = str(getattr(exc, "user_message", None) or getattr(exc, "message", None) or exc).lower()
    return "already set to be canceled at period end" in message


def construct_stripe_event(payload: bytes, signature: str | None):
    _require_billing_ready(require_price=False, require_webhook=True)
    return stripe.Webhook.construct_event(payload, signature or "", get_settings().stripe_webhook_secret)


def handle_stripe_event(db: Session, event) -> bool:
    event_record = _prepare_stripe_webhook_event(db, event)
    if event_record.status in {"processed", "skipped"}:
        return False

    event_record.status = "processing"
    event_record.error_message = None
    event_record.processed_at = None
    stripe_event_id = event_record.stripe_event_id
    db.add(event_record)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        event_record = db.query(StripeWebhookEvent).filter_by(stripe_event_id=stripe_event_id).first()
        if not event_record:
            raise
        if event_record.status in {"processed", "skipped"}:
            return False
        event_record.status = "processing"
        event_record.error_message = None
        event_record.processed_at = None
        db.add(event_record)
        db.commit()

    event_type = _stripe_value(event, "type")
    data_object = _stripe_value(_stripe_value(event, "data", {}) or {}, "object", {}) or {}
    try:
        result = False
        status = "skipped"
        if event_type == "checkout.session.completed":
            result = _handle_checkout_completed(db, data_object)
            status = "processed" if result else "skipped"
        elif event_type in {"customer.subscription.created", "customer.subscription.updated", "customer.subscription.deleted"}:
            result = _handle_subscription_event(
                db,
                data_object,
                deleted=event_type == "customer.subscription.deleted",
                event_created=event_record.event_created,
                current_event_id=event_record.stripe_event_id,
            )
            status = "processed" if result else "skipped"
        event_record.status = status
        event_record.processed_at = utc_now()
        db.add(event_record)
        db.commit()
        return result
    except Exception as exc:
        db.rollback()
        failed_event = db.query(StripeWebhookEvent).filter_by(stripe_event_id=event_record.stripe_event_id).first()
        if failed_event:
            failed_event.status = "failed"
            failed_event.error_message = _truncate_error_message(str(exc))
            failed_event.processed_at = utc_now()
            db.add(failed_event)
            db.commit()
        raise


def _prepare_stripe_webhook_event(db: Session, event) -> StripeWebhookEvent:
    full_event_json = _stripe_full_event_json(event)
    payload_hash = hashlib.sha256(full_event_json.encode("utf-8")).hexdigest()
    stripe_event_id = _stripe_value(event, "id") or f"generated:{payload_hash}"
    existing = db.query(StripeWebhookEvent).filter_by(stripe_event_id=stripe_event_id).first()
    if existing and existing.status in {"processed", "skipped"}:
        return existing
    event_record = existing or StripeWebhookEvent(stripe_event_id=stripe_event_id)
    event_record.event_type = _stripe_value(event, "type") or "unknown"
    event_record.event_created = _coerce_stripe_timestamp(_stripe_value(event, "created"))
    event_record.raw_event_json = _stripe_minimized_event_json(event, payload_hash)
    event_record.payload_hash = payload_hash
    return event_record


def _stripe_full_event_json(event) -> str:
    if hasattr(event, "to_dict_recursive"):
        event = event.to_dict_recursive()
    elif hasattr(event, "to_dict"):
        event = event.to_dict()
    return json.dumps(event, sort_keys=True, default=str)


def _stripe_minimized_event_json(event, payload_hash: str) -> str:
    event_type = _stripe_value(event, "type") or "unknown"
    data_object = _stripe_value(_stripe_value(event, "data", {}) or {}, "object", {}) or {}
    subscription_id = _stripe_value(data_object, "id")
    if event_type == "checkout.session.completed":
        subscription_id = _stripe_value(data_object, "subscription")
    ledger_event = {
        "event_id": _stripe_value(event, "id"),
        "event_type": event_type,
        "event_created": _stripe_value(event, "created"),
        "customer_id": _stripe_value(data_object, "customer"),
        "subscription_id": subscription_id,
        "subscription_status": _stripe_value(data_object, "status"),
        "current_period_end": _stripe_value(data_object, "current_period_end"),
        "payload_hash": payload_hash,
    }
    return json.dumps(ledger_event, sort_keys=True, default=str)


def _truncate_error_message(message: str, limit: int = 1000) -> str:
    return (message or "")[:limit]


def _handle_checkout_completed(db: Session, session) -> bool:
    user_id = _stripe_value(session, "client_reference_id") or _stripe_value(_stripe_value(session, "metadata", {}) or {}, "user_id")
    if not user_id:
        return False
    user = db.query(User).filter_by(id=int(user_id)).first()
    if not user:
        return False
    customer_id = _stripe_value(session, "customer")
    subscription_id = _stripe_value(session, "subscription")
    if customer_id:
        user.stripe_customer_id = customer_id
    if subscription_id:
        user.stripe_subscription_id = subscription_id
    user.billing_status = "checkout_complete"
    selected_plan = _stripe_value(_stripe_value(session, "metadata", {}) or {}, "selected_plan")
    if selected_plan in PLAN_DEFINITIONS:
        user.selected_plan = selected_plan
        user.billing_price_id = plan_option(selected_plan)["stripe_price_id"] or user.billing_price_id
    else:
        user.billing_price_id = get_settings().stripe_price_id or user.billing_price_id
    return True


def _handle_subscription_event(
    db: Session,
    subscription,
    *,
    deleted: bool = False,
    event_created: datetime | None = None,
    current_event_id: str | None = None,
) -> bool:
    customer_id = _stripe_value(subscription, "customer")
    if not customer_id:
        return False
    user = db.query(User).filter_by(stripe_customer_id=customer_id).first()
    if not user:
        return False
    subscription_id = _stripe_value(subscription, "id") or user.stripe_subscription_id
    period_end = _coerce_stripe_timestamp(_stripe_value(subscription, "current_period_end"))
    if _stripe_subscription_event_is_stale(
        db,
        user,
        customer_id=customer_id,
        subscription_id=subscription_id,
        event_created=event_created,
        period_end=period_end,
        current_event_id=current_event_id,
    ):
        return False
    user.stripe_subscription_id = subscription_id
    cancel_at_period_end = bool(_stripe_value(subscription, "cancel_at_period_end"))
    if deleted:
        user.billing_status = "canceled"
    elif cancel_at_period_end:
        user.billing_status = "canceling"
    else:
        user.billing_status = _stripe_value(subscription, "status") or "unknown"
    price_id = _price_id_from_subscription(subscription)
    user.billing_price_id = price_id or user.billing_price_id
    selected_plan = _plan_key_from_price_id(price_id)
    if selected_plan:
        user.selected_plan = selected_plan
    if period_end:
        user.stripe_current_period_end = period_end
    return True


def _stripe_subscription_event_is_stale(
    db: Session,
    user: User,
    *,
    customer_id: str,
    subscription_id: str | None,
    event_created: datetime | None,
    period_end: datetime | None,
    current_event_id: str | None,
) -> bool:
    if period_end and user.stripe_current_period_end and period_end < user.stripe_current_period_end:
        return True
    if not event_created:
        return False
    processed_events = (
        db.query(StripeWebhookEvent)
        .filter(StripeWebhookEvent.status == "processed")
        .filter(StripeWebhookEvent.stripe_event_id != current_event_id)
        .filter(StripeWebhookEvent.event_created.isnot(None))
        .filter(StripeWebhookEvent.event_created > event_created)
        .order_by(StripeWebhookEvent.event_created.desc())
        .all()
    )
    for processed_event in processed_events:
        if processed_event.event_type not in {
            "customer.subscription.created",
            "customer.subscription.updated",
            "customer.subscription.deleted",
        }:
            continue
        try:
            raw_event = json.loads(processed_event.raw_event_json or "{}")
        except json.JSONDecodeError:
            continue
        if not isinstance(raw_event, dict):
            continue
        raw_object = ((raw_event.get("data") or {}).get("object") or {}) if "data" in raw_event else {}
        processed_customer_id = raw_event.get("customer_id") or raw_object.get("customer")
        processed_subscription_id = raw_event.get("subscription_id") or raw_object.get("id")
        if processed_customer_id != customer_id:
            continue
        if subscription_id and processed_subscription_id not in {None, subscription_id}:
            continue
        return True
    return False


def _price_id_from_subscription(subscription) -> str | None:
    items = _stripe_value(_stripe_value(subscription, "items", {}) or {}, "data", []) or []
    if not items:
        return None
    price = _stripe_value(items[0], "price", {}) or {}
    return _stripe_value(price, "id")


def _plan_key_from_price_id(price_id: str | None) -> str | None:
    if not price_id:
        return None
    for option in plan_options():
        if option["stripe_price_id"] == price_id:
            return option["key"]
    return None


def _stripe_value(obj, key: str, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _coerce_stripe_timestamp(value) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    try:
        return datetime.fromtimestamp(int(value), tz=UTC).replace(tzinfo=None)
    except (TypeError, ValueError, OSError, OverflowError):
        return None
