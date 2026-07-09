from __future__ import annotations

from app.core.config import get_settings

# Faithful port of Flask feature_access.py: plan-tier gating for features.
# Billing/plan selection itself ports in Phase 6; the gate is needed from
# Phase 2c because subscription endpoints are plan-gated in Flask.

PLAN_ORDER = {
    "at_cost": 0,
    "basic": 1,
    "premium": 2,
    "__hidden__": 99,
}

PLAN_ALIASES = {
    "free": "at_cost",
    "cost": "at_cost",
    "at-cost": "at_cost",
    "plus": "basic",
    "premier": "premium",
    "planner": "premium",
}

PLAN_DISPLAY_NAMES = {
    "at_cost": "Basic",
    "basic": "Plus",
    "premium": "Premier",
    "__hidden__": "Coming Later",
}

BASE_FEATURE_MIN_PLAN = {
    "dashboard": "at_cost",
    "quick_planning": "at_cost",
    "budgets": "at_cost",
    "transactions": "at_cost",
    "auto_rules": "at_cost",
    "analytics": "at_cost",
    "goals": "at_cost",
    "education_center": "at_cost",
    "income_planning": "basic",
    "cash_projection": "basic",
    "subscriptions": "basic",
    "subscription_analytics": "basic",
    "ai_planner": "premium",
    "ai_coach": "premium",
    "mortgage_loan_planning": "basic",
    "retirement_planning": "premium",
}

VALIDATION_FEATURE_MIN_PLAN = {
    "dashboard": "basic",
    "quick_planning": "basic",
    "budgets": "basic",
    "transactions": "basic",
    "auto_rules": "basic",
    "analytics": "basic",
    "goals": "basic",
    "education_center": "basic",
    "income_planning": "premium",
    "cash_projection": "premium",
    "subscriptions": "premium",
    "subscription_analytics": "premium",
    "mortgage_loan_planning": "premium",
    "ai_planner": "__hidden__",
    "ai_coach": "__hidden__",
    "retirement_planning": "__hidden__",
}


def validation_pricing_mode_enabled() -> bool:
    return get_settings().validation_pricing_mode


def normalize_plan_key(plan_key: str | None) -> str:
    normalized = (plan_key or "").strip().lower()
    normalized = PLAN_ALIASES.get(normalized, normalized)
    return normalized if normalized in PLAN_ORDER else ""


def plan_display_name(plan_key: str | None) -> str:
    normalized = normalize_plan_key(plan_key)
    return PLAN_DISPLAY_NAMES.get(normalized, "Not Selected")


def feature_min_plan(feature_key: str) -> str:
    if validation_pricing_mode_enabled():
        return VALIDATION_FEATURE_MIN_PLAN.get(feature_key, "premium")
    return BASE_FEATURE_MIN_PLAN.get(feature_key, "premium")


def feature_min_plan_label(feature_key: str) -> str:
    return plan_display_name(feature_min_plan(feature_key))


def feature_is_temporarily_hidden(feature_key: str) -> bool:
    return feature_min_plan(feature_key) == "__hidden__"


def user_plan_key(user) -> str:
    plan_key = normalize_plan_key(getattr(user, "selected_plan", None))
    return "" if plan_key == "__hidden__" else plan_key


def user_has_plan_at_least(user, minimum_plan: str) -> bool:
    plan_key = user_plan_key(user)
    minimum_key = normalize_plan_key(minimum_plan)
    if not plan_key or not minimum_key or minimum_key == "__hidden__":
        return False
    return PLAN_ORDER[plan_key] >= PLAN_ORDER[minimum_key]


def user_has_feature(user, feature_key: str) -> bool:
    return user_has_plan_at_least(user, feature_min_plan(feature_key))
