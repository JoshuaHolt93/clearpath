"""The API schema and interactive docs must not be served in production.

Flask never exposed an OpenAPI schema, so publishing one from the port would
hand anonymous callers the full API surface. Every endpoint still enforces auth
either way -- this is surface reduction, not an authz control.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import create_app

DOC_ROUTES = ("/openapi.json", "/docs", "/redoc")


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    # Settings is lru_cached; drop it so CLEARPATH_ENV changes take effect.
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.parametrize("route", DOC_ROUTES)
def test_doc_routes_are_absent_in_production(monkeypatch: pytest.MonkeyPatch, route: str) -> None:
    monkeypatch.setenv("CLEARPATH_ENV", "production")
    client = TestClient(create_app())
    assert client.get(route).status_code == 404


@pytest.mark.parametrize("route", DOC_ROUTES)
def test_doc_routes_are_available_outside_production(
    monkeypatch: pytest.MonkeyPatch, route: str
) -> None:
    monkeypatch.setenv("CLEARPATH_ENV", "development")
    client = TestClient(create_app())
    assert client.get(route).status_code == 200


def test_health_still_served_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLEARPATH_ENV", "production")
    client = TestClient(create_app())
    assert client.get("/v1/health").status_code == 200


def test_schema_is_still_generable_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    # scripts/export_openapi.py calls app.openapi() in-process for the
    # api-client codegen; disabling the HTTP route must not break that.
    monkeypatch.setenv("CLEARPATH_ENV", "production")
    assert len(create_app().openapi()["paths"]) > 0
