"""Env-parsing parity for Settings.

Flask reads PLAID_PRODUCTS / PLAID_COUNTRY_CODES as comma-separated strings
(app/__init__.py:1339-1340). pydantic-settings would otherwise JSON-decode any
list-typed field, which turns a copied `PLAID_PRODUCTS=transactions` variable
into a startup crash rather than a parse difference.
"""

from __future__ import annotations

import pytest

from app.core.config import Settings


def _settings(monkeypatch: pytest.MonkeyPatch, **env: str) -> Settings:
    for key in ("PLAID_PRODUCTS", "PLAID_COUNTRY_CODES"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return Settings(_env_file=None)


def test_defaults_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(monkeypatch)
    assert settings.plaid_products == ["transactions"]
    assert settings.plaid_country_codes == ["US"]


def test_single_bare_value_matches_flask(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(monkeypatch, PLAID_PRODUCTS="transactions", PLAID_COUNTRY_CODES="US")
    assert settings.plaid_products == ["transactions"]
    assert settings.plaid_country_codes == ["US"]


def test_comma_separated_values_are_split_and_stripped(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(
        monkeypatch,
        PLAID_PRODUCTS="transactions, liabilities ,investments",
        PLAID_COUNTRY_CODES="US,CA",
    )
    assert settings.plaid_products == ["transactions", "liabilities", "investments"]
    assert settings.plaid_country_codes == ["US", "CA"]


def test_empty_string_yields_empty_list_like_flask(monkeypatch: pytest.MonkeyPatch) -> None:
    # Flask: [p.strip() for p in "".split(",") if p.strip()] == []
    settings = _settings(monkeypatch, PLAID_PRODUCTS="", PLAID_COUNTRY_CODES="")
    assert settings.plaid_products == []
    assert settings.plaid_country_codes == []


def test_json_array_still_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(
        monkeypatch,
        PLAID_PRODUCTS='["transactions","auth"]',
        PLAID_COUNTRY_CODES='["US"]',
    )
    assert settings.plaid_products == ["transactions", "auth"]
    assert settings.plaid_country_codes == ["US"]
