from __future__ import annotations

import datetime

from pydantic import BaseModel, ConfigDict, Field


class SubscriptionEvidenceItem(BaseModel):
    # The field is named `date`, so the type must be module-qualified or the
    # field name shadows it during pydantic's annotation evaluation.
    id: int | None = None
    date: datetime.date | None = None
    description: str | None = None
    amount: float | None = None


class SubscriptionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    merchant_key: str
    name: str
    category: str
    service_category: str
    amount: float
    monthly_amount: float
    annual_amount: float
    cycle: str
    cycle_days: int
    confidence: float
    status: str
    cancel_url: str | None = None
    replaceable: bool
    first_seen: datetime.date | None = None
    last_seen: datetime.date | None = None
    next_charge_date: datetime.date | None = None
    notes: str | None = None
    is_manual: bool
    cycle_is_manual: bool
    # validation_alias keeps from_attributes from ingesting the ORM's raw
    # `evidence` JSON string; the route layer assigns the parsed rows.
    evidence: list[SubscriptionEvidenceItem] = Field(default_factory=list, validation_alias="evidence_rows")


class SubscriptionSummary(BaseModel):
    active_count: int
    review_count: int
    action_count: int
    manage_link_count: int
    monthly_total: float
    annual_total: float
    potential_savings: float
    average_confidence: int
    transaction_count: int


class SubscriptionCategoryBreakdownRow(BaseModel):
    category: str
    amount: float
    percent: int


class SubscriptionOpportunity(BaseModel):
    subscription_id: int
    reason: str


class SubscriptionListResponse(BaseModel):
    subscriptions: list[SubscriptionResponse]
    summary: SubscriptionSummary
    category_breakdown: list[SubscriptionCategoryBreakdownRow]
    opportunities: list[SubscriptionOpportunity]
    upcoming_subscription_ids: list[int]
    statuses: dict[str, str]
    cycles: list[str]


class SubscriptionScanResponse(BaseModel):
    synced_count: int
    subscriptions: list[SubscriptionResponse]


class SubscriptionCreateRequest(BaseModel):
    name: str
    amount: float
    cycle: str = "Monthly"
    next_charge_date: str | None = None
    notes: str | None = None


class SubscriptionUpdateRequest(BaseModel):
    # Unified PATCH covering Flask's confirm/status/cycle/manage-url routes.
    status: str | None = None
    notes: str | None = None
    cycle: str | None = None
    cancel_url: str | None = None


class SubscriptionLinkHelpRequest(BaseModel):
    pass


class SubscriptionLinkCandidateResponse(BaseModel):
    title: str
    url: str
    reason: str
    confidence: str


class SubscriptionLinkHelpResponse(BaseModel):
    source: str
    provider: str
    model: str
    status: str
    candidates: list[SubscriptionLinkCandidateResponse] = Field(default_factory=list)
    message: str


class SubscriptionImportRequest(BaseModel):
    csv_text: str | None = None
    csv_base64: str | None = None


class SubscriptionImportResponse(BaseModel):
    imported: int
    synced_count: int
