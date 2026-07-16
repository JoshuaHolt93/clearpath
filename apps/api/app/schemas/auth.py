from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RegisterRequest(BaseModel):
    email: str
    password: str
    display_name: str
    household_name: str | None = None
    policy_acknowledgement: bool = False
    ethics_acknowledgement: bool = False
    legal_acknowledgement: bool = False

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class LoginRequest(BaseModel):
    email: str
    password: str
    stay_signed_in: bool = False

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class LogoutRequest(BaseModel):
    everywhere: bool = False


class UserSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    display_name: str | None = None
    household_name: str | None = None
    selected_plan: str
    billing_status: str
    is_admin: bool


class SessionPrincipal(BaseModel):
    user_id: int
    subject_type: str
    subject_id: int
    household_member_id: int | None = None
    household_role: str | None = None
    mfa_verified: bool
    stay_signed_in: bool


class AuthSessionResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    mfa_verified: bool
    requires_mfa: bool
    next_step: str
    user: UserSummary
    principal: SessionPrincipal
    recovery_codes: list[str] | None = None


class AuthLoginResponse(AuthSessionResponse):
    pass


class LogoutResponse(BaseModel):
    ok: bool = True


class MfaSetupResponse(BaseModel):
    subject_type: str
    subject_id: int
    email: str
    mfa_enabled: bool
    preferred_method: str
    provisioning_uri: str | None = None
    mobile_setup_token: str | None = None
    push_available: bool = False
    email_available: bool = False
    recovery_codes: list[str] | None = None


class MfaSetupConfirmRequest(BaseModel):
    action: str = Field(default="verify_totp", pattern="^(verify_totp|skip|confirm_email_code)$")
    code: str | None = None
    email_code: str | None = None
    mfa_push_opt_in: bool = False


class MfaEmailCodeSendRequest(BaseModel):
    purpose: str = Field(default="setup", pattern="^(setup|verify)$")


class MfaEmailCodeSendResponse(BaseModel):
    sent: bool
    reason: str | None = None


class MfaChallengeResponse(BaseModel):
    subject_type: str
    subject_id: int
    email: str
    preferred_method: str
    push_available: bool
    email_available: bool
    email_challenge_sent: bool = False


class MfaVerifyRequest(BaseModel):
    method: str = Field(default="totp", pattern="^(totp|email|push)$")
    code: str | None = None
    email_code: str | None = None


class MfaRecoveryChallengeResponse(BaseModel):
    available: bool = True


class MfaRecoveryVerifyRequest(BaseModel):
    recovery_code: str


class MfaPushStartRequest(BaseModel):
    next_url: str | None = None


class MfaPushStartResponse(BaseModel):
    push_available: bool
    fallback: str = "totp"
    authorization_url: str | None = None
    reason: str | None = None


class MfaPushCallbackQuery(BaseModel):
    state: str | None = None
    duo_code: str | None = None


class MfaMobileSetupResponse(BaseModel):
    provisioning_uri: str | None
    expired: bool = False
    email: str | None = None
    subject_type: str | None = None


class PasswordResetRequest(BaseModel):
    email: str

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class PasswordResetRequestResponse(BaseModel):
    message: str
    reset_token: str | None = None


class PasswordResetTokenResponse(BaseModel):
    valid: bool
    email: str | None = None


class PasswordResetConfirmRequest(BaseModel):
    password: str
    confirm_password: str


class PasswordResetConfirmResponse(BaseModel):
    ok: bool


class HouseholdInviteTokenResponse(BaseModel):
    valid: bool
    email: str | None = None
    household_name: str | None = None
    role: str | None = None


class HouseholdInviteAcceptRequest(BaseModel):
    display_name: str
    password: str
    confirm_password: str
    policy_acknowledgement: bool = False
