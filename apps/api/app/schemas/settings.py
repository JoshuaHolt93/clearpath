from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.transactions import CategoryResponse


class CategoryManagerRowResponse(BaseModel):
    category: CategoryResponse
    usage: dict[str, int]
    can_manage: bool


class HouseholdMemberResponse(BaseModel):
    id: int
    email: str
    display_name: str | None = None
    role: str | None = None
    status: str
    accepted_at: datetime | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class HouseholdInviteResponse(BaseModel):
    id: int
    email: str
    role: str
    status: str
    expires_at: datetime | None = None
    created_at: datetime
    revoked_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class SettingsDashboardResponse(BaseModel):
    email: str
    display_name: str | None = None
    household_name: str | None = None
    category_rows: list[CategoryManagerRowResponse]
    rules_count: int
    plaid_status: dict
    push_mfa: dict
    mfa_enabled: bool
    mfa_preferred_method: str
    mfa_push_enabled: bool
    billing_status: dict
    feedback_options: dict
    household_role_options: dict[str, str]
    household_members: list[HouseholdMemberResponse]
    pending_household_invites: list[HouseholdInviteResponse]
    can_manage_household_access: bool
    household_access_is_shared: bool
    ethics_acknowledged_at: datetime | None = None
    ethics_policy_version: str | None = None
    account_delete_confirmation: str
    account_delete_billing_blocked: bool
    # Ordered (value, label) pairs, matching Flask's tuple-of-tuples constant.
    account_classification_options: list[tuple[str, str]] = Field(default_factory=list)


class PasswordChangeRequest(BaseModel):
    current_password: str = ""
    new_password: str = ""
    confirm_password: str = ""


class PasswordChangeResponse(BaseModel):
    updated: bool


class HouseholdUpdateRequest(BaseModel):
    household_name: str = ""


class HouseholdResponse(BaseModel):
    household_name: str | None = None


class MfaPreferenceUpdateRequest(BaseModel):
    mfa_preferred_method: str = "totp"


class MfaPreferenceResponse(BaseModel):
    mfa_preferred_method: str
    mfa_push_enabled: bool
    push: dict
    message: str


class AccountDeleteRequest(BaseModel):
    current_password: str = ""
    confirmation: str = ""


class AccountDeleteResponse(BaseModel):
    deleted: bool


class EthicsAcknowledgementRequest(BaseModel):
    acknowledged: bool = True


class EthicsAcknowledgementResponse(BaseModel):
    ethics_acknowledged_at: datetime
    ethics_policy_version: str


class HouseholdInviteCreateRequest(BaseModel):
    invite_email: str = ""
    invite_role: str | None = None


class HouseholdInviteCreateResponse(BaseModel):
    invite: HouseholdInviteResponse
    email_sent: bool
    # Flask parity: when email delivery is unavailable the invite URL is
    # surfaced for manual sharing (session fallback in Flask).
    fallback_invite_url: str | None = None
    delivery_reason: str | None = None


class HouseholdMemberRoleUpdateRequest(BaseModel):
    member_role: str | None = None


class HouseholdMemberRevokeRequest(BaseModel):
    confirm: bool = True


class HouseholdInviteRevokeRequest(BaseModel):
    confirm: bool = True
