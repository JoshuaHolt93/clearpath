from __future__ import annotations

import json

from app.models import ProductFeedback, User

# Faithful port of the Flask feedback service (feedback_service.py at 92ccdbc).
# The standalone feedback endpoints port with Phase 6 slice 6.4; the builder is
# here already because billing cancellation records cancellation feedback.

FEEDBACK_REASONS = [
    ("feature_expectations", "Feature expectations"),
    ("broken", "Something is not working"),
    ("too_expensive", "Too expensive"),
    ("other", "Other"),
]

FEATURE_EXPECTATION_REASONS = [
    ("not_enough_features", "Not enough features"),
    ("features_not_as_expected", "Features did not work as expected"),
    ("missing_desired_features", "Features I wish existed"),
]

BROKEN_FEATURES = [
    ("dashboard", "Dashboard"),
    ("monthly_plan", "Budgets and monthly plan"),
    ("transactions", "Transactions"),
    ("plaid_sync", "Bank connection or Plaid sync"),
    ("subscriptions", "Subscriptions"),
    ("forecasting", "Forecasting"),
    ("cash_projection", "Cash Balance Projections"),
    ("ai_coach", "AI Planner or AI Coach"),
    ("billing", "Billing"),
    ("onboarding", "Setup or onboarding"),
]

FEEDBACK_TYPES = {"general", "cancellation"}
SOURCES = {"feedback", "settings_billing", "billing_cancel"}


def feedback_form_options() -> dict:
    return {
        "reasons": FEEDBACK_REASONS,
        "feature_expectation_reasons": FEATURE_EXPECTATION_REASONS,
        "broken_features": BROKEN_FEATURES,
    }


def _valid_keys(options: list[tuple[str, str]]) -> set[str]:
    return {key for key, _label in options}


def build_product_feedback(
    user: User,
    form: dict,
    *,
    feedback_type: str = "general",
    source: str = "feedback",
) -> tuple[ProductFeedback | None, list[str]]:
    # Flask reads a form MultiDict; the API passes a plain dict whose
    # broken_features value is already a list.
    feedback_type = feedback_type if feedback_type in FEEDBACK_TYPES else "general"
    source = source if source in SOURCES else "feedback"
    reason = (form.get("reason") or "").strip()
    feature_expectation_reason = (form.get("feature_expectation_reason") or "").strip()
    raw_broken = form.get("broken_features") or []
    broken_features = [value for value in raw_broken if value in _valid_keys(BROKEN_FEATURES)]
    description = (form.get("description") or "").strip()
    notify_when_addressed = bool(form.get("notify_when_addressed"))
    errors = []

    if reason not in _valid_keys(FEEDBACK_REASONS):
        errors.append("Choose the main reason.")
    if reason == "feature_expectations" and feature_expectation_reason not in _valid_keys(FEATURE_EXPECTATION_REASONS):
        errors.append("Choose which feature expectation was not met.")
    if reason != "feature_expectations":
        feature_expectation_reason = None
    if reason == "broken" and not broken_features:
        errors.append("Choose at least one feature that was not working.")
    if reason != "broken":
        broken_features = []

    if errors:
        return None, errors

    entry = ProductFeedback(
        user_id=user.id,
        feedback_type=feedback_type,
        source=source,
        reason=reason,
        feature_expectation_reason=feature_expectation_reason or None,
        broken_features=json.dumps(broken_features),
        notify_when_addressed=notify_when_addressed,
        description=description or None,
        selected_plan=user.selected_plan,
        billing_status=user.billing_status,
        stripe_customer_id=user.stripe_customer_id,
        stripe_subscription_id=user.stripe_subscription_id,
    )
    return entry, []
