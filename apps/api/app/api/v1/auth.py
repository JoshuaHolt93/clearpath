from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import password_policy_errors, totp_provisioning_uri
from app.dependencies import Principal, require_full_session, require_pending_auth
from app.models import HouseholdMember, User
from app.schemas.auth import (
    AuthLoginResponse,
    AuthSessionResponse,
    HouseholdInviteAcceptRequest,
    HouseholdInviteTokenResponse,
    LoginRequest,
    LogoutRequest,
    LogoutResponse,
    MfaChallengeResponse,
    MfaEmailCodeSendRequest,
    MfaEmailCodeSendResponse,
    MfaMobileSetupResponse,
    MfaPushStartRequest,
    MfaPushStartResponse,
    MfaRecoveryChallengeResponse,
    MfaRecoveryVerifyRequest,
    MfaSetupConfirmRequest,
    MfaSetupResponse,
    MfaVerifyRequest,
    PasswordResetConfirmRequest,
    PasswordResetConfirmResponse,
    PasswordResetRequest,
    PasswordResetRequestResponse,
    PasswordResetTokenResponse,
    RegisterRequest,
    UserSummary,
)
from app.services.auth_service import (
    accept_household_invite,
    authenticate_principal,
    confirm_totp_setup,
    invite_from_token,
    invite_is_usable,
    issue_auth_response,
    password_reset_token_for,
    record_failed_login,
    register_user,
    resolve_mfa_setup_token,
    setup_response_for_pending,
    should_mark_mfa_verified,
    skip_mfa_setup,
    too_many_login_attempts,
    user_from_password_reset_token,
    verify_mfa,
    verify_recovery_code,
)

router = APIRouter(tags=["auth"])


def _source_addr(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.post("/auth/register", response_model=AuthSessionResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, request: Request, response: Response, db: Annotated[Session, Depends(get_db)]) -> AuthSessionResponse:
    policy_acknowledged = payload.policy_acknowledgement or (payload.ethics_acknowledgement and payload.legal_acknowledgement)
    user = register_user(
        db,
        email=payload.email,
        password=payload.password,
        display_name=payload.display_name,
        household_name=payload.household_name,
        policy_acknowledged=policy_acknowledged,
        source_addr=_source_addr(request),
    )
    mfa_verified = should_mark_mfa_verified(user)
    return issue_auth_response(user=user, mfa_verified=mfa_verified, response=response)


@router.post("/auth/login", response_model=AuthLoginResponse)
def login(payload: LoginRequest, request: Request, response: Response, db: Annotated[Session, Depends(get_db)]) -> AuthSessionResponse:
    user, household_member = authenticate_principal(db, email=payload.email, password=payload.password, source_addr=_source_addr(request))
    subject = household_member or user
    mfa_verified = should_mark_mfa_verified(subject)
    return issue_auth_response(
        user=user,
        household_member=household_member,
        mfa_verified=mfa_verified,
        stay_signed_in=payload.stay_signed_in,
        response=response,
    )


@router.delete("/auth/session", response_model=LogoutResponse)
def logout(payload: LogoutRequest, response: Response) -> LogoutResponse:
    response.delete_cookie(get_settings().session_cookie_name)
    return LogoutResponse(ok=True)


@router.get("/me", response_model=UserSummary)
def me(principal: Annotated[Principal, Depends(require_full_session)]) -> UserSummary:
    return UserSummary.model_validate(principal.user)


@router.get("/auth/mfa/setup", response_model=MfaSetupResponse)
def mfa_setup(principal: Annotated[Principal, Depends(require_pending_auth)], db: Annotated[Session, Depends(get_db)]) -> dict:
    return setup_response_for_pending(principal, db)


@router.post("/auth/mfa/setup", response_model=AuthSessionResponse)
def mfa_setup_confirm(
    payload: MfaSetupConfirmRequest,
    response: Response,
    principal: Annotated[Principal, Depends(require_pending_auth)],
    db: Annotated[Session, Depends(get_db)],
) -> AuthSessionResponse:
    recovery_codes = None
    if payload.action == "skip":
        skip_mfa_setup(principal, db)
    elif payload.action == "verify_totp":
        recovery_codes, _ = confirm_totp_setup(principal, db, code=payload.code, push_opt_in=payload.mfa_push_opt_in)
    else:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Email code MFA is not configured in Phase 1.")
    return issue_auth_response(
        user=principal.user,
        household_member=principal.household_member,
        mfa_verified=True,
        stay_signed_in=principal.stay_signed_in,
        response=response,
        recovery_codes=recovery_codes,
    )


@router.post("/auth/mfa/setup/email-code", response_model=MfaEmailCodeSendResponse)
def mfa_setup_email_code(
    payload: MfaEmailCodeSendRequest,
    principal: Annotated[Principal, Depends(require_pending_auth)],
) -> MfaEmailCodeSendResponse:
    return MfaEmailCodeSendResponse(sent=False, reason="email_mfa_not_configured")


@router.get("/auth/mfa/setup/mobile/{token}", response_model=MfaMobileSetupResponse)
def mfa_mobile_setup(token: str, db: Annotated[Session, Depends(get_db)]) -> MfaMobileSetupResponse:
    subject = resolve_mfa_setup_token(db, token)
    if not subject:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="MFA setup token is expired or invalid.")
    secret = subject.ensure_mfa_secret()
    db.commit()
    subject_type = "household_member" if isinstance(subject, HouseholdMember) else "user"
    return MfaMobileSetupResponse(
        provisioning_uri=totp_provisioning_uri(email=subject.email, secret=secret),
        expired=False,
        email=subject.email,
        subject_type=subject_type,
    )


