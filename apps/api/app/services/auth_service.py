from __future__ import annotations

import hashlib
import hmac
import logging
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
from app.services.email_service import email_delivery_configured, send_transactional_email
from app.services.mfa_push_service import push_mfa_available, push_mfa_status

ETHICS_POLICY_VERSION = "2026-01"
HOUSEHOLD_ROLE_EDITOR = "editor"
HOUSEHOLD_ROLE_VIEWER = "viewer"
LOGIN_WINDOW = timedelta(minutes=15)
MAX_LOGIN_ATTEMPTS = 5
MFA_EMAIL_CODE_TTL_MINUTES = 10

logger = logging.getLogger(__name__)


def _login_key(email: str, purpose: str = "login", source_addr: str | None = None) -> str:
    # Flask keys throttles by purpose, request source address, and email
    # (auth.py::_login_key) so one source cannot burn another's window.
    return f"{purpose}:{source_addr or 'unknown'}:{(email or '').strip().lower()}"


def _prune_old_login_attempts(db: Session, cutoff) -> None:
    db.query(LoginAttempt).filter(LoginAttempt.attempted_at < cutoff).delete(synchronize_session=False)


def too_many_login_attempts(db: Session, email: str, purpose: str = "login", source_addr: str | None = None) -> bool:
    cutoff = utc_now() - LOGIN_WINDOW
    _prune_old_login_attempts(db, cutoff)
    failed_count = (
        db.query(LoginAttempt)
        .filter(
            LoginAttempt.key == _login_key(email, purpose, source_addr),
            LoginAttempt.success.is_(False),
            LoginAttempt.attempted_at >= cutoff,
        )
        .count()
    )
    is_locked = failed_count >= MAX_LOGIN_ATTEMPTS
    if is_locked:
        # Flask 8c9f0bf: record the throttling threshold in the security
        # incident ledger (deduplicated inside a 30-minute window).
        from app.services.compliance_service import create_security_incident

        create_security_incident(
            db,
            incident_type="authentication_throttled",
            severity="high",
            source=f"{purpose}_throttle",
            description=f"{purpose.title()} throttling threshold reached.",
        )
        logger.warning("Authentication throttled. purpose=%s source=%s", purpose, source_addr or "unknown")
    return is_locked


def record_failed_login(db: Session, email: str, purpose: str = "login", source_addr: str | None = None) -> None:
    db.add(LoginAttempt(key=_login_key(email, purpose, source_addr), attempted_at=utc_now(), success=False))
    db.commit()


def clear_failed_logins(db: Session, email: str, purpose: str = "login", source_addr: str | None = None) -> None:
    key = _login_key(email, purpose, source_addr)
    db.query(LoginAttempt).filter(LoginAttempt.key == key, LoginAttempt.success.is_(False)).delete(synchronize_session=False)
    db.add(LoginAttempt(key=key, attempted_at=utc_now(), success=True))
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
    stay_signed_in: bool = False,
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
        stay_signed_in=stay_signed_in,
    )
    if response is not None:
        settings = get_settings()
        if not mfa_verified:
            cookie_max_age = settings.pending_session_minutes * 60
        elif stay_signed_in:
            cookie_max_age = settings.stay_signed_in_days * 24 * 60 * 60
        else:
            cookie_max_age = None
        response.set_cookie(
            settings.session_cookie_name,
            token,
            httponly=True,
            secure=bool(settings.session_cookie_secure),
            samesite="lax",
            max_age=cookie_max_age,
        )
    principal = SessionPrincipal(
        user_id=user.id,
        subject_type=subject_type,
        subject_id=subject_id,
        household_member_id=household_member.id if household_member else None,
        household_role=household_member.role if household_member else None,
        mfa_verified=mfa_verified,
        stay_signed_in=stay_signed_in,
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


def register_user(
    db: Session,
    *,
    email: str,
    password: str,
    display_name: str,
    household_name: str | None,
    policy_acknowledged: bool,
    source_addr: str | None = None,
) -> User:
    # Flask throttles sign-ups per source (5 per 15 minutes) via the durable
    # LoginAttempt store, counting each created account toward the window.
    if too_many_login_attempts(db, "", "register", source_addr):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many sign-up attempts from this connection. Please wait a few minutes and try again.",
        )
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
    # Counts each account created from this source toward the sign-up
    # throttle window, matching Flask's post-registration record.
    record_failed_login(db, "", "register", source_addr)
    return user


