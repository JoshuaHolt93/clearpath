from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.plaid import AccountResponse, PlaidStatusResponse


class RetirementPlanQuery(BaseModel):
    pass


class RetirementProfileResponse(BaseModel):
    retirement_enabled: bool
    retirement_has_employer_plan: bool
    retirement_employer_withheld: bool
    retirement_has_personal_plan: bool
    retirement_monthly_contribution: float
    retirement_personal_monthly_contribution: float
    retirement_lifestyle_notes: str | None = None
    retirement_location_notes: str | None = None
    retirement_healthcare_notes: str | None = None
    retirement_income_notes: str | None = None
    retirement_debt_notes: str | None = None
    retirement_family_notes: str | None = None

    model_config = ConfigDict(from_attributes=True)


class RetirementPlanResponse(BaseModel):
    profile: RetirementProfileResponse
    retirement_accounts: list[AccountResponse] = Field(default_factory=list)
    retirement_contribution: float
    plaid_status: PlaidStatusResponse


class RetirementPlanUpdateRequest(BaseModel):
    # Flask's form POST overwrites every survey field when omitted. The JSON
    # PATCH keeps that behavior instead of using fields-set semantics.
    retirement_enabled: bool = False
    retirement_has_employer_plan: bool = False
    retirement_employer_withheld: bool = False
    retirement_has_personal_plan: bool = False
    retirement_monthly_contribution: float | str | None = 0
    retirement_personal_monthly_contribution: float | str | None = 0


class RetirementWorksheetUpdateRequest(BaseModel):
    # The HTML maxlength was client-side only; Flask trims and stores whatever
    # reaches the handler, so the API intentionally adds no new length rule.
    retirement_lifestyle_notes: str | None = ""
    retirement_location_notes: str | None = ""
    retirement_healthcare_notes: str | None = ""
    retirement_income_notes: str | None = ""
    retirement_debt_notes: str | None = ""
    retirement_family_notes: str | None = ""
