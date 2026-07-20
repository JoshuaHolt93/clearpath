from __future__ import annotations

import re
import ssl
from collections.abc import Mapping

# Faithful port of the Flask payment-card guards (security.py at 92ccdbc):
# billing endpoints must reject and redact any direct card data so payment
# details only ever touch Stripe-hosted pages.

CARD_DATA_REDACTION = "[REDACTED_CARD_DATA]"
CARD_PARENT_KEYS = {"card", "paymentcard", "paymentmethod", "paymentdetails", "carddetails"}
CARD_NUMBER_CHILD_KEYS = {"number", "cardnumber", "accountnumber", "primaryaccountnumber"}
SENSITIVE_CARD_KEYS = {
    "cardnumber",
    "fullcardnumber",
    "primaryaccountnumber",
    "pan",
    "cvv",
    "cvc",
    "cvv2",
    "cvc2",
    "cid",
    "securitycode",
    "cardsecuritycode",
    "verificationcode",
    "verificationvalue",
    "cardverificationcode",
    "cardverificationvalue",
}
DIRECT_CARD_EXPIRATION_KEYS = {
    "exp",
    "expdate",
    "expmonth",
    "expyear",
    "expiry",
    "expirydate",
    "expirymonth",
    "expiryyear",
    "expiration",
    "expirationdate",
    "expirationmonth",
    "expirationyear",
    "cardexp",
    "cardexpdate",
    "cardexpmonth",
    "cardexpyear",
    "cardexpiry",
    "cardexpirydate",
    "cardexpirymonth",
    "cardexpiryyear",
    "cardexpiration",
    "cardexpirationdate",
    "cardexpirationmonth",
    "cardexpirationyear",
}
PAN_VALUE_PATTERN = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")
CARD_SECURITY_CODE_VALUE_PATTERN = re.compile(
    r"\b(?:cvv|cvc|cid|security[\s_-]*code|card[\s_-]*verification[\s_-]*(?:code|value))\b[\s:=#-]{0,8}\d{3,4}\b",
    re.IGNORECASE,
)


def _normalized_key(key) -> str:
    return re.sub(r"[^a-z0-9]", "", str(key or "").lower())


def is_sensitive_card_key(key, *, parent_key=None) -> bool:
    normalized = _normalized_key(key)
    parent = _normalized_key(parent_key)
    if normalized in SENSITIVE_CARD_KEYS:
        return True
    if parent in CARD_PARENT_KEYS and normalized in CARD_NUMBER_CHILD_KEYS:
        return True
    return False


def is_direct_card_submission_key(key, *, parent_key=None) -> bool:
    normalized = _normalized_key(key)
    parent = _normalized_key(parent_key)
    if is_sensitive_card_key(key, parent_key=parent_key):
        return True
    if normalized in DIRECT_CARD_EXPIRATION_KEYS:
        return True
    if parent in CARD_PARENT_KEYS and normalized in DIRECT_CARD_EXPIRATION_KEYS:
        return True
    return False


def _redact_card_numbers(text: str) -> str:
    redacted = PAN_VALUE_PATTERN.sub(CARD_DATA_REDACTION, text)
    return CARD_SECURITY_CODE_VALUE_PATTERN.sub(CARD_DATA_REDACTION, redacted)


def sanitize_card_data(value, *, parent_key=None):
    """Return a copy of value with raw PAN/CVV-style payment card data redacted."""
    if isinstance(value, Mapping):
        sanitized = {}
        for key, nested_value in value.items():
            if is_sensitive_card_key(key, parent_key=parent_key):
                sanitized[key] = CARD_DATA_REDACTION
            else:
                sanitized[key] = sanitize_card_data(nested_value, parent_key=key)
        return sanitized
    if isinstance(value, list):
        return [sanitize_card_data(item, parent_key=parent_key) for item in value]
    if isinstance(value, tuple):
        return tuple(sanitize_card_data(item, parent_key=parent_key) for item in value)
    if isinstance(value, set):
        return {sanitize_card_data(item, parent_key=parent_key) for item in value}
    if isinstance(value, str):
        return _redact_card_numbers(value)
    return value


def sanitize_direct_card_submission(value, *, parent_key=None):
    """Redact card-submission fields, including expiration values, for billing-surface evidence logs."""
    if isinstance(value, Mapping):
        sanitized = {}
        for key, nested_value in value.items():
            if is_direct_card_submission_key(key, parent_key=parent_key):
                sanitized[key] = CARD_DATA_REDACTION
            else:
                sanitized[key] = sanitize_direct_card_submission(nested_value, parent_key=key)
        return sanitized
    if isinstance(value, list):
        return [sanitize_direct_card_submission(item, parent_key=parent_key) for item in value]
    if isinstance(value, tuple):
        return tuple(sanitize_direct_card_submission(item, parent_key=parent_key) for item in value)
    if isinstance(value, set):
        return {sanitize_direct_card_submission(item, parent_key=parent_key) for item in value}
    if isinstance(value, str):
        return _redact_card_numbers(value)
    return value


def contains_direct_card_submission(value, *, parent_key=None) -> bool:
    if isinstance(value, Mapping):
        for key, nested_value in value.items():
            if is_direct_card_submission_key(key, parent_key=parent_key):
                return True
            if contains_direct_card_submission(nested_value, parent_key=key):
                return True
        return False
    if isinstance(value, (list, tuple, set)):
        return any(contains_direct_card_submission(item, parent_key=parent_key) for item in value)
    if isinstance(value, str):
        return bool(PAN_VALUE_PATTERN.search(value) or CARD_SECURITY_CODE_VALUE_PATTERN.search(value))
    return False


def minimum_tls_12_context() -> ssl.SSLContext:
    context = ssl.create_default_context()
    if hasattr(ssl, "TLSVersion"):
        context.minimum_version = ssl.TLSVersion.TLSv1_2
    else:  # pragma: no cover - Python 3.12 always has TLSVersion
        context.options |= getattr(ssl, "OP_NO_TLSv1", 0)
        context.options |= getattr(ssl, "OP_NO_TLSv1_1", 0)
    return context