def authenticate_principal(db: Session, *, email: str, password: str, source_addr: str | None = None) -> tuple[User, HouseholdMember | None]:
    if too_many_login_attempts(db, email, "login", source_addr):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many failed sign-in attempts. Please wait a few minutes and try again.")

    user = db.scalar(select(User).where(User.email == email))
    if user and user.check_password(password):
        clear_failed_logins(db, email, "login", source_addr)
        return user, None

    household_member = None if user else db.scalar(select(HouseholdMember).where(HouseholdMember.email == email, HouseholdMember.status == "active"))
    if household_member and household_member.check_password(password) and household_member.owner_user:
        clear_failed_logins(db, email, "login", source_addr)
        household_member.last_login_at = utc_now()
        db.commit()
        return household_member.owner_user, household_member

    record_failed_login(db, email, "login", source_addr)
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password.")


def should_mark_mfa_verified(subject: User | HouseholdMember, settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    return (not settings.mfa_required) or mfa_setup_is_skipped(subject)


def _mfa_subject_type(subject: User | HouseholdMember) -> str:
    return "household_member" if isinstance(subject, HouseholdMember) else "user"


def _mfa_subject_key(subject: User | HouseholdMember) -> str:
    return f"{_mfa_subject_type(subject)}:{int(subject.id)}"


def _mfa_secret_fingerprint(secret: str | None) -> str:
    return hashlib.sha256((secret or "").encode("utf-8")).hexdigest()


def _mfa_email_code_hash(subject: User | HouseholdMember, purpose: str, code: str) -> str:
    payload = f"{_mfa_subject_key(subject)}:{purpose}:{(code or '').strip()}".encode("utf-8")
    secret = get_settings().secret_key.encode("utf-8")
    return hmac.new(secret, payload, hashlib.sha256).hexdigest()


def mfa_subject_allows_push(subject: User | HouseholdMember) -> bool:
    return not isinstance(subject, HouseholdMember)


def mfa_push_status_for_subject(subject: User | HouseholdMember) -> dict:
    provider_status = push_mfa_status()
    if mfa_subject_allows_push(subject):
        return {**provider_status, "shared_access_totp_only": False}
    return {
        **provider_status,
        "available": False,
        "configured": False,
        "shared_access_totp_only": True,
    }


def send_mfa_email_code(subject: User | HouseholdMember, purpose: str) -> tuple[bool, str | None, str | None]:
    if purpose not in {"setup", "verify"}:
        raise ValueError("Unsupported MFA email-code purpose.")
    if not email_delivery_configured():
        return False, "email_mfa_not_configured", None

    code = f"{secrets.randbelow(1_000_000):06d}"
    result = send_transactional_email(
        to_email=subject.email,
        subject="Your ClearPath Finance verification code",
        text_body=(
            f"Your ClearPath Finance verification code is {code}.\n\n"
            "This code expires in 10 minutes. If you did not request this code, sign in and change your password."
        ),
    )
    if not result.sent:
        logger.error(
            "Email MFA code could not be sent. subject_type=%s subject_id=%s reason=%s",
            _mfa_subject_type(subject),
            int(subject.id),
            result.reason,
        )
        return False, result.reason or "email_delivery_failed", None

    challenge_token = create_purpose_token(
        purpose="mfa_email_challenge",
        subject=_mfa_subject_key(subject),
        minutes=MFA_EMAIL_CODE_TTL_MINUTES,
        extra={
            "challenge_purpose": purpose,
            "code_hash": _mfa_email_code_hash(subject, purpose, code),
        },
    )
    return True, None, challenge_token


def verify_mfa_email_code(
    subject: User | HouseholdMember,
    *,
    purpose: str,
    code: str | None,
    challenge_token: str | None,
) -> bool:
    challenge = mfa_email_challenge_for(subject, purpose=purpose, challenge_token=challenge_token)
    if not challenge:
        return False
    expected = str(challenge.get("code_hash") or "")
    actual = _mfa_email_code_hash(subject, purpose, code or "")
    return bool(expected and hmac.compare_digest(expected, actual))


def mfa_email_challenge_for(
    subject: User | HouseholdMember,
    *,
    purpose: str,
    challenge_token: str | None,
) -> dict | None:
    if not challenge_token:
        return None
    try:
        challenge = decode_purpose_token(challenge_token, purpose="mfa_email_challenge")
    except Exception:
        return None
    if challenge.get("sub") != _mfa_subject_key(subject) or challenge.get("challenge_purpose") != purpose:
        return None
    return challenge


def _ensure_mfa_attempt_allowed(db: Session, subject: User | HouseholdMember, source_addr: str | None) -> None:
    if too_many_login_attempts(db, subject.email, "mfa", source_addr):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed MFA attempts. Please wait a few minutes and try again.",
        )


