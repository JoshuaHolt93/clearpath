from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class PlannerGuidanceQuery(BaseModel):
    pass


class PlannerGuidanceGenerateRequest(BaseModel):
    pass


class PlannerPreferenceUpdateRequest(BaseModel):
    provider: str
    model: str


class PlannerPageContextRequest(BaseModel):
    path: str = ""
    title: str = ""
    section: str = ""
    visible_text: str = ""
    question: str = ""


class PlannerGuidanceActionResponse(BaseModel):
    label: str
    target: str


class PlannerGuidanceItemResponse(BaseModel):
    title: str
    body: str
    level: str = "info"
    type: str = "planner_note"
    disclaimer: str | None = None
    action: PlannerGuidanceActionResponse | None = None


class PlannerModelChoiceResponse(BaseModel):
    id: str
    label: str


class PlannerModelOptionResponse(BaseModel):
    key: str
    label: str
    configured: bool
    models: list[PlannerModelChoiceResponse] = Field(default_factory=list)


class PlannerUsageMetadataResponse(BaseModel):
    burst_count: int
    daily_count: int
    monthly_count: int
    monthly_cost_cents: float
    burst_limit: int
    daily_limit: int
    monthly_limit: int
    monthly_cost_limit_cents: int
    current_limit_reason: str | None = None


class PlannerGuidanceResponse(BaseModel):
    source: str
    provider: str
    model: str
    items: list[PlannerGuidanceItemResponse] = Field(default_factory=list)
    status: str
    message: str
    generated_at: datetime | None = None
    model_options: list[PlannerModelOptionResponse] = Field(default_factory=list)
    selected_provider: str
    selected_model: str
    usage: PlannerUsageMetadataResponse


class PlannerPageContextResponse(BaseModel):
    source: str
    provider: str
    model: str
    items: list[PlannerGuidanceItemResponse] = Field(default_factory=list)
    status: str
    message: str


class PlannerDashboardFocusResponse(BaseModel):
    items: list[PlannerGuidanceItemResponse] = Field(default_factory=list)
    generated_at: datetime | None = None
    message: str
