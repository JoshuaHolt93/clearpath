from __future__ import annotations

from fastapi import FastAPI

from app.api.v1.auth import router as auth_router
from app.api.v1.health import router as health_router
from app.api.v1.transactions import router as transactions_router


def create_app() -> FastAPI:
    app = FastAPI(title="ClearPath Finance API", version="0.1.0")
    app.include_router(health_router, prefix="/v1")
    app.include_router(auth_router, prefix="/v1")
    app.include_router(transactions_router, prefix="/v1")
    return app


app = create_app()
