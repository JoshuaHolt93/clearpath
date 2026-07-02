from __future__ import annotations

from werkzeug.security import check_password_hash, generate_password_hash

from app.core.config import get_settings


def hash_password(password: str) -> str:
    """Hash a password using the configured method.

    Production uses a strong, memory-hard default (scrypt). Tests and local dev
    can set PASSWORD_HASH_METHOD to a cheap method (e.g. pbkdf2:sha256:1000) so
    suites that create many accounts / recovery codes are not dominated by KDF
    cost. The method is stored inside the hash string, so verification stays
    method-agnostic and hashes migrated from the Flask app still verify.
    """
    return generate_password_hash(password, method=get_settings().password_hash_method)


def verify_password(password_hash: str | None, password: str) -> bool:
    if not password_hash:
        return False
    return check_password_hash(password_hash, password)
