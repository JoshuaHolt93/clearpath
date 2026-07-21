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


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # Railway/Render hand out this form; SQLAlchemy would pick psycopg2.
        (
            "postgresql://user:pw@host.railway.internal:5432/railway",
            "postgresql+psycopg://user:pw@host.railway.internal:5432/railway",
        ),
        # Legacy Heroku-style scheme.
        ("postgres://user:pw@host:5432/db", "postgresql+psycopg://user:pw@host:5432/db"),
        # Already explicit: left untouched.
        ("postgresql+psycopg://user:pw@host:5432/db", "postgresql+psycopg://user:pw@host:5432/db"),
        # An explicit psycopg2 opt-in is honoured rather than rewritten.
        ("postgresql+psycopg2://user:pw@host:5432/db", "postgresql+psycopg2://user:pw@host:5432/db"),
        # Non-Postgres URLs pass through.
        ("sqlite:///./clearpath_dev.db", "sqlite:///./clearpath_dev.db"),
    ],
)
def test_postgres_urls_are_pinned_to_psycopg3(
    monkeypatch: pytest.MonkeyPatch, raw: str, expected: str
) -> None:
    monkeypatch.setenv("DATABASE_URL", raw)
    assert Settings(_env_file=None).database_url == expected


def test_password_containing_scheme_like_text_is_not_mangled(monkeypatch: pytest.MonkeyPatch) -> None:
    # Only a leading scheme is rewritten; credentials are left byte-identical.
    raw = "postgresql://user:pg%2Fpostgres%3A%2F%2Fpw@host:5432/db"
    monkeypatch.setenv("DATABASE_URL", raw)
    assert Settings(_env_file=None).database_url == "postgresql+psycopg://" + raw[len("postgresql://") :]
