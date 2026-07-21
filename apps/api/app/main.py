from __future__ import annotations

from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.v1.auth import router as auth_router
from app.api.v1.billing import router as billing_router
from app.api.v1.cash_projections import router as cash_projections_router
from app.api.v1.compliance import router as compliance_router
from app.api.v1.dashboard import router as dashboard_router
from app.api.v1.goals import router as goals_router
from app.api.v1.health import router as health_router
from app.api.v1.loan_plans import router as loan_plans_router
from app.api.v1.onboarding import router as onboarding_router
from app.api.v1.plaid import router as plaid_router
from app.api.v1.planner import router as planner_router
from app.api.v1.planning import router as planning_router
from app.api.v1.retirement import router as retirement_router
from app.api.v1.settings import router as settings_router
from app.api.v1.subscriptions import router as subscriptions_router
from app.api.v1.transactions import router as transactions_router


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    # API adaptation of Flask's set_security_headers after-request hook
    # (security.py at 92ccdbc). The page-oriented CSP/nonce/analytics pieces
    # belong to the web app; the JSON API applies the static protections and
    # HSTS when HTTPS is enforced.
    async def dispatch(self, request, call_next):
        from app.core.config import get_settings

        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()")
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        if request.url.scheme == "https" or get_settings().force_https:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response


def create_app() -> FastAPI:
    # Keep the interactive docs and the schema route out of production so the
    # full API surface isn't published to anonymous callers. Flask never served
    # a schema, so this also restores parity. `app.openapi()` still works
    # in-process, which is what scripts/export_openapi.py uses for codegen.
    from app.core.config import get_settings

    docs_enabled = not get_settings().is_production
    app = FastAPI(
        title="ClearPath Finance API",
        version="0.1.0",
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.include_router(health_router, prefix="/v1")
    app.include_router(auth_router, prefix="/v1")
    app.include_router(billing_router, prefix="/v1")
    app.include_router(cash_projections_router, prefix="/v1")
    app.include_router(compliance_router, prefix="/v1")
    app.include_router(dashboard_router, prefix="/v1")
    app.include_router(goals_router, prefix="/v1")
    app.include_router(loan_plans_router, prefix="/v1")
    app.include_router(onboarding_router, prefix="/v1")
    app.include_router(planner_router, prefix="/v1")
    app.include_router(transactions_router, prefix="/v1")
    app.include_router(planning_router, prefix="/v1")
    app.include_router(plaid_router, prefix="/v1")
    app.include_router(retirement_router, prefix="/v1")
    app.include_router(settings_router, prefix="/v1")
    app.include_router(subscriptions_router, prefix="/v1")
    return app


app = create_app()
