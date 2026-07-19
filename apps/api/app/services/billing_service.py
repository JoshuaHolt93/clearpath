from __future__ import annotations

from importlib.util import find_spec

from app.core.config import get_settings

# Phase 6 slice 6.2 ports billing_status() so the settings aggregate matches
# Flask (billing_service.py at 92ccdbc). Plan options, Stripe checkout/portal/
# cancel, and the webhook handler port with slice 6.3.


def _stripe_sdk_installed() -> bool:
    return find_spec("stripe") is not None


def billing_status() -> dict:
    settings = get_settings()
    at_cost_price_id = settings.stripe_basic_price_id or settings.stripe_at_cost_price_id or settings.stripe_free_price_id
    basic_price_id = settings.stripe_plus_price_id
    premium_price_id = settings.stripe_premium_price_id or settings.stripe_price_id
    return {
        "enabled": settings.billing_enabled,
        "sdk_installed": _stripe_sdk_installed(),
        "has_secret_key": bool(settings.stripe_secret_key),
        "has_price_id": bool(at_cost_price_id or basic_price_id or premium_price_id),
        "has_at_cost_price_id": bool(at_cost_price_id),
        "has_basic_price_id": bool(basic_price_id),
        "has_premium_price_id": bool(premium_price_id),
        "has_webhook_secret": bool(settings.stripe_webhook_secret),
    }
