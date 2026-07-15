from __future__ import annotations

from fastapi import FastAPI

from app.api.v1.auth import router as auth_router
from app.api.v1.cash_projections import router as cash_projections_router
from app.api.v1.dashboard import router as dashboard_router
from app.api.v1.goals import router as goals_router
from app.api.v1.health import router as health_router
from app.api.v1.loan_plans import router as loan_plans_router
from app.api.v1.plaid import router as plaid_router
from app.api.v1.planner import router as planner_router
from app.api.v1.planning import router as planning_router
from app.api.v1.retirement import router as retirement_router
from app.api.v1.subscriptions import router as subscriptions_router
from app.api.v1.transactions import router as transactions_router


def create_app() -> FastAPI:
    app = FastAPI(title="ClearPath Finance API", version="0.1.0")
    app.include_router(health_router, prefix="/v1")
    app.include_router(auth_router, prefix="/v1")
    app.include_router(cash_projections_router, prefix="/v1")
    app.include_router(dashboard_router, prefix="/v1")
    app.include_router(goals_router, prefix="/v1")
    app.include_router(loan_plans_router, prefix="/v1")
    app.include_router(planner_router, prefix="/v1")
    app.include_router(transactions_router, prefix="/v1")
    app.include_router(planning_router, prefix="/v1")
    app.include_router(plaid_router, prefix="/v1")
    app.include_router(retirement_router, prefix="/v1")
    app.include_router(subscriptions_router, prefix="/v1")
    return app


app = create_app()
