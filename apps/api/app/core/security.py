from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import string
import struct
import time
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from urllib.parse import quote

import jwt

from app.core.config import get_settings

COMMON_PASSWORDS = {
    "password",
    "password1",
    "password123",
    "qwerty",
    "letmein",
    "welcome",
    "admin",
    "iloveyou",
    "clearpath",
}
TOTP_INTERVAL_SECONDS = 30
TOTP_DIGITS = 6
ALGORITHM = "HS256"
SessionSubjectType = Literal["user", "household_member"]


def password_policy_errors(password: str | None, email: str | None = None) -> list[str]:
    password = password or ""
    email = (email or "").strip().lower()
    local_part = email.split("@", 1)[0] if "@" in email else email
    lowered_password = password.lower()
    errors: list[str] = []

    if len(password) < 12:
        errors.append("Password must be at least 12 characters long.")
    if not any(character.isupper() for character in password):
        errors.append("Password must include at least one uppercase letter.")
    if not any(character.islower() for character in password):
        errors.append("Password must include at least one lowercase letter.")
    if not any(character.isdigit() for character in password):
        errors.append("Password must include at least one number.")
    if not any(character in string.punctuation or not character.isalnum() for character in password):
        errors.append("Password must include at least one symbol.")
    if lowered_password in COMMON_PASSWORDS:
        errors.append("Choose a less common password.")
    if email and email in lowered_password:
        errors.append("Password cannot include your email address.")
    if local_part and local_part in lowered_password:
        errors.append("Password cannot include the part of your email before @.")
    return errors


def generate_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _decode_totp_secret(secret: str) -> bytes:
    normalized = "".join(str(secret or "").split()).upper()
    padding = "=" * ((8 - len(normalized) % 8) % 8)
    return base64.b32decode(normalized + padding, casefold=True)


def totp_code(secret: str, *, for_time: int | None = None) -> str:
    counter = int((for_time if for_time is not None else time.time()) // TOTP_INTERVAL_SECONDS)
    digest = hmac.new(_decode_totp_secret(secret), struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(value % (10**TOTP_DIGITS)).zfill(TOTP_DIGITS)


def verify_totp_code(secret: str | None, code: str | None, *, window: int = 1) -> bool:
    supplied = "".join(str(code or "").split())
    if not secret or not supplied.isdigit() or len(supplied) != TOTP_DIGITS:
        return False
    now = int(time.time())
    for step in range(-window, window + 1):
        expected = totp_code(secret, for_time=now + (step * TOTP_INTERVAL_SECONDS))
        if hmac.compare_digest(expected, supplied):
            return True
    return False


def totp_provisioning_uri(*, email: str, secret: str, issuer: str = "ClearPath Finance") -> str:
    label = f"{issuer}:{email}"
    return f"otpauth://totp/{quote(label)}?secret={quote(secret)}&issuer={quote(issuer)}"


def generate_recovery_codes(count: int = 10) -> list[str]:
    codes = []
    for _ in range(count):
        token = secrets.token_hex(6).upper()
        codes.append(f"{token[:4]}-{token[4:8]}-{token[8:12]}")
    return codes


def normalize_recovery_code(code: str | None) -> str:
    return "".join(character for character in str(code or "").upper() if character.isalnum())


def _utc_timestamp(minutes: int) -> datetime:
    return datetime.now(UTC) + timedelta(minutes=minutes)


def create_session_token(
    *,
    user_id: int,
    subject_type: SessionSubjectType,
    subject_id: int,
    mfa_verified: bool,
    household_member_id: int | None = None,
    household_role: str | None = None,
) -> str:
    settings = get_settings()
    minutes = settings.session_minutes if mfa_verified else settings.pending_session_minutes
    payload: dict[str, Any] = {
        "iss": "clearpath-api",
        "type": "session",
        "sub": str(user_id),
        "user_id": int(user_id),
        "subject_type": subject_type,
        "subject_id": int(subject_id),
        "household_member_id": household_member_id,
        "household_role": household_role,
        "mfa_verified": bool(mfa_verified),
        "exp": _utc_timestamp(minutes),
        "iat": datetime.now(UTC),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, get_settings().secret_key, algorithms=[ALGORITHM], issuer="clearpath-api")


def create_purpose_token(*, purpose: str, subject: str, minutes: int = 15, extra: dict[str, Any] | None = None) -> str:
    payload: dict[str, Any] = {
        "iss": "clearpath-api",
        "type": purpose,
        "sub": subject,
        "exp": _utc_timestamp(minutes),
        "iat": datetime.now(UTC),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, get_settings().secret_key, algorithm=ALGORITHM)


def decode_purpose_token(token: str, *, purpose: str) -> dict[str, Any]:
    payload = decode_token(token)
    if payload.get("type") != purpose:
        raise jwt.InvalidTokenError("Unexpected token purpose.")
    return payload
