from __future__ import annotations

# Faithful port of the Flask feedback options (feedback_service.py at 92ccdbc).
# build_product_feedback and the feedback endpoints port with Phase 6 slice 6.4.

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