@router.get("/auth/mfa/challenge", response_model=MfaChallengeResponse)
def mfa_challenge(principal: Annotated[Principal, Depends(require_pending_auth)]) -> MfaChallengeResponse:
    subject = principal.subject
    if not subject.mfa_enabled:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="MFA setup is required.")
    return MfaChallengeResponse(
        subject_type=principal.subject_type,
        subject_id=principal.subject_id,
        email=subject.email,
        preferred_method=subject.mfa_preferred_method or "totp",
        push_available=False,
        email_available=False,
        email_challenge_sent=False,
    )


@router.post("/auth/mfa/verify", response_model=AuthSessionResponse)
def mfa_verify(
    payload: MfaVerifyRequest,
    response: Response,
    principal: Annotated[Principal, Depends(require_pending_auth)],
    db: Annotated[Session, Depends(get_db)],
) -> AuthSessionResponse:
    if payload.method != "totp":
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Only authenticator-code MFA is available in Phase 1.")
    verify_mfa(principal, db, code=payload.code)
    return issue_auth_response(
        user=principal.user,
        household_member=principal.household_member,
        mfa_verified=True,
        stay_signed_in=principal.stay_signed_in,
        response=response,
    )


@router.post("/auth/mfa/push/start", response_model=MfaPushStartResponse)
def mfa_push_start(
    payload: MfaPushStartRequest,
    principal: Annotated[Principal, Depends(require_pending_auth)],
) -> MfaPushStartResponse:
    return MfaPushStartResponse(push_available=False, fallback="totp", reason="push_mfa_not_configured")


@router.get("/auth/mfa/push/callback", response_model=MfaPushStartResponse)
def mfa_push_callback(principal: Annotated[Principal, Depends(require_pending_auth)]) -> MfaPushStartResponse:
    return MfaPushStartResponse(push_available=False, fallback="totp", reason="push_mfa_not_configured")


@router.get("/auth/mfa/recovery/challenge", response_model=MfaRecoveryChallengeResponse)
def mfa_recovery_challenge(principal: Annotated[Principal, Depends(require_pending_auth)]) -> MfaRecoveryChallengeResponse:
    return MfaRecoveryChallengeResponse(available=True)


