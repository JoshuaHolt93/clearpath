from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.feature_access import (
    feature_is_temporarily_hidden,
    feature_min_plan_label,
)
from app.dependencies import Principal, require_household_access
from app.schemas.planner import (
    PlannerGuidanceGenerateRequest,
    PlannerGuidanceResponse,
    PlannerPageContextRequest,
    PlannerPageContextResponse,
    PlannerPreferenceUpdateRequest,
)
from app.services.planner_service import (
    generate_page_context_guidance,
    generate_planner_guidance,
    local_planner_guidance,
    normalize_planner_model,
    planner_guidance_with_actions,
    planner_model_options,
    planner_usage_metadata,
    save_planner_guidance,
    saved_planner_guidance,
    user_has_planner_access,
)
from app.services.transaction_service import require_onboarding_complete

router = APIRouter(tags=["planner"])


def _require_planner_access(principal: Principal) -> None:
    require_onboarding_complete(principal.user)
    if user_has_planner_access(principal.user):
        return
    if feature_is_temporarily_hidden("ai_planner"):
        message = (
            "AI Planner and Ask AI Coach are not available during the current "
            "ClearPath validation period."
        )
    else:
        message = (
            f"AI Planner and Ask AI Coach require ClearPath "
            f"{feature_min_plan_label('ai_planner')}."
        )
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={
            "code": "feature_locked",
            "feature": "ai_planner",
            "required_plan": feature_min_plan_label("ai_planner"),
            "message": message,
        },
    )


def _guidance_response(
    db: Session,
    principal: Principal,
    guidance: dict,
) -> PlannerGuidanceResponse:
    user = principal.user
    guidance = planner_guidance_with_actions(guidance)
    selected_provider, selected_model = normalize_planner_model(
        user.ai_provider,
        user.ai_model,
    )
    return PlannerGuidanceResponse(
        **guidance,
        model_options=planner_model_options(),
        selected_provider=selected_provider,
        selected_model=selected_model,
        usage=planner_usage_metadata(db, user),
    )


def _current_guidance(db: Session, principal: Principal) -> dict:
    user = principal.user
    guidance = saved_planner_guidance(user)
    if guidance:
        return guidance
    provider, model = normalize_planner_model(user.ai_provider, user.ai_model)
    return {
        "source": "ClearPath rules engine",
        "provider": provider,
        "model": model,
        "items": local_planner_guidance(db, user),
        "status": "ready",
        "message": (
            "No saved AI coaching yet. Click Generate AI Guidance when you want "
            "provider-generated coaching."
        ),
        "generated_at": None,
    }


@router.get("/planner/guidance", response_model=PlannerGuidanceResponse)
def get_planner_guidance(
    principal: Annotated[
        Principal,
        Depends(require_household_access("viewer")),
    ],
    db: Annotated[Session, Depends(get_db)],
) -> PlannerGuidanceResponse:
    _require_planner_access(principal)
    return _guidance_response(db, principal, _current_guidance(db, principal))


@router.post("/planner/guidance/generate", response_model=PlannerGuidanceResponse)
def generate_and_save_planner_guidance(
    _payload: PlannerGuidanceGenerateRequest,
    principal: Annotated[
        Principal,
        Depends(require_household_access("editor")),
    ],
    db: Annotated[Session, Depends(get_db)],
) -> PlannerGuidanceResponse:
    _require_planner_access(principal)
    guidance = generate_planner_guidance(db, principal.user)
    saved = save_planner_guidance(db, principal.user, guidance)
    return _guidance_response(db, principal, saved)


@router.patch("/planner/preferences", response_model=PlannerGuidanceResponse)
def update_planner_preferences(
    payload: PlannerPreferenceUpdateRequest,
    principal: Annotated[
        Principal,
        Depends(require_household_access("editor")),
    ],
    db: Annotated[Session, Depends(get_db)],
) -> PlannerGuidanceResponse:
    _require_planner_access(principal)
    provider, model = normalize_planner_model(payload.provider, payload.model)
    principal.user.ai_provider = provider
    principal.user.ai_model = model
    db.commit()
    return _guidance_response(db, principal, _current_guidance(db, principal))


@router.post("/planner/page-context", response_model=PlannerPageContextResponse)
def get_planner_page_context(
    payload: PlannerPageContextRequest,
    principal: Annotated[
        Principal,
        Depends(require_household_access("viewer")),
    ],
    db: Annotated[Session, Depends(get_db)],
) -> PlannerPageContextResponse:
    _require_planner_access(principal)
    return PlannerPageContextResponse.model_validate(
        generate_page_context_guidance(
            db,
            principal.user,
            payload.model_dump(),
        )
    )
