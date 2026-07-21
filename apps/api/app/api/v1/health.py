from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    # Deliberately discloses nothing beyond liveness (Flask commit 8c9f0bf
    # stopped /healthz from reporting the environment name).
    return {"status": "ok"}