@router.post("/auth/mfa/recovery", response_model=AuthSessionResponse)
def mfa_recovery(
    payload: MfaRecoveryVerifyRequest,
    response: Response,
    principal: Annotated[Principal, Depends(require_pending_auth)],
    db: Annotated[Session, Depends(get_db)],
) -> AuthSessionResponse:
    verify_recovery_code(principal, db, code=payload.recovery_code)
    return issue_auth_response(
        user=principal.user,
        household_member=principal.household_member,
        mfa_verified=True,
        stay_signed_in=principal.stay_signed_in,
        response=response,
    )


@router.post("/auth/password-reset/request", response_model=PasswordResetRequestResponse)
def password_reset_request(payload: PasswordResetRequest, request: Request, db: Annotated[Session, Depends(get_db)]) -> PasswordResetRequestResponse:
    # Flask throttles reset requests per source+email (5 per 15 minutes) and
    # skips the account lookup entirely while throttled, keeping the response
    # indistinguishable so accounts cannot be enumerated.
    source_addr = _source_addr(request)
    throttled = too_many_login_attempts(db, payload.email, "reset", source_addr)
    if not throttled:
        record_failed_login(db, payload.email, "reset", source_addr)
    user = db.scalar(select(User).where(User.email == payload.email)) if payload.email and not throttled else None
    token = password_reset_token_for(user) if user else None
    return PasswordResetRequestResponse(
        message="If an account exists for that email, a password reset link has been sent.",
        reset_token=token if (token and get_settings().expose_dev_tokens) else None,
    )


@router.get("/auth/password-reset/{token}", response_model=PasswordResetTokenResponse)
def password_reset_token(token: str, db: Annotated[Session, Depends(get_db)]) -> PasswordResetTokenResponse:
    user = user_from_password_reset_token(db, token)
    return PasswordResetTokenResponse(valid=bool(user), email=user.email if user else None)


@router.post("/auth/password-reset/{token}", response_model=PasswordResetConfirmResponse)
def password_reset_confirm(token: str, payload: PasswordResetConfirmRequest, db: Annotated[Session, Depends(get_db)]) -> PasswordResetConfirmResponse:
    user = user_from_password_reset_token(db, token)
    if not user:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="That password reset link is invalid or expired.")
    if payload.password != payload.confirm_password:
        raise HTTPException(status_code=422, detail="New password and confirmation did not match.")
    errors = password_policy_errors(payload.password, user.email)
    if errors:
        raise HTTPException(status_code=422, detail=" ".join(errors))
    user.set_password(payload.password)
    db.commit()
    return PasswordResetConfirmResponse(ok=True)


@router.get("/household-invites/{token}", response_model=HouseholdInviteTokenResponse)
def household_invite(token: str, db: Annotated[Session, Depends(get_db)]) -> HouseholdInviteTokenResponse:
    invite = invite_from_token(db, token)
    if not invite_is_usable(invite):
        return HouseholdInviteTokenResponse(valid=False)
    return HouseholdInviteTokenResponse(
        valid=True,
        email=invite.email,
        household_name=invite.owner_user.household_name if invite.owner_user else None,
        role=invite.role,
    )


@router.post("/household-invites/{token}/accept", response_model=AuthSessionResponse)
def household_invite_accept(
    token: str,
    payload: HouseholdInviteAcceptRequest,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> AuthSessionResponse:
    invite = invite_from_token(db, token)
    if not invite_is_usable(invite):
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="That household invite is expired or has already been used.")
    member = accept_household_invite(
        db,
        invite=invite,
        display_name=payload.display_name,
        password=payload.password,
        confirm_password=payload.confirm_password,
        accepted_terms=payload.policy_acknowledgement,
    )
    owner = member.owner_user
    mfa_verified = should_mark_mfa_verified(member)
    return issue_auth_response(user=owner, household_member=member, mfa_verified=mfa_verified, response=response)
