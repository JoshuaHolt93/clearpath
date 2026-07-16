from __future__ import annotations

from typing import Any

from app.core.config import Settings, get_settings
from app.core.security import create_purpose_token, decode_purpose_token
from app.models import HouseholdMember, User

try:  # pragma: no cover - provider SDK behavior is exercised through mocks
    import duo_universal
except ImportError:  # pragma: no cover
    duo_universal = None


class PushMFAError(RuntimeError):
    pass


def push_mfa_configured(settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    if settings.mfa_push_provider.lower() != "duo":
        return False
    return all((settings.duo_client_id, settings.duo_client_secret, settings.duo_api_hostname))


def push_mfa_available(settings: Settings | None = None) -> bool:
    return bool(push_mfa_configured(settings) and duo_universal is not None)


def push_mfa_status(settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    provider = settings.mfa_push_provider.lower()
    configured_values = {
        "DUO_CLIENT_ID": settings.duo_client_id,
        "DUO_CLIENT_SECRET": settings.duo_client_secret,
        "DUO_API_HOSTNAME": settings.duo_api_hostname,
    }
    missing = [name for name, value in configured_values.items() if provider == "duo" and not value]
    return {
        "provider": provider,
        "configured": push_mfa_configured(settings),
        "available": push_mfa_available(settings),
        "missing": missing,
        "dependency_installed": duo_universal is not None,
    }


def _subject_key(subject: User | HouseholdMember) -> str:
    subject_type = "household_member" if isinstance(subject, HouseholdMember) else "user"
    return f"{subject_type}:{int(subject.id)}"


def _duo_client(redirect_uri: str, settings: Settings | None = None):
    settings = settings or get_settings()
    if not push_mfa_configured(settings):
        raise PushMFAError("Push MFA is not configured.")
    if duo_universal is None:
        raise PushMFAError("Push MFA dependency is not installed.")
    return duo_universal.Client(
        settings.duo_client_id,
        settings.duo_client_secret,
        settings.duo_api_hostname,
        redirect_uri,
    )


def start_push_mfa(subject: User | HouseholdMember, *, redirect_uri: str) -> str:
    if isinstance(subject, HouseholdMember):
        raise PushMFAError("Shared household access uses authenticator codes.")
    client = _duo_client(redirect_uri)
    try:
        client.health_check()
        provider_state = client.generate_state()
        state = create_purpose_token(
            purpose="mfa_push_state",
            subject=_subject_key(subject),
            minutes=get_settings().pending_session_minutes,
            extra={"provider_state": provider_state},
        )
        return client.create_auth_url(subject.email, state)
    except PushMFAError:
        raise
    except Exception as exc:  # pragma: no cover - provider SDK errors vary by version
        raise PushMFAError("Push MFA could not be started.") from exc


def complete_push_mfa(
    subject: User | HouseholdMember,
    *,
    state: str | None,
    code: str | None,
    redirect_uri: str,
) -> None:
    if isinstance(subject, HouseholdMember):
        raise PushMFAError("Shared household access uses authenticator codes.")
    if not state or not code:
        raise PushMFAError("Push MFA callback was incomplete.")
    try:
        payload = decode_purpose_token(state, purpose="mfa_push_state")
    except Exception as exc:
        raise PushMFAError("Push MFA state did not match.") from exc
    if payload.get("sub") != _subject_key(subject) or not payload.get("provider_state"):
        raise PushMFAError("Push MFA state did not match.")

    client = _duo_client(redirect_uri)
    try:
        client.exchange_authorization_code_for_2fa_result(code, subject.email)
    except Exception as exc:  # pragma: no cover - provider SDK errors vary by version
        raise PushMFAError("Push MFA was not approved.") from exc