def _record_invalid_mfa_attempt(db: Session, subject: User | HouseholdMember, source_addr: str | None) -> None:
    record_failed_login(db, subject.email, "mfa", source_addr)


def _clear_mfa_attempts(db: Session, subject: User | HouseholdMember, source_addr: str | None) -> None:
    clear_failed_logins(db, subject.email, "mfa", source_addr)


def setup_response_for_pending(principal: Principal, db: Session) -> dict:
    subject = principal.subject
    if subject.mfa_enabled:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="MFA is already enabled; verification is required.")
    secret = subject.ensure_mfa_secret()
    db.commit()
    push_status = mfa_push_status_for_subject(subject)
    return {
        "subject_type": principal.subject_type,
        "subject_id": principal.subject_id,
        "email": subject.email,
        "mfa_enabled": bool(subject.mfa_enabled),
        "preferred_method": subject.mfa_preferred_method or "totp",
        "setup_key": secret,
        "provisioning_uri": totp_provisioning_uri(email=subject.email, secret=secret),
        "mobile_setup_token": create_mfa_setup_token(principal),
        "push_available": bool(push_status["available"]),
        "push_provider": str(push_status["provider"]),
        "push_configured": bool(push_status["configured"]),
        "shared_access_totp_only": bool(push_status["shared_access_totp_only"]),
        "email_available": email_delivery_configured(),
        "recovery_codes": None,
    }


def create_mfa_setup_token(principal: Principal) -> str:
    return create_purpose_token(
        purpose="mfa_setup",
        subject=f"{principal.subject_type}:{principal.subject_id}",
        minutes=15,
        extra={
            "subject_type": principal.subject_type,
            "subject_id": principal.subject_id,
            "secret_fingerprint": _mfa_secret_fingerprint(principal.subject.mfa_secret),
        },
    )


def resolve_mfa_setup_token(db: Session, token: str) -> User | HouseholdMember | None:
    try:
        payload = decode_purpose_token(token, purpose="mfa_setup")
    except Exception:
        return None
    subject_type = payload.get("subject_type")
    try:
        subject_id = int(payload.get("subject_id") or 0)
    except (TypeError, ValueError):
        return None
    if subject_type == "household_member":
        subject = db.get(HouseholdMember, subject_id)
    elif subject_type == "user":
        subject = db.get(User, subject_id)
    else:
        return None
    if not subject or subject.mfa_enabled:
        return None
    if payload.get("secret_fingerprint") != _mfa_secret_fingerprint(subject.mfa_secret):
        return None
    return subject


def confirm_totp_setup(
    principal: Principal,
    db: Session,
    *,
    code: str | None,
    push_opt_in: bool,
    source_addr: str | None,
) -> tuple[list[str], bool]:
    subject = principal.subject
    _ensure_mfa_attempt_allowed(db, subject, source_addr)
    secret = subject.ensure_mfa_secret()
    if not verify_totp_code(secret, code):
        _record_invalid_mfa_attempt(db, subject, source_addr)
        raise HTTPException(status_code=422, detail="Invalid authentication code.")
    recovery_codes = subject.generate_mfa_recovery_codes()
    subject.mfa_enabled = True
    subject.mfa_confirmed_at = utc_now()
    subject.mfa_push_enabled = bool(push_opt_in and mfa_subject_allows_push(subject) and push_mfa_available())
    subject.mfa_preferred_method = "push" if subject.mfa_push_enabled else "totp"
    db.commit()
    _clear_mfa_attempts(db, subject, source_addr)
    return recovery_codes, True


