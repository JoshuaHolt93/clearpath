from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies import Principal, require_admin, require_household_access
from app.models import ControlEvaluation
from app.schemas.compliance import (
    ControlEvaluationListResponse,
    ControlEvaluationResponse,
    ControlEvaluationRunRequest,
    ControlEvaluationRunResponse,
    FeedbackCreateRequest,
    FeedbackOptionsResponse,
    FeedbackResponse,
)
from app.services.compliance_service import run_control_evaluations, soc2_cc41_controls
from app.services.feedback_service import build_product_feedback, feedback_form_options

router = APIRouter(tags=["compliance"])


@router.get("/feedback/options", response_model=FeedbackOptionsResponse)
def get_feedback_options(
    principal: Annotated[Principal, Depends(require_household_access("viewer"))],
) -> FeedbackOptionsResponse:
    return FeedbackOptionsResponse(**feedback_form_options())


@router.post("/feedback", response_model=FeedbackResponse, status_code=201)
def create_feedback(
    payload: FeedbackCreateRequest,
    principal: Annotated[Principal, Depends(require_household_access("viewer"))],
    db: Annotated[Session, Depends(get_db)],
) -> FeedbackResponse:
    entry, errors = build_product_feedback(
        principal.user,
        {
            "reason": payload.reason,
            "feature_expectation_reason": payload.feature_expectation_reason,
            "broken_features": payload.broken_features,
            "description": payload.description,
            "notify_when_addressed": payload.notify_when_addressed,
        },
        feedback_type="general",
        source="feedback",
    )
    if errors:
        raise HTTPException(status_code=422, detail=" ".join(errors))
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return FeedbackResponse.model_validate(entry)


@router.get("/compliance/control-evaluations", response_model=ControlEvaluationListResponse)
def list_control_evaluations(
    principal: Annotated[Principal, Depends(require_admin(action="compliance.control_evaluations", resource="SOC2 CC4.1 control evaluations"))],
    db: Annotated[Session, Depends(get_db)],
) -> ControlEvaluationListResponse:
    evaluations = db.scalars(
        select(ControlEvaluation)
        .order_by(ControlEvaluation.evaluated_at.desc(), ControlEvaluation.control_id.asc())
        .limit(60)
    ).all()
    return ControlEvaluationListResponse(
        evaluations=[ControlEvaluationResponse.model_validate(evaluation) for evaluation in evaluations],
        controls=soc2_cc41_controls(),
    )


@router.post("/compliance/control-evaluations/run", response_model=ControlEvaluationRunResponse)
def run_control_evaluations_endpoint(
    request: Request,
    payload: ControlEvaluationRunRequest,
    principal: Annotated[Principal, Depends(require_admin(action="compliance.control_evaluations", resource="SOC2 CC4.1 control evaluations"))],
    db: Annotated[Session, Depends(get_db)],
) -> ControlEvaluationRunResponse:
    result = run_control_evaluations(db, request.app)
    return ControlEvaluationRunResponse(
        evaluated=result["evaluated"],
        evaluated_at=result["evaluated_at"],
        results=result["results"],
    )
