from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta

from fastapi import HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.defaults import REGISTRATION_DEFAULT_PAYCHECK_CADENCE
from app.core.security import (
    create_purpose_token,
    create_session_token,
    decode_purpose_token,
    password_policy_errors,
    totp_provisioning_uri,
    verify_totp_code,
)
from app.dependencies import Principal
from app.models import HouseholdInvite, HouseholdMember, LoginAttempt, OnboardingProfile, User, utc_now
from app.schemas.auth import AuthSessionResponse, SessionPrincipal, UserSummary

ETHICS_POLICY_VERSION = "2026-01"
HOUSEHOLD_ROLE_EDITOR = "editor"
HOUSEHOLD_ROLE_VIEWER = "viewer"
LOGIN_WINDOW = timedelta(minutes=15)
MAX_LOGIN_ATTEMPTS = 5



def _login_key(email: str, purpose: str = "login") -> str:
    return f"{purpose}:{(email or '').strip().lower()}"


def _prune_old_login_attempts(db: Session, cutoff) -> None:
    db.query(LoginAttempt).filter(LoginAttempt.attempted_at < cutoff).delete(synchronize_session=False)


def too_many_login_attempts(db: Session, email: str, purpose: str = "login") -> bool:
    cutoff = utc_now() - LOGIN_WINDOW
    _prune_old_login_attempts(db, cutoff)
    failed_count = (
        db.query(LoginAttempt)
        .filter(LoginAttempt.key == _login_key(email, purpose), LoginAttempt.success.is_(False), LoginAttempt.attempted_at >= cutoff)
        .count()
    )
    return failed_count >= MAX_LOGIN_ATTEMPTS


def record_failed_login(db: Session, email: str, purpose: str = "login") -> None:
    db.add(LoginAttempt(key=_login_key(email, purpose), attempted_at=utc_now(), success=False))
    db.commit()


def clear_failed_logins(db: Session, email: str, purpose: str = "login") -> None:
    db.query(LoginAttempt).filter(LoginAttempt.key == _login_key(email, purpose), LoginAttempt.success.is_(False)).delete(synchronize_session=False)
    db.add(LoginAttempt(key=_login_key(email, purpose), attempted_at=utc_now(), success=True))
    db.commit()


def normalize_household_role(role: str | None) -> str:
    cleaned = (role or "").strip().lower()
    return cleaned if cleaned in {HOUSEHOLD_ROLE_EDITOR, HOUSEHOLD_ROLE_VIEWER} else HOUSEHOLD_ROLE_EDITOR


def household_invite_token_hash(token: str) -> str:
    return hashlib.sha256((token or "").strip().encode("utf-8")).hexdigest()


def is_onboarding_complete(user: User) -> bool:
    profile = user.profile
    if not profile:
        return False
    return bool((profile.income_amount or 0) > 0 or (profile.monthly_income or 0) > 0)


def mfa_setup_is_skipped(subject: User | HouseholdMember) -> bool:
    return bool(not subject.mfa_enabled and (subject.mfa_preferred_method or "").lower() == "none")


def _subject_tuple(user: User, household_member: HouseholdMember | None) -> tuple[str, int, User | HouseholdMember]:
    if household_member is not None:
        return "household_member", household_member.id, household_member
    return "user", user.id, user


def _next_step_for_subject(user: User, subject: User | HouseholdMember, *, mfa_verified: bool) -> str:
    if not mfa_verified:
        return "mfa_verify" if subject.mfa_enabled else "mfa_setup"
    if not user.selected_plan:
        return "select_plan"
    return "dashboard" if is_onboarding_complete(user) else "onboarding"


def issue_auth_response(
    *,
    user: User,
    household_member: HouseholdMember | None = None,
    mfa_verified: bool,
    response: Response | None = None,
    recovery_codes: list[str] | None = None,
) -> AuthSessionResponse:
    subject_type, subject_id, subject = _subject_tuple(user, household_member)
    token = create_session_token(
        user_id=user.id,
        subject_type=subject_type,  # type: ignore[arg-type]
        subject_id=subject_id,
        household_member_id=household_member.id if household_member else None,
        household_role=household_member.role if household_member else None,
        mfa_verified=mfa_verified,
    )
    if response is not None:
        settings = get_settings()
        response.set_cookie(
            settings.session_cookie_name,
            token,
            httponly=True,
            secure=settings.is_production,
            samesite="lax",
            max_age=(settings.session_minutes if mfa_verified else settings.pending_session_minutes) * 60,
        )
    principal = SessionPrincipal(
        user_id=user.id,
        subject_type=subject_type,
        subject_id=subject_id,
        household_member_id=household_member.id if household_member else None,
        household_role=household_member.role if household_member else None,
        mfa_verified=mfa_verified,
    )
    return AuthSessionResponse(
        access_token=token,
        mfa_verified=mfa_verified,
        requires_mfa=not mfa_verified,
        next_step=_next_step_for_subject(user, subject, mfa_verified=mfa_verified),
        user=UserSummary.model_validate(user),
        principal=principal,
        recovery_codes=recovery_codes,
    )