def confirm_email_setup(
    principal: Principal,
    db: Session,
    *,
    code: str | None,
    challenge_token: str | None,
    source_addr: str | None,
) -> list[str]:
    subject = principal.subject
    _ensure_mfa_attempt_allowed(db, subject, source_addr)
    if not verify_mfa_email_code(
        subject,
        purpose="setup",
        code=code,
        challenge_token=challenge_token,
    ):
        _record_invalid_mfa_attempt(db, subject, source_addr)
        raise HTTPException(status_code=422, detail="Invalid or expired email code.")
    recovery_codes = subject.generate_mfa_recovery_codes()
    subject.mfa_enabled = True
    subject.mfa_confirmed_at = utc_now()
    subject.mfa_push_enabled = False
    subject.mfa_preferred_method = "email"
    db.commit()
    _clear_mfa_attempts(db, subject, source_addr)
    return recovery_codes


def skip_mfa_setup(principal: Principal, db: Session) -> None:
    subject = principal.subject
    subject.mfa_push_enabled = False
    subject.mfa_preferred_method = "none"
    db.commit()


def verify_mfa(principal: Principal, db: Session, *, code: str | None, source_addr: str | None) -> None:
    subject = principal.subject
    if not subject.mfa_enabled:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="MFA setup is required.")
    _ensure_mfa_attempt_allowed(db, subject, source_addr)
    if not verify_totp_code(subject.mfa_secret, code):
        _record_invalid_mfa_attempt(db, subject, source_addr)
        raise HTTPException(status_code=422, detail="Invalid authentication code.")
    _clear_mfa_attempts(db, subject, source_addr)


def verify_email_mfa(
    principal: Principal,
    db: Session,
    *,
    code: str | None,
    challenge_token: str | None,
    source_addr: str | None,
) -> None:
    subject = principal.subject
    if not subject.mfa_enabled:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="MFA setup is required.")
    _ensure_mfa_attempt_allowed(db, subject, source_addr)
    if not verify_mfa_email_code(
        subject,
        purpose="verify",
        code=code,
        challenge_token=challenge_token,
    ):
        _record_invalid_mfa_attempt(db, subject, source_addr)
        raise HTTPException(status_code=422, detail="Invalid or expired email code.")
    _clear_mfa_attempts(db, subject, source_addr)


def verify_recovery_code(principal: Principal, db: Session, *, code: str | None, source_addr: str | None) -> None:
    subject = principal.subject
    if not subject.mfa_enabled:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="MFA setup is required.")
    _ensure_mfa_attempt_allowed(db, subject, source_addr)
    if not subject.verify_mfa_recovery_code(code):
        _record_invalid_mfa_attempt(db, subject, source_addr)
        raise HTTPException(status_code=422, detail="Invalid recovery code.")
    db.commit()
    _clear_mfa_attempts(db, subject, source_addr)


def password_reset_token_for(user: User) -> str:
    settings = get_settings()
    return create_purpose_token(
        purpose="password_reset",
        subject=str(user.id),
        minutes=settings.password_reset_token_max_age_seconds / 60,
        extra={"password_hash": user.password_hash},
    )


def user_from_password_reset_token(db: Session, token: str) -> User | None:
    try:
        payload = decode_purpose_token(token, purpose="password_reset")
    except Exception:
        return None
    user = db.get(User, int(payload["sub"]))
    if not user or not hmac.compare_digest(user.password_hash or "", str(payload.get("password_hash") or "")):
        return None
    return user


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
    member.last_login_at = utc_now()
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


def create_household_invite(db: Session, owner: User, email: str, role: str) -> tuple[HouseholdInvite, str]:
    # Flask household_access.create_household_invite at 92ccdbc: validation +
    # revoking prior pending invites for the same email, then a fresh token.
    cleaned_email = (email or "").strip().lower()
    if not cleaned_email:
        raise ValueError("Email is required.")
    if cleaned_email == (owner.email or "").strip().lower():
        raise ValueError("You already have access with that email.")
    if db.scalar(select(User).where(User.email == cleaned_email)):
        raise ValueError("That email already has its own ClearPath account.")
    existing_member = db.scalar(select(HouseholdMember).where(HouseholdMember.email == cleaned_email))
    if existing_member and existing_member.status == "active":
        raise ValueError("That email already has shared access.")

    db.query(HouseholdInvite).filter_by(
        owner_user_id=owner.id,
        email=cleaned_email,
        status="pending",
    ).update({"status": "revoked", "revoked_at": utc_now()})
    return create_invite(owner, cleaned_email, role, db=db)


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

