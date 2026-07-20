from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class FeedbackCreateRequest(BaseModel):
    reason: str = ""
    feature_expectation_reason: str | None = None
    broken_features: list[str] = Field(default_factory=list)
    description: str | None = None
    notify_when_addressed: bool = False


class FeedbackResponse(BaseModel):
    id: int
    feedback_type: str
    source: str
    reason: str
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FeedbackOptionsResponse(BaseModel):
    reasons: list[tuple[str, str]]
    feature_expectation_reasons: list[tuple[str, str]]
    broken_features: list[tuple[str, str]]


class ControlEvaluationResponse(BaseModel):
    id: int
    control_id: str
    control_name: str
    status: str
    evidence: str
    evaluated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ControlEvaluationListResponse(BaseModel):
    evaluations: list[ControlEvaluationResponse]
    controls: list[dict]


class ControlEvaluationRunRequest(BaseModel):
    confirm: bool = True


class ControlEvaluationRunResponse(BaseModel):
    evaluated: int
    evaluated_at: datetime
    results: list[dict]