def create_default_profile(user: User) -> OnboardingProfile:
    return OnboardingProfile(
        user=user,
        income_amount=0,
        income_basis="take_home",
        income_type="salary",
        income_frequency="monthly",
        paycheck_cadence=REGISTRATION_DEFAULT_PAYCHECK_CADENCE,
        hourly_hours_per_week=40,
        monthly_income=0,
        fixed_expenses=0,
        planned_savings_contribution=0,
        planned_debt_payment=0,
        target_investment_contribution=0,
    )


def register_user(db: Session, *, email: str, password: str, display_name: str, household_name: str | None, policy_acknowledged: bool) -> User:
    password_errors = password_policy_errors(password, email)
    if not display_name.strip():
        raise HTTPException(status_code=422, detail="Your name is required.")
    if not email or not password:
        raise HTTPException(status_code=422, detail="Email and password are required.")
    if password_errors:
        raise HTTPException(status_code=422, detail=" ".join(password_errors))
    if not policy_acknowledged:
        raise HTTPException(
            status_code=422,
            detail="Please review and accept the ClearPath Terms of Service, Privacy Policy, and Ethics Policy to create an account.",
        )
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with that email already exists.")
    if db.scalar(select(HouseholdMember).where(HouseholdMember.email == email)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="That email already has shared household access. Sign in instead.")

    user = User(
        email=email,
        display_name=display_name.strip(),
        household_name=(household_name or "").strip() or "My Household",
        ethics_acknowledged_at=utc_now(),
        ethics_policy_version=ETHICS_POLICY_VERSION,
        selected_plan="",
    )
    user.set_password(password)
    db.add(user)
    db.flush()
    db.add(create_default_profile(user))
    db.commit()
    db.refresh(user)
    return user


def authenticate_principal(db: Session, *, email: str, password: str) -> tuple[User, HouseholdMember | None]:
    if too_many_login_attempts(db, email):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many failed sign-in attempts. Please wait a few minutes and try again.")

    user = db.scalar(select(User).where(User.email == email))
    if user and user.check_password(password):
        clear_failed_logins(db, email)
        return user, None

    household_member = None if user else db.scalar(select(HouseholdMember).where(HouseholdMember.email == email, HouseholdMember.status == "active"))
    if household_member and household_member.check_password(password) and household_member.owner_user:
        clear_failed_logins(db, email)
        household_member.last_login_at = utc_now()
        db.commit()
        return household_member.owner_user, household_member

    record_failed_login(db, email)
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password.")


def should_mark_mfa_verified(subject: User | HouseholdMember, settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    return (not settings.mfa_required) or mfa_setup_is_skipped(subject)


def setup_response_for_pending(principal: Principal, db: Session) -> dict:
    subject = principal.subject
    secret = subject.ensure_mfa_secret()
    db.commit()
    return {
        "subject_type": principal.subject_type,
        "subject_id": principal.subject_id,
        "email": subject.email,
        "mfa_enabled": bool(subject.mfa_enabled),
        "preferred_method": subject.mfa_preferred_method or "totp",
        "provisioning_uri": None if subject.mfa_enabled else totp_provisioning_uri(email=subject.email, secret=secret),
        "mobile_setup_token": create_mfa_setup_token(principal),
        "push_available": False,
        "email_available": False,
        "recovery_codes": None,
    }


def create_mfa_setup_token(principal: Principal) -> str:
    return create_purpose_token(
        purpose="mfa_setup",
        subject=f"{principal.subject_type}:{principal.subject_id}",
        minutes=15,
        extra={"subject_type": principal.subject_type, "subject_id": principal.subject_id},
    )


def resolve_mfa_setup_token(db: Session, token: str) -> User | HouseholdMember | None:
    try:
        payload = decode_purpose_token(token, purpose="mfa_setup")
    except Exception:
        return None
    subject_type = payload.get("subject_type")
    subject_id = int(payload.get("subject_id") or 0)
    if subject_type == "household_member":
        return db.get(HouseholdMember, subject_id)
    if subject_type == "user":
        return db.get(User, subject_id)
    return None


def confirm_totp_setup(principal: Principal, db: Session, *, code: str | None, push_opt_in: bool) -> tuple[list[str], bool]:
    subject = principal.subject
    secret = subject.ensure_mfa_secret()
    if not verify_totp_code(secret, code):
        raise HTTPException(status_code=422, detail="Invalid authentication code.")
    recovery_codes = subject.generate_mfa_recovery_codes()
    subject.mfa_enabled = True
    subject.mfa_confirmed_at = utc_now()
    subject.mfa_push_enabled = False
    subject.mfa_preferred_method = "totp"
    db.commit()
    return recovery_codes, True


def skip_mfa_setup(principal: Principal, db: Session) -> None:
    subject = principal.subject
    subject.mfa_push_enabled = False
    subject.mfa_preferred_method = "none"
    db.commit()


def verify_mfa(principal: Principal, db: Session, *, code: str | None) -> None:
    subject = principal.subject
    if not subject.mfa_enabled:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="MFA setup is required.")
    if not verify_totp_code(subject.mfa_secret, code):
        raise HTTPException(status_code=422, detail="Invalid authentication code.")
    db.commit()


