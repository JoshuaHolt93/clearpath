from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class BillingPlanResponse(BaseModel):
    key: str
    name: str
    amount_cents: int
    currency: str
    billing_interval: str
    price_display: str
    interval_display: str
    trial_period_days: int
    features: list[str] = Field(default_factory=list)
    price_configured: bool


class UpgradeTutorialItemResponse(BaseModel):
    title: str
    body: str
    target: str | None = None
    cta: str | None = None


class BillingPlansResponse(BaseModel):
    plans: list[BillingPlanResponse]
    billing_status: dict
    pricing_policy: dict
    free_tier_signups_enabled: bool
    upgrade_tutorials: dict[str, list[UpgradeTutorialItemResponse]]


class UserBillingStateResponse(BaseModel):
    selected_plan: str | None = None
    billing_status: str
    has_stripe_customer: bool
    has_stripe_subscription: bool
    stripe_current_period_end: datetime | None = None
    billing_price_id: str | None = None
    config: dict


class BillingPlanSelectionRequest(BaseModel):
    plan: str = ""
    promotion_code: str | None = None
    # Local web paths for the Checkout redirect targets (validated, joined to
    # WEB_APP_URL); Flask derived these from url_for/return_to.
    success_path: str | None = None
    cancel_path: str | None = None


class BillingPlanSelectionResponse(BaseModel):
    selected_plan: str
    plan_name: str
    already_selected: bool = False
    checkout_url: str | None = None
    billing: UserBillingStateResponse
    upgrade_tutorial_items: list[UpgradeTutorialItemResponse] = Field(default_factory=list)


class BillingCheckoutSessionCreateRequest(BaseModel):
    plan: str | None = None
    promotion_code: str | None = None
    success_path: str | None = None
    cancel_path: str | None = None


class BillingCheckoutSessionResponse(BaseModel):
    checkout_url: str


class BillingPortalSessionCreateRequest(BaseModel):
    confirm: bool = True


class BillingPortalSessionResponse(BaseModel):
    portal_url: str


class BillingCancellationSessionCreateRequest(BaseModel):
    reason: str | None = None
    feature_expectation_reason: str | None = None
    broken_features: list[str] = Field(default_factory=list)
    description: str | None = None
    notify_when_addressed: bool = False


class BillingCancellationSessionResponse(BaseModel):
    feedback_saved: bool
    portal_url: str | None = None
    message: str | None = None


class StripeWebhookAckResponse(BaseModel):
    received: bool
