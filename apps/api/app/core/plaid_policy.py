from __future__ import annotations

import re

# Faithful port of the Plaid data-purpose and redaction slice of the Flask
# app's policies.py. The broader SOC2/policy catalog ports in Phase 6; these
# pieces are required now because every Plaid data access asserts a purpose
# and every Plaid error message is redacted before leaving the service layer.

PLAID_DATA_REDACTION = "[REDACTED_PLAID_DATA]"

APPROVED_PLAID_DATA_PURPOSES = {
    "account_sync",
    "dashboard",
    "forecast",
    "monthly_plan",
    "subscriptions",
    "transactions",
    "user_settings",
}

PLAID_DERIVED_FIELD_CLASSES = {
    "token": {
        "access_token",
        "access_token_encrypted",
        "public_token",
        "link_token",
        "processor_token",
    },
    "account": {
        "account",
        "accounts",
        "account_id",
        "account_number",
        "plaid_account_id",
        "account_name",
        "official_name",
        "institution",
        "institution_id",
        "institution_name",
        "item_id",
        "mask",
        "plaid_item_id",
    },
    "balance": {
        "balance",
        "balances",
        "available",
        "available_balance",
        "current",
        "current_balance",
        "limit",
    },
    "transaction": {
        "transaction",
        "transactions",
        "transaction_id",
        "plaid_transaction_id",
        "pending_transaction_id",
        "cursor",
        "next_cursor",
        "sync_cursor",
        "amount",
        "date",
    },
    "merchant": {
        "description",
        "merchant",
        "merchant_name",
        "name",
        "original_description",
        "personal_finance_category",
    },
    "raw_payload": {
        "metadata",
        "payload",
        "raw",
        "request",
        "response",
    },
}

PLAID_SENSITIVE_TEXT_PATTERNS = [
    re.compile(r"\b(?:access|public|link)-(?:sandbox|development|production)-[A-Za-z0-9_-]+\b"),
    re.compile(r"\b(?:plaid[_-]?)?(?:account|transaction|item)[_-]?[A-Za-z0-9_-]{8,}\b", re.IGNORECASE),
]


class PlaidDataPurposeError(RuntimeError):
    pass


def plaid_data_purposes() -> tuple[str, ...]:
    return tuple(sorted(APPROVED_PLAID_DATA_PURPOSES))


def assert_plaid_data_purpose(purpose: str) -> str:
    normalized = (purpose or "").strip().lower()
    if normalized not in APPROVED_PLAID_DATA_PURPOSES:
        raise PlaidDataPurposeError(f"Plaid data purpose '{purpose or 'missing'}' is not approved for ClearPath use.")
    return normalized


def plaid_data_purpose_allowed(purpose: str) -> bool:
    return (purpose or "").strip().lower() in APPROVED_PLAID_DATA_PURPOSES


def classify_plaid_derived_field(field_name: str | None) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", (field_name or "").strip().lower()).strip("_")
    for field_class, field_names in PLAID_DERIVED_FIELD_CLASSES.items():
        if normalized in field_names:
            return field_class
    return "unclassified"


def _redact_plaid_text(value: str) -> str:
    redacted = value
    for pattern in PLAID_SENSITIVE_TEXT_PATTERNS:
        redacted = pattern.sub(PLAID_DATA_REDACTION, redacted)
    return redacted


def redact_plaid_sensitive_data(value, *, field_name: str | None = None):
    if classify_plaid_derived_field(field_name) != "unclassified":
        return PLAID_DATA_REDACTION
    if isinstance(value, dict):
        return {key: redact_plaid_sensitive_data(nested_value, field_name=str(key)) for key, nested_value in value.items()}
    if isinstance(value, list):
        return [redact_plaid_sensitive_data(item, field_name=field_name) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_plaid_sensitive_data(item, field_name=field_name) for item in value)
    if isinstance(value, set):
        return {redact_plaid_sensitive_data(item, field_name=field_name) for item in value}
    if isinstance(value, str):
        return _redact_plaid_text(value)
    return value