def verify_recovery_code(principal: Principal, db: Session, *, code: str | None) -> None:
    subject = principal.subject
    if not subject.mfa_enabled:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="MFA setup is required.")
    if not subject.verify_mfa_recovery_code(code):
        raise HTTPException(status_code=422, detail="Invalid recovery code.")
    db.commit()


def password_reset_token_for(user: User) -> str:
    return create_purpose_token(purpose="password_reset", subject=str(user.id), minutes=60)


def user_from_password_reset_token(db: Session, token: str) -> User | None:
    try:
        payload = decode_purpose_token(token, purpose="password_reset")
    except Exception:
        return None
    return db.get(User, int(payload["sub"]))


def invite_from_token(db: Session, token: str | None) -> HouseholdInvite | None:
    if not token:
        return None
    return db.scalar(select(HouseholdInvite).where(HouseholdInvite.token_hash == household_invite_token_hash(token)))


def invite_is_usable(invite: HouseholdInvite | None) -> bool:
    return bool(invite and invite.status == "pending" and invite.expires_at and invite.expires_at >= utc_now())


def accept_household_invite(db: Session, *, invite: HouseholdInvite, display_name: str, password: str, confirm_password: str, accepted_terms: bool) -> HouseholdMember:
    if not invite_is_usable(invite):
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="This invite is no longer available.")
    password_errors = password_policy_errors(password, invite.email)
    if not display_name.strip():
        raise HTTPException(status_code=422, detail="Your name is required.")
    if not accepted_terms:
        raise HTTPException(status_code=422, detail="Please accept the ClearPath Terms, Privacy Policy, and Ethics Policy to use shared access.")
    if password != confirm_password:
        raise HTTPException(status_code=422, detail="Password and confirmation did not match.")
    if password_errors:
        raise HTTPException(status_code=422, detail=" ".join(password_errors))

    existing = db.scalar(select(HouseholdMember).where(HouseholdMember.email == invite.email))
    if existing and existing.status == "active":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="That email already has shared access.")
    member = existing or HouseholdMember(owner_user_id=invite.owner_user_id, invited_by_user_id=invite.invited_by_user_id, email=invite.email)
    member.owner_user_id = invite.owner_user_id
    member.invited_by_user_id = invite.invited_by_user_id
    member.display_name = display_name.strip() or member.display_name
    member.role = normalize_household_role(invite.role)
    member.status = "active"
    member.accepted_at = utc_now()
    member.policy_version = ETHICS_POLICY_VERSION
    member.set_password(password)
    db.add(member)
    db.flush()
    invite.status = "accepted"
    invite.accepted_at = utc_now()
    invite.accepted_member_id = member.id
    db.commit()
    db.refresh(member)
    return member


def create_invite(owner: User, email: str, role: str, *, db: Session) -> tuple[HouseholdInvite, str]:
    token = secrets.token_urlsafe(32)
    invite = HouseholdInvite(
        owner_user_id=owner.id,
        invited_by_user_id=owner.id,
        email=email.strip().lower(),
        role=normalize_household_role(role),
        token_hash=household_invite_token_hash(token),
        status="pending",
        expires_at=utc_now() + timedelta(days=14),
    )
    db.add(invite)
    db.commit()
    db.refresh(invite)
    return invite, token





